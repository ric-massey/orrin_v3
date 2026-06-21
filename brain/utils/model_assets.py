"""
utils/model_assets.py — point the ML stack at PRE-BUNDLED weights so a frozen Orrin
boots with zero network (Part 4 / I2).

The single most likely thing to break on a clean machine is that
`sentence-transformers` and spaCy's `en_core_web_sm` try to **download their weights at
runtime** into a cache dir. A frozen app that relies on that hangs or fails on first
launch for anyone offline or behind a proxy. So the build ships the weights under
`Resources/models/` and this module points the libraries at them:

  • `SENTENCE_TRANSFORMERS_HOME` / `HF_HOME` → the bundled cache, plus the offline flags
    (`HF_HUB_OFFLINE` / `TRANSFORMERS_OFFLINE`) so the libs never reach for the network.
  • spaCy is loaded from an explicit bundled model path (it can't be steered by env).

In a dev checkout (no bundle, no `ORRIN_MODELS_DIR`) this is a no-op: the normal
pip-installed model and HF cache/download behavior is unchanged.

Acceptance (§Part 4): install on a machine that never had Python, Wi-Fi OFF → Orrin
boots, thinks, and renders. `apply_offline_env()` is what makes that true; call it at
the very top of boot, before any ML import.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from brain.utils.runtime_python import _bundle_root  # reuse the frozen-bundle locator


def models_dir() -> Optional[Path]:
    """The bundled weights directory, or None in a normal dev checkout.
    `ORRIN_MODELS_DIR` overrides (the I3 build sets it; tests use it)."""
    override = os.environ.get("ORRIN_MODELS_DIR")
    if override:
        p = Path(override).expanduser()
        return p if p.exists() else None
    root = _bundle_root()
    if root is not None:
        for sub in ("models", "Resources/models", "../Resources/models", "_internal/models"):
            p = (root / sub).resolve()
            if p.exists():
                return p
    return None


def apply_offline_env() -> bool:
    """If bundled weights exist, point the HF / sentence-transformers caches at them and
    flip on offline mode so nothing reaches the network. Returns True if applied.
    setdefault throughout: an explicit dev env always wins."""
    mdir = models_dir()
    if mdir is None:
        return False
    hf = mdir / "hf"
    st = mdir / "sentence_transformers"
    os.environ.setdefault("HF_HOME", str(hf if hf.exists() else mdir))
    os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(st if st.exists() else mdir))
    # Hard-offline: a bundled app must never block on a download at boot.
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    return True


def spacy_model(name: str = "en_core_web_sm"):
    """The argument to hand `spacy.load(...)`: a bundled model PATH when frozen, else the
    package `name` (dev uses the pip-installed model)."""
    mdir = models_dir()
    if mdir is not None:
        for cand in (mdir / "spacy" / name, mdir / name):
            if cand.exists():
                return str(cand)
    return name
