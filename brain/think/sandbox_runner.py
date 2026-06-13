# think/sandbox_runner.py
from __future__ import annotations
from core.runtime_log import get_logger
import subprocess, sys, tempfile, os, shutil
from typing import Dict, Any
from utils.failure_counter import record_failure
_log = get_logger(__name__)

def run_python(code: str, timeout: float = 5.0, cwd: str | None = None) -> Dict[str, Any]:
    """
    Execute untrusted Python in a *separate* process with -I (isolated) & -S (no site),
    returning {"ok": bool, "stdout": str, "stderr": str, "returncode": int}.
    """
    if not isinstance(code, str):
        return {"ok": False, "stdout": "", "stderr": "code must be str", "returncode": -1}

    py = sys.executable
    env = {"PYTHONIOENCODING": "utf-8"}  # no secrets

    _tmp_dir = None
    if cwd:
        work = cwd
    else:
        _tmp_dir = tempfile.mkdtemp(prefix="orrin_sbx_")
        work = _tmp_dir

    # Write code to a temp file to avoid shell quoting issues
    with tempfile.NamedTemporaryFile("w", suffix=".py", dir=work, delete=False) as f:
        f.write(code)
        path = f.name

    try:
        proc = subprocess.run(
            [py, "-I", "-S", path],
            cwd=work,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "ok": proc.returncode == 0,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "returncode": proc.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": "timeout", "returncode": -9}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": str(e), "returncode": -2}
    finally:
        try:
            os.unlink(path)
        except Exception as _e:
            record_failure("sandbox_runner.run_python", _e)
        if _tmp_dir:
            try:
                shutil.rmtree(_tmp_dir, ignore_errors=True)
            except Exception as _e:
                record_failure("sandbox_runner.run_python.2", _e)
