# brain/cognition/prediction.py
#
# Grounded predictive learning — no LLM.
#
# SCIENTIFIC BASIS
# ──────────────────────────────────────────────────────────────────
# Friston (2010) Free Energy Principle / Predictive Processing:
#   The system continuously generates predictions and updates its model
#   based on prediction error. Surprise = large prediction error.
#   Free energy is minimised by improving predictions OR acting to
#   make outcomes match predictions.
#
# Rescorla-Wagner (1972):
#   ΔV = α·β·(λ − V)
#   Learning is proportional to prediction error (λ − V).
#   When prediction accuracy is high, learning rate effectively drops.
#   Implemented: error_magnitude scales learning updates to affect signals.
#
# Tolman (1948) Cognitive Maps:
#   Predictions are not just stimulus-response chains but structured
#   internal representations of the environment that can be flexibly used.
#   Implemented: predictions carry domain tags and causal provenance,
#   not just raw text.
#
# Grounding principle:
#   Predictions must be falsifiable against observable state:
#   event_types in working memory, affect signal values, function outcomes.
#   No LLM interpretation — purely structural comparison.
#
from __future__ import annotations
from core.runtime_log import get_logger

import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from utils.json_utils import load_json, save_json
from utils.log import log_activity, log_private
from utils.signal_utils import create_signal
from cog_memory.long_memory import update_long_memory
from brain.paths import PREDICTIONS_FILE, LONG_MEMORY_FILE, WORKING_MEMORY_FILE
from utils.failure_counter import record_failure
_log = get_logger(__name__)


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


# ─── Prediction generation (symbolic, grounded) ──────────────────────────────

