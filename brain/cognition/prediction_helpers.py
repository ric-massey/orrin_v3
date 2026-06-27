# brain/cognition/prediction_helpers.py
#
# Leaf support helpers for prediction.py (CODEBASE_CLEANUP_PLAN 4.5C), lifted
# verbatim to bring that module under the 600-line soft limit. Three independent
# concerns, each only called from generate_predictions / check_predictions:
#
#   Behavioral receipts — the "second checker" (master plan Phase 1): grade an
#       inner affect prediction against an observable behavioral corollary read
#       from the cognition log, instead of reading affect_state back on itself.
#   Rule distillation — tally resolved predictions and promote a repeatedly
#       confirmed regularity into a symbolic rule (rule_candidates.json).
#   Surprise/miss firing + observable-state gathering — emit the affect signals
#       and WM/long-memory notes a prediction error produces, build the grounded
#       observable-state dict, classify domain, and age predictions.
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_activity, log_private
from brain.utils.signal_utils import create_signal
from brain.cog_memory.long_memory import update_long_memory
from brain.paths import LONG_MEMORY_FILE, WORKING_MEMORY_FILE
from brain.utils.failure_counter import record_failure


# ─── Behavioral receipts (master plan Phase 1: the second checker) ───────────
#
# Inner predictions (affect_trend / affect-causal) used to be graded by reading
# context["affect_state"] back — scientist and subject were the same variable
# read twice, so the 46% inner / 87% outer accuracy gap could never close.
# Each inner prediction now carries a *behavioral corollary*: an observable the
# affect claim implies, drawn from a small fixed table and checked against
# cognition_log — the same machinery the 87%-accurate outer predictions use.

_RECEIPT_WINDOW = 8   # cognition_log picks inspected when grading a receipt

# Goal-pursuit picks: what "motivation rises" should look like from outside.
_RECEIPT_PURSUE_FNS = frozenset({
    "assess_goal_progress", "plan_next_step", "adapt_subgoals",
    "select_focus_goals", "maybe_complete_goals", "generate_intrinsic_goals",
})
# Exploration picks: what "exploration_drive rises" should look like.
_RECEIPT_EXPLORE_FNS = frozenset({
    "look_outward", "look_around", "seek_novelty", "search_own_files",
    "research_topic", "wikipedia_search", "fetch_and_read", "read_a_book",
})
# Deliberation picks: low confidence shows up as deliberation crowding action
# (meta_controller already implements "confidence drops → deliberate more").
_RECEIPT_DELIBERATION_FNS = frozenset({
    "assess_goal_progress", "adapt_subgoals", "adjust_goal_weights",
    "abduce", "reflection", "self_review", "narrative_update",
    "reflect_on_directive", "reflect_on_affect", "metacog_flush",
    "introspective_planning", "associative_recall", "plan_next_step",
})

_RECEIPT_TABLE: Dict[Tuple[str, str], Tuple[str, str]] = {
    ("motivation", "up"):           ("pursue_pick",     "a goal-pursuit action is selected"),
    ("motivation", "down"):         ("no_pursue_pick",  "no goal-pursuit action is selected"),
    ("impasse_signal", "up"):       ("switch_rate_up",  "function switching rate rises"),
    ("impasse_signal", "down"):     ("switch_rate_down","function switching rate stays normal"),
    ("confidence", "down"):         ("deliberation_up", "deliberation crowds out action"),
    ("confidence", "up"):           ("deliberation_down","action outweighs deliberation"),
    ("exploration_drive", "up"):    ("explore_pick",    "an exploration action is selected"),
    ("exploration_drive", "down"):  ("no_explore_pick", "no exploration action is selected"),
}


def _behavioral_receipt(signal: str, direction: str) -> Optional[Dict[str, Any]]:
    """Return the receipt dict for an inner prediction, or None when the fixed
    table has no observable corollary for this signal."""
    entry = _RECEIPT_TABLE.get((signal, direction))
    if entry is None:
        return None
    kind, expected = entry
    return {"kind": kind, "expected": expected, "window": _RECEIPT_WINDOW}


