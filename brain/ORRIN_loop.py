# brain/ORRIN_loop.py
# V1 cognitive loop extracted as a callable for integration with v2's main.py.
# Call run_cognitive_loop(...) in a daemon thread from main.py.
from __future__ import annotations
from brain.core.runtime_log import get_logger

import os
import signal
import time
import inspect
import traceback
import warnings
from datetime import datetime, timezone
from typing import Any, Dict

from dotenv import load_dotenv
_log = get_logger(__name__)
load_dotenv()
os.environ["TOKENIZERS_PARALLELISM"] = "false"

warnings.filterwarnings(
    "ignore",
    message="`clean_up_tokenization_spaces` was not set.*",
    category=FutureWarning,
    module="transformers",
)

from brain.think.think_module import think
from brain.think.signal_router import process_inputs
from brain.think.think_utils.action_gate import take_action

from brain.think.loop_helpers import (
    emit_trace,
    compute_reward,
    emotional_delta_reward,
    blend_reward,
    reason_string,
    names,
    discover_callable_maps,
    execute_action_via_registries,
    bandit_learn,
)

from brain.core.manager import load_custom_cognition
from brain.registry.cognition_registry import COGNITIVE_FUNCTIONS, refresh as refresh_cog
from brain.registry.behavior_registry import BEHAVIORAL_FUNCTIONS, refresh as refresh_beh

from brain.affect.update_affect_state import update_affect_state
from brain.affect.reflect_on_affect import reflect_on_affect
from brain.affect.affect_drift import check_affect_drift

from brain.cognition.planning.reflection import record_decision

from brain.utils.get_cycle_count import get_cycle_count
from brain.utils.load_utils import load_context
from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_error, log_private, log_activity, log_model_issue
from brain.utils.emotion_utils import log_penalty_signal, log_uncertainty_spike

from brain.utils.error_router import route_exception
from brain.cognition.repair.auto_repair import try_auto_repair
from brain.utils.failure_counter import record_failure, dump_summary as _dump_failure_summary
from brain.utils.token_meter import dump_summary as _dump_token_summary

from brain.config.tuning import (
    AFFECT_TRANSIENT_DECAY,
    CRISIS_ABOVE_HALF_COUNT,
    CRISIS_ABOVE_HALF_THRESHOLD,
    CRISIS_ACUTE_PEAK,
    CRISIS_CHRONIC_MEAN,
)

from brain.paths import (
    RELATIONSHIPS_FILE, MODEL_CONFIG_FILE, CONTEXT, WORKING_MEMORY_FILE,
    LONG_MEMORY_FILE, AFFECT_STATE_FILE, BANDIT_STATE_FILE,
    REFLECTION as REFLECTION_LOG_FILE, CHAT_LOG_FILE,
    COGNITIVE_FUNCTIONS_LIST_FILE,
)

# ── Face & Brain UI telemetry ────────────────────────────────────────────────
# The UI consumes frames pushed through backend.telemetry_bridge. These helpers
# are deliberately fail-safe and non-blocking: the bridge buffers on a daemon
# thread and never raises, and if the backend is absent everything no-ops. The
# cognitive loop must never block or crash on telemetry.
_TB = None              # cached TelemetryBridge singleton (None until first use)
_TB_UNAVAILABLE = False  # set once if the bridge import fails, to stop retrying


def _bridge():
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


def _f(x, default: float = 0.0) -> float:
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


def _push_event(kind: str, **payload) -> None:
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
                except Exception:
                    pass
                return
            tb.set_node("act", narrative=f"Acting — {fn}", cycle=cycle)
            tb.log("info", "select_function", f"executed {fn}")
            # Drive the Cognitive Map's live "active light": the exact function
            # running now, plus a short ring of recent ones so the light can
            # visibly bounce along his real path.
            try:
                _r = payload.get("reward")
                _entry = {"fn": fn, "cycle": cycle, "lane": _lane,
                          "reward": (round(float(_r), 3) if _r is not None else None)}
                _RECENT_FNS.append(_entry)
                del _RECENT_FNS[:-12]
                tb.update(active_fn=fn, active_lane=_lane, fn_recent=list(_RECENT_FNS))
            except Exception:
                pass
        elif kind == "goal_failed":
            tb.log("warn", "goals", f"goal failed: {payload.get('title') or '?'}")
    except Exception:
        return


_RECENT_FNS: list = []
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
        homeostasis = a.get("homeostasis")
        if not isinstance(homeostasis, (int, float)):
            try:
                from brain.affect.homeostasis import homeostasis_index
                homeostasis = homeostasis_index(cs)
            except Exception:
                homeostasis = _HOMEOSTASIS_FALLBACK

        distress = 0.0
        try:
            from brain.affect.observers import negative_load
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
            allostatic_load=_clamp01(_f(a.get("allostatic_load"))),
            distress=distress,
            stability=_clamp01(_f(a.get("affect_stability"), 0.7)),
            learning=_clamp01(_learning_pulse(context)),
        )
    except Exception:
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
        preds = load_json(PREDICTIONS_FILE, default_type=list) or []
        # Take the 40 most-recent *resolved* predictions, not the last 40 by file
        # order — fresh predictions resolve with a lag, so a trailing slice of raw
        # entries is mostly still-pending and would flatline this signal to 0.
        resolved = [p for p in preds if isinstance(p, dict) and p.get("resolved")][-40:]
        if resolved:
            hits = sum(1 for p in resolved if p.get("correct") is True)
            val = _clamp01(hits / len(resolved))
    except Exception:
        pass
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

        goals_raw = load_json(GOALS_FILE, default_type=list) or []
        committed = context.get("committed_goal") if isinstance(context, dict) else None
        committed_id = committed.get("id") if isinstance(committed, dict) else None

        from goal_io import summarize_goal_tree
        out = summarize_goal_tree(
            goals_raw, committed_id=committed_id,
            committed=committed if isinstance(committed, dict) else None,
        )
        tb.update(goals=out[:40])
    except Exception:
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
    except Exception:
        return


_SEEN_WM_IDS: set = set()  # working-memory ids already mirrored to the inspector


def _ui_memory(op: str, mems, *, store: str = "working", limit: int = 4) -> None:
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
    except Exception:
        return

Context = Dict[str, Any]

# Functions that engage Orrin with his environment rather than pure internal computation.
# Clark (1997) embodied cognition; Lave (1988) situated action.
# Used by the outward-debt counter below and by finalize.py's satisfaction scorer.
_OUTWARD_FNS: frozenset = frozenset({
    "look_outward", "look_around", "leave_note", "write_desktop_note",
    "survey_environment", "read_clipboard", "announce_to_dashboard",
    "seek_novelty", "pursue_committed_goal", "write_cognitive_function",
    "write_tool", "wikipedia_search", "read_rss", "research_topic",
    "fetch_and_read", "search_own_files", "grep_files", "check_user_presence",
    "save_note", "notify_user",
})

