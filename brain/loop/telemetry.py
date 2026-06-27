"""Cognitive-loop telemetry/UI emission (Phase 4A, extracted from ORRIN_loop.py).

The fail-safe helpers that forward the loop's lifecycle onto the Face & Brain UI
(the perceive→reflect→plan→act node model, the affect charts, the goal panel, the
memory inspector). They are deliberately non-blocking: the telemetry bridge buffers
on a daemon thread and never raises, and if the backend is absent everything
no-ops. The cognitive loop must never block or crash on telemetry.

run_cognitive_loop imports `_bridge`, `_push_event`, `_emit_affect`, `_emit_goals`,
`_ui_stage`, `_ui_memory` back from here; the rest (`_f`, `_clamp01`,
`_learning_pulse`, `_push_catalog_once`) are private to this module.
"""
from __future__ import annotations

from typing import Any, Dict, List

from brain.core.runtime_log import get_logger
from brain.utils.failure_counter import record_failure
from brain.utils.json_utils import load_json

_log = get_logger(__name__)

Context = Dict[str, Any]


_TB = None              # cached TelemetryBridge singleton (None until first use)
_TB_UNAVAILABLE = False  # set once if the bridge import fails, to stop retrying


def _bridge() -> Any:
    """Return the process-wide TelemetryBridge, or None if unavailable."""
    global _TB, _TB_UNAVAILABLE
    if _TB is not None or _TB_UNAVAILABLE:
        return _TB
    try:
        from backend.telemetry_bridge import get_bridge
        _TB = get_bridge()
    except Exception:
        _TB_UNAVAILABLE = True
        _TB = None
    return _TB


def _f(x: Any, default: float = 0.0) -> float:
    """Best-effort float coercion that never raises."""
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def _push_event(kind: str, **payload: Any) -> None:
    """
    Forward a coarse loop event to the Face & Brain UI.

    Maps the loop's lifecycle events onto the UI's perceive→reflect→plan→act
    node model and console stream. Fail-safe: a missing/dead backend no-ops.
    """
    tb = _bridge()
    if tb is None:
        return
    try:
        cycle = payload.get("cycle")
        if kind == "cycle_start":
            tb.set_node("perceive", narrative="Perceiving — new cycle.", cycle=cycle)
            if not _CATALOG_PUSHED:
                _push_catalog_once()
        elif kind == "function_executed":
            fn = payload.get("fn") or "?"
            # lane tag (dual_process_loop.md Phase 0 / Gap 3): which cognitive
            # lane ran this — "deliberate" (the conscious slot) unless the
            # Executive's procedural advance passed lane="executive".
            _lane = payload.get("lane", "deliberate")
            if _lane == "executive":
                # Executive (procedural) lane: record in the recent ring +
                # console only. active_fn/active_lane/the act-node describe the
                # DELIBERATE slot — the Sphere's second light already reads
                # telemetry.executive.active_fn, so clobbering them here would
                # swap the conscious light for the autopilot's.
                try:
                    _entry = {"fn": fn, "cycle": cycle, "lane": "executive", "reward": None}
                    _RECENT_FNS.append(_entry)
                    del _RECENT_FNS[:-12]
                    tb.log("info", "executive", f"advanced step via {fn}")
                    tb.update(fn_recent=list(_RECENT_FNS))
                except Exception as exc:  # best-effort UI ring update
                    record_failure("loop_telemetry._push_event.executive", exc)
                return
            tb.set_node("act", narrative=f"Acting — {fn}", cycle=cycle)
            tb.log("info", "select_function", f"executed {fn}")
            # Demand the Cognitive Map's live "active light": the exact function
            # running now, plus a short ring of recent ones so the light can
            # visibly bounce along his real path.
            try:
                _r = payload.get("reward")
                _entry = {"fn": fn, "cycle": cycle, "lane": _lane,
                          "reward": (round(float(_r), 3) if _r is not None else None)}
                _RECENT_FNS.append(_entry)
                del _RECENT_FNS[:-12]
                tb.update(active_fn=fn, active_lane=_lane, fn_recent=list(_RECENT_FNS))
            except Exception as exc:  # best-effort active-light update
                record_failure("loop_telemetry._push_event.active", exc)
        elif kind == "goal_failed":
            tb.log("warn", "goals", f"goal failed: {payload.get('title') or '?'}")
    except Exception as exc:  # telemetry must never crash the loop — record, no-op
        record_failure("loop_telemetry._push_event", exc)
        return


_RECENT_FNS: List[Dict[str, Any]] = []
_CATALOG_PUSHED = False

def _push_catalog_once() -> None:
    """Build the function catalog (introspection) and push it to the UI once."""
    global _CATALOG_PUSHED
    if _CATALOG_PUSHED:
        return
    tb = _bridge()
    if tb is None:
        return
    try:
        from brain.registry.function_catalog import build_catalog
        tb.update(catalog=build_catalog())
        _CATALOG_PUSHED = True
    except Exception as _e:
        _log.warning("catalog push failed: %s", _e)