def generate_predictions(
    context: Dict[str, Any],
    recent_wm: List[str],
    emotional_block: str = "",  # kept for API compat — not used
    identity: str = "",
) -> List[Dict]:
    """
    Generate falsifiable predictions from observable patterns — no LLM.

    Sources (in order of reliability):
      1. Event-type frequency: if event_type X appeared in ≥3 of last 10 WM entries,
         predict it appears again next cycle. (Tolman: pattern map)
      2. Causal graph: if function F was just executed, predict its known effects.
         (Pearl Level 1/2 evidence from causal_graph)
      3. Affect trajectory: if a signal has been rising for 3+ cycles, predict
         it continues. (Predictive processing: autoregressive model of internal state)
      4. Decision stats: if avg_reward for current top-selected function < 0.20,
         predict a strategy shift (meta-prediction). (Rescorla-Wagner: V below λ)
    """
    preds: List[Dict] = []

    # Defensive chunk-label guard: WM/causal content embedded into prediction text
    # could carry residual `[Chunk: …]` wrappers (the corruption fixed at source in
    # working_memory). Strip any that slip through so predictions read cleanly and
    # don't poison ToM / self-model downstream.
    try:
        from cog_memory.working_memory import _strip_chunk_label as _san
    except Exception:
        def _san(s):
            return s

    # --- Source 1: Event-type frequency from working memory ---
    wm = load_json(WORKING_MEMORY_FILE, default_type=list) or []
    recent = wm[-15:]
    event_counts: Counter = Counter(
        e.get("event_type", "") for e in recent
        if isinstance(e, dict) and e.get("event_type")
    )
    for etype, count in event_counts.most_common(3):
        if not etype or count < 3:
            continue
        _etype = _san(etype)
        preds.append(_make_pred(
            f"event_type:{_etype}",
            f"Event type '{_etype}' will occur (appeared {count}/15 recent cycles)",
            confidence=min(0.85, 0.4 + count * 0.08),
            horizon="short",
            domain=_classify_domain(_etype),
            basis="frequency",
            source_data={"event_type": _etype, "count": count},
        ))

    # --- Source 2: Causal effects from last executed function ---
    # Prefer the reliable in-context value (the WM "choice" entries this used to
    # parse are no longer written, so parsing always yielded None → zero causal
    # predictions despite a populated causal graph).
    last_fn = (context.get("last_function_chosen")
               or (context.get("recent_picks") or [None])[-1])
    if not last_fn:
        for e in reversed(recent):
            if isinstance(e, dict) and e.get("event_type") == "choice":
                m = re.search(r"Chose:\s*(\S+)", e.get("content", ""))
                if m:
                    last_fn = m.group(1).strip(" —")
                    break

    if last_fn:
        try:
            from symbolic.causal_graph import get_effects
            _affect2 = context.get("affect_state") or {}
            _core2 = _affect2.get("core_signals") or _affect2
            effects = get_effects(last_fn, min_score=0.35)[:2]
            for eff in effects:
                _effect = _san(str(eff["effect"]))
                _sd = {"cause": last_fn, "effect": _effect}
                # Affect-consequence edge ("motivation rises") → make it VERIFIABLE:
                # carry the signal, predicted direction, and its current baseline so the
                # checker can confirm the felt change actually happened next cycle.
                _m = re.match(r"^(\w+)\s+(rises|falls)$", _effect.strip(), re.I)
                if _m and isinstance(_core2, dict) and _m.group(1) in _core2:
                    _dir = "up" if _m.group(2).lower() == "rises" else "down"
                    _sd.update({
                        "signal":    _m.group(1),
                        "direction": _dir,
                        "baseline":  float(_core2.get(_m.group(1), 0.5) or 0.5),
                    })
                    # Phase 1: inner prediction → attach the behavioral corollary
                    # the affect claim implies, so a second checker can grade it.
                    _rcpt = _behavioral_receipt(_m.group(1), _dir)
                    if _rcpt:
                        _sd["receipt"] = _rcpt
                preds.append(_make_pred(
                    f"causal:{last_fn}→{_effect}",
                    f"After '{last_fn}': expect '{_effect[:80]}'",
                    confidence=round(eff["causal_score"] * 0.9, 3),
                    horizon="short",
                    domain="COGNITIVE",
                    basis="causal",
                    source_data=_sd,
                ))
        except Exception as _e:
            record_failure("prediction.generate_predictions", _e)

    # --- Source 3: Affect trajectory prediction ---
    affect = (context.get("affect_state") or {})
    core = affect.get("core_signals") or affect
    if isinstance(core, dict):
        # Get history from recent WM affect snapshots
        signal_history: defaultdict = defaultdict(list)
        for e in recent:
            if not isinstance(e, dict):
                continue
            ec = e.get("emotional_context") or e.get("affective_context") or {}
            for sig, val in ec.items():
                try:
                    signal_history[sig].append(float(val))
                except (ValueError, TypeError) as _e:
                    record_failure("prediction.generate_predictions.2", _e)

        for sig, vals in signal_history.items():
            if len(vals) < 3:
                continue
            recent_trend = vals[-1] - vals[-3]
            current = float(core.get(sig, 0.0) or 0.0)
            if abs(recent_trend) >= 0.10:  # meaningful trend
                direction = "rise" if recent_trend > 0 else "fall"
                predicted_val = round(min(1.0, max(0.0, current + recent_trend * 0.5)), 2)
                _sd3: Dict[str, Any] = {"signal": sig, "current": current,
                                        "trend": recent_trend, "predicted": predicted_val}
                _rcpt3 = _behavioral_receipt(sig, "up" if recent_trend > 0 else "down")
                if _rcpt3:
                    _sd3["receipt"] = _rcpt3
                # Confidence prior scaled by the learned introspection-trust
                # score (Phase 1.3): 0.60 at neutral trust, [0.30, 0.90] range —
                # affect-derived claims are believed as much as the receipts
                # say introspection has earned.
                try:
                    from cognition.calibration import get_introspection_trust
                    _conf3 = 0.30 + 0.60 * get_introspection_trust("INTERNAL")
                except Exception:
                    _conf3 = 0.60
                preds.append(_make_pred(
                    f"affect_trend:{sig}:{direction}",
                    f"Affect signal '{sig}' will {direction} (trend={recent_trend:+.2f}, predicted≈{predicted_val})",
                    confidence=_conf3,
                    horizon="short",
                    domain="INTERNAL",
                    basis="affect_trend",
                    source_data=_sd3,
                ))

    # --- Source 4: Strategy-shift meta-prediction (Rescorla-Wagner) ---
    try:
        from brain.paths import DECISION_STATS_FILE
        stats = load_json(DECISION_STATS_FILE, default_type=dict) or {}
        # Last selected function
        if last_fn and last_fn in stats:
            avg_r = float(stats[last_fn].get("avg_reward", 0.5))
            if avg_r < 0.20:
                preds.append(_make_pred(
                    f"strategy_shift:{last_fn}",
                    f"Strategy shift likely — '{last_fn}' has avg_reward={avg_r:.2f} (below λ=0.20)",
                    confidence=0.65,
                    horizon="short",
                    domain="PLANNING",
                    basis="reward_error",
                    source_data={"function": last_fn, "avg_reward": avg_r},
                ))
    except Exception as _e:
        record_failure("prediction.generate_predictions.3", _e)

    return preds[:6]  # cap at 6 per generation round


