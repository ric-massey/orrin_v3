# brain/think/meta_controller.py
# Decides what the inner loop should do after each draft round.
#
# Four decisions:
#   "think_more" — run another critique+revise cycle (rounds remain)
#   "act"        — content is ready; fire the best available action now
#   "output"     — content is ready; write to working memory, no external action
#   "defer"      — nothing actionable this cycle; skip quietly
#
# Architecture
# ────────────
# 1.  _ThresholdBandit (UCB1) — learns which threshold configuration produces
#     the best outcomes.  Four arms map to (think_more_thresh, output_thresh)
#     pairs.  reward_outcome() updates the bandit after each completed cycle.
#
# 2.  _EWMASuccessRate — rolling exponential average of cycle success rate.
#     Feeds into the bandit as a meta-signal (high success → tighten thresholds).
#
# 3.  simulate_outcome() — optional: run a quick lookahead before "act" to
#     verify the decision is safe.  Triggered when:
#       - debt >= 2, confidence > 0.55, and at least 1 round remains.
#
# 4.  recommend_rounds() — suggestion from this module to inner_loop about how
#     many rounds it should run (separate from depth_bandit, which uses harder
#     outcome data).  Based on current EWMA success rate.
from __future__ import annotations
from core.runtime_log import get_logger

import math
import time
from typing import Any, Dict, List, Literal, Optional, Tuple

from utils.json_utils import load_json, save_json
from utils.log import log_private
from paths import DATA_DIR
from utils.failure_counter import record_failure
_log = get_logger(__name__)

MetaDecision = Literal["think_more", "act", "output", "defer"]

_BANDIT_FILE = DATA_DIR / "meta_ctrl_bandit.json"
_EWMA_FILE   = DATA_DIR / "meta_ctrl_ewma.json"
_EWMA_ALPHA  = 0.15     # smoothing factor for EWMA (lower = slower adaptation)
_UCB_C       = 1.6      # exploration coefficient for threshold bandit

# ── Threshold arm definitions ─────────────────────────────────────────────────
# (arm_id, think_more_conf_threshold, output_conf_threshold)
# think_more fires when confidence < think_more_threshold AND round_num < max
# output    fires when confidence > output_threshold
_ARMS: List[Tuple[int, float, float]] = [
    (0, 0.38, 0.80),   # aggressive: act quickly, demand high confidence to output
    (1, 0.48, 0.74),   # balanced
    (2, 0.58, 0.68),   # thoughtful: think more often, lower output bar
    (3, 0.65, 0.62),   # deep-thinker: always prefers more thinking
]
_DEFAULT_ARM = 1   # arm used during seed phase / on error


# ── ThresholdBandit ───────────────────────────────────────────────────────────

class _ThresholdBandit:
    """UCB1 bandit over threshold-arm configurations."""

    def __init__(self) -> None:
        self._stats: Dict[str, Dict] = {}
        self._load()

    def _load(self) -> None:
        raw = load_json(_BANDIT_FILE, default_type=dict) or {}
        for arm_id, _, _ in _ARMS:
            key = str(arm_id)
            blk = raw.get(key, {})
            self._stats[key] = {
                "count":      float(blk.get("count", 0)),
                "total":      float(blk.get("total", 0)),
                "avg_reward": float(blk.get("avg_reward", 0.5)),
            }

    def _save(self) -> None:
        try:
            save_json(_BANDIT_FILE, self._stats)
        except Exception as _e:
            record_failure("meta_controller._ThresholdBandit._save", _e)

    def choose(self) -> int:
        """Return arm_id via UCB1; falls back to _DEFAULT_ARM on error."""
        try:
            total = sum(s["count"] for s in self._stats.values())
            # Seed phase
            for arm_id, _, _ in _ARMS:
                if self._stats[str(arm_id)]["count"] < 2:
                    return arm_id

            best_id, best_ucb = _DEFAULT_ARM, -1.0
            for arm_id, _, _ in _ARMS:
                s = self._stats[str(arm_id)]
                if s["count"] == 0:
                    return arm_id
                ucb = s["avg_reward"] + _UCB_C * math.sqrt(math.log(total) / s["count"])
                if ucb > best_ucb:
                    best_ucb = ucb
                    best_id  = arm_id
            return best_id
        except Exception:
            return _DEFAULT_ARM

    def update(self, arm_id: int, reward: float) -> None:
        r = max(-1.0, min(1.0, float(reward)))
        key = str(arm_id)
        s = self._stats.setdefault(key, {"count": 0, "total": 0, "avg_reward": 0.5})
        s["count"]     += 1
        s["total"]     += r
        s["avg_reward"] = s["total"] / s["count"]
        self._save()
        log_private(
            f"[meta_ctrl/bandit] arm={arm_id} reward={r:.3f} "
            f"→ avg={s['avg_reward']:.3f} (n={int(s['count'])})"
        )

    def thresholds(self, arm_id: int) -> Tuple[float, float]:
        """Return (think_more_thresh, output_thresh) for the given arm."""
        for aid, tm, op in _ARMS:
            if aid == arm_id:
                return tm, op
        return _ARMS[_DEFAULT_ARM][1], _ARMS[_DEFAULT_ARM][2]