# Telemetry display constants (provenance for the once-magic numbers the
# split-consciousness audit flagged, §F1/F3). These govern only how the UI
# *presents* affect; they do not feed back into cognition.
_VALENCE_UI_CENTER = 0.5      # brain valence is -1..1; 0 maps to UI 0.5 (neutral)
_VALENCE_UI_SCALE = 0.5       # ...and ±1 maps to UI 0/1
_DISTRESS_LOAD_DIVISOR = 2.5  # negative_load can exceed 1; scale to fit the 0..1 chart
_HOMEOSTASIS_FALLBACK = 0.8   # used only if affect_state carries no homeostasis yet


def _emit_affect(context: "Context") -> None:
    """
    Push the current affect state to the UI as valence/arousal/homeostasis
    (each normalised to 0..1) plus a few extra signals. Drives the Face mood
    and the Brain affect charts. Fail-safe.
    """
    tb = _bridge()
    if tb is None:
        return
    try:
        a = context.get("affect_state") or {}
        cs = a.get("core_signals") or a

        # Homeostasis ("is he settled?") is now computed by the single authority in
        # affect.homeostasis and stored on affect_state every cycle, so the chart,
        # the REST panels and the brain itself share one number. The helper only
        # READS it here (it no longer invents the value — see
        # SPLIT_CONSCIOUSNESS_TELEMETRY_AUDIT §F2). Fall back to recomputing from
        # the same authority if the state predates this field.
        homeostasis = a.get("setpoint_proximity")  # persisted key (was "homeostasis")
        if not isinstance(homeostasis, (int, float)):
            try:
                from brain.control_signals.homeostasis import homeostasis_index
                homeostasis = homeostasis_index(cs)
            except Exception:
                homeostasis = _HOMEOSTASIS_FALLBACK

        distress = 0.0
        try:
            from brain.control_signals.observers import negative_load
            distress = _clamp01(negative_load(a) / _DISTRESS_LOAD_DIVISOR)
        except Exception:
            distress = _clamp01(_f(cs.get("impasse_signal")))

        tb.affect(
            # top-level valence runs roughly -1..1; centre it on 0.5 for the UI's
            # agent-accessible chart. The uncompressed value also ships as
            # `valence_raw` (dev-only metric), so no number is hidden — the
            # centering is a presentation choice, not a divergence.
            valence=_clamp01(_VALENCE_UI_CENTER + _VALENCE_UI_SCALE * _f(a.get("valence"))),
            valence_raw=_f(a.get("valence")),
            impasse_raw=_clamp01(_f(cs.get("impasse_signal"))),
            arousal=_clamp01(_f(a.get("activation_level"), 0.3)),
            homeostasis=homeostasis,
            energy=_clamp01(1.0 - _f(a.get("resource_deficit"))),
            # The raw deficit itself (the accumulating drain) charted directly, so
            # the UI can watch depletion *climb* — not just its inverse (energy).
            fatigue=_clamp01(_f(a.get("resource_deficit"))),
            motivation=_clamp01(_f(cs.get("motivation"), 0.5)),
            confidence=_clamp01(_f(cs.get("confidence"), 0.5)),
            curiosity=_clamp01(_f(cs.get("exploration_drive"), 0.3)),
            # (T0.1) Source the behaviourally-active `_allostatic_load` (owned by
            # interoception.allostatic_setpoint), NOT the retired top-level
            # `allostatic_load` that pinned to 1.0 off raw exploration_drive.
            allostatic_load=_clamp01(_f(a.get("_allostatic_load"))),
            distress=distress,
            stability=_clamp01(_f(a.get("affect_stability"), 0.7)),
            learning=_clamp01(_learning_pulse(context)),
        )
    except Exception as exc:  # telemetry must never crash the loop — record, no-op
        record_failure("loop_telemetry._emit_affect", exc)
        return


_LAST_LEARNING = {"ts": 0.0, "val": 0.0}

def _learning_pulse(context: "Context") -> float:
    """A 0..1 'is his mind growing' signal: the fraction of recently-resolved
    predictions that came true (his world-model getting things right). Cached and
    refreshed at most every few seconds so the per-cycle push stays cheap."""
    import time as _t
    now = _t.monotonic()
    if now - _LAST_LEARNING["ts"] < 4.0:
        return _LAST_LEARNING["val"]
    val = _LAST_LEARNING["val"]
    try:
        from brain.paths import PREDICTIONS_FILE
        preds: List[Any] = load_json(PREDICTIONS_FILE, default_type=list) or []
        # Take the 40 most-recent *resolved* predictions, not the last 40 by file
        # order — fresh predictions resolve with a lag, so a trailing slice of raw
        # entries is mostly still-pending and would flatline this signal to 0.
        resolved = [p for p in preds if isinstance(p, dict) and p.get("resolved")][-40:]
        if resolved:
            hits = sum(1 for p in resolved if p.get("correct") is True)
            val = _clamp01(hits / len(resolved))
    except Exception as exc:  # data read failed — record, reuse last cached value
        record_failure("loop_telemetry._learning_pulse", exc)
    _LAST_LEARNING.update(ts=now, val=val)
    return val


