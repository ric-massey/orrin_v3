# brain/cognition/contradiction_surfacing.py
# Stochastic contradiction surfacing: sometimes — probabilistically, never on a
# schedule — find a held rule that CONFLICTS with the current conscious position
# and offer it into the workspace competition, so coherence has an antagonist.
# The offer competes on salience like any other candidate (same discipline as
# binding.py / metacog_monitor); it is never injected and never preempts.
#
# Adapted from the Athena-Class Cognitive Architecture (Vesper & Hypatia,
# Project Anamnesis, v1.0, 2026-06-07): explicitly stochastic because "the
# agent cannot build a routine for dismissing what doesn't arrive on a
# schedule." Predicate reused from meta_rules._are_contradictory (the reactive
# detector that already existed); this module adds the proactive path.
#
# Ablation flag: `contradiction_surfacing` (run_config). Telemetry:
# data/contradiction_surfacing.json, a bounded log of every surfaced conflict.
from __future__ import annotations

import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from brain.paths import DATA_DIR
from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_activity
from brain.utils.failure_counter import record_failure

_SURFACE_PROBABILITY = 0.03    # per ignitable cycle; low by design — rarity is the mechanism
_MIN_RULE_CONFIDENCE = 0.35    # don't weaponize rules already on their way out
_OFFER_SALIENCE      = 0.55    # must compete, not dominate (metacog offers run 0.5–0.9)
_SURFACING_LOG       = DATA_DIR / "contradiction_surfacing.json"
_LOG_CAP             = 200


def _current_position(context: Dict[str, Any]) -> str:
    """The text Orrin is currently coherent AROUND: the conscious broadcast."""
    ws = context.get("global_workspace")
    if isinstance(ws, dict):
        content = str(ws.get("content") or "").strip()
        if content:
            return content
    return ""


def maybe_surface_contradiction(
    context: Dict[str, Any],
    probability: float = _SURFACE_PROBABILITY,
) -> Optional[str]:
    """Roll the dice; on a hit, offer the strongest rule contradicting the
    current conscious position into the next workspace competition. Returns the
    offered rule id, or None (the overwhelmingly common case). Fail-safe."""
    # P7 ablation entry point: `contradiction_surfacing` off ⇒ never surfaces.
    try:
        from brain.run_config import subsystem_enabled as _sub_on
        if not _sub_on("contradiction_surfacing"):
            return None
    except Exception:  # intentional: ablation-gate fail-safe (stays ON)
        pass

    if not isinstance(context, dict):
        return None
    if random.random() >= probability:
        return None

    position = _current_position(context)
    if not position:
        return None

    try:
        from brain.symbolic.rule_engine import get_all_rules
        from brain.symbolic.meta_rules import _are_contradictory
        from brain.cognition.global_workspace import offer_to_workspace
    except ImportError:  # intentional: rule engine / workspace optional
        return None

    try:
        pseudo = {"conclusion": position}
        best: Optional[Dict[str, Any]] = None
        for rule in get_all_rules():
            if rule.get("source") == "tombstoned":
                continue
            if float(rule.get("confidence", 0.0)) < _MIN_RULE_CONFIDENCE:
                continue
            if not _are_contradictory(pseudo, rule):
                continue
            if best is None or float(rule.get("confidence", 0)) > float(best.get("confidence", 0)):
                best = rule
        if best is None:
            return None

        rid = str(best.get("id") or "")
        offer_to_workspace(context, {
            "content": f"A held rule disagrees with this: {best.get('conclusion', '')}",
            "salience": _OFFER_SALIENCE,
            "source": "contradiction_surfacing",
            "wants": "reconcile-contradiction",
            "kind": "tension",
        })
        log_activity(
            f"[contradiction_surfacing] Offered conflicting rule '{rid}' "
            f"against current position: {position[:80]}"
        )
        _record(rid, position)
        return rid
    except Exception as e:
        record_failure("contradiction_surfacing.maybe_surface", e)
        return None


def _record(rule_id: str, position: str) -> None:
    try:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ts": time.time(),
            "rule_id": rule_id,
            "position": position[:160],
        }
        series = load_json(_SURFACING_LOG, default_type=list) or []
        series.append(entry)
        save_json(_SURFACING_LOG, series[-_LOG_CAP:])
    except Exception as e:
        record_failure("contradiction_surfacing.record", e)