# ── EWMA success tracker ──────────────────────────────────────────────────────

class _EWMASuccessRate:
    """Exponentially-weighted moving average of binary cycle success (reward > 0)."""

    def __init__(self) -> None:
        self._rate: float = 0.60   # initial assumption: 60% success
        self._load()

    def _load(self) -> None:
        try:
            raw = load_json(_EWMA_FILE, default_type=dict) or {}
            self._rate = max(0.0, min(1.0, float(raw.get("rate", 0.60))))
        except Exception as _e:
            record_failure("meta_controller._EWMASuccessRate._load", _e)

    def _save(self) -> None:
        try:
            save_json(_EWMA_FILE, {"rate": round(self._rate, 4), "updated": time.time()})
        except Exception as _e:
            record_failure("meta_controller._EWMASuccessRate._save", _e)

    def update(self, success: bool) -> None:
        signal = 1.0 if success else 0.0
        self._rate = (1.0 - _EWMA_ALPHA) * self._rate + _EWMA_ALPHA * signal
        self._save()

    @property
    def rate(self) -> float:
        return self._rate


# ── Module-level singletons ───────────────────────────────────────────────────

_bandit = _ThresholdBandit()
_ewma   = _EWMASuccessRate()


# ── Helpers ───────────────────────────────────────────────────────────────────

_UNCERTAINTY_SIGNALS = frozenset({
    "maybe", "might", "unclear", "not sure", "unsure", "perhaps",
    "could be", "i think", "possibly", "uncertain", "hard to say",
    "i'm not", "i am not", "difficult to say",
})


def _draft_confidence(context: Dict[str, Any]) -> float:
    """0.0=very uncertain, 1.0=very confident based on scratchpad latest draft."""
    pad = context.get("_scratchpad") or []
    drafts = [e for e in pad if e.get("role") in ("draft", "revision")]
    if not drafts:
        return 0.5
    latest = drafts[-1].get("content", "").lower()
    hits = sum(1 for s in _UNCERTAINTY_SIGNALS if s in latest)
    raw = max(0.0, min(1.0, 1.0 - hits * 0.12))
    # Recalibrate by track record: if Orrin has been systematically over/under
    # confident, correct the reading so "think more vs act" uses a calibrated
    # number (Nelson & Narens 1990 monitoring → control).
    try:
        from cognition.calibration import recalibrate_confidence
        return recalibrate_confidence(context, raw)
    except Exception:
        return raw


def _depth_preference() -> float:
    """0.0–1.0 preference for deep thinking from the thinking_depth bandit."""
    try:
        from cognition.planning.thinking_depth import depth_as_signal
        return depth_as_signal()
    except Exception:
        return 0.5


def _emit(decision: str, context: Dict[str, Any], round_num: int, reason: str = "") -> None:
    try:
        from think.thought_stream import emit_thought
        goal       = (context.get("committed_goal") or {}).get("title", "")
        confidence = round(_draft_confidence(context), 2)
        debt       = int(context.get("action_debt", 0) or 0)
        emit_thought(
            "deciding",
            f"{decision} (r{round_num}{', ' + reason if reason else ''})",
            full_trace=(
                f"decision={decision} round={round_num}/{context.get('_max_rounds', '?')} "
                f"debt={debt} confidence={confidence} reason={reason or 'heuristic'} "
                f"ewma_success={_ewma.rate:.2f}"
            ),
            meta_decision=decision, goal=goal, depth=round_num,
        )
    except Exception as _e:
        record_failure("meta_controller._emit", _e)