def _make_pred(
    pred_id: str,
    text: str,
    confidence: float,
    horizon: str,
    domain: str,
    basis: str,
    source_data: dict,
) -> Dict:
    return {
        "prediction":  text,
        "pred_id":     pred_id,
        "horizon":     horizon,
        "confidence":  round(confidence, 3),
        "created_ts":  datetime.now(timezone.utc).isoformat(),
        "status":      "pending",
        "checked_ts":  None,
        "outcome":     None,
        "domain":      domain,
        "basis":       basis,
        "source_data": source_data,
        "resolved":    False,
        "correct":     None,
        "mismatch_score": None,
    }


def save_predictions(new_preds: List[Dict]) -> None:
    if not new_preds:
        return
    existing = load_json(PREDICTIONS_FILE, default_type=list) or []
    existing.extend(new_preds)
    save_json(PREDICTIONS_FILE, existing[-150:])
    log_activity(f"[prediction] Saved {len(new_preds)} symbolic prediction(s).")


# ─── Prediction checking (symbolic, grounded) ────────────────────────────────

# ─── Rule distillation: confirmed predictions → symbolic rules (#9 Phase 1) ──
#
# The self-improvement loop was starved — it rehabilitates/prunes rules but almost
# nothing flowed IN. The most grounded source of new rules is a prediction that
# keeps coming true: a *verified* regularity. Track per-causal-pattern confirms vs
# fails; once a causal prediction has been confirmed enough times, distill it into
# a symbolic rule (cause → effect). This is the foundation the gated metacog and
# peer-observer producers (Phases 2/3) build on.

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
                from symbolic.rule_engine import add_rule
                from symbolic.ground_truth import grounding_score as _gs
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


