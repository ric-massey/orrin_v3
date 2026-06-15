"""
utils/runtime_python.py — which Python interpreter Orrin shells out to for sandboxed
code (§10.2 / I1).

Orrin runs untrusted, self-written Python in a *separate, timeout-guarded* process
(see behavior/tools/sandbox.py and think/sandbox_runner.py). In a dev checkout
`sys.executable` is a real CPython, so that works. But in a **PyInstaller-frozen app**
`sys.executable` is the frozen host binary (`Orrin.app/Contents/MacOS/Orrin`) — running
`[sys.executable, "-I", script]` would relaunch the whole app, not run the snippet. And
shelling out to whatever `python3` the user happens to have is unreliable and a security
surprise.

So a frozen Orrin ships a **private embedded CPython** under `Resources/python/` and
that becomes the only interpreter the sandbox uses. This module is the one resolver:

  • `ORRIN_EMBEDDED_PYTHON` env override (explicit; wins everywhere — also how tests and
    the I3 build point at the bundled interpreter).
  • frozen → the bundled interpreter beside the app resources.
  • dev checkout → `sys.executable` (a real Python).

The heavy ML stack (torch/spacy/sentence-transformers) lives only in the frozen HOST
process, never in this embedded runtime — a generated snippet that imports it fails
cleanly rather than mysteriously (documented boundary, §10.2).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional


def is_frozen() -> bool:
    """True when running inside a PyInstaller (or similar) frozen bundle."""
    return bool(getattr(sys, "frozen", False)) or hasattr(sys, "_MEIPASS")


def _bundle_root() -> Optional[Path]:
    """The directory that holds bundled resources in a frozen app, or None in dev."""
    mei = getattr(sys, "_MEIPASS", None)
    if mei:
        return Path(mei)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return None


def _candidate_embedded_paths(root: Path):
    """Where the private interpreter lives under the bundle, per OS. We probe a few
    layouts so the I3 spec has latitude in where it drops `Resources/python/`."""
    if os.name == "nt":
        names = ("python.exe",)
        subdirs = ("python", "Resources/python", "_internal/python")
    else:
        names = ("python3", "python")
        subdirs = ("python/bin", "Resources/python/bin", "../Resources/python/bin", "_internal/python/bin")
    for sub in subdirs:
        for name in names:
            p = (root / sub / name).resolve()
            if p.exists():
                return p
    return None


def embedded_python() -> Optional[Path]:
    """The bundled interpreter path if one is configured/present, else None."""
    override = os.environ.get("ORRIN_EMBEDDED_PYTHON")
    if override:
        p = Path(override).expanduser()
        return p if p.exists() else None
    root = _bundle_root()
    if root is not None:
        return _candidate_embedded_paths(root)
    return None


def interpreter() -> str:
    """The interpreter the sandbox should invoke. Prefers the embedded CPython (override
    or bundled); falls back to `sys.executable`, which is correct in a dev checkout and
    is a safe last resort if a frozen build is missing its bundled interpreter (the
    sandbox snippet then simply runs in the host — still timeout-guarded)."""
    emb = embedded_python()
    if emb is not None:
        return str(emb)
    return sys.executable


def using_embedded() -> bool:
    return embedded_python() is not None