# ── simulate_outcome ──────────────────────────────────────────────────────────

_BRANCH_CONF_LOW  = 0.35   # below this: don't bother simulating (too uncertain for sim to help)
_BRANCH_CONF_HIGH = 0.72   # above this: linear sim is enough (already confident)

# Valence vocabulary for scoring a projected belief-chain. Matched against the
# conclusions of causal edges / rule steps (Orrin's own signal names).
_LOOKAHEAD_NEG = ("stagnation", "impasse", "conflict", "threat", "penalty",
                  "rejection", "risk", "melancholy", "failure", "frustrat",
                  "stuck", "blocked", "loop", "avoidance", "debt", "regret",
                  "error", "worse", "decline")
_LOOKAHEAD_POS = ("expected_gain", "reward", "confidence", "motivation",
                  "exploration", "novelty", "progress", "insight", "growth",
                  "understanding", "resolved", "success", "complete", "improve",
                  "learn")


def _symbolic_lookahead(intent: str, context: Dict[str, Any]) -> bool:
    """Conservative symbolic forward check, used when the LLM can't simulate.

    Rolls the intent forward through the causal graph (get_effects) plus the
    rule/causal-chain planner, and scores the projected conclusions for valence.
    Vetoes ONLY on a confident, net-negative projection — a clear bad outcome.
    A sparse or empty projection (the common case while the causal graph is still
    growing) returns True, so it can never block on no signal and cannot create
    false-veto think_more loops. It sharpens automatically as beliefs accumulate.

    Returns True to proceed, False to veto (→ think_more).
    """
    try:
        conclusions: List[str] = []
        confs: List[float] = []

        # 1) Direct causal forward model: what does this action tend to cause?
        try:
            from symbolic.causal_graph import get_effects
            for e in get_effects(intent, min_score=0.4)[:6]:
                conclusions.append(str(e.get("effect", "")).lower())
                confs.append(float(e.get("causal_score", 0.5)))
        except Exception:
            pass

        # 2) Rule/causal chain rollout — skip analogy steps (no valence signal).
        try:
            from symbolic.temporal_planner import plan as _tplan
            proj = _tplan(intent, horizon="short")
            for s in (proj.get("steps") or []):
                if s.get("type") in ("rule", "causal_edge"):
                    conclusions.append(str(s.get("conclusion", "")).lower())
                    confs.append(float(s.get("confidence", 0.5)))
        except Exception:
            pass

        if not conclusions:
            log_private("[meta_ctrl] symbolic lookahead: no projection → no veto")
            return True

        neg = sum(1 for c in conclusions if any(w in c for w in _LOOKAHEAD_NEG))
        pos = sum(1 for c in conclusions if any(w in c for w in _LOOKAHEAD_POS))
        mean_conf = (sum(confs) / len(confs)) if confs else 0.5

        # Temper by how reliable predictions are in this domain.
        try:
            from symbolic.prediction_engine import domain_weighted_prediction_error
            reliability = 1.0 - min(1.0, domain_weighted_prediction_error(intent))
        except Exception:
            reliability = 0.6
        veto_conf = mean_conf * reliability

        confidently_negative = (neg > pos) and (neg >= 2) and (veto_conf >= 0.5)
        log_private(
            f"[meta_ctrl] symbolic lookahead: neg={neg} pos={pos} "
            f"veto_conf={veto_conf:.2f} → {'VETO' if confidently_negative else 'proceed'}"
        )
        return not confidently_negative
    except Exception:
        return True


