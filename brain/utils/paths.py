# utils/paths.py
# Repo/dist path helpers (env-override aware, portable)

from __future__ import annotations
from pathlib import Path
import os

def compute_repo_root(this_file: str) -> Path:
    """Resolve repo root from the caller's file unless ORRIN_REPO_ROOT overrides."""
    env = os.environ.get("ORRIN_REPO_ROOT")
    return Path(env).resolve() if env else Path(this_file).resolve().parent

def resolve_dist(env_var: str, default_path: Path) -> Path:
    """Resolve a UI dist directory with env override and absolute pathing."""
    return Path(os.environ.get(env_var, default_path)).resolve()

def require_dist(dist_dir: Path, ui_name: str, repo_root: Path) -> None:
    """
    Hard-require a Vite dist with helpful relative build instructions.
    Prefer using utils.ui_build.ensure_ui_build() to auto-build instead.
    """
    idx = dist_dir / "index.html"
    print(f"[{ui_name}] using dist_dir: {dist_dir}")
    print(f"[{ui_name}] dist_dir exists: {dist_dir.exists()}  index.html exists: {idx.exists()}")
    if not dist_dir.exists() or not idx.exists():
        try:
            ui_rel = dist_dir.relative_to(repo_root)
            build_cd = repo_root / ui_rel.parent
        except ValueError:
            build_cd = dist_dir.parent
        raise SystemExit(
            f"[{ui_name}] UI build not found.\nBuild it, then run again:\n"
            f"  cd {build_cd}\n  npm install\n  npm run build\n"
        )