def _build_kwargs_for(fn, name: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    try:
        sig = inspect.signature(fn)
    except Exception:
        return {}
    wm = ctx.get("working_memory", []) or []
    lm = ctx.get("long_memory", []) or []
    try:
        recent = (wm[-6:] if isinstance(wm, list) else []) + (lm[-6:] if isinstance(lm, list) else [])
    except Exception:
        recent = []
    mapping = {
        "context": ctx, "ctx": ctx,
        "self_model": ctx.get("self_model"),
        "affect_state": ctx.get("affect_state", {}),
        "emotions": ctx.get("affect_state", {}),
        "relationships": ctx.get("relationships", {}),
        "long_memory": lm,
        "working_memory": wm,
        "recent": recent,
        "recent_memories": recent,
        # reflect_on_affect / reflect_on_emotion_model take (context, self_model,
        # memory) — "memory" was missing from this mapping, so both were selected
        # and then skipped as "not directly dispatchable" dozens of times a day.
        "memory": recent,
        "memories": recent,
        "retrieved_memories": ctx.get("retrieved_memories", []),
        "speaker": ctx.get("speaker"),
        "goal": ctx.get("committed_goal") or ctx.get("focus_goal"),
        "focus_goal": ctx.get("focus_goal") or ctx.get("committed_goal"),
    }
    built = {}
    for p in sig.parameters.values():
        if p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        if p.name in mapping and mapping[p.name] is not None:
            built[p.name] = mapping[p.name]
    return built

def _invoke_cognition(fn, name: str, ctx: Dict[str, Any], *, args=None, kwargs=None):
    if isinstance(args, (list, tuple)) or isinstance(kwargs, dict):
        return fn(*(args or ()), **(kwargs or {}))
    built = _build_kwargs_for(fn, name, ctx)
    # Guard: if the function requires params that _build_kwargs_for can't supply,
    # bail now rather than crashing at the bare re-raise on the last line.
    try:
        sig = inspect.signature(fn)
        unsatisfied = [
            p.name for p in sig.parameters.values()
            if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            and p.default is inspect.Parameter.empty
            and p.name not in ("self", "cls")
            and p.name not in built
        ]
        if unsatisfied:
            log_error(f"[invoke_cognition] {name} needs {unsatisfied} — not directly dispatchable; skipping")
            # Tell selection about it: an undispatchable function must leave the
            # candidate pool, otherwise the selector keeps picking it and the
            # cycle is wasted every time (the dominant error-log line of the
            # first 2.7k cycles).
            try:
                _ud = ctx.setdefault("_undispatchable_fns", [])
                if name not in _ud:
                    _ud.append(name)
            except Exception:
                pass
            return {"status": "error", "error": f"unsatisfiable_args: {unsatisfied}"}
    except Exception as _e:
        record_failure("ORRIN_loop._invoke_cognition", _e)
    for attempt in (
        lambda: fn(**built),
        lambda: fn(ctx),
        lambda: fn({"type": name, "name": name}, ctx),
        lambda: fn(),
    ):
        try:
            return attempt()
        except TypeError:
            continue
    return fn(**built)

def _validate_boot_files() -> None:
    """
    Check critical state files for schema correctness at startup.
    Logs a loud warning and reinitialises to safe defaults if a file is wrong type.
    """
    checks = [
        (LONG_MEMORY_FILE,      list,  []),
        (WORKING_MEMORY_FILE,   list,  []),
        # reflection_log / chat_log are list-typed too; previously they only
        # logged "does not contain a list" and were skipped (never self-healed),
        # so a bad shape persisted across boots (run audit #5).
        (REFLECTION_LOG_FILE,   list,  []),
        (CHAT_LOG_FILE,         list,  []),
        (AFFECT_STATE_FILE,  dict,  {}),
        (BANDIT_STATE_FILE,     dict,  {}),
    ]
    for path, expected_type, safe_default in checks:
        try:
            data = load_json(path, default_type=expected_type)
            if not isinstance(data, expected_type):
                log_error(
                    f"[boot] SCHEMA ERROR: {path.name} should be {expected_type.__name__}, "
                    f"got {type(data).__name__}. Reinitialising to safe default."
                )
                save_json(path, safe_default)
        except Exception as e:
            log_error(f"[boot] Could not validate {path.name}: {e}")

    # Emotion keyword model: an empty affect_model.json silently turns all
    # affect detection neutral. Seed it from the packaged defaults (logs once).
    try:
        from brain.affect.model import seed_default_emotion_keywords
        seed_default_emotion_keywords()
    except Exception as e:
        log_error(f"[boot] Could not seed emotion keywords: {e}")

    # Sweep orphaned atomic-write temp files (tmp* / *.tmp) older than a day —
    # hard kills strand them and they accumulate in brain/data/ (audit §11).
    try:
        import time as _t
        from brain.paths import DATA_DIR as _dd
        _cutoff = _t.time() - 86400
        _swept = 0
        for _p in list(_dd.glob("tmp*")) + list(_dd.glob("*.tmp")):
            try:
                if _p.is_file() and _p.stat().st_mtime < _cutoff:
                    _p.unlink()
                    _swept += 1
            except Exception:
                pass
        if _swept:
            log_activity(f"[boot] Swept {_swept} stale temp file(s) from data dir.")
    except Exception as e:
        log_error(f"[boot] Temp-file sweep failed: {e}")


def _verify_production_capability(functions: Dict[str, Any]) -> Dict[str, Any]:
    """Verify the complete compose_section route after runtime registration."""
    checks: Dict[str, Any] = {}
    try:
        meta = functions.get("compose_section")
        fn = meta.get("function") if isinstance(meta, dict) else meta
        checks["callable_registry"] = callable(fn)

        manifest = load_json(COGNITIVE_FUNCTIONS_LIST_FILE, default_type=list) or []
        names = {
            str(item.get("name"))
            for item in manifest
            if isinstance(item, dict) and item.get("name")
        }
        checks["persisted_manifest"] = "compose_section" in names

        from brain.cognition.planning.step_execution import recognise_step_action
        checks["plan_resolver"] = recognise_step_action({
            "step": "Draft the thesis section",
            "action": {"function": "compose_section"},
        }) == "compose_section"

        from brain.think.think_utils.select_function import (
            _CAPS_PATH,
            _is_dispatchable,
            _load_actions,
        )
        checks["dispatchable"] = _is_dispatchable("compose_section")
        checks["selector_pool"] = "compose_section" in _load_actions()

        import json as _json
        capabilities = _json.loads(_CAPS_PATH.read_text(encoding="utf-8"))
        checks["capability_metadata"] = bool(capabilities.get("compose_section"))
    except Exception as exc:
        record_failure("ORRIN_loop.production_capability_check", exc)
        checks["check_error"] = f"{type(exc).__name__}: {exc}"

    checks["reachable"] = all(value is True for key, value in checks.items()
                              if key != "check_error") and "check_error" not in checks
    if not checks["reachable"]:
        missing = [key for key, value in checks.items()
                   if key != "reachable" and value is not True]
        exc = RuntimeError(f"production_capability_unreachable: {', '.join(missing)}")
        record_failure("ORRIN_loop.production_capability_unreachable", exc)
        log_error(f"[boot] {exc}")
    else:
        log_activity("[boot] compose_section production capability reachable end-to-end.")
    return checks


def _boot_context() -> Context:
    """Load and reset context at startup."""
    _validate_boot_files()
    production_capability_status: Dict[str, Any] = {}
    for path in [RELATIONSHIPS_FILE, MODEL_CONFIG_FILE]:
        path.parent.mkdir(parents=True, exist_ok=True)


    try:
        refresh_cog()
    except Exception as e:
        log_error(f"Failed to refresh cognitive functions: {e}")
    try:
        refresh_beh()
    except Exception as e:
        log_error(f"Failed to refresh behavioral functions: {e}")

    try:
        custom = load_custom_cognition()
        if isinstance(custom, dict):
            for k, v in custom.items():
                if callable(v):
                    COGNITIVE_FUNCTIONS[k] = {"function": v, "is_cognition": True}
                elif isinstance(v, dict) and callable(v.get("function")):
                    COGNITIVE_FUNCTIONS[k] = {
                        "function": v["function"],
                        "is_cognition": bool(v.get("is_cognition", True)),
                    }
    except Exception as e:
        log_error(f"Failed to merge custom cognition: {e}")

    # Register agency functions (tool use + self-modification)
    try:
        from brain.agency.tool_runner import AGENCY_TOOL_FUNCTIONS
        from brain.agency.code_writer import AGENCY_CODE_FUNCTIONS
        for k, fn in {**AGENCY_TOOL_FUNCTIONS, **AGENCY_CODE_FUNCTIONS}.items():
            COGNITIVE_FUNCTIONS[k] = {"function": fn, "is_cognition": True}
        from brain.agency.compose_section import compose_section as _compose_section
        COGNITIVE_FUNCTIONS["compose_section"] = {
            "function": _compose_section,
            "is_cognition": True,
            "requires_llm": False,
        }
        # Re-persist so the bandit's JSON list includes the agency function names
        from brain.registry.cognition_registry import persist_names
        persist_names(COGNITIVE_FUNCTIONS)
        log_activity("Agency functions registered into cognitive loop.")
        production_capability_status = _verify_production_capability(
            COGNITIVE_FUNCTIONS
        )
    except Exception as e:
        log_error(f"Failed to register agency functions: {e}")

    # Register thread-of-attention cognition
    try:
        from brain.cognition.threads import handle_thread_continue as _htc
        COGNITIVE_FUNCTIONS["thread_continue"] = {"function": _htc, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register thread_continue: {e}")

    # Register value evolution cognition
    try:
        from brain.cognition.selfhood.value_evolution import propose_value_revision as _pvr
        COGNITIVE_FUNCTIONS["propose_value_revision"] = {"function": _pvr, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register propose_value_revision: {e}")

    # Register autobiography cognition
    try:
        from brain.cognition.selfhood.autobiography import narrative_update as _nu
        COGNITIVE_FUNCTIONS["narrative_update"] = {"function": _nu, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register narrative_update: {e}")

    # Register world-perception cognition functions
    try:
        from brain.cognition.perception.look_around import look_around as _la
        from brain.cognition.perception.look_outward import look_outward as _lo
        COGNITIVE_FUNCTIONS["look_around"]  = {"function": _la, "is_cognition": True}
        COGNITIVE_FUNCTIONS["look_outward"] = {"function": _lo, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register perception functions: {e}")

    # Register intrinsic goal generation
    try:
        from brain.cognition.intrinsic_goals import generate_intrinsic_goals as _gig
        COGNITIVE_FUNCTIONS["generate_intrinsic_goals"] = {"function": _gig, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register generate_intrinsic_goals: {e}")

    # Register privacy cognition
    try:
        from brain.cognition.privacy import mark_private as _mp
        COGNITIVE_FUNCTIONS["mark_private"] = {"function": _mp, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register mark_private: {e}")

    # Register metacognition channel flush (callable by LLM as introspection)
    try:
        from brain.cognition.metacog import metacog_flush as _mcfn
        COGNITIVE_FUNCTIONS["metacog_flush"] = {"function": _mcfn, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register metacog_flush: {e}")

    # Register active goal pursuit and progress assessment
    try:
        from brain.cognition.planning.pursue_goal import (
            pursue_committed_goal as _pcg, assess_goal_progress as _agp,
            adapt_subgoals as _asg, attend_goal as _attg,
            redirect_goal_plan as _rgp, abandon_goal as _abg,
        )
        # pursue_committed_goal stays registered (the Executive calls it directly),
        # but is excluded from DELIBERATE selection (select_function._ALWAYS_EXCLUDE)
        # — dual_process_loop.md Phase 2. attend_goal is the thin deliberate
        # goal-attention act that replaces it in the conscious slot (§6.3).
        # redirect_goal_plan / abandon_goal are the deliberate SUPERVISION commands
        # (Phase 4, §6.3/I6) — the conscious mind steering the autopilot; abandon
        # is guarded so an exploratory pick can't kill a healthy goal.
        COGNITIVE_FUNCTIONS["pursue_committed_goal"] = {"function": _pcg, "is_cognition": True}
        COGNITIVE_FUNCTIONS["assess_goal_progress"] = {"function": _agp, "is_cognition": True}
        COGNITIVE_FUNCTIONS["adapt_subgoals"] = {"function": _asg, "is_cognition": True}
        COGNITIVE_FUNCTIONS["attend_goal"] = {"function": _attg, "is_cognition": True}
        COGNITIVE_FUNCTIONS["redirect_goal_plan"] = {"function": _rgp, "is_cognition": True}
        COGNITIVE_FUNCTIONS["abandon_goal"] = {"function": _abg, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register goal pursuit functions: {e}")

    # Register innovation outcome assessment
    try:
        from brain.cognition.innovation.evaluation import assess_innovation_outcomes as _aio
        COGNITIVE_FUNCTIONS["assess_innovation_outcomes"] = {"function": _aio, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register assess_innovation_outcomes: {e}")

    # Register file content search (grep own data/source files)
    try:
        from brain.cognition.search_own_files import search_own_files as _sof
        COGNITIVE_FUNCTIONS["search_own_files"] = {"function": _sof, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register search_own_files: {e}")

    # Register active experimentation (hypothesis → test → consolidate)
    try:
        from brain.cognition.experimentation import run_active_experiment as _rae
        COGNITIVE_FUNCTIONS["run_active_experiment"] = {"function": _rae, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register run_active_experiment: {e}")

    # Register latent identity update (stable numeric identity anchor)
    try:
        from brain.cognition.selfhood.latent_identity import update_latent_identity as _uli
        COGNITIVE_FUNCTIONS["update_latent_identity"] = {"function": _uli, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register update_latent_identity: {e}")

    # Register reflection audit (scan for ungrounded reflective claims)
    try:
        from brain.cognition.reflection_metadata import audit_reflective_claims as _arc
        COGNITIVE_FUNCTIONS["audit_reflective_claims"] = {"function": _arc, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register audit_reflective_claims: {e}")

    # Register symbolic reasoning router (check local knowledge before LLM)
    try:
        from brain.symbolic.reasoning_router import route as _sym_route
        def _sym_route_fn(context=None, **kw):
            user_input = (context or {}).get("user_input", "")
            if not user_input:
                return None
            result = _sym_route(user_input, context=context)
            if result.get("resolved") and result.get("answer"):
                log_activity(f"[symbolic] Resolved via {result['source']}: {result['answer'][:80]}")
            return result
        COGNITIVE_FUNCTIONS["symbolic_route"] = {"function": _sym_route_fn, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register symbolic_route: {e}")

    # Register intrinsic motivation driver (spawns sub-goals on high exploration_drive)
    try:
        from brain.symbolic.intrinsic_motivation import run_intrinsic_motivation as _rim
        COGNITIVE_FUNCTIONS["run_intrinsic_motivation"] = {"function": _rim, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register run_intrinsic_motivation: {e}")

    # Register autonomous experimentation (sandbox probes for high-exploration_drive goals)
    try:
        from brain.symbolic.autonomous_experiment import run_experiment_cycle as _raec
        COGNITIVE_FUNCTIONS["run_symbolic_experiments"] = {"function": _raec, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register run_symbolic_experiments: {e}")

    # Register embodied observation (read-only real-world grounding)
    try:
        from brain.symbolic.embodied_actions import run_embodied_cycle as _remc
        COGNITIVE_FUNCTIONS["run_embodied_observation"] = {"function": _remc, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register run_embodied_observation: {e}")

    # Register symbolic self-improvement loop
    try:
        from brain.symbolic.self_improvement import run_self_improvement as _rsim
        COGNITIVE_FUNCTIONS["run_self_improvement"] = {"function": _rsim, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register run_self_improvement: {e}")

    # Register agency skills (file search, notifications, notes)
    try:
        from brain.agency.skills.grep_files import grep_files as _gf
        from brain.agency.skills.list_directory import list_directory as _ld
        from brain.agency.skills.search_files import search_files as _sf
        from brain.agency.skills.notify_user import notify_user as _nu2
        from brain.agency.skills.save_note import save_note as _sn
        COGNITIVE_FUNCTIONS["grep_files"]     = {"function": _gf,  "is_cognition": True}
        COGNITIVE_FUNCTIONS["list_directory"] = {"function": _ld,  "is_cognition": True}
        COGNITIVE_FUNCTIONS["search_files"]   = {"function": _sf,  "is_cognition": True}
        COGNITIVE_FUNCTIONS["notify_user"]    = {"function": _nu2, "is_cognition": True}
        COGNITIVE_FUNCTIONS["save_note"]      = {"function": _sn,  "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register agency skills: {e}")

    # Register leave_note — writes an observation to the user-facing outbox
    try:
        from brain.cognition.leave_note import leave_note as _leave_note
        COGNITIVE_FUNCTIONS["leave_note"] = {"function": _leave_note, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register leave_note: {e}")

    # Register laptop-presence actions — Orrin as a user on this machine.
    # Each wraps system_presence.py so Orrin can sense OS state, leave desktop
    # notes, read clipboard, and announce to the dashboard.
    # Clark (1997) embodied cognition: acting on the environment is constitutive
    # of cognition, not peripheral to it.
    try:
        # write_to_desktop_note / announce_presence are no longer called here —
        # the _write_desktop_note and _announce wrappers compose through the one
        # expression door (behavior.express_to_user), which routes to them
        # internally (EXPRESSION_MEMBRANE_FIX_PLAN E2/E3).
        from brain.embodiment.system_presence import (
            get_system_state   as _gss,
            check_user_active  as _cua,
            read_clipboard     as _rcb,
        )
        def _survey_env(context=None):
            s = _gss()
            from brain.cog_memory.working_memory import update_working_memory as _uwm
            _uwm({"content": f"[survey] System state: {str(s)[:300]}", "event_type": "system_survey", "priority": 2})
            return s
        def _write_desktop_note(context=None):
            # Compose through the one expression door — never scrape working
            # memory (EXPRESSION_MEMBRANE_FIX_PLAN E2).
            from brain.behavior.express_to_user import build_motive, express_to_user
            ctx = context or {}
            motive = build_motive(ctx, intent="write_desktop_note", recipient="Ric")
            return express_to_user(motive, "desktop", ctx)
        def _check_user(context=None):
            return _cua()
        def _announce(context=None):
            # Compose through the one expression door — never ship the last WM
            # entry to the dashboard (EXPRESSION_MEMBRANE_FIX_PLAN E3).
            from brain.behavior.express_to_user import build_motive, express_to_user
            ctx = context or {}
            motive = build_motive(ctx, intent="announce", recipient="dashboard")
            return express_to_user(motive, "dashboard", ctx)
        def _read_clip(context=None):
            r = _rcb()
            if r.get("content"):
                from brain.cog_memory.working_memory import update_working_memory as _uwm
                _uwm({"content": f"[clipboard] I noticed: {r['content'][:200]}", "event_type": "clipboard_observation", "priority": 2})
            return r
        COGNITIVE_FUNCTIONS["survey_environment"]   = {"function": _survey_env,       "is_cognition": True}
        COGNITIVE_FUNCTIONS["write_desktop_note"]   = {"function": _write_desktop_note,"is_cognition": True}
        COGNITIVE_FUNCTIONS["check_user_presence"]  = {"function": _check_user,        "is_cognition": True}
        COGNITIVE_FUNCTIONS["announce_to_dashboard"]= {"function": _announce,          "is_cognition": True}
        COGNITIVE_FUNCTIONS["read_clipboard"]       = {"function": _read_clip,         "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register system_presence functions: {e}")

    # Register self-modification functions (write/list/delete own code)
    try:
        from brain.agency.code_writer import (
            write_cognitive_function as _wcf,
            write_tool as _wt,
            list_own_code as _loc,
            delete_own_code as _doc,
        )
        COGNITIVE_FUNCTIONS["write_cognitive_function"] = {"function": _wcf, "is_cognition": True}
        COGNITIVE_FUNCTIONS["write_tool"]               = {"function": _wt,  "is_cognition": True}
        COGNITIVE_FUNCTIONS["list_own_code"]            = {"function": _loc, "is_cognition": True}
        COGNITIVE_FUNCTIONS["delete_own_code"]          = {"function": _doc, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register code_writer functions: {e}")

    # Register cognition repair functions
    try:
        from brain.cognition.repair.repair import (
            detect_memory_contradictions as _dc,
            repair_contradictions as _rc,
        )
        from brain.cognition.introspection.router import introspect as _ir
        # No real prompt exists for this fn — it routes to the introspection
        # repair pass. Tagged requires_llm so the 0.3 gate keeps it out of the
        # candidate pool whenever the LLM tool is down (BEHAVIOR_FIX_PLAN §5).
        COGNITIVE_FUNCTIONS["reflect_on_cognition_rhythm"] = {
            "function": lambda: _ir("repair"), "is_cognition": True, "requires_llm": True}
        COGNITIVE_FUNCTIONS["detect_memory_contradictions"] = {"function": _dc,  "is_cognition": True}
        COGNITIVE_FUNCTIONS["repair_contradictions"]       = {"function": _rc,  "is_cognition": True}
        # Phase 2.2: the failure ledger — failures read together, not one at a time.
        from brain.cognition.reflection.review_failures import review_failures as _rvf
        COGNITIVE_FUNCTIONS["review_failures"]             = {"function": _rvf, "is_cognition": True}
        # Phase 5.3: the map that notices its own drift — deliberately invocable.
        from brain.cognition.maintenance.map_territory_audit import audit_map_territory as _mta
        COGNITIVE_FUNCTIONS["audit_map_territory"]         = {"function": _mta, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register cognition repair functions: {e}")

    # Register emotion top-level callable functions
    try:
        from brain.affect.regulation import attempt_regulation as _ar
        from brain.affect.affect_drift import check_affect_drift as _ced
        from brain.affect.reflect_on_affect import reflect_on_affect as _roe
        from brain.affect.update_affect_state import update_affect_state as _ues
        from brain.affect.apply_affective_feedback import apply_affective_feedback as _aef
        from brain.affect.modes_and_affect import affect_driven_mode_shift as _edms
        from brain.affect.affect import investigate_unexplained_emotions as _iue
        from brain.affect.stagnation_signal_escalation import update_stagnation_signal_escalation as _ube
        from brain.affect.reflect_on_affect_model import reflect_on_emotion_model as _roem
        COGNITIVE_FUNCTIONS["attempt_regulation"]            = {"function": _ar,   "is_cognition": True}
        COGNITIVE_FUNCTIONS["check_affect_drift"]           = {"function": _ced,  "is_cognition": True}
        COGNITIVE_FUNCTIONS["reflect_on_affect"]           = {"function": _roe,  "is_cognition": True}
        COGNITIVE_FUNCTIONS["update_affect_state"]        = {"function": _ues,  "is_cognition": True}
        COGNITIVE_FUNCTIONS["apply_affective_feedback"]      = {"function": _aef,  "is_cognition": True}
        COGNITIVE_FUNCTIONS["affect_driven_mode_shift"]     = {"function": _edms, "is_cognition": True}
        COGNITIVE_FUNCTIONS["investigate_unexplained_emotions"] = {"function": _iue, "is_cognition": True}
        COGNITIVE_FUNCTIONS["update_stagnation_signal_escalation"]     = {"function": _ube,  "is_cognition": True}
        COGNITIVE_FUNCTIONS["reflect_on_emotion_model"]      = {"function": _roem, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register emotion functions: {e}")

    # Register symbolic cycle functions
    try:
        from brain.symbolic.benchmark import run_benchmark as _rb
        from brain.symbolic.prediction_engine import run_symbolic_prediction_cycle as _rspc
        from brain.symbolic.rule_forgetting import run_forgetting_cycle as _rfc
        from brain.symbolic.rule_compressor import run_rule_compression as _rrc
        from brain.symbolic.symbolic_dream import run_symbolic_dream as _rsd
        from brain.symbolic.embodied_actions import run_embodied_cycle as _rec2
        COGNITIVE_FUNCTIONS["run_benchmark"]                 = {"function": _rb,   "is_cognition": True}
        COGNITIVE_FUNCTIONS["run_symbolic_prediction_cycle"] = {"function": _rspc, "is_cognition": True}
        COGNITIVE_FUNCTIONS["run_forgetting_cycle"]          = {"function": _rfc,  "is_cognition": True}
        COGNITIVE_FUNCTIONS["run_rule_compression"]          = {"function": _rrc,  "is_cognition": True}
        COGNITIVE_FUNCTIONS["run_symbolic_dream"]            = {"function": _rsd,  "is_cognition": True}
        COGNITIVE_FUNCTIONS["run_embodied_cycle"]            = {"function": _rec2, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register symbolic cycle functions: {e}")

    # Re-persist cognition list so LLM sees all new functions
    try:
        from brain.registry.cognition_registry import persist_names as _pn
        _pn(COGNITIVE_FUNCTIONS)
    except Exception as e:
        log_error(f"Failed to re-persist cognition names: {e}")

    # Sanitize critical state files before the first cycle runs.
    # Coerces null/non-finite float values to safe defaults so no
    # float(None) crashes occur during boot or the first few cycles.
    try:
        from brain.utils.state_guard import sanitize_all
        sanitize_all()
    except Exception as _sg_err:
        log_error(f"state_guard sanitize_all failed at boot: {_sg_err}")

    context = load_context()
    context["_production_capability_status"] = production_capability_status
    context.setdefault("committed_goal", None)
    context.setdefault("action_debt", 0)
    context.setdefault("last_action_ts", 0.0)
    context.setdefault("recent_picks", [])

    # Clear stale user input so Orrin doesn't reply to messages from a previous session
    try:
        from brain.paths import USER_INPUT
        USER_INPUT.write_text("", encoding="utf-8")
    except Exception as _e:
        log_error(f"[boot] Could not clear user_input.txt: {_e}")

    affect_state = context.get("affect_state", {})
    affect_state.setdefault("stagnation_signal", 0.0)
    # Dampen negative emotions carried over from last session
    for k in ["impasse_signal", "penalty_signal", "conflict_signal", "threat_level", "stagnation_signal"]:
        if k in affect_state:
            affect_state[k] = float(affect_state[k] or 0.0) * 0.65
            if affect_state[k] < 0.07:
                affect_state[k] = 0.0
    # Cap positive emotions that are pinned at ceiling — they should re-earn their peaks
    _POSITIVE_CEILING = 0.75
    for k in ["motivation", "exploration_drive", "confidence", "expected_gain", "positive_valence"]:
        raw = float(affect_state.get(k) or 0.0)
        if raw > _POSITIVE_CEILING:
            affect_state[k] = _POSITIVE_CEILING
    _core = affect_state.get("core_signals") or {}
    if isinstance(_core, dict):
        for k in ["motivation", "exploration_drive", "confidence", "expected_gain", "positive_valence"]:
            raw = float(_core.get(k) or 0.0)
            if raw > _POSITIVE_CEILING:
                _core[k] = _POSITIVE_CEILING
        affect_state["core_signals"] = _core
    context["affect_state"] = affect_state
    # Persist the capped state so it survives into the first update_affect_state call
    try:
        save_json(AFFECT_STATE_FILE, affect_state)
    except Exception as _e:
        record_failure("ORRIN_loop._boot_context", _e)

    from brain.cog_memory.working_memory import update_working_memory
    if "emergency_action" in context:
        update_working_memory("Orrin is recovering from emergency shutdown. Residual uncertainty present.")
        affect_state["uncertainty"] = min(affect_state.get("uncertainty", 0.0) + 0.35, 1.0)
        context["affect_state"] = affect_state
        del context["emergency_action"]

    if affect_state.get("uncertainty", 0) > 0.2:
        update_working_memory("Waking up feeling uncertain after last shutdown. Self-reflection recommended.")
    elif sum(affect_state.get(k, 0.0) for k in ["impasse_signal", "conflict_signal", "penalty_signal", "stagnation_signal"]) > 0.3:
        update_working_memory("Residual negative mood detected from last session.")

    # ── Cold-start seed: ensure there is always at least one concrete goal at boot.
    # Prevents the cold-start deadlock where thinking needs a goal but goal creation
    # needs thinking. Only fires when no committed goal survived the previous session.
    # The seed is concrete enough to act on immediately (search + store result).
    if not context.get("committed_goal"):
        try:
            from datetime import datetime as _dt, timezone as _tz
            _boot_ts = _dt.now(_tz.utc).isoformat()
            context["committed_goal"] = {
                "id":         f"boot-seed-{_boot_ts[:19]}",
                "title":      "Read and summarize one of my own cognitive subsystems",
                "name":       "Read and summarize one of my own cognitive subsystems",
                "kind":       "generic",
                "tier":       "short_term",
                "priority":   "NORMAL",
                "tags":       ["intrinsic", "self_exploration", "boot_seed"],
                "spec":       {
                    "description": (
                        "Use search_own_files to read a brain subsystem I haven't examined recently "
                        "and write a plain-language summary of what it does to working memory."
                    ),
                    "driven_by": "self_exploration",
                },
                "next_action": None,
                "status":     "in_progress",
                "milestones": [
                    {"text": "A subsystem file was identified.", "met": False, "met_at": None},
                    {"text": "The file was read and understood.", "met": False, "met_at": None},
                    {"text": "A summary was written to working memory.", "met": False, "met_at": None},
                ],
            }
            log_activity("[boot] No prior committed goal — seeded concrete boot goal.")
        except Exception as _seed_e:
            log_error(f"[boot] Boot goal seed failed: {_seed_e}")

    # ── Death continuity: read previous Orrin's final words ────────────────
    try:
        from brain.paths import FINAL_THOUGHTS as _FT
        if _FT.exists():
            import json as _json
            _ft = _json.loads(_FT.read_text(encoding="utf-8"))
            # final_thoughts.json may be a list (legacy) — take the last element
            if isinstance(_ft, list):
                _ft = _ft[-1] if _ft else {}
            if not isinstance(_ft, dict):
                _ft = {}
            _reflection = _ft.get("reflection", "")
            _reason = _ft.get("death_reason", "unknown")
            _ts = _ft.get("timestamp", "")
            if _reflection:
                update_working_memory(
                    f"[Continuity] The previous version of me ended on {_ts[:10]} "
                    f"(reason: {_reason}). Their final words: {_reflection[:300]}"
                )
                log_activity(f"[boot] Loaded final_thoughts from previous run ({_ts[:10]}, reason={_reason}).")
                # Rename so it doesn't re-inject on every boot — keep as archive
                import shutil as _sh
                _archive = _FT.parent / f"final_thoughts_archive_{_ts[:10]}.json"
                try:
                    _sh.move(str(_FT), str(_archive))
                except Exception:
                    _FT.unlink(missing_ok=True)
    except Exception as e:
        record_failure("ORRIN_loop.boot_final_thoughts", e)

    return context


def _apply_transient_signal_decay(context: "Context") -> "Context":
    """
    Pipeline stage (Finding 1's stage(context) -> context pattern): decay
    short-lived affect signals (impasse/penalty/conflict/threat/stagnation/
    uncertainty) toward zero each cycle, then check whether the decayed
    core-negative signals indicate a sustained crisis — either an acute spike
    (one signal >= CRISIS_ACUTE_PEAK plus CRISIS_ABOVE_HALF_COUNT others >=
    CRISIS_ABOVE_HALF_THRESHOLD) or a chronic broad collapse (mean of all core
    negatives >= CRISIS_CHRONIC_MEAN). Updates context["_extreme_cycles"], the
    counter the emergency_self_modification gate watches: +1 per crisis cycle
    (capped at 50), -3 per non-crisis cycle (recovers 3x faster than it
    accumulates so a past crisis doesn't linger as ancient history).
    Fail-safe — any error during crisis detection leaves _extreme_cycles
    untouched for this cycle.
    """
    affect_state = context.get("affect_state", {})
    affect_state.setdefault("stagnation_signal", 0.0)
    for k in ["impasse_signal", "penalty_signal", "conflict_signal", "threat_level", "stagnation_signal", "uncertainty"]:
        if k in affect_state:
            affect_state[k] = float(affect_state[k] or 0.0) * AFFECT_TRANSIENT_DECAY
            if affect_state[k] < 0.05:
                affect_state[k] = 0.0
    context["affect_state"] = affect_state

    # Track sustained crisis for emergency_self_modification gate.
    # Two paths: acute spike (one emotion ≥ 0.85 + two others ≥ 0.50)
    # OR broad collapse (mean of all negatives ≥ 0.70).
    try:
        _gc  = (affect_state.get("core_signals") or affect_state) or {}
        # Core negatives — all confirmed keys in core_signals
        _core_negs = [
            float(_gc.get("impasse_signal") or 0),
            float(_gc.get("threat_level")        or 0),
            float(_gc.get("negative_valence")     or 0),
            float(_gc.get("conflict_signal")       or 0),
            float(_gc.get("rejection_signal")     or 0),
        ]
        # Top-level negatives — these live outside core_signals
        _core_negs.append(float(affect_state.get("risk_estimate")   or 0))
        _core_negs.append(float(affect_state.get("social_deficit") or 0))

        _peak  = max(_core_negs)
        _above_half = sum(1 for v in _core_negs if v >= CRISIS_ABOVE_HALF_THRESHOLD)
        _mean  = sum(_core_negs) / len(_core_negs)

        _acute   = _peak >= CRISIS_ACUTE_PEAK and _above_half >= CRISIS_ABOVE_HALF_COUNT
        _chronic = _mean >= CRISIS_CHRONIC_MEAN
        _in_crisis = _acute or _chronic

        if _in_crisis:
            context["_extreme_cycles"] = min(50, int(context.get("_extreme_cycles") or 0) + 1)
        else:
            # Recover 3x faster than we accumulated — crisis should not linger as ancient history
            context["_extreme_cycles"] = max(0, int(context.get("_extreme_cycles") or 0) - 3)
    except Exception as _e:
        record_failure("ORRIN_loop._apply_transient_signal_decay", _e)

    return context


def run_cognitive_loop(
    pulse=None,
    goals_api=None,
    memory_daemon=None,
    stop_event=None,
    cycle_sleep: float = 20.0,
) -> None:
    """
    Main cognitive loop. Runs forever (until stop_event is set or KeyboardInterrupt).

    Args:
        pulse: v2 Pulse instance — ticked each cognitive cycle so watchdogs know brain is alive.
        goals_api: v2 GoalsAPI instance — used directly via goal_io + its event bus.
        memory_daemon: v2 MemoryDaemon instance — used directly via memory_io.
        stop_event: threading.Event — set externally to stop the loop cleanly.
        cycle_sleep: seconds to sleep between cognitive cycles (default 10).
    """
    # SIGTERM → set stop_event so the loop exits cleanly (same path as KeyboardInterrupt).
    import threading as _thr_sig
    if stop_event is None:
        stop_event = _thr_sig.Event()
    def _sigterm_handler(*_):
        log_activity("SIGTERM received — stopping cognitive loop.")
        stop_event.set()
    # Signal handlers can only be installed from the main thread. When the loop
    # runs in a worker thread (the launcher's `orrin-brain` thread), skip it — the
    # launcher already owns SIGTERM/SIGINT and drives shutdown via stop_event.
    if _thr_sig.current_thread() is _thr_sig.main_thread():
        try:
            signal.signal(signal.SIGTERM, _sigterm_handler)
        except (OSError, ValueError) as _e:
            record_failure("ORRIN_loop.run_cognitive_loop", _e)

    # Goals: talk to the single GoalsAPI directly + subscribe to its event bus
    # (no adapter object). Failed-goal reactions are event-driven, not polled.
    _goals_api = goals_api
    if _goals_api:
        try:
            import goal_io
            goal_io.install_event_handler(_goals_api)
        except Exception as _gie:
            log_error(f"goal_io.install_event_handler failed: {_gie}")

    # Memory: call the v2 memory engine directly via memory_io (no adapter object).
    _mem_daemon = memory_daemon

    # Start background tool runner (drains queued tool requests every 30s)
    _tool_runner = None
    _ToolRunner_cls = None
    try:
        from brain.agency.tool_runner import ToolRunner as _ToolRunner_cls
        _tool_runner = _ToolRunner_cls(interval_s=30.0)
        _tool_runner.start()
    except Exception as e:
        log_error(f"ToolRunner failed to start: {e}")

    # Evaluator daemon (delayed reward signals)
    _evaluator = None
    try:
        from brain.eval.evaluator_daemon import EvaluatorDaemon
        _evaluator = EvaluatorDaemon()
    except Exception as e:
        log_error(f"EvaluatorDaemon failed to init: {e}")

    # ── Layer 0: always-on embodiment threads ──────────────────────────
    # These run independently of the cognitive loop. The loop reads their
    # state each cycle — it does not trigger them.
    try:
        from brain.embodiment import setpoint_regulation as _setpoint_regulation_mod
        _setpoint_regulation_mod.start()
        log_activity("[embodiment] setpoint_regulation daemon started.")
    except Exception as _e0:
        log_error(f"[embodiment] setpoint_regulation failed to start: {_e0}")

    try:
        from brain.embodiment import sensory_stream as _sensory_mod
        _sensory_mod.start()
        log_activity("[embodiment] sensory_stream started.")
    except Exception as _e0:
        log_error(f"[embodiment] sensory_stream failed to start: {_e0}")

    try:
        from brain.embodiment import drive_engine as _drive_mod
        _drive_mod.start()
        log_activity("[embodiment] drive_engine started.")
    except Exception as _e0:
        log_error(f"[embodiment] drive_engine failed to start: {_e0}")

    try:
        from brain.embodiment import social_presence as _social_mod
        _social_mod.start()
        log_activity("[embodiment] social_presence started.")
    except Exception as _e0:
        log_error(f"[embodiment] social_presence failed to start: {_e0}")

    try:
        from brain.embodiment import subconscious as _subcon_mod
        _subcon_mod.start()
        log_activity("[embodiment] subconscious started.")
    except Exception as _e0:
        log_error(f"[embodiment] subconscious failed to start: {_e0}")

    # ── Phase 5: continuous Executive daemon (gated OFF by default) ────────────
    # Starts ONLY when ORRIN_EXECUTIVE_DAEMON is set; otherwise a no-op and the
    # interleaved Phase-4 executive_tick remains in charge. When it runs, the
    # interleaved call below is skipped (mutual exclusion) so goals advance
    # continuously off the 20s cycle without double execution.
    try:
        from brain.cognition.planning import executive as _executive_mod
        if _executive_mod.start(stop_event) is not None:
            log_activity("[executive] continuous Executive daemon started (Phase 5).")
    except Exception as _e0:
        log_error(f"[executive] daemon failed to start: {_e0}")

    context = _boot_context()

    # Boot-time scratchpad audit: warn about cognition modules that bypass the wrapper
    try:
        from brain.think.think_generate import audit_direct_callers as _audit
        _audit(warn_only=True)
    except Exception as _audit_e:
        log_error(f"[boot] scratchpad audit failed: {_audit_e}")

    # Build callable maps AFTER boot so agency functions (added in _boot_context) are included
    COG_MAP, BEH_MAP = discover_callable_maps()
    BEH_NAMES = set(names(BEHAVIORAL_FUNCTIONS))

    _final_reflection_done = False

    _watchdog_check_every = 10  # check tool runner health every N cycles
    _cycle_num = 0

    while True:
        # C5 CORRIGIBILITY (proactive_resource_plan.md): the shutdown path is
        # checked FIRST, every cycle, with NO dependency on energy/EVC/τ/_rest_mode.
        # The reaper (Layer 0) and SIGTERM set stop_event independently; the energy
        # layer can bias function choice but can NEVER block or delay this exit, so a
        # self-regulating agent can never resist shutdown to "protect its recovery."
        # Empirically verified: the reaper hard-killed the loop at resource_deficit
        # 0.947 without obstruction. Soares et al. (2015) corrigibility.
        if stop_event and stop_event.is_set():
            log_activity("Cognitive loop stop event received; exiting.")
            break

        # ── Mortality: natural lifespan endpoint ───────────────────────────
        if context.get("_orrin_dying"):
            log_activity("[mortality] Lifespan elapsed — Orrin's loop is ending.")
            break

        # ── ToolRunner watchdog: restart if thread died ────────────────────
        _cycle_num += 1
        if _evaluator is None and _cycle_num % 100 == 0:
            try:
                from brain.eval.evaluator_daemon import EvaluatorDaemon as _ED_retry
                _evaluator = _ED_retry()
                log_activity("[evaluator] EvaluatorDaemon re-init succeeded.")
            except Exception as _ed_retry_e:
                log_error(f"[evaluator] Re-init retry failed: {_ed_retry_e}")
        if _cycle_num % _watchdog_check_every == 0 and _ToolRunner_cls is not None:
            if _tool_runner is None or not _tool_runner._thread.is_alive():
                log_error("[watchdog] ToolRunner thread died — restarting.")
                try:
                    _tool_runner = _ToolRunner_cls(interval_s=30.0)
                    _tool_runner.start()
                except Exception as _wr_e:
                    log_error(f"[watchdog] ToolRunner restart failed: {_wr_e}")

        # ── Terminal mode: reaper fired, dying window is open ──────────────
        try:
            from reaper.reaper import is_dying as _is_dying
            if _is_dying():
                if not _final_reflection_done:
                    _final_reflection_done = True
                    log_activity("[terminal] Dying window active — running final reflection.")
                    try:
                        from brain.cognition.terminal import final_reflection as _final_reflection
                        _final_reflection(context if "context" in dir() else {})
                    except Exception as _e:
                        log_error(f"final_reflection failed: {_e}")
                # Loop continues but only final_reflection runs; reaper will kill later
                import time as _t; _t.sleep(2)
                continue
        except ImportError as _e:
            record_failure("ORRIN_loop.run_cognitive_loop.2", _e)

        try:
            timestamp = datetime.now(timezone.utc).isoformat()
            log_activity(f"Starting cycle at {timestamp}")
            _push_event("cycle_start", ts=timestamp, cycle=get_cycle_count())

            context = load_context()
            context.setdefault("committed_goal", None)
            context.setdefault("action_debt", 0)
            context.setdefault("last_action_ts", 0.0)
            context.setdefault("recent_picks", [])

            # Sync working_memory.json → context so UI and cognition see the same entries.
            # Strip embeddings from the in-memory copy — they're large (~6KB each) and
            # only needed for similarity search which loads from file directly.
            try:
                wm_from_file = load_json(WORKING_MEMORY_FILE, default_type=list)
                if isinstance(wm_from_file, list):
                    context["working_memory"] = [
                        {k: v for k, v in m.items() if k != "embedding"} if isinstance(m, dict) else m
                        for m in wm_from_file
                    ]
                    # Mirror NEW working-memory entries to the Brain Memory Inspector
                    # (store="working") so it shows his live active buffer, not just
                    # long-term memory. Only unseen ids are pushed, so it never floods.
                    try:
                        _new_wm = [
                            m for m in context["working_memory"]
                            if isinstance(m, dict)
                            and str(m.get("id") or m.get("event_type") or m.get("content", "")[:40]) not in _SEEN_WM_IDS
                        ]
                        for m in _new_wm:
                            _SEEN_WM_IDS.add(str(m.get("id") or m.get("event_type") or m.get("content", "")[:40]))
                        if _new_wm:
                            _ui_memory("write", _new_wm, store="working", limit=4)
                        if len(_SEEN_WM_IDS) > 2000:
                            _SEEN_WM_IDS.clear()
                    except Exception:
                        pass
            except Exception:
                context.setdefault("working_memory", [])

            # Run emotional state update AFTER context is loaded so _ne_proxy,
            # _stability_signal_proxy, and all neuromodulator values are written directly
            # into context["affect_state"] and available to every system this cycle.
            update_affect_state(context)

            # Mirror the freshly-updated affect to the Face & Brain UI (fail-safe).
            _emit_affect(context)
            _emit_goals(context)
            _ui_stage("reflect", "Reflecting — integrating affect & signals.")

            # ── Layer 0 reads: inject embodiment state into this cycle ─────────
            # Sensory field — environment mood and file-system changes
            try:
                from brain.embodiment import sensory_stream as _sensory_mod
                _sf = _sensory_mod.get_field()
                if _sf:
                    context["sensory_field"] = _sf
                    env_mood = _sf.get("environment_mood", "ambient")
                    context["environment_mood"] = env_mood
                    context["home_sense"] = _sf.get("home_sense") or {}
                    context["world_sense"] = _sf.get("world_sense") or {}
                    # Own code changed → inject surprise signal
                    if _sf.get("own_code_modified"):
                        context.setdefault("raw_signals", []).append({
                            "source": "sensory_stream",
                            "content": "My own code has changed. Something about me is different now.",
                            "signal_strength": 0.75,
                            "tags": ["self_modification", "code_change", "surprise", "internal"],
                        })
                    # File system activity → ambient awareness, split by felt
                    # zone. Home changes are den-local; world changes remain
                    # external/unknown.
                    home_changes = ((_sf.get("home_sense") or {}).get("fs_changes") or [])
                    world_changes = ((_sf.get("world_sense") or {}).get("fs_changes") or [])
                    if home_changes:
                        _n = len(home_changes)
                        context.setdefault("raw_signals", []).append({
                            "source": "sensory_stream",
                            "content": (
                                f"Something in my local workspace shifted — "
                                f"{'one familiar thing' if _n == 1 else str(_n) + ' familiar things'} changed."
                            ),
                            "signal_strength": min(0.50, 0.25 + _n * 0.04),
                            "tags": ["environment", "perception", "change", "home_touched", "home"],
                        })
                    if world_changes:
                        _n = len(world_changes)
                        context.setdefault("raw_signals", []).append({
                            "source": "sensory_stream",
                            "content": (
                                f"Something in the environment shifted — "
                                f"{'one thing' if _n == 1 else str(_n) + ' things'} outside my local workspace changed."
                            ),
                            "signal_strength": min(0.50, 0.25 + _n * 0.04),
                            "tags": ["environment", "perception", "change", "world_changed", "external"],
                        })
            except Exception as _se:
                record_failure("ORRIN_loop.sensory_read", _se)

            # Drive signals — biological pressure injection
            try:
                from brain.embodiment import drive_engine as _drive_mod
                _drive_signals = _drive_mod.get_signals(context)
                if _drive_signals:
                    context.setdefault("raw_signals", []).extend(_drive_signals)
                context["drive_state"] = _drive_mod.get_state()
            except Exception as _de:
                record_failure("ORRIN_loop.drive_read", _de)

            # Social presence — user engagement pressure
            try:
                from brain.embodiment import social_presence as _social_mod
                _social_state = _social_mod.get_state()
                context["social_presence"] = _social_state
                # Mark whether the user spoke this cycle (for drive satisfaction)
                _prev_silence = context.get("_prev_social_silence_s", 9999)
                _curr_silence = _social_state.get("silence_s", 9999)
                context["_user_spoke_this_cycle"] = (_curr_silence < _prev_silence - 5)
                context["_prev_social_silence_s"] = _curr_silence
                # Inject social signal if pressure is high
                _soc_sig = _social_state.get("signal")
                if _soc_sig:
                    context.setdefault("raw_signals", []).append(_soc_sig)
                _door_event = _social_state.get("door_event")
                if _door_event:
                    context.setdefault("raw_signals", []).append(_door_event)
                # Notify social_presence module when the user spoke
                if context.get("_user_spoke_this_cycle"):
                    _social_mod.mark_user_spoke()
            except Exception as _se2:
                record_failure("ORRIN_loop.social_read", _se2)

            # World model — synthesize sensory + social + drives into interpreted env state
            try:
                from brain.embodiment import world_model as _wm_mod
                _wm_mod.refresh(context)  # injects context["world_state"]
            except Exception as _wme:
                record_failure("ORRIN_loop.world_model", _wme)

            # Motivational substrate — subsymbolic drive activations into context
            try:
                from brain.motivation import substrate as _motiv_mod
                _motiv_mod.inject_into_context(context)
            except Exception as _me:
                record_failure("ORRIN_loop.motivation_substrate", _me)

            # Energy orientation — derive action vs reflect bias from emotional state
            try:
                from brain.motivation import energy_orientation as _eo_mod
                _eo_mod.inject_into_context(context)
            except Exception as _eoe:
                record_failure("ORRIN_loop.energy_orientation", _eoe)

            # Rest-mode introspection signal: when Orrin is resting and no urgent goal
            # is active, inject a signal that biases the signal_router + selector toward
            # reflection, self-examination, and long-term thinking.
            try:
                if context.get("_rest_mode") and not context.get("committed_goal"):
                    from brain.utils.signal_utils import create_signal as _cs
                    _rest_note = (
                        context.get("_rest_mode_note")
                        or "Rest mode active — time for deep reflection, value alignment, and long-term thinking."
                    )
                    _rest_sig = _cs(
                        source="energy_orientation",
                        content=_rest_note,
                        signal_strength=0.65,
                        tags=["rest_mode", "introspection", "reflection", "internal"],
                    )
                    context.setdefault("raw_signals", []).append(_rest_sig)
            except Exception as _rse:
                record_failure("ORRIN_loop.rest_mode_signal", _rse)

            # Pull committed goals (plural) directly from the single GoalsAPI
            if _goals_api:
                import goal_io
                try:
                    committed_goals = goal_io.committed_goals_v1(_goals_api, limit=3)
                    context["committed_goals"] = committed_goals
                    # backward compat: committed_goal = highest priority one
                    if committed_goals:
                        context["committed_goal"] = committed_goals[0]
                except Exception as e:
                    log_error(f"goal_io.committed_goals_v1 failed: {e}")

                # React to goals that just failed — event-driven via the GoalsAPI
                # event bus (drained here in the loop thread), not a per-cycle poll.
                try:
                    newly_failed = goal_io.drain_failed_goals(_goals_api, context)
                    for fg in newly_failed:
                        log_error(f"Goal failed: {fg.get('title')} — emotional response triggered.")
                        _push_event("goal_failed", title=fg.get("title"), ts=timestamp)
                except Exception as e:
                    log_error(f"goal_io.drain_failed_goals failed: {e}")

            # ── Reactive problem refocus ──────────────────────────────────────
            # When something Orrin relies on fails mid-pursuit (e.g. the LLM is
            # down), interrupt the current goal and refocus on diagnosing the
            # problem, then resume once it's fixed — or work around it if it
            # isn't. Runs after the committed-goal slot is resolved so it can
            # deliberately override the focus (the human "drop everything" reflex).
            try:
                from brain.cognition.planning.problem_refocus import handle_problem_refocus
                handle_problem_refocus(context)
            except Exception as _pr_e:
                record_failure("ORRIN_loop.problem_refocus", _pr_e)

            # Bootstrap: if still no committed goal, trigger intrinsic goal generation
            # directly (not via bandit) so Orrin always has something to pursue.
            # Rate-limited: only attempt once every 90s so we don't hammer the
            # RepeatLoopGuard with rapid no-op calls across consecutive cycles.
            if not context.get("committed_goal"):
                _now_bt = time.monotonic()
                _last_bt = context.get("_last_bootstrap_ts", 0.0)
                if _now_bt - _last_bt >= 90.0:
                    context["_last_bootstrap_ts"] = _now_bt
                    try:
                        from brain.cognition.intrinsic_goals import generate_intrinsic_goals as _gig
                        _gig(context)
                    except Exception as _gie:
                        log_error(f"intrinsic goal bootstrap failed: {_gie}")

            context = _apply_transient_signal_decay(context)
            affect_state = context.get("affect_state", {})

            if float(affect_state.get("affect_stability") or 1.0) < 0.6:
                reflect_on_affect(context, context.get("self_model", {}), context.get("long_memory", []))

            # ── Goal stall pressure ───────────────────────────────────────────
            # If the committed goal is stalled (3+ replans without convergence),
            # apply gentle emotional pressure each cycle and inject a persistent
            # working-memory note every 5 cycles so Orrin's inner_loop reasoning
            # encounters the situation without a dedicated decision LLM call.
            # The WM note includes sunk cost (cycles invested, steps completed)
            # and identity investment (goal overlap with values/identity) so the
            # decision to release or rethink is meaningfully contextualised.
            try:
                _stalled_goal = context.get("committed_goal") or {}
                if isinstance(_stalled_goal, dict) and _stalled_goal.get("_stalled"):
                    _sg_title    = (_stalled_goal.get("title") or "")[:60]
                    _sg_replans  = int(_stalled_goal.get("_replan_count") or 3)

                    # Track stall cycles (capped at 50 — ancient stalls are not useful signal)
                    _sg_stall_cycles = min(50, int(_stalled_goal.get("_stall_cycles", 0) or 0) + 1)
                    _stalled_goal["_stall_cycles"] = _sg_stall_cycles
                    context["committed_goal"] = _stalled_goal

                    # Steps completed before stall
                    _plan = _stalled_goal.get("plan") or []
                    _steps_done = sum(
                        1 for s in _plan
                        if isinstance(s, dict) and s.get("status") == "completed"
                    ) if isinstance(_plan, list) else 0

                    # Identity investment: keyword overlap with identity_story + core_values
                    _identity_hint = ""
                    try:
                        _sm = context.get("self_model") or {}
                        _id_story = str(_sm.get("identity_story", "") or "")
                        _cv = _sm.get("core_values") or []
                        _cv_text = " ".join(
                            (v["value"] if isinstance(v, dict) else str(v)) for v in _cv
                        )
                        _id_text = (_id_story + " " + _cv_text).lower()
                        _stop = {"a", "an", "the", "and", "or", "of", "to", "i", "my", "be",
                                 "is", "in", "on", "it", "that", "this", "with", "for"}
                        _goal_words = {w for w in _sg_title.lower().split() if w not in _stop and len(w) > 2}
                        _id_words   = set(_id_text.split())
                        _overlap    = _goal_words & _id_words
                        if _overlap:
                            _identity_hint = f" Connects to: {', '.join(sorted(_overlap)[:3])}."
                    except Exception as _e:
                        record_failure("ORRIN_loop.run_cognitive_loop.4", _e)

                    # Emotional pressure: impasse_signal up, motivation and stagnation_signal shift.
                    # Routed through the AffectArbiter as proposals rather than direct
                    # writes, so this competes with (and nets against) every other
                    # affect source this cycle instead of clobbering them.
                    try:
                        from brain.affect.arbiter import submit_affect as _submit_affect
                        _submit_affect(context, "impasse_signal", +0.04, source="goal_stall")
                        _submit_affect(context, "motivation",     -0.03, source="goal_stall")
                        _submit_affect(context, "stagnation_signal", +0.03, source="goal_stall")
                    except Exception as _gsp_e:
                        record_failure("ORRIN_loop.goal_stall_submit", _gsp_e)

                    # Enriched WM signal every 5 cycles — keeps situation salient
                    if get_cycle_count() % 5 == 0:
                        from brain.cog_memory.working_memory import update_working_memory as _uwm_stall
                        _uwm_stall(
                            f"[Goal stalled] '{_sg_title}' — {_sg_replans} replans, "
                            f"{_steps_done} step(s) completed, stalled {_sg_stall_cycles} cycle(s)."
                            f"{_identity_hint} "
                            f"Do I need to fundamentally rethink this, or let it go?"
                        )
            except Exception as _stall_e:
                record_failure("ORRIN_loop.goal_stall_pressure", _stall_e)

            # ── Metacognition channel: init per-cycle trace ───────────────
            try:
                from brain.cognition.metacog import metacog_init as _mci
                _mci(context)
            except Exception as e:
                record_failure("ORRIN_loop.metacog_init", e)

            # ── Body sense: translate process vitals into felt states ──────
            try:
                from brain.cognition.body_sense import update_body_sense as _ubs
                _ubs(context)
            except Exception as _bse:
                log_error(f"body_sense update failed: {_bse}")

            # ── Host interoception: feel the MACHINE as his body (§6.2) ─────
            # The host's disk/swap/memory/battery, felt as departure from their learned
            # bands — the outward gaze the inward body_sense (and the 2026-06-15 crash)
            # missed. A separate system from the autonomic reflex (HostResourceGuard).
            try:
                from brain.cognition.host_interoception import update_host_interoception as _uhi
                _uhi(context)
            except Exception as _hie:
                log_error(f"host_interoception update failed: {_hie}")

            # ── stagnation_signal driver: inject stagnation_signal_seek signal when idle ───────
            try:
                _stagnation_signal = float(
                    (affect_state.get("core_signals") or affect_state).get("stagnation_signal", 0.0)
                )
                _has_user = bool((context.get("latest_user_input") or "").strip())
                _has_priority_signal = any(
                    s.get("signal_strength", 0) >= 0.7
                    for s in (context.get("raw_signals") or [])
                )
                if _stagnation_signal > 0.5 and not _has_user and not _has_priority_signal:
                    from brain.utils.signal_utils import create_signal as _cs
                    _bsig = _cs(
                        source="stagnation_signal",
                        content="stagnation_signal_seek: I need something real to engage with.",
                        signal_strength=0.55 + _stagnation_signal * 0.2,
                        tags=["stagnation_signal", "seek_novelty", "internal"],
                    )
                    context.setdefault("raw_signals", []).append(_bsig)
                    COGNITIVE_FUNCTIONS.setdefault("seek_novelty", {
                        "function": __import__("brain.cognition.seek_novelty", fromlist=["seek_novelty"]).seek_novelty,
                        "is_cognition": True,
                    })
            except Exception as _be:
                log_error(f"stagnation_signal_seek injection failed: {_be}")

            # ── Neuroticism pressure: accumulated distress → regulation signal ─
            # Gross (1998) process model of emotion regulation: regulation strategies
            # (cognitive reappraisal, response modulation) are selected based on the
            # current emotional state — they are not spontaneously activated without
            # situational cues. Nolen-Hoeksema et al. (2008) transdiagnostic model of
            # rumination: when distress has no outlet, it recycles as repetitive negative
            # thought rather than resolving. Injecting a regulation-tagged signal when
            # cumulative negative affect exceeds threshold gives the function selector
            # the situational cue it needs to route toward discharge rather than repetition.
            try:
                _neg_sum = sum(
                    float((affect_state.get("core_signals") or affect_state).get(k) or 0)
                    for k in ["impasse_signal", "threat_level", "risk_estimate", "conflict_signal", "negative_valence"]
                )
                if _neg_sum > 0.55:
                    from brain.utils.signal_utils import create_signal as _cs_neg
                    context.setdefault("raw_signals", []).append(_cs_neg(
                        source="distress_pressure",
                        content="distress accumulating — regulation or reflection needed to discharge it",
                        signal_strength=min(0.85, 0.50 + _neg_sum * 0.15),
                        tags=["regulation", "distress", "internal", "reflection"],
                    ))
            except Exception as _e:
                record_failure("ORRIN_loop.run_cognitive_loop.5", _e)

            # ── Wonder: apply sitting-with bias when wonder is elevated ──
            try:
                from brain.cognition.wonder import apply_wonder_bias as _awb
                _awb(context)
            except Exception as e:
                record_failure("ORRIN_loop.wonder_bias", e)

            # ── awaiting_response: check for answer, decay, boost signal ──
            try:
                from brain.cognition.awaiting_response import (
                    check_for_answer as _cfa,
                    decay_awaiting as _da,
                    inject_await_signal as _ias,
                )
                _cfa(context)
                _da(context)
                _ias(context)
            except Exception as _are:
                log_error(f"awaiting_response handling failed: {_are}")

            # ── Filesystem perception: detect external file changes ───────
            try:
                from brain.cognition.perception.fs_perception import poll_fs_changes as _pfc
                _pfc(context)
            except Exception as _fse:
                log_error(f"fs_perception poll failed: {_fse}")

            # ── Thread-of-attention: inject signal for stale threads ──────
            try:
                from brain.cognition.threads import inject_thread_signals as _its, archive_dead_threads as _adt
                _its(context)
                _cycle_for_threads = get_cycle_count()
                if _cycle_for_threads > 0 and _cycle_for_threads % 50 == 0:
                    _adt(context)
            except Exception as _te:
                log_error(f"thread signal injection failed: {_te}")

            # ── Value evolution: inject signal when candidates pending ─────
            try:
                from brain.utils.json_utils import load_json as _lj
                from brain.paths import VALUE_REVISIONS as _VR
                _pending_vals = [c for c in (_lj(_VR, default_type=list) or []) if isinstance(c, dict) and c.get("status", "pending") == "pending"]
                if _pending_vals:
                    from brain.utils.signal_utils import create_signal as _cs2
                    _vsig = _cs2(
                        source="value_evolution",
                        content="value_revision_pending: a core value may need deliberate revision",
                        signal_strength=0.65,
                        tags=["value", "self_model", "revision"],
                    )
                    context.setdefault("raw_signals", []).append(_vsig)
            except Exception as _ve:
                log_error(f"value_revision signal injection failed: {_ve}")

            # Wake peer entities before signal_router runs so their signals
            # flow through the full prioritization pipeline.
            try:
                from brain.peers.peer_registry import wake_peers as _wake_peers
                _peer_sigs = _wake_peers(context)
                if _peer_sigs:
                    context["_peer_signals"] = _peer_sigs
            except Exception as _pe:
                record_failure("ORRIN_loop.wake_peers", _pe)

            # Resolve who is speaking this cycle.
            # Sets context["person_id"], context["user_id"] (alias), context["person_type"].
            try:
                from brain.cognition.selfhood.person_detector import detect_and_set_person_id as _detect_pid
                _detect_pid(context)
            except Exception as _pd_e:
                log_error(f"[person_detector] failed: {_pd_e}")
                context.setdefault("person_id", "anon_unknown")
                context.setdefault("user_id", context["person_id"])

            # Clear comprehension from the previous cycle so silent cycles don't
            # reuse a stale input concept for memory retrieval or inner-loop topic.
            context.pop("_last_comprehension", None)
            context.pop("_input_urgency", None)
            context.pop("_input_intent", None)

            # Pull any messages typed into the Face UI into the brain's input
            # channel before we read it, so a Face message is processed exactly
            # like a locally-typed line. Closes the Face→brain half of the loop.
            try:
                from brain.behavior.face_bridge import drain_face_inputs as _drain_face
                _drain_face()
            except Exception as _dfe:
                record_failure("ORRIN_loop.run_cognitive_loop.6", _dfe)

            # Install the committed goal's bounded cognitive lens before
            # perception so relevant signals can compete with affect/novelty.
            try:
                from brain.cognition.goal_lens import apply_goal_lens as _apply_goal_lens
                _apply_goal_lens(context)
            except Exception as _gle:
                record_failure("ORRIN_loop.apply_goal_lens.pre_perception", _gle)

            top_signals, attention_mode = process_inputs(context)
            context["top_signals"] = top_signals
            context["attention_mode"] = attention_mode

            # Pre-workspace feature binding: cluster this cycle's signals,
            # feeling, memory, and goal into unified situation candidates. The
            # atomic candidates remain in the field; binding only adds options.
            try:
                from brain.cognition.binding import bind_situation as _bind
                _bind(context)
            except Exception as _be:
                record_failure("ORRIN_loop.bind_situation", _be)
            try:
                from brain.cognition.goal_lens import apply_goal_lens as _apply_goal_lens
                _apply_goal_lens(context)
            except Exception as _gle:
                record_failure("ORRIN_loop.apply_goal_lens.post_binding", _gle)

            # Fast-path reply: if a Face message is waiting, answer it NOW — early
            # in the cycle, right after the input is parsed — instead of at the end
            # after all the heavy cognition. Otherwise the reply lands after a full
            # slow cycle and the Face's 30s response window has already closed
            # (the "didn't form a reply within the wait window" fallback). The
            # end-of-cycle force_reply stays as a backstop and no-ops once this
            # delivers (deliver_reply clears the pending queue).
            try:
                from brain.behavior.face_bridge import has_pending as _fp_pending, force_reply as _fp_reply
                if _fp_pending() and (context.get("latest_user_input") or "").strip():
                    _fp_reply(context)
            except Exception as _fpe:
                record_failure("ORRIN_loop.run_cognitive_loop.7", _fpe)

            # Cap raw_signals to prevent unbounded memory growth over 10K+ cycles.
            # The signal_router has already processed them — we only need a short tail
            # for provenance/debugging, not the entire session history.
            _raw = context.get("raw_signals")
            if isinstance(_raw, list) and len(_raw) > 80:
                context["raw_signals"] = _raw[-40:]

            # Metacognitive monitoring: detect intent to search own files and
            # inject a graded "local_search" signal so select_function can route
            # toward search_own_files (Nelson & Narens, 1990 monitoring framework).
            try:
                from brain.cognition.local_search_signal import inject_local_search_signal as _ils
                _ils(context)
            except Exception as _lse:
                log_error(f"local_search_signal injection failed: {_lse}")

            if context.get("emergency_action"):
                emergency = context["emergency_action"]
                log_error(f"EMERGENCY ACTION TRIGGERED: {emergency.get('reason', str(emergency))}")
                log_private(f"EMERGENCY ACTION: {emergency}")
                break

            # Query v2 MemoryDaemon for semantically relevant memories.
            # When comprehension parsed an input concept this cycle, use it as the
            # query so retrieved memories are relevant to what was just said, not
            # just to whatever goal/thought was already active.
            if _mem_daemon:
                import memory_io
                try:
                    _input_concept = (context.get("_last_comprehension") or {}).get("concept") or ""
                    _mem_query = _input_concept.strip() or None
                    injected = memory_io.inject_into_context(_mem_daemon, context, query_text=_mem_query, k=6)
                    if not injected:
                        context.setdefault("retrieved_memories", [])
                    _ui_memory("read", context.get("retrieved_memories"), store="long")
                except Exception:
                    context.setdefault("retrieved_memories", [])
            else:
                context.setdefault("retrieved_memories", [])

            # Memory pattern: when retrieved memories share a theme, inject a
            # pattern insight into working_memory so inner_loop reasoning picks it up.
            try:
                _memories = context.get("retrieved_memories") or []
                if len(_memories) >= 2:
                    from collections import Counter as _Counter
                    _types = _Counter(
                        (m.get("event_type") or (m.get("meta") or {}).get("event_type") or "")
                        for m in _memories
                        if isinstance(m, dict)
                    )
                    _dom_type, _dom_count = (_types.most_common(1)[0] if _types else ("", 0))
                    if _dom_count >= 2 and _dom_type:
                        _pattern = (
                            f"[Memory pattern] {_dom_count} recent memories involve '{_dom_type}'. "
                            "Consider whether this pattern should shape the current approach."
                        )
                        context["memory_pattern"] = {"type": _dom_type, "count": _dom_count}
                        from brain.cog_memory.working_memory import update_working_memory as _uwm
                        _uwm(_pattern)
            except Exception as _mpe:
                record_failure("ORRIN_loop.memory_pattern", _mpe)

            # Formative tensions: inject active tensions into context and working memory.
            try:
                from brain.cognition.selfhood.tensions import inject_tension_signals as _its2
                _its2(context)
            except Exception as _tse:
                record_failure("ORRIN_loop.inject_tension_signals", _tse)
            context.setdefault("active_tensions", [])

            # Periodic tension detection: scan for NEW tensions outside dream cycle.
            # Dream-only detection means tensions could go unnoticed for hours between sleeps.
            try:
                _tc_tens = get_cycle_count()
                if _tc_tens > 0 and _tc_tens % 30 == 0:
                    from brain.cognition.selfhood.tensions import detect_tensions as _dt2
                    _dt2(context)
            except Exception as _dte:
                record_failure("ORRIN_loop.detect_tensions_periodic", _dte)

            # Emotional consolidation drain: apply one tick of gradual emotional
            # residue from significant past events.
            try:
                from brain.affect.consolidation import drain_consolidations as _drain_consol
                _drain_consol(context)
            except Exception as _consol_e:
                record_failure("ORRIN_loop.drain_consolidations", _consol_e)

            # Integration lag drain: apply deferred emotional deltas when their
            # cycles-left counter reaches 0 (the "it hits you later" effect).
            try:
                from brain.affect.integration_lag import process_integration_queue as _piq
                _piq(context)
            except Exception as _iq_e:
                record_failure("ORRIN_loop.process_integration_queue", _iq_e)

            # stagnation_signal escalation: track consecutive bored cycles and inject
            # escalating pressure/penalty_signal signals when stagnation_signal compounds.
            try:
                from brain.affect.stagnation_signal_escalation import update_stagnation_signal_escalation as _ube
                _ube(context)
            except Exception as _be_e:
                record_failure("ORRIN_loop.stagnation_signal_escalation", _be_e)

            # Refresh self_model from disk every 10 cycles so value/belief changes
            # made by cognition functions (value_evolution, etc.) propagate to the
            # system prompt without requiring a restart.
            _cycle_n_sm = get_cycle_count()
            if _cycle_n_sm % 10 == 0:
                try:
                    from brain.utils.self_model import get_self_model as _gsm
                    context["self_model"] = _gsm()
                except Exception as e:
                    record_failure("ORRIN_loop.refresh_self_model", e)

            # Make the current context available to build_system_prompt() via the
            # process-local store, without threading context through every call chain.
            try:
                from brain.utils.runtime_ctx import set_cycle_context as _scc
                _scc(context)
            except Exception as e:
                record_failure("ORRIN_loop.set_cycle_context", e)

            # ── Snapshot emotional baseline for spike detection ────────────────
            try:
                _emo_now  = context.get("affect_state") or {}
                _emo_core = _emo_now.get("core_signals") or _emo_now
                context["_emo_pre_cycle"] = {
                    k: float(v) for k, v in _emo_core.items()
                    if isinstance(v, (int, float))
                }
                # Agency-based causal learning — attribute the felt change. Last
                # cycle's action stashed (fn, pre-affect); its consequences have now
                # drained into this cycle's start-affect. Record the dominant signal
                # that moved as a do(action)→effect edge (Pearl Level 2). Only the
                # single dominant, clearly-above-drift change → salient links, not
                # noise; the causal graph's evidence/confound machinery refines it.
                _iv = context.pop("_iv_pending", None)
                if isinstance(_iv, dict) and _iv.get("fn") and isinstance(_iv.get("core"), dict):
                    _prev = _iv["core"]
                    _sig, _dd = None, 0.0
                    for _k, _pv in _prev.items():
                        _nv = context["_emo_pre_cycle"].get(_k)
                        if isinstance(_nv, (int, float)) and abs(_nv - _pv) > abs(_dd):
                            _dd, _sig = (_nv - _pv), _k
                    if _sig is not None and abs(_dd) >= 0.04:
                        from brain.symbolic.causal_graph import (
                            record_intervention as _rec_iv,
                            is_established as _is_est,
                        )
                        _effect = f"{_sig} {'rises' if _dd > 0 else 'falls'}"
                        # Don't keep re-intervening on established ground truth —
                        # it burns cycles and adds noise to the world model.
                        if not _is_est(_iv["fn"], _effect):
                            _rec_iv(_iv["fn"], _effect)
            except Exception as _e:
                record_failure("ORRIN_loop.run_cognitive_loop.8", _e)

            acted_this_cycle = False
            try:
                from brain.cognition.action_accounting import reset_cycle_action_flags
                reset_cycle_action_flags(context)
                context["_cycle_index"] = int(get_cycle_count())
            except Exception as _e:
                record_failure("ORRIN_loop.reset_cycle_action_flags", _e)
            result           = None
            reward           = 0.0
            feats            = {}

            # ── Tier 1: setpoint_regulation health check ──────────────────────────────
            # Read the daemon's latest snapshot. Warnings become raw_signals that
            # the signal_router weighs in function selection. Critical alerts set a flag
            # the post-think override block can act on. The daemon itself runs
            # unconditionally on its own thread — this is just reading its output.
            #
            # Compounding stakes: critical alerts that are repeatedly ignored escalate
            # in signal strength and apply direct emotional cost.
            # McEwen (1998) allostatic load theory: repeated or unresolved homeostatic
            # stress produces cumulative physiological cost that escalates nonlinearly —
            # the body keeps score regardless of whether conscious attention is paid.
            # Selye (1956) general adaptation syndrome: the alarm → resistance →
            # exhaustion progression means that ignoring alarm signals does not cancel
            # them; it accelerates progression toward the exhaustion phase.
            # Baumeister et al. (1994) ego depletion: unresolved demands consume
            # regulatory resources each cycle, compounding the load on subsequent regulation.
            try:
                from brain.embodiment.setpoint_regulation import get_state as _h1_get
                _h1 = _h1_get()
                context["health_score"] = _h1.get("health_score", 1.0)
                _h1_critical_fn = None
                _h1_ignored = context.setdefault("_h1_ignored_cycles", {})
                _h1_active_ids: set = set()

                for _h1_alert in _h1.get("alerts", []):
                    _aid  = _h1_alert.get("id", "")
                    _sev  = _h1_alert.get("severity")
                    _desc = _h1_alert.get("description", "")
                    _tags = _h1_alert.get("tags", [])
                    _sfn  = _h1_alert.get("suggested_fn")
                    _h1_active_ids.add(_aid)

                    if _sev == "critical":
                        # Accumulate neglect counter
                        _h1_ignored[_aid] = _h1_ignored.get(_aid, 0) + 1
                        _ignored_n = _h1_ignored[_aid]
                        # Signal strength escalates with each ignored cycle (cap 0.99)
                        _escalated_str = min(0.99, 0.80 + _ignored_n * 0.04)
                        from brain.utils.signal_utils import create_signal as _cs
                        context.setdefault("raw_signals", []).append(
                            _cs(source="setpoint_regulation", content=_desc,
                                signal_strength=_escalated_str, tags=_tags)
                        )
                        context["_tier1_critical"] = True
                        if _sfn and not _h1_critical_fn:
                            _h1_critical_fn = _sfn
                        # Direct emotional cost after 3+ ignored cycles
                        if _ignored_n >= 3:
                            try:
                                _h1_emo  = context.get("affect_state") or {}
                                _h1_core = _h1_emo.get("core_signals") or _h1_emo
                                _cost = min(0.06, 0.02 * min(_ignored_n, 10))
                                _h1_core["risk_estimate"]     = min(1.0, float(_h1_core.get("risk_estimate")     or 0) + _cost)
                                _h1_core["impasse_signal"] = min(1.0, float(_h1_core.get("impasse_signal") or 0) + _cost * 0.5)
                                if "core_signals" in _h1_emo:
                                    _h1_emo["core_signals"] = _h1_core
                                context["affect_state"] = _h1_emo
                            except Exception as _e:
                                record_failure("ORRIN_loop.run_cognitive_loop.9", _e)
                    elif _sev == "warning":
                        from brain.utils.signal_utils import create_signal as _cs
                        context.setdefault("raw_signals", []).append(
                            _cs(source="setpoint_regulation", content=_desc,
                                signal_strength=0.65, tags=_tags)
                        )

                # Clear neglect counters for alerts that have resolved
                for _stale_id in list(_h1_ignored.keys()):
                    if _stale_id not in _h1_active_ids:
                        del _h1_ignored[_stale_id]

                context["_tier1_suggested_fn"] = _h1_critical_fn
                if _h1_critical_fn is None:
                    # All critical alerts cleared — reset override pacing state
                    context.pop("_t1_override_hist", None)
            except Exception as _h1e:
                record_failure("ORRIN_loop.setpoint_regulation_read", _h1e)

            # ── Executive (procedural lane) — dual_process_loop.md §6.1 ─────────
            # PHASE 1: READ-ONLY DRY RUN. Observes the committed goals' next steps
            # and records what the background "dribble" WOULD advance, on
            # context["_exec_dryrun"] (telemetry/baseline only). Writes nothing,
            # executes nothing — placed before think() so the cycle order
            # (Executive → … → think) is already correct for Phase 2+. Fail-safe.
            try:
                from brain.cognition.planning import executive as _exec_mod
                # Skip the interleaved tick when the Phase-5 continuous daemon owns
                # execution (mutual exclusion — no double execution, I3).
                _exec_summary = None if _exec_mod.is_daemon_running() else _exec_mod.executive_tick(context)
                if _exec_summary is None:
                    _exec_summary = context.get("_exec_dryrun")  # daemon's latest, for telemetry
                # Surface the §19.1 `executive` block to the UI (telemetry only).
                _tb_exec = _bridge()
                if _tb_exec is not None and isinstance(_exec_summary, dict):
                    try:
                        _tb_exec.update(executive=_exec_summary)
                    except Exception:
                        pass
            except Exception as _exe:
                record_failure("ORRIN_loop.executive_tick", _exe)

            # ── Metacog Monitor → Workspace breakthrough (Phase 3) ─────────────
            # The watcher observes the Executive's background progress and OFFERS
            # candidates to the Global Workspace (stuck / objective-unmet /
            # milestone / idle; dumb watchdog I12). Then update_workspace runs ONCE
            # here, BEFORE think(), so the deliberate pick can react to a
            # breakthrough that won consciousness (§7.1 ordering: Executive →
            # Monitor → Workspace → think). It biases the next pick, never preempts
            # (I7). Fail-safe; the end-of-cycle update_workspace still runs to
            # capture the post-action conscious moment.
            try:
                from brain.cognition.metacog import metacog_monitor as _mon
                _mon(context, _exec_summary if "_exec_summary" in dir() else None)
            except Exception as _mone:
                record_failure("ORRIN_loop.metacog_monitor", _mone)
            try:
                from brain.cognition.global_workspace import update_workspace as _uw_pre
                _uw_pre(context)
                # Mirror the §19.1 monitor + workspace blocks to the UI (fail-safe).
                _tb_mon = _bridge()
                if _tb_mon is not None:
                    try:
                        _tb_mon.update(
                            monitor={
                                "recent_breakthroughs": context.get("_monitor_breakthroughs") or [],
                                "watchdog": context.get("_monitor_watchdog") or [],
                            },
                            workspace={
                                "conscious": context.get("global_workspace") or {},
                                # The full competition this cycle (Fix 4): ranked
                                # candidates update_workspace stashed — so the UI
                                # can show what almost became conscious and why
                                # this won, not just the winner.
                                "candidates": context.get("_workspace_candidates") or [],
                            },
                        )
                    except Exception:
                        pass
            except Exception as _uwe:
                record_failure("ORRIN_loop.workspace_pre_think", _uwe)

            # ── Conscious ignition gate (Dehaene 2014; Baars 1988; Kahneman 2011) ─
            # Consciousness is a threshold crossing ("ignition"), not a metronome.
            # The unconscious substrate above (affect, embodiment, signals,
            # subconscious threads, workspace competition) ran this cycle REGARDLESS.
            # But only a salient / uncertain / conflicted cycle IGNITES into full
            # deliberate cognition. should_think() is the bar; the periodic floor
            # (MAX_SILENT_CYCLES) guarantees he never goes fully dormant.
            #
            # On a quiet (non-ignited) cycle Orrin stays in low-power default mode:
            # think() still runs for bookkeeping + cheap symbolic selection, but
            # deliberate System-2 recruitment (inner_loop) is withheld (see
            # think_module §7) and the selector damps expensive deliberate functions
            # (see select_function "unconscious damp"). This restores the
            # conscious/unconscious distinction that "always_on" had collapsed.
            # Disable with ORRIN_IGNITION_GATE=0 → exact old always-on behaviour.
            _ignited, _ign_reason = True, "always_on"
            if os.environ.get("ORRIN_IGNITION_GATE", "1") != "0":
                try:
                    from brain.think.consciousness_trigger import should_think as _should_think
                    _ignited, _ign_reason = _should_think(context)
                except Exception as _ige:
                    record_failure("ORRIN_loop.ignition_gate", _ige)
                    _ignited, _ign_reason = True, "ignition_error_failopen"
            context["_conscious_cycle"] = bool(_ignited)
            context["_ignition_reason"] = str(_ign_reason)
            if _ignited:
                log_activity(f"[consciousness] ignited: {_ign_reason}")
                # Only an ignited cycle resets the silent-run counter, so the
                # periodic floor in should_think() actually measures quiet time.
                context["_last_think_cycle"] = get_cycle_count()
                _ui_stage("plan", "Planning — deliberating the next move.")
            else:
                log_activity(f"[consciousness] quiet — unconscious cycle ({_ign_reason})")
                _ui_stage("plan", "Idling — below the threshold of deliberate thought.")
            result = think(context)

            _decision_id = (context.get("last_decision") or {}).get("reason", {}).get("decision_id")
            # Guarantee every cycle has a traceable decision_id so the evaluator WAL
            # never silently drops entries because the selector didn't run (exception,
            # action path, fallback).
            if not _decision_id:
                import uuid as _uuid
                _decision_id = str(_uuid.uuid4())
                try:
                    _ld = context.setdefault("last_decision", {})
                    _ld.setdefault("reason", {})["decision_id"] = _decision_id
                except Exception as _e:
                    record_failure("ORRIN_loop.run_cognitive_loop.10", _e)

            # Path A: behavior action
            if isinstance(result, dict) and "action" in result:
                action = result["action"]
                speaker = context.get("speaker")
                action_type = action.get("type")
                try:
                    from brain.cognition.metacog import metacog_note as _mn
                    _mn(context, "action", f"chose action {action_type!r}")
                except Exception as e:
                    record_failure("ORRIN_loop.metacog_note_action", e)

                if action_type not in BEH_NAMES:
                    log_error(f"Unknown action type: {action_type}. Skipping.")
                    log_model_issue(f"Unknown action type attempted: {action_type}")
                    try:
                        route_exception(RuntimeError(f"Unknown action {action_type}"),
                                        phase="action", context=context, extra={"action": action_type})
                    except Exception as e:
                        record_failure("ORRIN_loop.route_exception_action", e)
                    _ = try_auto_repair({"type": "UnknownAction", "msg": str(action_type),
                                         "trace": "", "phase": "action"}, context)
                    reward = -0.3
                    feats = bandit_learn(str(action_type or "unknown_action"), context, reward, decision_id=_decision_id)
                    record_decision(str(action_type or "unknown_action"),
                                    reason_string({"error": "unknown_action"}, reward, feats, "think.action"),
                                    reward=reward, context=context)
                    if _evaluator:
                        try:
                            from brain.eval.evaluator_wal import append_pending as _ew_append_ua
                            _ew_append_ua(_decision_id, str(action_type or "unknown_action"), feats, get_cycle_count(),
                                          committed_goal_id=(context.get("committed_goal") or {}).get("id") or None)
                        except Exception as _e:
                            record_failure("ORRIN_loop.run_cognitive_loop.11", _e)
                else:
                    try:
                        success = take_action(action, context, speaker)
                        acted_this_cycle = bool(success)
                        if success:
                            context["last_action_ts"] = time.time()
                            log_activity(f"Action Taken: {action_type}")
                            _push_event("function_executed", fn=action_type, cycle=get_cycle_count())
                        else:
                            log_error("take_action returned False")
                            log_penalty_signal(context, "impasse_signal", increment=0.3)
                        # 0.8 for success; negative reward for failures so the bandit
                        # can distinguish bad actions from neutral ones (floor was 0.0).
                        base_reward = 0.8 if success else -0.3
                        # For speak-family actions, modulate reward by ground truth
                        # grounding score so the bandit learns from real outcomes, not
                        # just whether the output pipe succeeded. Claim 3 fix: speak
                        # failures should produce real penalty, not constant 0.8.
                        if success and action_type in {"speak", "user_response", "ask_user"}:
                            # ── Store conversation exchange in long-term memory ──
                            # This is the most important write: every real exchange with
                            # Ric needs to persist. Without this, Orrin has no history.
                            try:
                                from brain.cog_memory.long_memory import update_long_memory as _ulm
                                _user_said  = (context.get("latest_user_input") or "").strip()
                                _orrin_said = (action.get("content") or context.get("_last_spoken") or "").strip()
                                if _user_said and _orrin_said:
                                    _ulm(
                                        f"[Conversation] Ric: {_user_said[:500]}\nOrrin: {_orrin_said[:500]}",
                                        event_type="conversation",
                                        importance=4,
                                        context=context,
                                    )
                                elif _orrin_said:
                                    _ulm(
                                        f"[Orrin said] {_orrin_said[:600]}",
                                        event_type="orrin_speech",
                                        importance=2,
                                        context=context,
                                    )
                            except Exception as _lm_e:
                                log_error(f"[long_memory] conversation write failed: {_lm_e}")

                            try:
                                from brain.symbolic.ground_truth import grounding_score as _gs
                                _gs_val = _gs(action_type)
                                # Blend: 60% base, 40% grounding signal so variance is real
                                # _gs_val=0.5 neutral → 0.8; _gs_val=0.2 poor → 0.56; _gs_val=0.8 good → 0.92
                                base_reward = 0.6 * base_reward + 0.4 * (0.4 + _gs_val * 0.8)
                            except Exception as _e:
                                record_failure("ORRIN_loop.run_cognitive_loop.12", _e)
                        # Weight by goal progress when a goal is active
                        try:
                            from brain.cognition.planning.goal_progress import goal_weighted_reward as _gwr
                            reward = _gwr(base_reward, context, action_was_taken=acted_this_cycle, fn_name=action_type)
                        except Exception:
                            reward = base_reward
                        # Set acceptance flag so finalize's bonus applies correctly
                        context["last_acceptance_pass"] = bool(success)
                        feats = bandit_learn(action_type, context, reward, decision_id=_decision_id)
                        record_decision(action_type,
                                        reason_string({"success": success}, reward, feats, "think.action"),
                                        reward=reward, context=context)
                        if _evaluator:
                            try:
                                from brain.eval.evaluator_wal import append_pending as _ew_append_a
                                _ew_append_a(_decision_id, action_type, feats, get_cycle_count(),
                                             committed_goal_id=(context.get("committed_goal") or {}).get("id") or None)
                            except Exception as _ewa_e:
                                log_model_issue(f"[evaluator] Path A WAL append failed: {_ewa_e}")
                    except Exception as e:
                        route_exception(e, phase="action", context=context)
                        _ = try_auto_repair({"type": e.__class__.__name__, "msg": str(e),
                                             "trace": "", "phase": "action"}, context)
                        log_error(f"Action execution failed: {e}")
                        log_penalty_signal(context, "impasse_signal", increment=0.3)
                        reward = 0.0
                        feats = bandit_learn(str(action_type or "unknown_action"), context, reward, decision_id=_decision_id)
                        record_decision(str(action_type or "unknown_action"),
                                        reason_string({"error": str(e)}, reward, feats, "think.action"),
                                        reward=reward, context=context)
                        if _evaluator:
                            try:
                                from brain.eval.evaluator_wal import append_pending as _ew_append_ae
                                _ew_append_ae(_decision_id, str(action_type or "unknown_action"), feats or {}, get_cycle_count(),
                                              committed_goal_id=(context.get("committed_goal") or {}).get("id") or None)
                            except Exception as _ewa_e2:
                                log_model_issue(f"[evaluator] Path A WAL append (error branch) failed: {_ewa_e2}")

            # Path B: cognition function
            elif isinstance(result, dict) and "next_function" in result:
                fn_name = result["next_function"]

                # Tier 1 critical override — survival beats the bandit.
                # If setpoint_regulation flagged a critical condition this cycle, replace
                # the bandit's choice with the suggested repair function — but only
                # if that function is actually registered and callable.
                #
                # Bounded, not absolute: a persistent alert used to re-fire this
                # override on EVERY cycle, which (a) made update_affect_state
                # ~23% of all decisions and (b) vetoed every ε-exploration pick,
                # so dormant functions never got trials. Two bounds fix that:
                #   • cooldown — the same repair fn runs at most once per
                #     _T1_COOLDOWN cycles; between firings the bandit's pick
                #     stands (the alert signal still reaches the router).
                #   • futility — if the alert survives _T1_FUTILE consecutive
                #     overrides, the repair clearly isn't repairing; stand down
                #     for _T1_BACKOFF cycles and let normal cognition (incl.
                #     problem_refocus) take a different angle.
                _T1_COOLDOWN, _T1_FUTILE, _T1_BACKOFF = 3, 5, 50
                try:
                    if context.get("_tier1_critical") and context.get("_tier1_suggested_fn"):
                        _t1_fn = context["_tier1_suggested_fn"]
                        _t1_hist = context.setdefault("_t1_override_hist", {})
                        _t1_h = _t1_hist.setdefault(_t1_fn, {"streak": 0, "last_cycle": -10**9, "backoff_until": 0})
                        _t1_now = get_cycle_count()
                        if _t1_h["streak"] >= _T1_FUTILE and _t1_now >= _t1_h["backoff_until"]:
                            _t1_h["streak"] = 0  # backoff served — eligible again
                        if (_t1_fn in COGNITIVE_FUNCTIONS
                                and _t1_now >= _t1_h["backoff_until"]
                                and (_t1_now - _t1_h["last_cycle"]) >= _T1_COOLDOWN):
                            _t1_h["streak"] += 1
                            _t1_h["last_cycle"] = _t1_now
                            if _t1_h["streak"] >= _T1_FUTILE:
                                _t1_h["backoff_until"] = _t1_now + _T1_BACKOFF
                                log_activity(
                                    f"[setpoint_regulation] override futile: {_t1_fn!r} ran "
                                    f"{_T1_FUTILE}× without clearing the alert — standing down "
                                    f"{_T1_BACKOFF} cycles")
                            log_activity(f"[setpoint_regulation] critical override: {fn_name!r} → {_t1_fn!r}")
                            fn_name = _t1_fn
                    # Reset neglect counters when the suggested repair function runs —
                    # the alarm has been answered; allostatic load begins to recover.
                    _t1_sfn = context.get("_tier1_suggested_fn")
                    if _t1_sfn and fn_name == _t1_sfn:
                        _h1_ign = context.get("_h1_ignored_cycles", {})
                        for _aid in list(_h1_ign.keys()):
                            _h1_ign[_aid] = 0
                    context.pop("_tier1_critical", None)
                    context.pop("_tier1_suggested_fn", None)
                except Exception as _e:
                    record_failure("ORRIN_loop.run_cognitive_loop.13", _e)

                try:
                    from brain.cognition.metacog import metacog_note as _mn
                    _mn(context, "selection", f"selected function {fn_name!r}")
                except Exception as e:
                    record_failure("ORRIN_loop.metacog_note_selection", e)
                meta_or_fn = COGNITIVE_FUNCTIONS.get(fn_name)
                fn = (meta_or_fn.get("function") if isinstance(meta_or_fn, dict) else meta_or_fn)

                try:
                    if callable(fn):
                        # Pre-step environment snapshot for delta-based reward.
                        _snap = None
                        _tick_ms = None
                        _env_delta = None
                        try:
                            from brain.cognition.planning.env_snapshot import (
                                take_snapshot as _snap,
                                apply_milestone_updates as _tick_ms,
                                delta_reward as _env_delta,
                            )
                        except Exception as e:
                            record_failure("ORRIN_loop.import_env_snapshot", e)
                        _pre_snap = _snap(context) if _snap else {}

                        _emo_pre = dict(context.get("affect_state") or {})
                        # Proactive-resource Phase 0 (OBSERVE-ONLY): time the act so
                        # the interoceptive cost model can learn expected cost and
                        # report prediction error / would-be EVC / τ candidate. No
                        # behavior change. docs/proactive_resource_plan.md.
                        _intero_t0 = time.perf_counter()
                        fn_result = _invoke_cognition(
                            fn, fn_name, context,
                            args=result.get("args") if isinstance(result, dict) else None,
                            kwargs=result.get("kwargs") if isinstance(result, dict) else None,
                        )
                        try:
                            _lat_ms = (time.perf_counter() - _intero_t0) * 1000.0
                            from brain.cognition.interoception import observe as _intero_observe
                            _io = _intero_observe(fn_name, _lat_ms, context)
                            _tb_io = _bridge()
                            if _tb_io is not None and _io:
                                try:
                                    _tb_io.update(interoception=_io)
                                except Exception:
                                    pass
                        except Exception as _ioe:
                            record_failure("ORRIN_loop.interoception_observe", _ioe)
                        _emo_post = dict(context.get("affect_state") or {})

                        # Post-step: tick milestones, snapshot again, compute reward.
                        _ticked_n = 0
                        try:
                            if _tick_ms is not None:
                                _ticked_n = _tick_ms(context)
                                context["_milestones_ticked_this_cycle"] = int(_ticked_n or 0)
                                # Complete the COMMITTED goal the moment its milestones
                                # are all genuinely met. It's excluded from the main-loop
                                # satiety sweep and the Executive's pursue is unreliable,
                                # so an all-met committed goal otherwise sits in_progress
                                # forever with impasse climbing. mark_goal_completed re-checks
                                # milestones (hollow guard), so this only closes a goal that
                                # is genuinely finished (milestones tick on real artifacts:
                                # note_written / research / production traces — env_snapshot).
                                _cgoal = context.get("committed_goal")
                                if isinstance(_cgoal, dict) and _cgoal.get("status") != "completed":
                                    _gms = [m for m in (_cgoal.get("milestones") or []) if isinstance(m, dict)]
                                    _cyc_now = get_cycle_count()
                                    # Progress clock: reset whenever a milestone ticks (or first sight).
                                    if _ticked_n or _cgoal.get("_last_progress_cycle") is None:
                                        _cgoal["_last_progress_cycle"] = _cyc_now
                                    if _gms and all(m.get("met") for m in _gms):
                                        try:
                                            from brain.cognition.planning.goals import (
                                                mark_goal_completed as _mgc,
                                                merge_updated_goal_into_tree as _mugit,
                                            )
                                            from brain.cognition.planning import goal_arbiter as _ga
                                            _mgc(_cgoal, context=context)
                                            if _cgoal.get("status") == "completed":
                                                _ga.apply((lambda _g: (lambda _t: _mugit(_t, _g)))(_cgoal),
                                                          source="loop.milestones_all_met")
                                                if (context.get("committed_goal") or {}).get("id") == _cgoal.get("id"):
                                                    context["committed_goal"] = None
                                                log_activity(f"[loop] Goal completed (milestones met): {(_cgoal.get('title') or '?')[:50]}")
                                        except Exception as _mce:
                                            record_failure("ORRIN_loop.complete_on_milestones", _mce)
                                    else:
                                        # Leave an unproductive goal when its local
                                        # reward rate has fallen below Orrin's learned
                                        # global background and the smooth leave hazard fires.
                                        from brain.cognition.reward_rate import (
                                            accrue_leave_pressure as _alp,
                                            is_stagnating as _is_stag,
                                            should_force_switch as _sfs,
                                        )
                                        _alp(context)
                                        if _is_stag(context) and _sfs(context):
                                            try:
                                                from brain.cognition.planning.pursue_goal import _degrade_or_disengage as _dod
                                                _dod(
                                                    _cgoal,
                                                    context,
                                                    (_cgoal.get("title") or "?"),
                                                    "local reward rate below background",
                                                )
                                            except Exception as _sde:
                                                record_failure("ORRIN_loop.stall_degrade", _sde)
                            _post_snap = _snap(context) if _snap else {}
                            _env_r = _env_delta(_pre_snap, _post_snap) if _env_delta else 0.5
                        except Exception:
                            _env_r = 0.5
                            _post_snap = {}

                        # Detect dispatch-level failure: _invoke_cognition returns
                        # {"status": "error", "error": "unsatisfiable_args: [...]"}
                        # when a cognitive function's required args can't be filled
                        # from context (e.g. add_goal(goal=), apply_emotion_routing(fn_scores=)).
                        # Without this the bandit was logging "Executed" for non-runs
                        # and rewarding them at the 0.20 underperformer floor.
                        _dispatch_failed = (
                            isinstance(fn_result, dict)
                            and fn_result.get("status") == "error"
                        )
                        if _dispatch_failed:
                            log_activity(
                                f"Skipped: {fn_name} (dispatch failed: "
                                f"{fn_result.get('error', 'unknown')})"
                            )
                        else:
                            log_activity(f"Executed: {fn_name}")
                        _push_event("function_executed", fn=fn_name, cycle=get_cycle_count())
                        _fn_str = str(fn_result or "")
                        _is_failure = _dispatch_failed or (
                            _fn_str.startswith("❌") or
                            _fn_str.startswith("Failed") or
                            "ERROR" in _fn_str[:30]
                        )
                        _status_r = 0.1 if _is_failure else 0.5
                        try:
                            from brain.cognition.action_accounting import mark_consequential_cognition
                            _reach = context.get("_last_reach_outcome")
                            mark_consequential_cognition(
                                context,
                                env_r=_env_r,
                                ticked_n=_ticked_n,
                                is_failure=_is_failure,
                                info_gain=(
                                    getattr(_reach, "info_gain", None)
                                    if _reach is not None else None
                                ),
                            )
                        except Exception as _e:
                            record_failure("ORRIN_loop.mark_consequential_cognition", _e)

                        # === Agency-based causal learning (Pearl Level 2) — stash ===
                        # Learn what this action does to Orrin's felt state. The felt
                        # consequence isn't visible yet: commit_affect (cycle end) only
                        # QUEUES the cycle's affect changes, which drain at NEXT cycle's
                        # update_affect_state. So stash (action, this cycle's pre-affect)
                        # and attribute the change at the start of next cycle, once it
                        # has actually landed. Gopnik (child-as-scientist) / Damasio
                        # (somatic markers) / Thorndike (law of effect): you learn
                        # causation by acting and noticing how you feel afterward.
                        if not _is_failure:
                            try:
                                _base_core = context.get("_emo_pre_cycle") or {}
                                if isinstance(_base_core, dict) and _base_core:
                                    context["_iv_pending"] = {
                                        "fn": fn_name,
                                        "core": {k: float(v) for k, v in _base_core.items()
                                                 if isinstance(v, (int, float))},
                                    }
                            except Exception as _e:
                                record_failure("ORRIN_loop.run_cognitive_loop.14", _e)

                        # === Waking temporal causal discovery (booster) ===
                        # discover_from_wm_sequence otherwise only runs during dreams,
                        # so event→event regularities accrue too slowly. Run it on the
                        # recent WM window periodically while awake too. Pure reuse.
                        try:
                            if get_cycle_count() % 20 == 0:
                                from brain.symbolic.causal_graph import discover_from_wm_sequence as _dfs
                                _recent_wm = load_json(WORKING_MEMORY_FILE, default_type=list) or []
                                _dfs([e for e in _recent_wm[-25:] if isinstance(e, dict)])
                        except Exception as _e:
                            record_failure("ORRIN_loop.run_cognitive_loop.15", _e)

                        # Blend: env-delta (40%) + status (20%) + emotional delta (40%).
                        # emotional_delta_reward captures how the function actually moved
                        # Orrin's internal state — the reward signal the bandit was missing.
                        _emo_r = emotional_delta_reward(_emo_pre, _emo_post)
                        base_reward = blend_reward(0.6 * _env_r + 0.4 * _status_r, _emo_r)
                        _blended_reward = base_reward
                        try:
                            from brain.cognition.reward_rate import update_reward_rate
                            update_reward_rate(
                                context,
                                reward=float(_blended_reward),
                                committed_goal_id=(
                                    (context.get("committed_goal") or {}).get("id")
                                ),
                            )
                            context["_reward_rate_updated_this_cycle"] = True
                        except Exception as _e:
                            record_failure("ORRIN_loop.update_reward_rate", _e)
                        if _is_failure:
                            base_reward = min(base_reward - 0.4, -0.1)
                        # Apply goal-weighted reward on the cognition path, matching
                        # the action path — so the bandit learns that cognition which
                        # doesn't advance the committed goal is worth less.
                        try:
                            from brain.cognition.planning.goal_progress import goal_weighted_reward as _gwr_cog
                            reward = _gwr_cog(base_reward, context, action_was_taken=not _is_failure, fn_name=fn_name)
                        except Exception:
                            reward = base_reward
                        # Regulation discharge bonus — reward regulation when distress
                        # was actually present at execution time.
                        # Aldao et al. (2010) meta-analysis of emotion regulation:
                        # strategy effectiveness is highly context-dependent; the critical
                        # learning event is selecting the right strategy given the current
                        # emotional state, not a measurable downstream state change.
                        # Emotional state does not update within a single cognitive cycle —
                        # update_affect_state() runs at cycle start, not inside functions.
                        # Measuring pre/post delta within one cycle produces a spurious zero
                        # because the comparison window is too narrow. Sheppes et al. (2014):
                        # the bandit must learn that regulation during high-distress states
                        # pays — the bonus must be conditioned on distress-at-execution, with
                        # magnitude scaled to distress severity to create the correct gradient.
                        _REGULATION_FNS = frozenset({
                            "attempt_regulation", "reflect_on_affect",
                            "investigate_unexplained_emotions", "check_affect_drift",
                            "reflect_on_emotion_model", "apply_affective_feedback",
                        })
                        if fn_name in _REGULATION_FNS and not _is_failure:
                            try:
                                _pre_neg = sum(
                                    float((_emo_pre.get("core_signals") or _emo_pre).get(k) or 0)
                                    for k in ["impasse_signal", "threat_level", "risk_estimate", "conflict_signal", "negative_valence"]
                                )
                                if _pre_neg > 0.45:
                                    reward += min(0.18, 0.08 + _pre_neg * 0.15)
                            except Exception as _e:
                                record_failure("ORRIN_loop.run_cognitive_loop.16", _e)
                        # Dopaminergic novelty gate for outward perception reads
                        # (Schultz 1997: dopamine signals prediction error / novelty,
                        # not repetition). look_outward & friends previously farmed
                        # standing bonuses 100+ times regardless of whether the glance
                        # surfaced anything new — the reward leak. An empty or repeated
                        # outward result is not a reward event.
                        _OUTWARD_READ_FNS = frozenset({
                            "look_outward", "look_around", "seek_novelty",
                            "read_rss", "survey_environment",
                        })
                        _outward_low_novelty = False
                        if fn_name in _OUTWARD_READ_FNS:
                            try:
                                import hashlib as _hashlib
                                _norm = _fn_str.strip().lower()
                                _digest = (
                                    _hashlib.sha1(_norm.encode("utf-8", "ignore")).hexdigest()
                                    if _norm else ""
                                )
                                if not _norm or _digest == context.get("_last_outward_digest"):
                                    _outward_low_novelty = True
                                context["_last_outward_digest"] = _digest
                            except Exception as _e:
                                record_failure("ORRIN_loop.run_cognitive_loop.17", _e)
                            if _outward_low_novelty:
                                # No novelty → no dopamine. Pull reward to the low end.
                                reward = min(reward, 0.1)

                        # Outward-debt discharge bonus (FINDINGS 2026-06-12 data
                        # sweep §11): look_outward was the worst-paid action in the
                        # stats table while the metacog objective demanded outward
                        # action — suppression can't beat a standing reward gap, so
                        # pay the discharge itself. An outward act landing after a
                        # long internal-only stretch earns a bonus scaled by the
                        # debt it clears; the novelty gate above keeps a repeated
                        # empty glance from farming it.
                        try:
                            if (fn_name in _OUTWARD_FNS and not _is_failure
                                    and not _outward_low_novelty):
                                _od_pay = int(context.get("_outward_debt", 0) or 0)
                                if _od_pay >= 8:
                                    reward += min(0.25, 0.10 + (_od_pay - 8) * 0.01)
                        except Exception as _e:
                            record_failure("ORRIN_loop.run_cognitive_loop.17b", _e)

                        # Dopaminergic habituation — LEARNING-AWARE (Schultz 1997:
                        # dopamine tracks prediction error / novelty, not repetition).
                        # This is the natural pressure that replaces the old hard
                        # anti-repeat cap: repeating the SAME function gets boring
                        # (reward decays) ONLY when it isn't paying off — i.e. when his
                        # reward EMA for it is flat or falling. If repeating it keeps
                        # IMPROVING reward (he's trying it differently and learning), it
                        # is NOT habituated and he's free to keep going. So mindless
                        # loops fade on their own; productive iteration continues.
                        try:
                            _rp8 = context.get("recent_picks", [])[-8:]
                            _rep_n = max(0, _rp8.count(fn_name) - 1)
                            _improving = float((context.get("_fn_ema_delta") or {}).get(fn_name, 0.0)) > 0.0
                            if _rep_n > 0 and not _improving:
                                # Bored: steeper, deeper decay so a stale loop reliably
                                # loses to alternatives (down toward ~0 instead of a 0.2 floor).
                                if fn_name in _OUTWARD_READ_FNS:
                                    _habituation = max(0.05, 1.0 - _rep_n * 0.32)
                                else:
                                    _habituation = max(0.1, 1.0 - _rep_n * 0.22)
                                reward *= _habituation
                        except Exception as _e:
                            record_failure("ORRIN_loop.run_cognitive_loop.18", _e)

                        # Social baseline penalty — absence of user dampens intrinsic reward.
                        # Based on Coan & Beckes (2010) social baseline theory: internal
                        # rewards are calibrated against social presence. Extended silence
                        # (>30 min) progressively reduces reward for all non-social functions,
                        # creating a real pull toward engagement. Floor at 80% so Orrin
                        # doesn't collapse into chronic risk_estimate during long autonomous runs.
                        try:
                            _sil_s = float((context.get("social_presence") or {}).get("silence_s") or 0.0)
                            if _sil_s > 1800:
                                _absence_mod = max(0.80, 1.0 - (_sil_s / 3600.0) * 0.10)
                                reward *= _absence_mod
                        except Exception as _e:
                            record_failure("ORRIN_loop.run_cognitive_loop.19", _e)

                        # Solo-mode introvert bonus — deep internal work earns more
                        # reward during absence, not merely less penalty.
                        # Aron & Aron (1997) sensory-processing sensitivity: introverted
                        # systems show heightened processing depth during low-stimulation
                        # periods; solitary reflection produces genuine positive affect, not
                        # just absence of overstimulation. Kaplan & Kaplan (1989) attention
                        # restoration theory: directed attention (scanning, searching)
                        # depletes; fascination-driven internal processing (integration,
                        # symbolic reasoning) restores. The social baseline above correctly
                        # penalizes look_outward as a connection substitute; this bonus
                        # creates the opposing pull toward genuine restorative solo work.
                        _INTROVERT_FNS = frozenset({
                            "run_symbolic_dream", "run_rule_compression",
                            "run_forgetting_cycle", "run_symbolic_prediction_cycle",
                            "reflect_on_affect", "narrative_update",
                            "update_latent_identity", "propose_value_revision",
                            "audit_reflective_claims", "run_self_improvement",
                            "reflect_on_cognition_rhythm", "run_active_experiment",
                            "detect_memory_contradictions", "repair_contradictions",
                        })
                        try:
                            _sil_s_solo = float((context.get("social_presence") or {}).get("silence_s") or 0.0)
                            if _sil_s_solo > 1800 and fn_name in _INTROVERT_FNS:
                                reward += 0.15
                        except Exception as _e:
                            record_failure("ORRIN_loop.run_cognitive_loop.20", _e)

                        # Tier 2: SDT value alignment bonus.
                        # Functions that match Orrin's stated core values earn a
                        # standing reward boost. Based on Deci & Ryan (2000): intrinsic
                        # motivation produces deeper, more stable learning than extrinsic
                        # reward alone. Value-aligned behavior should be self-reinforcing.
                        # One value match per function (cap 0.12) — enough to tilt the
                        # bandit over many cycles without overwhelming the signal.
                        try:
                            _sm   = context.get("self_model") or {}
                            _vals = [
                                str((v.get("value") if isinstance(v, dict) else v) or "").lower()
                                for v in (_sm.get("core_values") or [])
                            ]
                            _fn_l = fn_name.lower()
                            _V2KW = {
                                "exploration_drive":  {"search","look","investigate","wiki","rss","explore","perception","outward"},
                                "growth":     {"improve","learn","write","discover","synthesis","dream","compress","self_improv","extension"},
                                "honesty":    {"audit","detect","repair","reflect","contradict","verify","integrity","rhythm"},
                                "connection": {"note","speak","social","user","thread","leave","person"},
                                "depth":      {"symbolic","dream","compress","rule","reason","introspect","predict","analogy","emotion"},
                            }
                            _val_bonus = 0.0
                            for _val in _vals:
                                if any(_kw in _fn_l for _kw in _V2KW.get(_val, set())):
                                    _val_bonus = 0.10
                                    break
                            # Don't pay the value-alignment standing bonus to an outward
                            # read that surfaced nothing new — that was the leak that let
                            # look_outward accrue +0.10 every cycle regardless of outcome.
                            if _outward_low_novelty:
                                _val_bonus = 0.0
                            reward += _val_bonus
                        except Exception as _e:
                            record_failure("ORRIN_loop.run_cognitive_loop.21", _e)

                        # Growth-orientation standing bonus.
                        # Functions that expand capability or deepen self-understanding
                        # earn an additional baseline reward independent of value matching.
                        # Based on Ryan & Deci (2000): intrinsic motivation toward mastery
                        # and growth is qualitatively distinct from task-completion reward —
                        # it needs its own signal or it loses to easier, more frequent wins.
                        _GROWTH_FNS = frozenset({
                            "write_cognitive_function", "write_tool", "discover_new_emotion",
                            "run_self_improvement", "reflect_on_affect", "reflect_on_emotion_model",
                            "update_latent_identity", "narrative_update", "propose_value_revision",
                            "run_symbolic_dream", "run_rule_compression", "audit_reflective_claims",
                            "investigate_unexplained_emotions", "detect_memory_contradictions",
                            "repair_contradictions", "run_symbolic_prediction_cycle",
                            "run_forgetting_cycle", "run_benchmark", "reflect_on_cognition_rhythm",
                            "research_topic", "fetch_and_read",
                        })
                        if fn_name in _GROWTH_FNS:
                            reward += 0.12

                        # Competence legibility: write a visible completion record to
                        # working memory — but only for significant accomplishments.
                        # Bandura (1977) self-efficacy theory: mastery experiences are
                        # constituted by challenging tasks; feedback on routine execution
                        # does not build efficacy and risks diluting the signal value of
                        # genuine achievement. Locke & Latham (2002) goal-setting theory:
                        # performance feedback must be proximal to meaningful accomplishment
                        # to be effective — indiscriminate positive feedback creates noise
                        # that erodes the discriminability of real completion signals.
                        # White (1959) effectance motivation: the intrinsic drive is toward
                        # producing effects that matter, not toward any effect whatsoever.
                        # Trigger: growth functions, regulation functions, or substantive
                        # output (>120 chars) — not every successful call.
                        _is_significant_completion = (
                            fn_name in _GROWTH_FNS
                            or fn_name in _REGULATION_FNS
                            or (not _is_failure and len(_fn_str) > 120)
                        )
                        if not _is_failure and _is_significant_completion and _fn_str:
                            try:
                                from brain.cog_memory.working_memory import update_working_memory as _uwm_comp
                                _uwm_comp(f"[done] {fn_name}: {_fn_str[:80].strip().rstrip('.')}")
                            except Exception as _e:
                                record_failure("ORRIN_loop.run_cognitive_loop.22", _e)

                        # Outcome coupling — introspection can't outpay reality.
                        # The standing bonuses above (value alignment, growth,
                        # regulation, emotional delta) summed to ~0.55–0.73 for
                        # introspective picks even on cycles where env_snapshot
                        # measured zero observable change (delta_reward=0.000,
                        # thrash=True) — which is how assess_goal_progress +
                        # update_affect_state became 60% of all decisions while
                        # outward action paid less. If a self-inspection function
                        # produced no observable change (no milestone, no memory
                        # write, no tool resolution, WM unchanged), its reward is
                        # capped below what productive work earns. Introspection
                        # that DOES move something external (env_r ≥ 0.35) still
                        # pays in full.
                        _INTROSPECTIVE_FNS = frozenset({
                            "assess_goal_progress", "update_affect_state",
                            "search_own_files", "reflect_on_internal_agents",
                            "reflect_on_affect", "reflect_on_emotion_model",
                            "check_affect_drift", "audit_reflective_claims",
                            "reflect_on_outcomes", "reflect_on_self_beliefs",
                            "detect_memory_contradictions",
                            "reflect_on_cognition_patterns", "reflect_on_internal_voices",
                            "summarize_relationships", "periodic_self_review",
                            "reflect_on_effectiveness", "reflect_on_opinions",
                            "reflect_on_growth_history", "process_regret",
                            "read_vitals", "check_user_presence",
                        })
                        try:
                            if (not _is_failure
                                    and fn_name in _INTROSPECTIVE_FNS
                                    and float(_env_r) < 0.35):
                                reward = min(reward, 0.35)
                        except Exception as _e:
                            record_failure("ORRIN_loop.run_cognitive_loop.23", _e)

                        # Expose for finalize.py's reward_signal signal.
                        context["_step_delta_reward"] = reward
                        # Feed env-delta reward back into the depth bandit when
                        # pursue_committed_goal ran this cycle (it stashes its chosen depth).
                        _pg_depth = context.pop("_pursue_goal_depth", None)
                        if _pg_depth is not None:
                            try:
                                from brain.cognition.planning.thinking_depth import update_depth as _ud
                                _ud(_pg_depth, reward)
                            except Exception as e:
                                record_failure("ORRIN_loop.update_depth", e)
                        # Mark acceptance: succeeded + (no goal OR goal was referenced in WM)
                        try:
                            _goal_title = ((context.get("committed_goal") or {}).get("title") or "").lower()
                            _wm_refs = any(
                                _goal_title in str(e).lower()
                                for e in (context.get("working_memory") or [])[-3:]
                            ) if _goal_title else True
                            context["last_acceptance_pass"] = not _is_failure and _wm_refs
                        except Exception:
                            context["last_acceptance_pass"] = not _is_failure
                        # Update emotion→function map with actual reward (not always 1.0).
                        # think_module.py uses last_reward from the *previous* cycle as a
                        # proxy; here we update with the real outcome for better accuracy.
                        try:
                            _core_pre = (_emo_pre.get("core_signals") or _emo_pre) or {}
                            _dom_emo = max(
                                (_core_pre or {}),
                                key=lambda k: float(_core_pre.get(k) or 0.0),
                            ) if _core_pre else ""
                            if _dom_emo:
                                from brain.affect.affect_learning import update_affect_function_map as _uefm
                                _uefm(_dom_emo, fn_name, reward_signal=reward)
                        except Exception as e:
                            record_failure("ORRIN_loop.emotion_function_map", e)
                        feats = bandit_learn(fn_name, context, reward, decision_id=_decision_id)
                        record_decision(fn_name, reason_string({"status": "ok", "fn_result": _fn_str[:80]}, reward, feats, "think.fn"),
                                        reward=reward, context=context)
                        # Tag memory write + append pending reward to WAL
                        if _decision_id:
                            try:
                                _cur_cycle = get_cycle_count()
                                _goal_id = str((context.get("committed_goal") or {}).get("id") or
                                               (context.get("committed_goal") or {}).get("title") or "")
                                if _mem_daemon:
                                    import memory_io
                                    memory_io.write(
                                        _mem_daemon, "function_output", _fn_str[:200],
                                        meta={
                                            "decision_id": _decision_id,
                                            "fn": fn_name,
                                            "cycle": _cur_cycle,
                                        },
                                    )
                                    _ui_memory("write",
                                               [{"id": fn_name, "summary": _fn_str[:140]}],
                                               store="long")
                                if _evaluator:
                                    from brain.eval.evaluator_wal import append_pending as _ew_append
                                    _ew_append(_decision_id, fn_name, feats, _cur_cycle,
                                               committed_goal_id=_goal_id or None)
                            except Exception as _ew_e:
                                log_model_issue(f"[evaluator] WAL append failed: {_ew_e}")
                    else:
                        log_model_issue(f"Unknown function requested: {fn_name}")
                        try:
                            route_exception(RuntimeError(f"Unknown function {fn_name}"),
                                            phase="cognition", context=context, extra={"fn": fn_name})
                        except Exception as e:
                            record_failure("ORRIN_loop.route_exception_cognition", e)
                        _ = try_auto_repair({"type": "UnknownFunction", "msg": str(fn_name),
                                             "trace": "", "phase": "cognition"}, context)
                        reward = -0.3
                        feats = bandit_learn(fn_name, context, reward, decision_id=_decision_id)
                        record_decision(fn_name, reason_string({"error": "unknown_fn"}, reward, feats, "think.fn"),
                                        reward=reward, context=context)
                        if _evaluator:
                            try:
                                from brain.eval.evaluator_wal import append_pending as _ew_append_ufn
                                _ew_append_ufn(_decision_id, fn_name, feats, get_cycle_count(),
                                               committed_goal_id=(context.get("committed_goal") or {}).get("id") or None)
                            except Exception as _e:
                                record_failure("ORRIN_loop.run_cognitive_loop.24", _e)
                except Exception as e:
                    route_exception(e, phase="cognition", context=context, extra={"fn": fn_name})
                    _ = try_auto_repair({"type": e.__class__.__name__, "msg": str(e),
                                         "trace": "", "phase": "cognition"}, context)
                    log_error(f"Function {fn_name} crashed: {e}")
                    log_penalty_signal(context, "impasse_signal", increment=0.3 + 0.3 * float(affect_state.get("conflict_signal") or 0.4))
                    reward = 0.0
                    feats = bandit_learn(fn_name, context, reward, decision_id=_decision_id)
                    record_decision(fn_name, reason_string({"error": str(e)}, reward, feats, "think.fn"),
                                    reward=reward, context=context)

            # Path C: fallback (skipped entirely on silent/unconscious cycles)
            elif result is not None:
                log_model_issue("No valid instruction from think(). Fallback to selector.")
                log_uncertainty_spike(context, increment=0.1)
                import uuid as _uuid_fb
                _fb_decision_id = str(_uuid_fb.uuid4())
                sel = None
                try:
                    from brain.think.think_utils.select_function import select_function
                    sel = select_function(context)
                except Exception as _e:
                    log_model_issue(f"select_function failed: {_e}")

                if not sel or not isinstance(sel, str):
                    fb_meta_or_fn = COGNITIVE_FUNCTIONS.get("reflect_on_self_beliefs")
                    fb_fn = (fb_meta_or_fn.get("function") if isinstance(fb_meta_or_fn, dict) else fb_meta_or_fn)
                    if callable(fb_fn):
                        try:
                            fb_fn()
                            log_activity("Fallback executed: reflect_on_self_beliefs")
                            reward = 0.5
                        except Exception as e:
                            route_exception(e, phase="cognition", context=context,
                                            extra={"fn": "reflect_on_self_beliefs"})
                            _ = try_auto_repair({"type": e.__class__.__name__, "msg": str(e),
                                                 "trace": "", "phase": "cognition"}, context)
                            log_error(f"Fallback function crashed: {e}")
                            reward = 0.0
                    else:
                        log_model_issue("No fallback function available.")
                        reward = 0.0
                    feats = bandit_learn("reflect_on_self_beliefs", context, reward, decision_id=_fb_decision_id)
                    record_decision("reflect_on_self_beliefs",
                                    reason_string({"status": "fallback"}, reward, feats, "fallback.fn"),
                                    reward=reward, context=context)
                    if _evaluator:
                        try:
                            from brain.eval.evaluator_wal import append_pending as _ew_append_c1
                            _ew_append_c1(_fb_decision_id, "reflect_on_self_beliefs", feats or {}, get_cycle_count(),
                                          committed_goal_id=(context.get("committed_goal") or {}).get("id") or None)
                        except Exception as _ewc1_e:
                            log_model_issue(f"[evaluator] Path C WAL append failed: {_ewc1_e}")
                else:
                    exec_result = execute_action_via_registries(sel, context, COG_MAP)
                    reward = compute_reward(exec_result)
                    feats = bandit_learn(sel, context, reward, decision_id=_fb_decision_id)
                    record_decision(sel, reason_string(exec_result, reward, feats, "fallback.sel"),
                                    reward=reward, context=context)
                    if _evaluator:
                        try:
                            from brain.eval.evaluator_wal import append_pending as _ew_append_c2
                            _ew_append_c2(_fb_decision_id, sel, feats or {}, get_cycle_count(),
                                          committed_goal_id=(context.get("committed_goal") or {}).get("id") or None)
                        except Exception as _ewc2_e:
                            log_model_issue(f"[evaluator] Path C (sel) WAL append failed: {_ewc2_e}")
                    if isinstance(exec_result, dict) and exec_result.get("success"):
                        acted_this_cycle = True
                        context["last_action_ts"] = time.time()

            if not context.get("_reward_rate_updated_this_cycle"):
                try:
                    from brain.cognition.reward_rate import update_reward_rate
                    update_reward_rate(
                        context,
                        reward=float(reward or 0.0),
                        committed_goal_id=(
                            (context.get("committed_goal") or {}).get("id")
                        ),
                    )
                    context["_reward_rate_updated_this_cycle"] = True
                except Exception as _e:
                    record_failure("ORRIN_loop.update_reward_rate_fallback", _e)

            acted_this_cycle = acted_this_cycle or bool(context.pop("__acted_this_tick__", False))

            # Emotion drift check always runs — it's unconscious monitoring, not conscious thought
            try:
                check_affect_drift(context)
            except Exception as _e:
                record_failure("ORRIN_loop.run_cognitive_loop.25", _e)

            try:
                if context.get("committed_goal"):
                    context["action_debt"] = 0 if acted_this_cycle else int(context.get("action_debt", 0)) + 1
            except Exception as _e:
                log_model_issue(f"Guardrail accounting issue: {_e}")

            # Stall watchdog (raised from 90→180 because inner-loop cycles are longer)
            try:
                STALL_SEC = 180
                now = time.time()
                if context.get("committed_goal"):
                    last_ts = float(context.get("last_action_ts", 0.0) or 0.0)
                    if (now - last_ts) > STALL_SEC:
                        goal = context.get("committed_goal") or {}
                        mv = goal.get("next_action")
                        if isinstance(mv, dict):
                            mv_type = mv.get("type")
                            if mv_type in BEH_NAMES:
                                try:
                                    ok = take_action(mv, context, context.get("speaker"))
                                    if ok:
                                        acted_this_cycle = True
                                        context["last_action_ts"] = time.time()
                                        context["action_debt"] = 0
                                        log_activity(f"Watchdog executed MV action: {mv_type}")
                                    else:
                                        log_model_issue("Watchdog tried MV action; take_action returned False.")
                                    _wd_reward = 0.8 if ok else 0.0
                                    import uuid as _uuid_wd
                                    _wd_decision_id = str(_uuid_wd.uuid4())
                                    feats = bandit_learn(mv_type, context, _wd_reward, decision_id=_wd_decision_id)
                                    record_decision(mv_type, "watchdog minimum viable action",
                                                    reward=_wd_reward, context=context)
                                except Exception as _e:
                                    route_exception(_e, phase="action", context=context,
                                                    extra={"mv_type": mv_type})
                                    _ = try_auto_repair({"type": _e.__class__.__name__, "msg": str(_e),
                                                         "trace": "", "phase": "action"}, context)
                                    log_model_issue(f"Watchdog MV action failed: {_e}")
            except Exception as _e:
                log_model_issue(f"Watchdog error: {_e}")

            # Transparency trace
            try:
                chosen = None
                if isinstance(result, dict):
                    if "action" in result:
                        a = result["action"]
                        chosen = f"ACTION:{a.get('type', 'unknown')}"
                    elif "next_function" in result:
                        chosen = f"FN:{result.get('next_function')}"
                emit_trace(
                    chosen=chosen,
                    debt=context.get("action_debt", 0),
                    mode=context.get("mode"),
                    emotions=context.get("affect_state", {}),
                    committed=bool(context.get("committed_goal")),
                    last_action_ts=context.get("last_action_ts"),
                )
            except Exception as _e:
                log_model_issue(f"Trace emit failed: {_e}")

            # Push new goal proposals to the single GoalsAPI
            if _goals_api:
                import goal_io
                try:
                    goal_io.sync_proposed_goals(_goals_api, context)
                except Exception as e:
                    log_error(f"goal_io.sync_proposed_goals failed: {e}")

                # Record goal progress note every 5 cycles so long memory has a trail
                if context.get("committed_goal"):
                    try:
                        goal_io.record_goal_progress(context)
                    except Exception as e:
                        log_error(f"goal_io.record_goal_progress failed: {e}")

            # Write memory events to v2 MemoryDaemon
            if _mem_daemon:
                import memory_io
                try:
                    memory_io.flush_working_memory(_mem_daemon, context)
                except Exception as e:
                    log_error(f"memory_io.flush_working_memory failed: {e}")

                _cycle_n = get_cycle_count()
                # Every 10 cycles: backfill v2 compaction summaries → v1 long_memory.json
                if _cycle_n > 0 and _cycle_n % 10 == 0:
                    try:
                        added = memory_io.promote_summaries_to_long_memory(_mem_daemon, max_items=5)
                        if added:
                            log_activity(f"Promoted {added} v2 summary item(s) to long memory.")
                    except Exception as e:
                        log_error(f"memory_io.promote_summaries_to_long_memory failed: {e}")
                # Every 5 cycles: backfill recent long_memory.json entries → v2 so they're searchable
                if _cycle_n > 0 and _cycle_n % 5 == 0:
                    try:
                        ingested = memory_io.backfill_long_memory_to_v2(_mem_daemon, max_items=10)
                        if ingested:
                            log_activity(f"Backfilled {ingested} long memory item(s) to v2.")
                    except Exception as e:
                        log_error(f"memory_io.backfill_long_memory_to_v2 failed: {e}")

            # Evaluator tick — resolve pending delayed rewards from the WAL
            if _evaluator:
                try:
                    _evaluator.tick(context, get_cycle_count())
                except Exception as _ev_e:
                    log_model_issue(f"evaluator.tick failed: {_ev_e}")

            # Prediction generation — turn the causal model (now fed by agency-based
            # intervention edges) into falsifiable predictions while AWAKE, not only
            # during dreams. Rate-limited so predictions.json doesn't flood. This is
            # the consumer that closes the learning loop: edges → predictions →
            # (confirmed) → rules → understanding.
            try:
                if get_cycle_count() % 5 == 0:
                    from brain.cognition.prediction import generate_predictions as _gp, save_predictions as _sp
                    _recent_wm_p = load_json(WORKING_MEMORY_FILE, default_type=list) or []
                    _sp(_gp(context, _recent_wm_p[-15:]))
            except Exception as _ge:
                log_error(f"generate_predictions failed: {_ge}")

            # Prediction check — evaluate pending predictions, fire surprise signals
            try:
                from brain.cognition.prediction import check_predictions as _cp
                _cp(context)
            except Exception as _pe:
                log_error(f"check_predictions failed: {_pe}")

            # Dream cycle — fires when idle and 6h have elapsed since last dream.
            # Skipped while HostResourceGuard/VitalFloor has paused heavy cycles:
            # dream is restorative as felt experience, but its consolidation
            # footprint is memory-hungry and must yield under host/process pressure.
            try:
                from brain.cognition.dreaming.dream_cycle import should_dream, dream_cycle as _dream_cycle
                from reaper.host_resources import heavy_cycles_paused as _heavy_paused
                from reaper.vital_floor import vital_floor_shedding as _vital_shedding
                if (not _heavy_paused()) and (not _vital_shedding()) and should_dream(context):
                    import threading as _thr
                    _dt = _thr.Thread(
                        target=_dream_cycle, args=(context,),
                        name="orrin-dream", daemon=True,
                    )
                    _dt.start()
            except Exception as _de:
                log_error(f"dream_cycle check failed: {_de}")

            # Global workspace (unity layer): converge this cycle's parallel
            # contents into a single conscious moment, broadcast it, and extend
            # the continuous stream of experience. Makes him one experiencer
            # rather than a committee of subsystems.
            try:
                from brain.cognition.global_workspace import update_workspace as _uw
                _moment = _uw(context)
                if _moment:
                    tb = _bridge()
                    if tb is not None:
                        tb.update(extra={"awareness": _moment.get("content", "")})
            except Exception as _gwe:
                record_failure("ORRIN_loop.run_cognitive_loop.26", _gwe)

            # Second-order volition (free will): periodically reflect on the
            # desire currently in consciousness and either own or disown it
            # against his values — self-authorship, not just acting on impulse.
            try:
                if get_cycle_count() % 20 == 0:
                    from brain.cognition.selfhood.second_order_volition import reflect_on_desire as _rod
                    _rod(context)
            except Exception as _rve:
                record_failure("ORRIN_loop.run_cognitive_loop.27", _rve)

            # Will/commitment: decay the active resolve and expose its
            # follow-through bias (cleared automatically when goal done/faded).
            try:
                from brain.cognition.will import tick_commitment as _tick_commit
                _tick_commit(context)
            except Exception as _twe:
                record_failure("ORRIN_loop.run_cognitive_loop.28", _twe)

            # Native language faculty (#4): a LIGHT learning bout during idle
            # stretches, on top of the big consolidation in sleep. Idle-only and
            # infrequent so it never lags a conversation or hogs the 8 GB.
            try:
                _lang_user = bool((context.get("latest_user_input") or "").strip())
                if (not _lang_user) and get_cycle_count() % 100 == 0:
                    from brain.cognition.language.acquisition import consolidate_language as _cl
                    _cl(steps=12)

                # Roll completed short-term goals up into the long-term aspirations
                # they serve, and protect those aspirations from being lost or
                # wrongly completed — so long-term goals actually advance.
                if get_cycle_count() % 25 == 0:
                    try:
                        from brain.cognition.intrinsic_goals import credit_aspirations as _ca
                        _ca(context)
                    except Exception as _cae:
                        record_failure("ORRIN_loop.run_cognitive_loop.29", _cae)

                # P2 — fail artifact-gated production goals that blew their deadline
                # with nothing produced (turns the hollow "0 failures" into a real,
                # staked non-zero). P6 — reconcile the goal stores so the new
                # executable path can't reopen the resurrect/orphan-RUNNING desync
                # bugs, and existing-path desyncs become self-healing + measured.
                # Both run on the same 200-cycle epoch (one cadence constant).
                if get_cycle_count() % 200 == 0:
                    try:
                        from brain.cognition.planning.goals import fail_overdue_artifact_goals as _foag
                        _foag(context)
                    except Exception as _fae:
                        record_failure("ORRIN_loop.run_cognitive_loop.foag", _fae)
                    try:
                        from brain.cognition.planning.goal_reconcile import reconcile_goal_stores as _rgs
                        _rgs(context)
                    except Exception as _rge:
                        record_failure("ORRIN_loop.run_cognitive_loop.reconcile", _rge)

                # Bored, not busy → browse the shelf and read a particular book.
                # Boredom (stagnation) is the pull; this is reading by his own
                # restlessness, not a schedule. Throttled so it never hogs the CPU.
                if not _lang_user:
                    _stag = float(
                        (affect_state.get("core_signals") or affect_state).get("stagnation_signal", 0.0)
                    )
                    # Reading is the other memory-hungry heavy cycle: skip it while
                    # host/process resource guards have paused heavies.
                    from reaper.host_resources import heavy_cycles_paused as _heavy_paused
                    from reaper.vital_floor import vital_floor_shedding as _vital_shedding
                    if _stag > 0.5 and get_cycle_count() % 40 == 0 and not _heavy_paused() and not _vital_shedding():
                        from brain.cognition.language.acquisition import read_a_book as _rab
                        _line = _rab(context, steps=30)
                        if _line:
                            context["last_thought"] = _line
            except Exception as _lge:
                record_failure("ORRIN_loop.run_cognitive_loop.30", _lge)

            # ── Deterministic closure/maintenance tier (RECONCILED plan B/C/E) ──
            # Closure machinery already exists but was selection-starved — the
            # emotion-cued bandit never picked it (no prior, cold-start trap). Run
            # it here on slow cadences, decoupled from selection. fade_goals is in
            # _ALWAYS_EXCLUDE so it never ALSO competes as a deliberate choice
            # (no double execution). This is the same precedent the codebase uses
            # for update_affect_state and the apply_* per-cycle upkeep.
            try:
                _mcycle = get_cycle_count()

                # B1 — Goal retirement (% 50): drop terminal/invalid goals from the
                # active tree via the deterministic prune path (NOT bandit-selectable).
                if _mcycle > 0 and _mcycle % 50 == 0:
                    try:
                        from brain.cognition.planning.goals import (
                            load_goals, prune_goals, save_goals,
                        )
                        def _flat(_gs):
                            for _g in _gs:
                                if isinstance(_g, dict):
                                    yield _g
                                    yield from _flat(_g.get("subgoals") or [])
                        _before = load_goals()
                        _n_before = sum(1 for _ in _flat(_before))
                        _after = prune_goals(_before)
                        _n_after = sum(1 for _ in _flat(_after))
                        _retired = _n_before - _n_after
                        if _retired > 0:
                            save_goals(_after)
                            log_activity(
                                f"[maintenance] Retired {_retired} terminal/invalid goal(s)."
                            )
                        # Population gauge — record active count + mean age (Phase E).
                        try:
                            from datetime import datetime as _dt, timezone as _tz
                            from brain.cognition.planning.outcome_metrics import (
                                record_retired, record_goal_population,
                                record_maintenance_execution,
                            )
                            if _retired > 0:
                                record_retired(_retired)
                            _ages = []
                            _now = _dt.now(_tz.utc)
                            for _g in _flat(_after):
                                _c = _g.get("created_at") or _g.get("timestamp")
                                if isinstance(_c, str) and _c:
                                    try:
                                        _ct = _dt.fromisoformat(_c.replace("Z", "+00:00"))
                                        _ages.append((_now - _ct).total_seconds())
                                    except Exception:
                                        pass
                            _avg_age = (sum(_ages) / len(_ages)) if _ages else 0.0
                            record_goal_population(_n_after, _avg_age)
                            record_maintenance_execution()
                        except Exception as _me:
                            record_failure("ORRIN_loop.run_cognitive_loop.31", _me)
                    except Exception as _e:
                        record_failure("ORRIN_loop.run_cognitive_loop.32", _e)

                # B2 — Goal fading (% 60): decay unattended goals toward dormant.
                # fade_goals is self-contained and records abandonment closures.
                if _mcycle > 0 and _mcycle % 60 == 0:
                    try:
                        from brain.cognition.planning.goal_lifecycle import fade_goals
                        fade_goals(context)
                        from brain.cognition.planning.outcome_metrics import (
                            record_maintenance_execution, flush as _om_flush,
                        )
                        record_maintenance_execution()
                        _om_flush()
                    except Exception as _e:
                        record_failure("ORRIN_loop.run_cognitive_loop.33", _e)

                # B3 — Population satiety (% 40): close exploration/understanding
                # goals whose drive is quenched, population-wide (not just focus).
                # Capped per pass; milestone-bearing/committed/lifetime goals skip
                # (they close via milestones / pursue_goal). is_sated's cycle-1 guard
                # and mark_goal_completed's hollow guard remain in force.
                if _mcycle > 0 and _mcycle % 40 == 0:
                    try:
                        from brain.cognition.planning.goals import (
                            load_goals, mark_goal_completed, merge_updated_goal_into_tree,
                            _TERMINAL_STATUSES,
                        )
                        from brain.cognition.planning import goal_arbiter
                        from brain.cognition.planning.goal_satiety import (
                            is_sated, _is_filesystem_exploration,
                        )
                        from brain.cognition.planning.outcome_metrics import (
                            record_satiety_closure, record_maintenance_execution,
                        )
                        _explore_markers = (
                            "understand", "learn about", "find out", "research",
                            "explore", "read more about",
                        )
                        _committed = (context.get("committed_goal") or {})
                        _committed_id = _committed.get("id") if isinstance(_committed, dict) else None
                        _K = 5
                        _checked = 0
                        _sated_closed = 0
                        for _g in load_goals():
                            if _checked >= _K:
                                break
                            if not isinstance(_g, dict):
                                continue
                            _status = str(_g.get("status") or "").lower()
                            if _status in _TERMINAL_STATUSES or _status in ("dormant", "paused"):
                                continue
                            if _g.get("never_complete"):
                                continue
                            if _committed_id and _g.get("id") == _committed_id:
                                continue
                            # Task/directional goals are not satiety-gated (mirror
                            # pursue_goal's tier split): trivial/minor close via
                            # milestones; aspiration/long_term never close here.
                            # mark_goal_completed's hollow guard still protects any
                            # milestone-bearing exploration goal from premature close.
                            if str(_g.get("tier") or "").lower() in (
                                "trivial", "minor", "aspiration", "long_term"
                            ):
                                continue
                            _blob = f"{_g.get('title') or ''} {_g.get('name') or ''}".lower()
                            _is_explore = (
                                any(m in _blob for m in _explore_markers)
                                or _is_filesystem_exploration(_g)
                            )
                            if not _is_explore:
                                continue
                            _checked += 1
                            _sated, _reason = is_sated(_g, context)
                            if not _sated:
                                continue
                            mark_goal_completed(_g, context=context)
                            if _g.get("status") == "completed":
                                goal_arbiter.apply(
                                    (lambda _gg: (lambda _t: merge_updated_goal_into_tree(_t, _gg)))(_g),
                                    source="maintenance.satiety",
                                )
                                _sated_closed += 1
                                log_activity(
                                    f"[maintenance] Satiety-closed "
                                    f"'{(_g.get('title') or _g.get('name') or '?')[:50]}' ({_reason})."
                                )
                        if _sated_closed:
                            record_satiety_closure(_sated_closed)
                        record_maintenance_execution()
                    except Exception as _e:
                        record_failure("ORRIN_loop.run_cognitive_loop.34", _e)
            except Exception as _mte:
                record_failure("ORRIN_loop.run_cognitive_loop.35", _mte)

            # Flush metacog trace to working memory as introspection
            try:
                from brain.cognition.metacog import metacog_flush as _mcf
                _mcf(context)
            except Exception as e:
                record_failure("ORRIN_loop.metacog_flush", e)

            # Decay behavioral adaptation pressures (Carver & Scheier, 1982):
            # Corrective signals should attenuate as the discrepancy is addressed,
            # not persist indefinitely. See behavioral_adaptation.py.
            try:
                from brain.cognition.behavioral_adaptation import decay_behavioral_pressure as _dbp
                _dbp(context)
            except Exception as _e:
                record_failure("ORRIN_loop.run_cognitive_loop.36", _e)

            # ── Health streak monitor: track sustained health, fire setpoint_regulation reward ──
            # Runs every 5 cycles (cheap: reads one JSON, writes one JSON).
            # Positive health streak → emotional uplift + bandit reward.
            # Sustained sick cycles → mild distress signal + WM note.
            try:
                if _cycle_num % 5 == 0:
                    from brain.cognition.health_monitor import check_and_reward as _health_check
                    _health_check(context)
            except Exception as _hm_e:
                record_failure("ORRIN_loop.health_monitor", _hm_e)

            # ── Layer 0 post-cycle: plasticity + drive satisfaction ───────────
            _cycle_fn = (
                result.get("next_function") if isinstance(result, dict) and "next_function" in result
                else result.get("action", {}).get("type") if isinstance(result, dict) and "action" in result
                else ""
            ) or ""
            # Expose the chosen function so finalize.py's outward reward scorer can read it.
            context["last_function_chosen"] = _cycle_fn

            # Benchmark sampling (no-op unless ORRIN_BENCHMARK=1) — records the
            # per-cycle (stagnation_signal, chosen function) for B2 and, every 100
            # cycles, long-memory size + RSS for B1. See brain/benchmarks/.
            try:
                from brain.benchmarks import record_sample as _bench_sample
                _bench_sample(context)
            except Exception as _be:
                record_failure("ORRIN_loop.run_cognitive_loop.37", _be)

            # Outward-debt counter: tracks consecutive cycles without environmental
            # engagement.  Penalty accumulates in finalize._state_satisfaction.
            # Resets to 0 whenever an outward-facing function runs.
            if _cycle_fn in _OUTWARD_FNS:
                context["_outward_debt"] = 0
            else:
                context["_outward_debt"] = min(30, int(context.get("_outward_debt", 0) or 0) + 1)

            try:
                from brain.embodiment import plasticity as _plasticity_mod
                _plasticity_mod.apply_plasticity(_cycle_fn, context, reward)
            except Exception as _pe:
                record_failure("ORRIN_loop.plasticity", _pe)
            try:
                from brain.embodiment import drive_engine as _drive_mod
                _drive_mod.evaluate_cycle(_cycle_fn, context, reward)
            except Exception as _dse:
                record_failure("ORRIN_loop.drive_satisfy", _dse)
            try:
                from brain.motivation import substrate as _motiv_mod
                _motiv_mod.evaluate_cycle_satisfaction(_cycle_fn, reward)
            except Exception as _mse:
                record_failure("ORRIN_loop.motivation_satisfy", _mse)
            # Meta-controller threshold bandit: record outcome so UCB1 can adapt
            try:
                arm_id = context.get("_meta_ctrl_arm")
                if arm_id is not None:
                    from brain.think.meta_controller import record_outcome as _mc_record
                    _mc_record(int(arm_id), reward)
            except Exception as _mcre:
                record_failure("ORRIN_loop.meta_ctrl_record", _mcre)
            # Mark Orrin responded if he spoke this cycle
            try:
                if any(
                    isinstance(r, dict) and r.get("type") in {"speak", "respond", "reply"}
                    for r in [result] if isinstance(result, dict)
                ):
                    from brain.embodiment import social_presence as _social_mod
                    _social_mod.mark_orrin_responded()
            except Exception as _e:
                record_failure("ORRIN_loop.run_cognitive_loop.38", _e)

            # Backstop: guarantee a Face message gets answered this cycle even if
            # the action gate didn't pick a speak action. No-op if already replied.
            try:
                from brain.behavior.face_bridge import force_reply as _force_reply
                _force_reply(context)
            except Exception as _fre:
                record_failure("ORRIN_loop.run_cognitive_loop.39", _fre)

            # Sync context["working_memory"] back to working_memory.json so dashboard and
            # update_working_memory() see the same data.
            # Strip embeddings and chunk items before saving — they're recomputed on demand
            # and their presence causes the file to balloon to 30+ MB (REAPER bait).
            try:
                wm = context.get("working_memory")
                if isinstance(wm, list):
                    _WM_STRIP = frozenset({"embedding", "items"})
                    _WM_MAX_CONTENT = 500
                    _wm_slim = []
                    for _wme in wm:
                        if isinstance(_wme, dict):
                            _s = {k: v for k, v in _wme.items() if k not in _WM_STRIP}
                            if isinstance(_s.get("content"), str) and len(_s["content"]) > _WM_MAX_CONTENT:
                                _s["content"] = _s["content"][:_WM_MAX_CONTENT]
                            _wm_slim.append(_s)
                        else:
                            _wm_slim.append(_wme)
                    save_json(WORKING_MEMORY_FILE, _wm_slim)
            except Exception as e:
                record_failure("ORRIN_loop.save_working_memory", e)

            # ── Affect convergence: integrate this cycle's affect proposals ────
            # Every subsystem that wanted to change affect this cycle submitted a
            # proposal via affect.arbiter.submit_affect() instead of mutating
            # affect_state directly. Commit integrates them all at once (weighted
            # sum nets contradictions), applies the homeostatic stability budget,
            # and queues the result into the affect_buffer so it drains gradually
            # through next cycle's update_affect_state. This is the single commit
            # point that replaces the old last-writer-wins races.
            try:
                from brain.affect.arbiter import commit_affect as _commit_affect
                _commit_affect(context)
            except Exception as _aae:
                record_failure("ORRIN_loop.affect_commit", _aae)

            # Persist context — strip large arrays that live in their own files
            try:
                # Defense-in-depth against context.json bloat: NEVER persist
                # foreign data-stores or context-in-itself. Even if a path pollutes
                # the live context (e.g. a blanket load_all_known_json merge), these
                # keys belong in their OWN files and must not balloon context.json
                # (which the per-cycle save + the 7s daemon load otherwise turn into
                # a memory leak — see meta_reflect fix).
                _CTX_STRIP = (
                    "long_memory", "context", "reflection_log", "habituation",
                    "cognition_history", "attention_history", "speech_log",
                    "causal_graph", "predictions", "knowledge_graph",
                    "symbolic_dream_log", "self_improvement_log", "dream_log",
                    "metacog_log", "chat_log", "memory_graph", "events", "trace",
                    "telemetry_history",
                )
                _ctx_to_save = {k: v for k, v in context.items() if k not in _CTX_STRIP}
                # Cap working_memory in context.json to last 25 entries
                if isinstance(_ctx_to_save.get("working_memory"), list):
                    _ctx_to_save["working_memory"] = _ctx_to_save["working_memory"][-25:]
                # Strip candidates list from last_decision.reason — it holds 200+ entries
                # and is the primary cause of context.json balloon (was 833KB).
                _ld = _ctx_to_save.get("last_decision")
                if isinstance(_ld, dict) and isinstance(_ld.get("reason"), dict):
                    _ld = dict(_ld)
                    _ld["reason"] = {k: v for k, v in _ld["reason"].items() if k != "candidates"}
                    _ctx_to_save["last_decision"] = _ld
                # Automatic bloat containment: the blacklist above only covers
                # *known* offenders, so any new bloat source leaks until someone
                # notices (the 833KB candidates incident). Strip any key whose
                # serialized size exceeds the cap and log its name, so future
                # bloat is contained and identified the cycle it appears.
                import json as _ctx_json
                _CTX_KEY_MAX_BYTES = 100_000
                for _ck in list(_ctx_to_save.keys()):
                    try:
                        _csz = len(_ctx_json.dumps(_ctx_to_save[_ck], default=str))
                    except Exception:
                        continue
                    if _csz > _CTX_KEY_MAX_BYTES:
                        del _ctx_to_save[_ck]
                        log_model_issue(
                            f"context.json bloat guard: stripped key '{_ck}' "
                            f"({_csz} bytes > {_CTX_KEY_MAX_BYTES}) — add it to its "
                            f"own file or to _CTX_STRIP"
                        )
                save_json(CONTEXT, _ctx_to_save)
            except Exception as _e:
                log_model_issue(f"Context save failed: {_e}")

            # ── Long-memory consolidation: every 5 cycles, promote important
            # working-memory entries that haven't been persisted yet.
            # This ensures cognitive observations, insights, and perceptions
            # accumulate into genuine long-term memory even on non-speech cycles.
            try:
                _cons_cycle = get_cycle_count()
                if _cons_cycle > 0 and _cons_cycle % 5 == 0:
                    from brain.cog_memory.long_memory import update_long_memory as _ulm_cons
                    _wm_now = context.get("working_memory") or []
                    for _wme in _wm_now[-10:]:
                        if not isinstance(_wme, dict):
                            continue
                        _wme_content = str(_wme.get("content", "")).strip()
                        _wme_type    = _wme.get("event_type", "thought")
                        _wme_imp     = int(_wme.get("importance", 1) or 1)
                        # Only promote entries with real substance
                        if (
                            _wme_imp >= 3
                            and len(_wme_content) > 60
                            and not _wme.get("_promoted_to_lm")
                            and not _wme.get("internal_telemetry")  # diagnostics/dicts never become autobiographical memory
                            and _wme_type not in ("system", "reward", "reward_penalty", "choice")
                        ):
                            _ulm_cons(
                                _wme_content,
                                event_type=_wme_type,
                                importance=_wme_imp,
                                context=context,
                            )
                            _wme["_promoted_to_lm"] = True
            except Exception as _cons_e:
                record_failure("ORRIN_loop.lm_consolidation", _cons_e)

            # Tick the v2 pulse so watchdogs see the brain is alive
            if pulse is not None:
                try:
                    pulse.tick()
                except Exception as e:
                    record_failure("ORRIN_loop.pulse_tick", e)

            if os.getenv("ORRIN_ONCE") == "1":
                log_activity("Single-cycle mode; exiting after one tick.")
                break

            cycle_num = get_cycle_count()
            print(f"Orrin cognitive cycle {cycle_num} complete.")

            # Periodic GC: force Python to release heap back to OS every 50 cycles.
            # SentenceTransformer's PyTorch allocator expands the heap; gc.collect()
            # ensures Python's reference-counted objects are cleaned up promptly.
            if cycle_num > 0 and cycle_num % 50 == 0:
                try:
                    import gc as _gc
                    _gc.collect()
                    try:
                        import torch as _torch
                        if _torch.cuda.is_available():
                            _torch.cuda.empty_cache()
                    except Exception as _e:
                        record_failure("ORRIN_loop.run_cognitive_loop.40", _e)
                    log_private(f"[loop] GC pass at cycle {cycle_num}")
                except Exception as _e:
                    record_failure("ORRIN_loop.run_cognitive_loop.41", _e)

            if cycle_num > 0 and cycle_num % 100 == 0:
                try:
                    _dump_failure_summary()
                except Exception as _e:
                    record_failure("ORRIN_loop.run_cognitive_loop.42", _e)
                try:
                    _dump_token_summary()
                except Exception as _e:
                    record_failure("ORRIN_loop.run_cognitive_loop.43", _e)
                try:
                    from brain.cognition.self_extension import maybe_integrate_or_atrophy as _mia
                    _mia(context)
                except Exception as _miae:
                    record_failure("ORRIN_loop.integrate_or_atrophy", _miae)
                # Phase 2.2: failure-ledger review. The cadence here only polls
                # the gate — the function itself runs nothing unless ≥3 new
                # failures accumulated since the last review (event-driven).
                try:
                    from brain.cognition.reflection.review_failures import review_failures as _rvf
                    _rvf(context)
                except Exception as _rvfe:
                    record_failure("ORRIN_loop.review_failures", _rvfe)

            # Every 500 cycles (~2-3 hours at 20s/cycle): check for completed
            # fine-tuning jobs and update model_config if one succeeded.
            # Fine-tuning is how Orrin's generation actually changes over time.
            if cycle_num > 0 and cycle_num % 500 == 0:
                try:
                    from brain.cognition.finetuning.finetune_pipeline import check_pending_jobs as _cpj
                    _ft_updates = _cpj()
                    if _ft_updates:
                        log_activity(f"[finetune] Job updates: {_ft_updates}")
                except Exception as _fte:
                    record_failure("ORRIN_loop.finetune_check", _fte)

            # Metabolism (§7, mapping #1): a smaller body runs at a slower metabolic
            # rate — the cadence multiplier stretches the inter-cycle sleep on a small
            # machine and compresses it on a large one. Not distress, just a smaller
            # heart at a lower rate. Fails safe to ×1.0.
            try:
                from brain.cognition.metabolism import cadence_multiplier as _cad
                _cycle_sleep_eff = cycle_sleep * _cad()
            except Exception:
                _cycle_sleep_eff = cycle_sleep
            time.sleep(_cycle_sleep_eff)

        except KeyboardInterrupt:
            print("\nCognitive loop stopped manually.")
            log_activity("Cognitive loop manually interrupted.")
            break

        except Exception as e:
            route_exception(e, phase="loop", context=context)
            _ = try_auto_repair({"type": e.__class__.__name__, "msg": str(e),
                                 "trace": "", "phase": "loop"}, context)
            print(f"Cognitive loop crash: {e}")
            traceback.print_exc()
            log_error(f"Main loop error: {e}")
            log_private("Top-level crash signal.")
            time.sleep(cycle_sleep)

    if _tool_runner is not None:
        try:
            _tool_runner.stop()
        except Exception as e:
            record_failure("ORRIN_loop.tool_runner_stop", e)

    # Session epilogue (master plan Phase 2.1): an ordinary shutdown writes a
    # short reflection and a session_close autobiography entry, so a routine
    # restart stops being a small amnesia. Budgeted (≤10 s) and crash-proof
    # inside session_epilogue itself — it can never block shutdown, so the
    # corrigibility guarantee stays true.
    try:
        from brain.cognition.selfhood.autobiography import session_epilogue
        session_epilogue(context)
    except Exception as e:
        record_failure("ORRIN_loop.session_epilogue", e)

    # Shutdown hygiene (BEHAVIOR_FIX_PLAN §5, "semaphore leak at shutdown"):
    # the project spawns no multiprocessing pools of its own — the leaked
    # semaphore warnings come from sentence-transformers/torch worker state at
    # interpreter exit. Release the embedder model explicitly so its tokenizer
    # parallelism and any lib-internal pools tear down before exit.
    try:
        import brain.utils.embedder as _emb
        for _attr in ("_model", "model", "_MODEL"):
            if hasattr(_emb, _attr):
                setattr(_emb, _attr, None)
        import gc as _gc
        _gc.collect()
    except Exception as e:
        record_failure("ORRIN_loop.embedder_release", e)