def simulate_outcome(context: Dict[str, Any], content: str) -> bool:
    """
    Run a forward simulation before committing to "act".
    Returns True if the simulation predicts a net-positive outcome.
    Falls back to True (optimistic) on error so it never blocks action.

    At medium confidence (0.35–0.72), uses branching simulation (steps=5)
    to explore two alternative futures before deciding.
    At high confidence (>0.72), uses a cheap 2-step linear chain.
    Below 0.35, skips simulation — too uncertain for the result to be trustworthy.
    """
    try:
        from think.simulate import simulate_lookahead
        goal_title  = (context.get("committed_goal") or {}).get("title", "")
        intent      = (f"Output toward goal '{goal_title}': {content[:200]}"
                       if goal_title else f"Output: {content[:200]}")
        draft_conf  = _draft_confidence(context)

        if draft_conf < _BRANCH_CONF_LOW:
            # Too uncertain — simulation would be noise
            log_private(f"[meta_ctrl] simulate skipped (conf={draft_conf:.2f} too low)")
            return True

        use_branching = _BRANCH_CONF_LOW <= draft_conf <= _BRANCH_CONF_HIGH
        steps = 5 if use_branching else 2

        result   = simulate_lookahead(context, intent=intent, steps=steps, branching=use_branching)

        # No LLM simulation (tool-only cognition) → conservative symbolic forward
        # check instead of a blind skip. It only vetoes a confidently-negative
        # projection; a sparse/empty projection proceeds, so it never fabricates a
        # positive nor blocks on no signal.
        if result.get("skipped"):
            proceed = _symbolic_lookahead(intent, context)
            log_private(f"[meta_ctrl] simulate_outcome via symbolic lookahead → "
                        f"{'proceed' if proceed else 'VETO (think_more)'}")
            return proceed

        positive = bool(result.get("positive", True))
        conf     = float(result.get("confidence", 0.5))
        branches = int(result.get("branches_explored", 0))

        log_private(
            f"[meta_ctrl] simulate_outcome positive={positive} sim_conf={conf:.2f} "
            f"draft_conf={draft_conf:.2f} branching={use_branching} branches={branches}"
        )
        return positive or conf < 0.4   # act unless simulation is confidently negative
    except Exception:
        return True


# ── Public: record_outcome ────────────────────────────────────────────────────

def record_outcome(arm_id: int, reward: float) -> None:
    """
    Called by ORRIN_loop after the cycle evaluator computes reward.
    Updates both the threshold bandit and the EWMA success tracker.
    """
    _bandit.update(arm_id, reward)
    _ewma.update(reward > 0.0)


# ── Public: recommend_rounds ──────────────────────────────────────────────────

def recommend_rounds(context: Optional[Dict[str, Any]] = None) -> int:
    """
    Suggest a round count to inner_loop based on EWMA success rate and energy state.
    High success → stay lean (4).  Low success → push deeper (6-7).
    Energy-state adjustment: high energy → -1, low/rest → +2.
    """
    rate = _ewma.rate
    if rate >= 0.70:
        base = 4
    elif rate >= 0.55:
        base = 5
    elif rate >= 0.40:
        base = 6
    else:
        base = 7

    if context:
        _energy = str(context.get("energy_state") or "medium")
        _bias   = float(context.get("action_vs_reflect_bias") or 0.5)
        _rest   = bool(context.get("_rest_mode"))
        if _energy == "high" or _bias > 0.65:
            base = max(2, base - 1)
        elif _energy == "low" or _rest or _bias < 0.35:
            base = base + 2
    return base


# ── Main decide ──────────────────────────────────────────────────────────────