def _recent_picks(context: Dict[str, Any], window: int) -> List[str]:
    """Last `window` deliberate-lane picks, from context or the history file."""
    log = context.get("cognition_log")
    if not isinstance(log, list) or not log:
        try:
            from brain.paths import COGNITION_HISTORY_FILE
            log = load_json(COGNITION_HISTORY_FILE, default_type=list) or []
        except Exception:
            log = []
    picks: List[str] = []
    for e in log[-window:]:
        if isinstance(e, dict) and e.get("choice"):
            picks.append(str(e["choice"]))
        elif isinstance(e, str) and e:
            picks.append(e)
    return picks


def _receipt_verdict(
    receipt: Dict[str, Any],
    context: Dict[str, Any],
) -> Optional[bool]:
    """Grade a behavioral receipt against the cognition log.
    Returns None when there isn't enough recorded behavior to grade."""
    kind = str(receipt.get("kind") or "")
    window = int(receipt.get("window") or _RECEIPT_WINDOW)
    picks = _recent_picks(context, window)
    if len(picks) < 3:
        return None
    distinct_ratio = len(set(picks)) / len(picks)
    delib_share = sum(1 for p in picks if p in _RECEIPT_DELIBERATION_FNS) / len(picks)

    if kind == "pursue_pick":
        return any(p in _RECEIPT_PURSUE_FNS for p in picks)
    if kind == "no_pursue_pick":
        return not any(p in _RECEIPT_PURSUE_FNS for p in picks)
    if kind == "explore_pick":
        return any(p in _RECEIPT_EXPLORE_FNS for p in picks)
    if kind == "no_explore_pick":
        return not any(p in _RECEIPT_EXPLORE_FNS for p in picks)
    if kind == "switch_rate_up":
        return distinct_ratio >= 0.7
    if kind == "switch_rate_down":
        return distinct_ratio < 0.7
    if kind == "deliberation_up":
        return delib_share >= 0.5
    if kind == "deliberation_down":
        return delib_share < 0.5
    return None


# ─── Rule distillation ───────────────────────────────────────────────────────

_RULE_CANDIDATES_FILE = None  # resolved lazily (paths.DATA_DIR)
_CONFIRMS_TO_PROMOTE = 3


def _candidates_path():
    global _RULE_CANDIDATES_FILE
    if _RULE_CANDIDATES_FILE is None:
        from brain.paths import DATA_DIR
        _RULE_CANDIDATES_FILE = DATA_DIR / "rule_candidates.json"
    return _RULE_CANDIDATES_FILE


# Internal plumbing event types — predicting these recur is noise, not insight
# (e.g. `event_type:chunk` is an artifact of the chunk machinery itself). They must
# never be distilled into rules.
_PLUMBING_EVENT_TYPES = frozenset({
    "chunk", "metacog_trace", "metacog_pattern", "wm_overflow",
    "wm_overflow_digest", "system", "reward", "reward_penalty",
    "choice", "function_selected", "function_executed", "thought",
})


def _rule_from_pred(pattern: str, sd: Dict) -> Optional[Tuple[List[str], str, Optional[Dict]]]:
    """
    Map a resolved prediction to a (conditions, conclusion, causal_claim) rule shape.
    Returns None when the prediction carries no distillable structure (e.g. the
    structureless symbolic preds) or is plumbing noise. Broadens distillation beyond
    causal so confirmed regularities of several kinds feed self-improvement, while a
    plumbing filter keeps junk out.
    """
    if pattern.startswith("causal:"):
        cause  = str(sd.get("cause") or "").strip()
        effect = str(sd.get("effect") or "").strip()
        if cause and effect:
            return ([f"function:{cause}"], effect, {"cause": cause, "effect": effect})
        return None
    if pattern.startswith("affect_trend:"):
        signal = str(sd.get("signal") or "").strip()
        trend  = float(sd.get("trend") or 0.0)
        if signal:
            direction = "rise" if trend >= 0 else "fall"
            return ([f"affect_trend:{signal}:{direction}"],
                    f"When '{signal}' is trending {direction}, it tends to continue.",
                    None)
        return None
    if pattern.startswith("event_type:"):
        etype = str(sd.get("event_type") or "").strip()
        if etype and etype not in _PLUMBING_EVENT_TYPES:
            return ([f"event_recent:{etype}"],
                    f"'{etype}' events tend to recur in clusters.", None)
        return None
    return None