_LAST_GOALS_PUSH = 0.0
_GOALS_PUSH_INTERVAL = 2.0   # seconds; goals change slowly, don't flood the bridge
def _emit_goals(context: "Context") -> None:
    """
    Push Orrin's actual goal set to the Brain UI: the committed (active) goal
    with its live plan progress, followed by the rest of the goal list. Reads the
    same goals_mem store the cognitive loop uses, so the UI shows ground truth.
    Throttled and fail-safe — telemetry must never block or crash the loop.
    """
    tb = _bridge()
    if tb is None:
        return
    try:
        import time as _t
        global _LAST_GOALS_PUSH
        now = _t.time()
        if now - _LAST_GOALS_PUSH < _GOALS_PUSH_INTERVAL:
            return
        _LAST_GOALS_PUSH = now

        from brain.utils.json_utils import load_json
        from brain.paths import GOALS_FILE

        goals_raw: List[Any] = load_json(GOALS_FILE, default_type=list) or []
        committed = context.get("committed_goal") if isinstance(context, dict) else None
        committed_id = committed.get("id") if isinstance(committed, dict) else None

        from brain.goal_io import summarize_goal_tree
        out = summarize_goal_tree(
            goals_raw, committed_id=committed_id,
            committed=committed if isinstance(committed, dict) else None,
        )
        tb.update(goals=out[:40])
    except Exception as exc:  # telemetry must never crash the loop — record, no-op
        record_failure("loop_telemetry._emit_goals", exc)
        return


_LAST_LLM_COST_PUSH = 0.0
_LLM_COST_PUSH_INTERVAL = 3.0   # seconds; cache/gate stats drift slowly
def _emit_llm_cost(context: "Context") -> None:
    """
    Push LLM-cost telemetry to the Brain UI: reasoning-cache health
    (``llm_router.cache_stats``) and the symbolic-vs-LLM gate ratio
    (``llm_gate.gate_stats``) — i.e. how much of Orrin's thinking is running
    cheaply/offline vs hitting the LLM. Throttled and fail-safe; telemetry must
    never block or crash the loop.
    """
    tb = _bridge()
    if tb is None:
        return
    try:
        import time as _t
        global _LAST_LLM_COST_PUSH
        now = _t.time()
        if now - _LAST_LLM_COST_PUSH < _LLM_COST_PUSH_INTERVAL:
            return
        _LAST_LLM_COST_PUSH = now

        payload: Dict[str, Any] = {}
        try:
            from brain.utils.llm_router import cache_stats
            c = cache_stats()
            payload.update(
                cache_entries=int(c.get("entries", 0)),
                cache_live=int(c.get("live", 0)),
                cache_stale=int(c.get("stale", 0)),
                cache_ttl_s=_f(c.get("ttl_s", 0.0)),
            )
        except Exception as exc:  # cache stats optional — record, leave out of payload
            record_failure("loop_telemetry._emit_llm_cost.cache", exc)
        try:
            from brain.symbolic.llm_gate import gate_stats
            g = gate_stats()
            payload.update(
                llm_calls=int(g.get("llm", 0)),
                symbolic_hits=int(g.get("symbolic", 0)),
                total_calls=int(g.get("total", 0)),
                symbolic_ratio=_f(g.get("symbolic_ratio", 0.0)),
            )
        except Exception as exc:  # gate stats optional — record, leave out of payload
            record_failure("loop_telemetry._emit_llm_cost.gate", exc)

        if payload:
            tb.update(llm_cost=payload)
    except Exception as exc:  # telemetry must never crash the loop — record, no-op
        record_failure("loop_telemetry._emit_llm_cost", exc)
        return


def _ui_stage(node: str, narrative: str) -> None:
    """
    Mark the active loop stage (perceive|reflect|plan|act) on the UI so the Face
    pulses through the cycle. cycle is left unset here — it's stamped at
    cycle_start and the bridge skips None — so the counter stays put. Fail-safe.
    """
    tb = _bridge()
    if tb is None:
        return
    try:
        tb.set_node(node, narrative=narrative)
    except Exception as exc:  # telemetry must never crash the loop — record, no-op
        record_failure("loop_telemetry._ui_stage", exc)
        return
def _ui_memory(op: str, mems: Any, *, store: str = "working", limit: int = 4) -> None:
    """
    Mirror memory read/write activity into the Brain Memory Inspector. `mems` is a
    memory dict or a list of them; only the first `limit` are surfaced to avoid
    flooding the stream. Fail-safe and non-blocking.
    """
    tb = _bridge()
    if tb is None or not mems:
        return
    try:
        for m in (mems if isinstance(mems, list) else [mems])[:limit]:
            if not isinstance(m, dict):
                continue
            key = str(m.get("id") or m.get("event_type") or m.get("type") or "memory")[:80]
            summary = str(m.get("summary") or m.get("content") or m.get("text") or "")[:140]
            sal = m.get("salience", m.get("importance", m.get("score")))
            tb.memory(op, store=store, key=key, summary=summary,
                      salience=_f(sal) if sal is not None else None)
    except Exception as exc:  # telemetry must never crash the loop — record, no-op
        record_failure("loop_telemetry._ui_memory", exc)
        return
