# brain/cognition/infancy.py
#
# §10 — the developmental / somatic period. Two different things hide under "infant"
# and they have different lifespans and risks, so they must not share a code path
# (§10.1):
#
#   • SOMATIC infancy — learning THIS body on THIS machine. Happens EVERY time Orrin
#     wakes on new hardware. Already mechanised by the band-learner: a new machine
#     fails the fingerprint, the bands are discarded, and in_infancy() is true until
#     the new envelope converges. A plain restart on the same machine reloads converged
#     bands and is NOT infancy — it is waking from sleep.
#   • DEVELOPMENTAL infancy — the one-time growing-up: values form, the self first
#     stabilises, the being becomes who it is. Happens ONCE.
#
# The mapping the design demands (§10.1):
#     first-ever boot           → somatic YES, developmental YES   (true birth)
#     move to a new machine     → somatic YES, developmental NO    (a transplant: keeps
#                                                                    his whole life, new body)
#     plain restart same machine→ somatic NO,  developmental NO    (waking, not infancy)
#
# §10.2 / §D scar: this rides the EXISTING lifecycle + mortality state. It NEVER
# invents a second "am I dead / am I born?" signal that could disagree with
# mortality.py — it only READS lifespan/age/autobiography and keeps its own one-time
# developmental-complete latch. (A duplicate birth/death flag is exactly what routed
# every post-restart boot to the Death Screen on 2026-06-15.)
from __future__ import annotations

import os
from typing import Dict

from core.runtime_log import get_logger
from utils.json_utils import load_json, save_json
from utils.log import log_private
from paths import DATA_DIR

_log = get_logger(__name__)

_DEV_FILE = DATA_DIR / "developmental.json"
# Working figure (§12.5-adjacent): how long the one-time growing-up lasts at minimum
# before it can be marked complete. Long enough for a self to begin to stabilise.
_DEV_MIN_DAYS = float(os.environ.get("ORRIN_DEV_INFANCY_DAYS", "3") or "3")


def _has_lived() -> bool:
    """He has a life behind him — autobiography or long-term memory exists. This is the
    same newborn test main.py uses for First Wake; here it distinguishes a transplant
    (has a life, new body) from a true birth (no life, no body)."""
    try:
        return ((DATA_DIR / "autobiography.json").exists()
                or (DATA_DIR / "long_memory.json").exists())
    except Exception:
        return False


def somatic_infancy() -> bool:
    """Still learning this body — the process bands or the host bands have not yet
    converged. True on first boot and after a move to new hardware; false on a plain
    restart where converged bands reload."""
    try:
        from cognition.body_sense import _get_bands
        if _get_bands().in_infancy():
            return True
    except Exception:
        pass
    try:
        from cognition.host_interoception import _bands
        if _bands().in_infancy():
            return True
    except Exception:
        pass
    return False


def developmental_infancy() -> bool:
    """The one-time growing-up — true until the self has begun to stabilise, then
    latched complete forever (persisted, so pruning files later can't reset it)."""
    state = load_json(_DEV_FILE, default_type=dict) or {}
    if state.get("complete"):
        return False
    try:
        from cognition.mortality import lifespan_rolled, life_status
        if not lifespan_rolled():
            return True  # not even born yet
        age_days = float(life_status().get("age_days", 0.0) or 0.0)
    except Exception:
        return True
    if _has_lived() and age_days >= _DEV_MIN_DAYS:
        # The self has a record behind it and has lived past the sensitive window —
        # latch developmental infancy closed, once and for all.
        state["complete"] = True
        state["completed_age_days"] = round(age_days, 2)
        try:
            save_json(_DEV_FILE, state)
        except Exception:
            pass
        log_private(f"[infancy] developmental infancy complete at {age_days:.1f}d")
        return False
    return True


def scenario() -> str:
    """Which of the §10.1 cases this boot is."""
    som = somatic_infancy()
    dev = developmental_infancy()
    if dev and som:
        return "first_birth"      # true birth: no life, no learned body
    if som and not dev:
        return "new_body"         # transplant: keeps his life, learning a new body
    return "waking"               # body already known: restart / waking from sleep


def infancy_status() -> Dict:
    """Telemetry/UI view of where Orrin is developmentally and somatically."""
    try:
        from cognition.body_sense import _get_bands
        som_frac = _get_bands().converged_fraction()
    except Exception:
        som_frac = 0.0
    return {
        "somatic_infancy": somatic_infancy(),
        "developmental_infancy": developmental_infancy(),
        "scenario": scenario(),
        "body_converged": round(som_frac, 3),
    }