def decide(
    context: Dict[str, Any],
    round_num: int,
    max_rounds: int,
) -> MetaDecision:
    """
    Called after each draft is written to the scratchpad.
    Returns one of: "think_more" | "act" | "output" | "defer"

    Stamps context["_meta_ctrl_arm"] so ORRIN_loop can call record_outcome().
    """
    # ── Choose threshold arm (UCB1) — must happen before any early return ────────
    # so context["_meta_ctrl_arm"] is always stamped for ORRIN_loop.record_outcome()
    arm_id = _bandit.choose()
    context["_meta_ctrl_arm"] = arm_id

    # ── 0. External UI control signal ─────────────────────────────────────────
    try:
        from think.thought_stream import consume_meta_control
        ui_cmd = consume_meta_control()
        if ui_cmd == "pause":
            log_private("[meta_ctrl] UI pause → defer")
            _emit("defer", context, round_num, "ui_pause")
            return "defer"
        if ui_cmd == "go_deeper" and round_num < max_rounds:
            log_private("[meta_ctrl] UI go_deeper → think_more")
            _emit("think_more", context, round_num, "ui_go_deeper")
            return "think_more"
    except Exception as _e:
        record_failure("meta_controller.decide", _e)
    think_more_thresh, output_thresh = _bandit.thresholds(arm_id)

    # ── Adaptive threshold nudge based on EWMA ─────────────────────────────────
    # When success rate is low, be more willing to think_more
    success_rate = _ewma.rate
    if success_rate < 0.45:
        think_more_thresh = min(0.72, think_more_thresh + 0.08)
        output_thresh     = max(0.55, output_thresh     - 0.05)
    elif success_rate > 0.75:
        think_more_thresh = max(0.30, think_more_thresh - 0.05)
        output_thresh     = min(0.88, output_thresh     + 0.05)

    # ── Energy-state threshold override ───────────────────────────────────────
    # High energy → act quickly; low/rest → think deeper.
    _energy_state = str(context.get("energy_state") or "medium")
    _action_bias  = float(context.get("action_vs_reflect_bias") or 0.5)
    _rest_mode    = bool(context.get("_rest_mode"))
    if _energy_state == "high" or _action_bias > 0.65:
        # Cap think_more_thresh low → rarely triggers; lower output_thresh → acts easily
        think_more_thresh = min(think_more_thresh, 0.28)
        output_thresh     = min(output_thresh, 0.45)
        log_private("[meta_ctrl] energy=high → think_more≤0.28 output≤0.45")
    elif _energy_state == "low" or _rest_mode or _action_bias < 0.35:
        # Raise think_more_thresh → triggers often; raise output_thresh → needs high confidence
        think_more_thresh = max(think_more_thresh, 0.68)
        output_thresh     = max(output_thresh, 0.78)
        log_private("[meta_ctrl] energy=low/rest → think_more≥0.68 output≥0.78")

    debt     = int(context.get("action_debt", 0) or 0)
    has_goal = bool(context.get("committed_goal"))
    act_now  = bool(context.get("act_now"))

    # ── 1. Hard ceiling ────────────────────────────────────────────────────────
    if round_num >= max_rounds:
        decision: MetaDecision = "act" if (has_goal and debt >= 2) else "output"
        log_private(f"[meta_ctrl] ceiling r={round_num}/{max_rounds} → {decision} (arm={arm_id})")
        _emit(decision, context, round_num, "ceiling")
        return decision

    # ── 2. Urgent action signal ────────────────────────────────────────────────
    if act_now:
        log_private("[meta_ctrl] act_now → act")
        _emit("act", context, round_num, "act_now")
        return "act"

    # ── 3. Action debt pressure ────────────────────────────────────────────────
    if debt >= 3:
        log_private(f"[meta_ctrl] debt={debt} → act")
        _emit("act", context, round_num, f"debt={debt}")
        return "act"

    # ── 4. Confidence + bandit thresholds ──────────────────────────────────────
    confidence = _draft_confidence(context)
    depth_pref = _depth_preference()

    if confidence < think_more_thresh and depth_pref > 0.45 and round_num < max_rounds:
        log_private(f"[meta_ctrl] conf={confidence:.2f}<{think_more_thresh:.2f} depth={depth_pref:.2f} → think_more (arm={arm_id})")
        _emit("think_more", context, round_num, f"conf={confidence:.2f}")
        return "think_more"

    if confidence > output_thresh:
        # Before acting, optionally verify with simulate_outcome
        should_simulate = (
            debt >= 2
            and confidence > 0.55
            and round_num < max_rounds
        )
        if should_simulate:
            latest_content = ""
            pad = context.get("_scratchpad") or []
            drafts = [e for e in pad if e.get("role") in ("revision", "draft")]
            if drafts:
                latest_content = drafts[-1].get("content", "")
            if latest_content and not simulate_outcome(context, latest_content):
                log_private("[meta_ctrl] simulate_outcome negative → think_more")
                _emit("think_more", context, round_num, "simulate_negative")
                return "think_more"

        decision = "act" if (has_goal and debt >= 1) else "output"
        log_private(f"[meta_ctrl] conf={confidence:.2f}>{output_thresh:.2f} → {decision} (arm={arm_id})")
        _emit(decision, context, round_num, f"conf={confidence:.2f}")
        return decision

    # ── 5. Goal + debt pressure ────────────────────────────────────────────────
    if has_goal and debt >= 1:
        log_private(f"[meta_ctrl] has_goal + debt={debt} → act")
        _emit("act", context, round_num, f"goal+debt={debt}")
        return "act"

    # ── 6. Default: depth preference tiebreak ─────────────────────────────────
    if round_num == 1 and depth_pref > 0.52:
        log_private(f"[meta_ctrl] r1 depth_pref={depth_pref:.2f} → think_more")
        _emit("think_more", context, round_num, "depth_pref")
        return "think_more"

    log_private(f"[meta_ctrl] default r={round_num} arm={arm_id} → output")
    _emit("output", context, round_num, "default")
    return "output"