def _distill_confirmed_prediction(pred: Dict, came_true: bool) -> None:
    """
    Tally a resolved prediction and promote it to a symbolic rule once it has been
    confirmed `_CONFIRMS_TO_PROMOTE` times. Handles causal, affect-trend, and
    (non-plumbing) frequency predictions — whichever carry distillable structure.
    Persistent failures retire the candidate so noise never gets promoted.
    """
    pattern = str(pred.get("pred_id") or "")
    sd = pred.get("source_data") or {}
    shape = _rule_from_pred(pattern, sd)
    if shape is None:
        return  # no distillable structure (structureless symbolic / plumbing)
    conditions, conclusion, causal_claim = shape
    try:
        cands = load_json(_candidates_path(), default_type=dict) or {}
        if not isinstance(cands, dict):
            cands = {}
        rec = cands.get(pattern) or {"confirms": 0, "fails": 0, "promoted": False}

        if came_true:
            rec["confirms"] = int(rec.get("confirms", 0)) + 1
        else:
            rec["fails"] = int(rec.get("fails", 0)) + 1

        # Retire a candidate that fails far more than it confirms — it's noise.
        if rec["fails"] >= 3 and rec["fails"] > rec["confirms"] * 2 and not rec.get("promoted"):
            cands.pop(pattern, None)
            save_json(_candidates_path(), cands)
            return

        if rec["confirms"] >= _CONFIRMS_TO_PROMOTE and not rec.get("promoted"):
            try:
                from brain.symbolic.rule_engine import add_rule
                from brain.symbolic.ground_truth import grounding_score as _gs
                try:
                    _g = float(_gs(pattern))
                except Exception:
                    _g = 0.0
                add_rule(
                    conditions=conditions,
                    conclusion=conclusion,
                    source="confirmed_prediction",
                    confidence=round(min(0.85, 0.6 + 0.2 * _g), 3),
                    causal_claim=causal_claim,
                    prediction=conclusion,
                )
                rec["promoted"] = True
                log_activity(
                    f"[prediction→rule] Distilled confirmed prediction into rule "
                    f"({pattern.split(':')[0]}): '{conclusion[:60]}' "
                    f"({rec['confirms']} confirms)"
                )
            except Exception as _e:
                record_failure("prediction._distill_confirmed_prediction", _e)

        cands[pattern] = rec
        save_json(_candidates_path(), cands)
    except Exception as _e:
        record_failure("prediction._distill_confirmed_prediction.2", _e)


# ─── Surprise firing + observable state ──────────────────────────────────────

def _fire_introspection_miss(pred: Dict, context: Dict[str, Any]) -> None:
    """
    Phase 1.4: felt yes / behaved no — disagreement is itself an event.
    Writes an introspection_miss WM entry (metacog already consumes WM event
    types) and a small surprise spike through the arbiter.
    """
    receipt = (pred.get("source_data") or {}).get("receipt") or {}
    text = (
        f"I thought '{pred.get('prediction', '')[:90]}' — and it felt true — "
        f"but behavior disagreed (expected: {receipt.get('expected', '?')})."
    )
    try:
        from brain.cog_memory.working_memory import update_working_memory
        update_working_memory({
            "content": text,
            "event_type": "introspection_miss",
            "importance": 3,
            "priority": 2,
        })
    except Exception as _e:
        record_failure("prediction._fire_introspection_miss", _e)
    try:
        from brain.control_signals.arbiter import submit_affect
        submit_affect(context, "exploration_drive", +0.04, source="introspection_miss")
        submit_affect(context, "confidence", -0.03, source="introspection_miss")
    except Exception as _e:
        record_failure("prediction._fire_introspection_miss.2", _e)
    log_private(f"[prediction] introspection miss: {text}")


