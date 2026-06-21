"""Newborn / forget-on-start helpers (Phase 4B, extracted from main.py).

`forget_everything()` wipes the durable state subtrees for a stateless boot
(ORRIN_FORGET_ON_START); `seed_if_newborn()` copies the bundled config seeds into
a fresh/relocated data dir so a newborn boots coherently. Both honor the brain's
own path resolvers and only fall back to repo-relative paths if those can't load.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from brain.core.runtime_log import get_logger

_log = get_logger(__name__)

# runtime/newborn.py → repo root two levels up; brain/ holds the shipped seed data.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_BRAIN_DIR = _REPO_ROOT / "brain"

# Bundled config seeds — the minimum a newborn needs to boot coherently. Shipped in
# the program folder's brain/data; copied into a fresh (relocated) data dir on first
# launch so the brain doesn't error on missing model_config / vocabulary / etc.
SEED_FILES = (
    "affect_model.json", "behavioral_functions_list.json",
    "capability_descriptions.json", "cognitive_functions.json",
    "meta_rules.json", "model_config.json", "vocab_weights.json", "vocabulary.json",
)


def forget_everything() -> None:
    """
    DANGER: Deletes Orrin's daemon-durability state (the resolved state tree) so he
    boots fresh. Controlled by ORRIN_FORGET_ON_START=1|true|yes. Targets only the
    known state subtrees, which relocate with ORRIN_STATE_DIR.
    """
    try:
        from brain.paths import STATE_DIR, MEMORY_DIR, GOALS_DIR
    except Exception:
        STATE_DIR = _REPO_ROOT / "data"
        MEMORY_DIR, GOALS_DIR = STATE_DIR / "memory", STATE_DIR / "goals"
    for p in (MEMORY_DIR, GOALS_DIR, STATE_DIR / "logs", _REPO_ROOT / "tmp"):
        try:
            if p.exists():
                print(f"[forget] removing {p}")
                shutil.rmtree(p, ignore_errors=True)
        except Exception as e:
            print(f"[forget] could not remove {p}: {e}")
    for p in (STATE_DIR, STATE_DIR / "logs", _REPO_ROOT / "tmp"):
        try:
            p.mkdir(parents=True, exist_ok=True)
        except Exception as _e:
            _log.warning("silent except: %s", _e)


def seed_if_newborn() -> None:
    """If the resolved data dir is a fresh/empty install (no model_config.json yet),
    seed the bundled config files so a newborn boots. No-op when running in-repo on
    the seed dir itself, or when state already exists (relaunch reuses it)."""
    try:
        from brain.paths import DATA_DIR
    except Exception:
        return
    seed_src = _BRAIN_DIR / "data"
    if DATA_DIR.resolve() == seed_src.resolve():
        return  # in-repo: the data dir IS the seed source
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if (DATA_DIR / "model_config.json").exists():
        return  # already a living mind here — reuse it
    copied = 0
    for name in SEED_FILES:
        src, dst = seed_src / name, DATA_DIR / name
        try:
            if src.exists() and not dst.exists():
                shutil.copy2(src, dst)
                copied += 1
        except Exception as e:
            print(f"[seed] could not seed {name}: {e}")
    print(f"[seed] newborn data dir → seeded {copied} config file(s) into {DATA_DIR}")