def check_predictions(context: Dict[str, Any]) -> int:
    """
    Evaluate pending predictions against observable state — no LLM.
    Returns number of surprises (large prediction errors).

    Friston: prediction error = |predicted - actual|.
    Error is injected into context as a surprise signal that modulates
    affect signals (exploration_drive ↑, confidence ↓ on miss).

    Rescorla-Wagner: ΔV = α·β·(λ − V) — the surprise magnitude scales
    the size of affect updates, so high error = larger learning signal.
    """
    predictions = load_json(PREDICTIONS_FILE, default_type=list) or []
    pending = [p for p in predictions if p.get("status") == "pending"]
    if not pending:
        return 0

    recent_events = _gather_observable_state(context)
    surprises = 0
    ts = datetime.now(timezone.utc).isoformat()
    _evaluated_mismatches: List[float] = []   # Fix 6: this call's resolved mismatches

    for pred in pending:
        horizon = pred.get("horizon", "short")
        created = pred.get("created_ts", "")
        age_h = _age_hours(created)

        if horizon == "short" and age_h < 0.08:   # ~5 min
            continue
        if horizon == "medium" and age_h < 4:
            continue
        if horizon == "long" and age_h < 20:
            continue

        came_true, mismatch = _evaluate_symbolically(pred, recent_events, context)
        pred["status"] = "evaluated"
        pred["checked_ts"] = ts
        pred["resolved"] = True
        pred["correct"] = came_true
        pred["mismatch_score"] = round(mismatch, 3)
        pred["outcome"] = "correct" if came_true else f"mismatch={mismatch:.2f}"
        _evaluated_mismatches.append(float(mismatch))   # Fix 6

        # Phase 1.3/1.4: introspection-trust ledger + disagreement events.
        # When an inner prediction carries both verdicts, their agreement rate
        # is the per-domain trust score; felt-yes/behaved-no is surfaced as an
        # introspection_miss event.
        _felt = pred.get("felt_true")
        _behaved = pred.get("behaved_true")
        _is_inner = pred.get("basis") in ("affect_trend", "causal") and _felt is not None
        _stat_weight = 1.0
        if _is_inner:
            if _behaved is None:
                _stat_weight = 0.5   # self-report alone earns at most half-weight
            else:
                try:
                    from cognition.calibration import update_introspection_trust
                    update_introspection_trust(pred.get("domain") or "INTERNAL",
                                               bool(_felt) == bool(_behaved))
                except Exception as _e:
                    record_failure("prediction.check_predictions.trust", _e)
                if _felt and not _behaved:
                    _fire_introspection_miss(pred, context)

        # Update domain accuracy stats
        try:
            from symbolic.prediction_engine import update_domain_stats, classify_domain
            domain = pred.get("domain") or classify_domain(pred.get("prediction", ""))
            update_domain_stats(domain, came_true, basis=pred.get("basis", "symbolic"),
                                mismatch_score=mismatch, weight=_stat_weight)
        except Exception as _e:
            record_failure("prediction.check_predictions", _e)

        # Feed back to causal graph
        try:
            from symbolic.causal_graph import update_from_prediction_outcome
            update_from_prediction_outcome(pred, came_true)
        except Exception as _e:
            record_failure("prediction.check_predictions.2", _e)

        # Distill confirmed causal predictions into symbolic rules (#9 Phase 1).
        _distill_confirmed_prediction(pred, came_true)

        # Master plan 3.1: grounded outcomes feed the opinion evidence ledger.
        # Inner predictions qualify only when receipt-confirmed (behaved_true
        # was graded); outer ones are already scored against observables.
        try:
            if (not _is_inner) or (_behaved is not None):
                from cognition.opinions import ingest_prediction_outcome
                ingest_prediction_outcome(
                    pred.get("prediction", ""), came_true,
                    ref_id=str(pred.get("id") or pred.get("created_ts") or ts),
                    context=context,
                )
        except Exception as _e:
            record_failure("prediction.opinion_evidence", _e)

        # Surprise signal when mismatch is large (Friston: free energy spike)
        if mismatch >= 0.5:
            surprises += 1
            _fire_surprise(pred.get("prediction", ""), mismatch, context)

    # Fix 6 (explore_loop_fix_plan.md §5): prediction-failure → policy feedback.
    # Sustained per-goal prediction failure ("my predictions about this keep failing")
    # should become a reason to STOP, not just affective surprise (E5). Maintain a
    # per-goal mismatch EMA on the Monitor state; when it stays high over several
    # resolutions, feed the committed goal's Fix-2 escalation counter (one bump per
    # crossing — sustained failure, never a single miss). Goal-scoped because the
    # prediction schema carries no (action, goal) key, so per-action payoff-lowering
    # would need new scoped state (noted in the plan's Fix 6 caveat). Flag-gated with
    # the same switch as the hard escalator it feeds.
    try:
        import os as _os
        # Default ON (opt out with ORRIN_HARD_DISENGAGE=0) — same gate as metacog's
        # hard escalator this feeds.
        _on = _os.environ.get("ORRIN_HARD_DISENGAGE", "1").strip().lower() not in ("0", "false", "no", "off")
        _gd = context.get("committed_goal") if isinstance(context, dict) else None
        if _on and _evaluated_mismatches and isinstance(_gd, dict) and (_gd.get("id") or _gd.get("title")):
            _miss = sum(_evaluated_mismatches) / len(_evaluated_mismatches)
            _gid = str(_gd.get("id") or _gd.get("title") or "goal")
            _gs = context.setdefault("_monitor_state", {}).setdefault(
                _gid, {"sig": None, "stall": 0, "met": 0, "prog": None})
            _ema = _gs.get("pred_ema")
            _ema = round(_miss if _ema is None else 0.6 * _ema + 0.4 * _miss, 3)
            _gs["pred_ema"] = _ema
            _gs["pred_runs"] = int(_gs.get("pred_runs", 0)) + 1
            if _ema > 0.6 and _gs["pred_runs"] >= 3:
                _gs["stall"] = int(_gs.get("stall", 0)) + 2
                _gs["pred_runs"] = 0   # re-accumulate; don't bump every cycle
                from utils.log import log_private as _lp
                _lp(f"[prediction] sustained mismatch EMA={_ema} on '{_gid}' → +2 stall (Fix 6 → Fix 2).")
    except Exception as _e:
        record_failure("prediction.check_predictions.3", _e)

    save_json(PREDICTIONS_FILE, predictions[-150:])
    return surprises