def _fire_surprise(prediction_text: str, mismatch: float, context: Dict[str, Any]) -> None:
    """
    Friston: large prediction error = surprise signal.
    Rescorla-Wagner: error magnitude (λ - V) scales the learning update.
    Surprise raises exploration_drive and wonder (exploration drive), reduces confidence.
    """
    # α·β·(λ − V): scale affect updates by mismatch magnitude
    rw_scale = min(1.0, mismatch)

    try:
        sig = create_signal(
            source="prediction_check",
            content=f"[surprise] Predicted: '{prediction_text[:80]}' — mismatch={mismatch:.2f}",
            signal_strength=round(0.5 + mismatch * 0.5, 2),
            tags=["surprise", "prediction_miss", "internal"],
        )
        context.setdefault("raw_signals", []).append(sig)
    except Exception as _e:
        record_failure("prediction._fire_surprise", _e)

    # Affect updates scaled by prediction error (Rescorla-Wagner)
    affect = context.get("affect_state") or {}
    core = affect.get("core_signals") or affect
    for sig_name, delta in [
        ("exploration_drive",  +0.10 * rw_scale),
        ("wonder",     +0.08 * rw_scale),
        ("confidence", -0.06 * rw_scale),
    ]:
        v = float(core.get(sig_name, 0.0) or 0.0)
        core[sig_name] = max(0.0, min(1.0, v + delta))
    if "core_signals" in affect:
        affect["core_signals"] = core
    else:
        affect.update(core)
    context["affect_state"] = affect

    update_long_memory(
        f"[prediction error] '{prediction_text[:100]}' did not materialise (mismatch={mismatch:.2f}). "
        f"Updating internal model.",
        emotion="exploration_drive",
        event_type="prediction_error",
        importance=3,
        context=context,
    )
    log_private(f"[prediction] Surprise: mismatch={mismatch:.2f}, text='{prediction_text[:60]}'")


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _gather_observable_state(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build the observable state dict for prediction evaluation.
    This is what predictions are checked against — grounded in actual data.
    """
    wm = load_json(WORKING_MEMORY_FILE, default_type=list) or []
    recent = wm[-20:]

    event_types = [e.get("event_type", "") for e in recent if isinstance(e, dict)]
    wm_contents = [e.get("content", "") for e in recent if isinstance(e, dict) and e.get("content")]

    # Also pull recent long memory event types
    long_mem = load_json(LONG_MEMORY_FILE, default_type=list) or []
    for e in long_mem[-5:]:
        if isinstance(e, dict) and e.get("event_type"):
            event_types.append(e["event_type"])

    cognition_log = context.get("cognition_log") or []

    return {
        "event_types":    list(set(filter(None, event_types))),
        "wm_contents":    wm_contents,
        "cognition_log":  cognition_log,
    }


def _classify_domain(text: str) -> str:
    lower = text.lower()
    if any(w in lower for w in ["user", "ric", "social", "talk", "conversation"]):
        return "SOCIAL"
    if any(w in lower for w in ["goal", "plan", "pursue", "commit"]):
        return "PLANNING"
    if any(w in lower for w in ["affect", "mood", "exploration_drive", "risk_estimate", "wonder"]):
        return "INTERNAL"
    if any(w in lower for w in ["code", "file", "error", "function", "module"]):
        return "TECHNICAL"
    return "COGNITIVE"


def _age_hours(created_ts: str) -> float:
    if not created_ts:
        return 999.0
    try:
        created = datetime.fromisoformat(created_ts.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - created).total_seconds() / 3600.0
    except (ValueError, TypeError, AttributeError):  # intentional: unparseable timestamp → far-past sentinel
        return 999.0
