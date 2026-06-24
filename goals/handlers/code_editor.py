# goals/handlers/code_edit.py
# Safely edit code using git, applying patches or simple transforms, running tests, and committing if successful.
from __future__ import annotations
from brain.core.runtime_log import get_logger
from pathlib import Path
from typing import Any
import subprocess, tempfile, time
_log = get_logger(__name__)

def _run(cmd: list[str], cwd: Path, timeout: int = 60) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except (OSError, subprocess.SubprocessError) as e:  # intentional: subprocess launch/timeout → error tuple
        return -1, "", str(e)

def _git_available(cwd: Path) -> bool:
    rc, _, _ = _run(["git", "--version"], cwd)
    return rc == 0

def _ensure_clean(cwd: Path) -> bool:
    rc, out, _ = _run(["git", "status", "--porcelain"], cwd)
    return rc == 0 and out.strip() == ""

def _create_branch(cwd: Path, name: str) -> bool:
    rc, _, _ = _run(["git", "checkout", "-b", name], cwd)
    return rc == 0

def _git_apply_patch(cwd: Path, patch_text: str) -> tuple[bool, str]:
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".patch") as tf:
        tf.write(patch_text)
        tmp = tf.name
    try:
        rc, _, err = _run(["git", "apply", "--check", tmp], cwd)
        if rc != 0:
            return False, f"git apply --check failed: {err}"
        rc, _, err = _run(["git", "apply", tmp], cwd)
        if rc != 0:
            return False, f"git apply failed: {err}"
        return True, "applied"
    finally:
        try: Path(tmp).unlink(missing_ok=True)
        except Exception:
            _log.warning("silent except")

def _git_commit(cwd: Path, msg: str) -> bool:
    _run(["git", "add", "-A"], cwd)
    rc, _, _ = _run(["git", "commit", "-m", msg], cwd)
    return rc == 0

def _run_tests(cwd: Path, cmd: list[str] | None = None) -> tuple[bool, str]:
    # prefer pytest; fallback to `python -m unittest`
    if cmd is None:
        cmd = ["pytest", "-q"]
    rc, out, err = _run(cmd, cwd, timeout=300)
    ok = (rc == 0)
    return ok, (out + "\n" + err)

ALLOWED_GLOBS = ( "**/*.py", "**/*.md", "UI/**/*.tsx", "UI/**/*.ts", "UI/**/*.js" )

def execute(goal: Any, ctx: Any) -> bool:
    """
    Edits code safely using a spec. Supports two modes:
      1) spec.patch (string): unified diff; applied via `git apply` on a new branch
      2) spec.transforms (list): simple search/replace micro-edits with allowlist globs

    If tests pass, commit the change. Otherwise revert.
    """
    repo_root = Path(ctx.get("repo_root", ".")).resolve()
    spec = (getattr(goal, "spec", None) or {}).copy()
    title = getattr(goal, "title", "code edit")
    ts = int(time.time())

    # Require git so we can branch + revert cleanly
    if not _git_available(repo_root):
        ctx_note = "[code-edit] git not found; cannot safely modify code"
        setattr(goal, "notes", (getattr(goal, "notes", "") or "") + "\n" + ctx_note)
        return False

    if not _ensure_clean(repo_root):
        ctx_note = "[code-edit] working tree not clean; commit/stash first"
        setattr(goal, "notes", (getattr(goal, "notes", "") or "") + "\n" + ctx_note)
        return False

    branch = spec.get("branch") or f"auto/{goal.id if hasattr(goal,'id') else 'goal'}-{ts}"
    if not _create_branch(repo_root, branch):
        setattr(goal, "notes", (getattr(goal, "notes", "") or "") + f"\n[code-edit] failed to create branch {branch}")
        return False

    changed = False
    try:
        if "patch" in spec:
            ok, msg = _git_apply_patch(repo_root, spec["patch"])
            if not ok:
                setattr(goal, "notes", (getattr(goal, "notes", "") or "") + f"\n[code-edit] {msg}")
                return False
            changed = True

        # Simple transforms (search/replace) on allowlisted paths
        for tr in spec.get("transforms", []):
            pat = tr.get("glob")
            if not pat: continue
            # enforce allowlist
            if not any(Path(pat).match(g) or pat.startswith(g.split("*")[0]) for g in ALLOWED_GLOBS):
                setattr(goal, "notes", (getattr(goal, "notes", "") or "") + f"\n[code-edit] blocked glob: {pat}")
                return False
            find = tr.get("find"); repl = tr.get("replace")
            if find is None or repl is None: continue
            for p in repo_root.glob(pat):
                if p.is_file() and p.stat().st_size < 2_000_000:  # 2MB guard
                    txt = p.read_text(encoding="utf-8", errors="ignore")
                    new = txt.replace(find, repl)
                    if new != txt:
                        p.write_text(new, encoding="utf-8")
                        changed = True

        if not changed:
            setattr(goal, "notes", (getattr(goal, "notes", "") or "") + "\n[code-edit] no changes produced")
            return True  # nothing to do = success

        # Run tests (or a custom command from spec)
        ok, out = _run_tests(repo_root, spec.get("test_cmd"))
        reports = repo_root / "data" / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        (reports / f"tests-{branch.replace('/','_')}.log").write_text(out, encoding="utf-8")

        if not ok:
            setattr(goal, "notes", (getattr(goal, "notes", "") or "") + "\n[code-edit] tests failed; reverting")
            # revert branch changes
            _run(["git", "restore", "--staged", "."], repo_root)
            _run(["git", "checkout", "."], repo_root)
            _run(["git", "checkout", "-"], repo_root)  # back to previous
            _run(["git", "branch", "-D", branch], repo_root)
            return False

        # Commit and keep branch
        if not _git_commit(repo_root, f"{title} [auto]"):
            setattr(goal, "notes", (getattr(goal, "notes", "") or "") + "\n[code-edit] commit failed")
            return False

        setattr(goal, "notes", (getattr(goal, "notes", "") or "") + f"\n[code-edit] committed on {branch}")
        return True

    finally:
        # Nothing else to do; we keep the branch for review if success.
        pass
