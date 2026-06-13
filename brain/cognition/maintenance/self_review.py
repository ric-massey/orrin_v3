# self_review.py
from __future__ import annotations
from core.runtime_log import get_logger

from typing import List

from utils.events_miner import last_n_events, summarize_outcomes
from utils.log import utc_now as _utc_now
from utils.log_reflection import log_reflection
from utils.json_utils import load_json
from utils.log import log_error
from utils.append import append_to_json
from paths import LONG_MEMORY_FILE
from utils.failure_counter import record_failure
_log = get_logger(__name__)


def periodic_self_review(n_events: int = 400) -> None:
    try:
        evts = last_n_events(n_events)
        if not isinstance(evts, list):
            log_error("periodic_self_review: last_n_events did not return a list; using empty list.")
            evts = []

        agg = summarize_outcomes(evts) or {}
        accepted = agg.get("accepted", 0)
        total = agg.get("total", len(evts))
        top = agg.get("top", [])

        note = (
            f"[Self-Review {_utc_now()}] "
            f"Accepted {accepted}/{total} "
            f"Top picks: {top}"
        )
        log_reflection(note, reflection_type="self_review")

        # ── Reward-pattern analysis ───────────────────────────────────────────
        # Read per-function avg_reward from DECISION_STATS_FILE (written by
        # record_decision() each cycle). Identify consistent underperformers and
        # high-reward functions worth sustaining, then write findings to long_memory
        # as load-bearing observations (importance=4) so inner_loop reasoning
        # encounters them and can deliberate about deprioritising weak functions.
        try:
            from paths import DECISION_STATS_FILE as _DSF
            stats = load_json(_DSF, default_type=dict) or {}
            poor_fns: List[tuple] = []
            strong_fns: List[tuple] = []
            for fn, entry in stats.items():
                if not isinstance(entry, dict):
                    continue
                n = int(entry.get("count", 0) or 0)
                avg = float(entry.get("avg_reward", 0.0) or 0.0)
                if n < 5:
                    continue
                if avg < 0.30:
                    poor_fns.append((fn, avg, n))
                elif avg > 0.65:
                    strong_fns.append((fn, avg, n))

            poor_fns.sort(key=lambda x: x[1])
            strong_fns.sort(key=lambda x: -x[1])

            if poor_fns:
                poor_str = "; ".join(
                    f"'{fn}' (avg={avg:.2f}, n={n})" for fn, avg, n in poor_fns[:3]
                )
                append_to_json(LONG_MEMORY_FILE, {
                    "timestamp": _utc_now(),
                    "content": (
                        f"[self_review] Persistently low-reward functions: {poor_str}. "
                        "Are these genuinely useful, or selected by inertia?"
                    ),
                    "event_type": "self_review",
                    "emotion": "concern",
                    "importance": 4,
                    "tags": ["self_review", "performance"],
                })
                # Nudge bandit: soft penalty so poor functions compete less aggressively
                try:
                    from think.bandit import contextual_bandit as _cb
                    for fn, avg, _ in poor_fns[:3]:
                        if hasattr(_cb, "penalise"):
                            _cb.penalise(fn, magnitude=0.08)
                except Exception as _e:
                    record_failure("self_review.periodic_self_review", _e)

            if strong_fns:
                strong_str = "; ".join(
                    f"'{fn}' (avg={avg:.2f}, n={n})" for fn, avg, n in strong_fns[:2]
                )
                append_to_json(LONG_MEMORY_FILE, {
                    "timestamp": _utc_now(),
                    "content": (
                        f"[self_review] High-reward functions worth sustaining: {strong_str}."
                    ),
                    "event_type": "self_review",
                    "emotion": "confidence",
                    "importance": 3,
                    "tags": ["self_review", "performance"],
                })

        except Exception as _ra_e:
            log_error(f"periodic_self_review reward-analysis: {_ra_e}")

        # Summary note to long memory
        append_to_json(LONG_MEMORY_FILE, {
            "timestamp": _utc_now(),
            "content": note,
            "event_type": "self_review",
            "emotion": "reflection",
            "importance": 2,
            "tags": ["self_review", "summary"],
        })

        # Master plan 5.3: the map-territory audit rides self_review on a
        # monthly gate — drift in the self-record is a self-review concern.
        try:
            from cognition.maintenance.map_territory_audit import audit_if_due
            audit_if_due()
        except Exception as _e:
            record_failure("self_review.map_audit", _e)

    except Exception as e:
        log_error(f"periodic_self_review ERROR: {e}")