def _evaluate_symbolically(
    pred: Dict,
    recent_events: Dict[str, Any],
    context: Dict[str, Any],
) -> Tuple[bool, float]:
    """
    Match prediction against observable state without LLM.
    Returns (came_true, mismatch_score 0.0–1.0).

    Matching strategy by prediction basis:
      frequency  — check if event_type appears in recent WM
      causal     — check if predicted effect event_type appeared
      affect_trend — compare predicted vs actual signal value
      reward_error — check if a different function was selected
    """
    basis = pred.get("basis", "frequency")
    source = pred.get("source_data") or {}
    wm_etypes = set(recent_events.get("event_types", []))
    cognition_log = recent_events.get("cognition_log", [])
    affect = context.get("affect_state") or {}
    core = affect.get("core_signals") or affect

    if basis == "frequency":
        etype = source.get("event_type", "")
        if not etype:
            return True, 0.3
        hit = etype in wm_etypes
        return hit, (0.0 if hit else 0.8)

    elif basis == "causal":
        # Affect-consequence edge ("motivation rises"): two-channel resolution
        # (Phase 1.2). felt_true = the self-reported signal moved as predicted;
        # behaved_true = the behavioral receipt agrees (graded against
        # cognition_log — something he can't argue with). Both verdicts are
        # recorded on the prediction; the combined verdict counts the
        # prediction correct only when the receipt agrees.
        _sig = source.get("signal")
        if _sig and _sig in core:
            baseline  = float(source.get("baseline", 0.5) or 0.5)
            actual    = float(core.get(_sig, baseline) or baseline)
            delta     = actual - baseline
            want_up   = source.get("direction", "up") == "up"
            moved     = delta if want_up else -delta
            felt_true = moved >= 0.02
            felt_mismatch = round(min(1.0, max(0.0, 0.02 - moved) * 5), 3)
            return _resolve_inner(pred, felt_true, felt_mismatch, context)
        # Fallback (dream/temporal event→event edges): token match against recent WM.
        effect = source.get("effect", "").lower()
        if not effect:
            return True, 0.3
        effect_tokens = set(re.findall(r"[a-z][a-z0-9]+", effect)) - {"the", "a", "an"}
        hit = any(
            effect_tokens & set(re.findall(r"[a-z][a-z0-9]+", str(e).lower()))
            for e in recent_events.get("wm_contents", [])
        )
        return hit, (0.0 if hit else 0.7)

    elif basis == "affect_trend":
        sig = source.get("signal", "")
        predicted_val = float(source.get("predicted", 0.5) or 0.5)
        actual_val = float(core.get(sig, 0.5) or 0.5)
        if not sig or sig not in core:
            return True, 0.3
        error = abs(predicted_val - actual_val)
        # Rescorla-Wagner: λ=actual, V=predicted, error=(λ-V)
        felt_true = error < 0.15
        return _resolve_inner(pred, felt_true, round(min(1.0, error * 2), 3), context)

    elif basis == "reward_error":
        fn = source.get("function", "")
        # Prediction was: strategy shift likely. Check if a different function ran.
        if cognition_log:
            last_ran = cognition_log[-1] if isinstance(cognition_log[-1], str) else (
                cognition_log[-1].get("choice", "") if isinstance(cognition_log[-1], dict) else ""
            )
            if last_ran and last_ran != fn:
                return True, 0.0  # strategy did shift
        return False, 0.5

    return True, 0.4  # unknown basis — treat as weak correct


def _resolve_inner(
    pred: Dict,
    felt_true: bool,
    felt_mismatch: float,
    context: Dict[str, Any],
) -> Tuple[bool, float]:
    """
    Two-channel resolution for inner (affect) predictions (Phase 1.2).

    Records felt_true (self-report) and behaved_true (receipt verdict) on the
    prediction. Combined verdict: correct only when the receipt agrees; when no
    receipt exists or behavior is too sparse to grade, the felt verdict stands
    alone (check_predictions weights it at half).
    """
    pred["felt_true"] = bool(felt_true)
    receipt = (pred.get("source_data") or {}).get("receipt")
    behaved: Optional[bool] = None
    if isinstance(receipt, dict):
        behaved = _receipt_verdict(receipt, context)
    pred["behaved_true"] = behaved

    if behaved is None:
        return felt_true, felt_mismatch
    if behaved and felt_true:
        return True, felt_mismatch
    if behaved and not felt_true:
        # Body moved but the feeling claim missed — partial credit; the
        # behavior is the senior channel but the stated claim was about affect.
        return False, min(felt_mismatch, 0.5)
    # Receipt says no. Felt-yes/behaved-no is the introspection-miss case:
    # the claim "counted" internally but nothing observable backed it.
    return False, max(felt_mismatch, 0.6)


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
        from cog_memory.working_memory import update_working_memory
        update_working_memory({
            "content": text,
            "event_type": "introspection_miss",
            "importance": 3,
            "priority": 2,
        })
    except Exception as _e:
        record_failure("prediction._fire_introspection_miss", _e)
    try:
        from affect.arbiter import submit_affect
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
    except Exception:
        return 999.0
