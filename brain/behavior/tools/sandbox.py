# sandbox.py
from __future__ import annotations
from brain.core.runtime_log import get_logger
from pathlib import Path
import sys, time, ast, subprocess, tempfile
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

# --- standardized import for project paths (explicit, robust) ---
DATA_DIR: Path
try:
    # Prefer importing exactly what we need
    from brain.paths import DATA_DIR as _DATA_DIR
    DATA_DIR = _DATA_DIR
except Exception:
    # Search upward for paths.py (up to 8 levels)
    base = Path(__file__).resolve().parent
    for _ in range(8):
        if (base / "paths.py").exists():
            if str(base) not in sys.path:
                sys.path.insert(0, str(base))
            break
        base = base.parent
    try:
        from brain.paths import DATA_DIR as _DATA_DIR
        DATA_DIR = _DATA_DIR
    except Exception:
        # Final fallback (works even if paths.py is missing)
        DATA_DIR = Path(__file__).resolve().parent / "data"

# Optional: if you define SANDBOX_TMP_DIR inside paths.py, you can import it explicitly.
try:
    from brain.paths import SANDBOX_TMP_DIR as _SANDBOX_TMP_DIR  # optional
    SANDBOX_TMP_DIR: Path = _SANDBOX_TMP_DIR
except Exception:
    SANDBOX_TMP_DIR = DATA_DIR / "sandbox_tmp"

SANDBOX_TMP_DIR.mkdir(parents=True, exist_ok=True)

# --- POSIX-only resource limits (safe on Windows: they just won't apply) ---
try:
    import resource  # type: ignore
    def _limit_resources():
        # CPU seconds, address space, file size. Best-effort per limit: some
        # limits are not enforceable on every platform (notably RLIMIT_AS on
        # macOS), and a failure inside preexec_fn raises and ABORTS the subprocess
        # launch entirely. Apply each independently so an unsupported limit just
        # gets skipped while the others (and the -I isolation + wall-clock
        # timeout) still bound the child.
        for _what, _soft, _hard in (
            (resource.RLIMIT_CPU, 2, 2),
            (resource.RLIMIT_AS, 256 * 1024 * 1024, 256 * 1024 * 1024),
            (resource.RLIMIT_FSIZE, 10 * 1024 * 1024, 10 * 1024 * 1024),
        ):
            try:
                resource.setrlimit(_what, (_soft, _hard))
            except (ValueError, OSError):
                pass
    _PREEXEC = _limit_resources  # used only on POSIX
except Exception:
    resource = None
    _PREEXEC = None  # type: ignore

ALLOWED_MODULES = {
    "math","random","statistics","json","re","itertools","functools",
    "datetime","collections"
}

def _safety_ast_check(code: str) -> bool:
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name.split('.')[0] for alias in getattr(node, "names", [])]
            for n in names:
                if n not in ALLOWED_MODULES:
                    raise ValueError(f"Disallowed import: {n}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"exec", "eval", "compile", "open", "__import__"}:
                raise ValueError(f"Disallowed builtin: {node.func.id}")
    return True

def run_python_sandboxed(code: str, *, dry_run: bool = False, timeout_s: int = 5) -> dict:
    _safety_ast_check(code)
    if dry_run:
        return {"status": "ok", "dry_run": True, "message": "AST OK; no execution"}

    # Create a temporary script in the sandbox dir
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".py", prefix="orrin_", dir=SANDBOX_TMP_DIR, delete=False
    ) as tf:
        tf.write(code)
        path = Path(tf.name)

    # Use the embedded CPython when frozen (§10.2 / I1) — sys.executable would be the
    # Orrin host binary in a packaged app, not a Python interpreter.
    from brain.utils.runtime_python import interpreter as _interp
    cmd = [_interp(), "-I", str(path)]  # isolated mode
    start = time.time()
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=_PREEXEC if _PREEXEC else None  # None on Windows
        )
        try:
            out, err = proc.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            proc.kill()
            return {"status": "error", "error": "timeout", "seconds": timeout_s}
        dur = round(time.time() - start, 3)
        return {
            "status": "ok" if proc.returncode == 0 else "error",
            "stdout": out,
            "stderr": err,
            "returncode": proc.returncode,
            "seconds": dur,
        }
    finally:
        try:
            path.unlink(missing_ok=True)
        except Exception as _e:
            record_failure("sandbox.run_python_sandboxed", _e)
