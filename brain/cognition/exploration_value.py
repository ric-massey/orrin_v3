# brain/cognition/exploration_value.py
# Explore/exploit value for outward-reaching actions — replaces the wall-clock
# cooldown that used to throttle look_outward (RUN_AUDIT_REPORT_2026-06-16 Issue 1;
# EXPLORE_EXPLOIT_VALUE_PLAN_2026-06-16).
#
# Instead of "how long since the last reach?", we ask "is reaching outward worth it
# right now?" — a value driven by outcome novelty (habituation), an open-question
# curiosity gap, marginal-value opportunity cost, a three-zone gradient, and a
# boredom override. The action competes on this value in select_function; there is
# no gate and no timer.
#
# Sources (see the plan §13): Sokolov 1963 (habituation comparator); Charnov 1976
# (marginal value theorem — opportunity cost); Loewenstein 1994 (curiosity as an
# information gap); Bench & Lench 2013 (boredom as a switch signal). Energy/effort
# cost is intentionally NOT recomputed here — select_function already applies the
# Shenhav et al. 2013 EVC penalty (`s_evc`) to every action, so adding it here would
# double-count.
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict

from brain.paths import DATA_DIR
from brain.utils.failure_counter import record_failure
from brain.utils.get_cycle_count import get_cycle_count

# Per-action habituation store: {fn: {"satiety": float[0..1], "cycle": int}}.
# Lives beside decision_stats.json (DATA_DIR honours ORRIN_DATA_DIR for test/per-user
# isolation). Satiety RISES when a reach returns little new information and DECAYS
# slowly (lazily, on read) so the drive recovers over time — the only place wall-time
# appears, and only as a decay constant, never a trigger.
_SATIETY_PATH = DATA_DIR / "outward_satiety.json"
_STATS_PATH = DATA_DIR / "decision_stats.json"

# Tuning (conservative defaults; calibrate against the replay in the plan §8).
_ALPHA = 0.5            # satiety gain per uninformative reach
_DECAY_PER_CYCLE = 0.97  # ~slow recovery: satiety halves in ~23 cycles
_W_NOVELTY = 0.24       # weight on curiosity_gap × expected_novelty (≈ s_emo scale)
_OPP_CAP = 0.30         # max opportunity-cost penalty
_BOREDOM_CAP = 0.22     # max boredom re-lift

# W3 three-zone prediction/reward gradient. Self/internal work is not an outward
# reach; home/den work is learnable and bounded; world work is open-ended and gets
# the strongest novelty multiplier.
_ZONE_WEIGHT = {
    "self": 0.0,
    "home": 0.72,
    "world": 1.0,
}

_OUTWARD_FNS = frozenset({
    "look_outward", "look_around", "seek_novelty",
    "search_own_files", "grep_files", "search_files",
    "wikipedia_search", "research_topic", "fetch_and_read", "read_a_book",
})

_HOMEWARD_FNS = frozenset({
    "look_around", "search_own_files", "grep_files", "search_files", "read_a_book",
})
_WORLDWARD_FNS = frozenset({
    "look_outward", "seek_novelty", "wikipedia_search", "research_topic", "fetch_and_read",
})

# Cached satiety + stats reads (cheap hot path; mirror select_function's ~15s cache).
_SAT_CACHE: Dict[str, Any] = {"t": 0.0, "data": {}}
_STATS_CACHE: Dict[str, Any] = {"t": 0.0, "data": {}}


@dataclass
class ReachOutcome:
    mode: str
    acted: bool
    is_external: bool
    info_gain: float = 0.0
    created_memory: bool = False
    satisfied_curiosity: bool = False
    inner_fn: str = ""
    text: str = ""


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _load_satiety() -> Dict[str, Dict[str, float]]:
    if time.time() - _SAT_CACHE["t"] < 5.0 and _SAT_CACHE["data"]:
        return _SAT_CACHE["data"]
    try:
        data = json.loads(_SATIETY_PATH.read_text("utf-8")) if _SATIETY_PATH.exists() else {}
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    _SAT_CACHE["data"] = data
    _SAT_CACHE["t"] = time.time()
    return data


def _save_satiety(data: Dict[str, Dict[str, float]]) -> None:
    try:
        _SATIETY_PATH.parent.mkdir(parents=True, exist_ok=True)
        _SATIETY_PATH.write_text(json.dumps(data, indent=2), "utf-8")
        _SAT_CACHE["data"] = data
        _SAT_CACHE["t"] = time.time()
    except Exception as e:
        record_failure("exploration_value._save_satiety", e)


def _learned_stats() -> Dict[str, Dict[str, float]]:
    if time.time() - _STATS_CACHE["t"] < 15.0 and _STATS_CACHE["data"]:
        return _STATS_CACHE["data"]
    try:
        d = json.loads(_STATS_PATH.read_text("utf-8"))
        _STATS_CACHE["data"] = {
            k: {"avg_reward": float(v.get("avg_reward", 0.5) or 0.5),
                "count": int(v.get("count", 0) or 0)}
            for k, v in d.items() if isinstance(v, dict)
        }
        _STATS_CACHE["t"] = time.time()
    except Exception:
        pass
    return _STATS_CACHE["data"]


def _decayed_satiety(fn: str) -> float:
    """Current satiety for `fn`, lazily decayed by the cycles elapsed since it was
    last written. No separate per-cycle sweep needed."""
    rec = _load_satiety().get(fn)
    if not isinstance(rec, dict):
        return 0.0
    s = float(rec.get("satiety", 0.0) or 0.0)
    elapsed = max(0, get_cycle_count() - int(rec.get("cycle", 0) or 0))
    if elapsed:
        s *= _DECAY_PER_CYCLE ** elapsed
    return _clamp(s)


# ── Components (each fail-safe → neutral) ──────────────────────────────────────

def _has_open_question(context: Dict[str, Any]) -> bool:
    """A genuine curiosity gap: a live committed goal, or an unresolved question in
    working memory that isn't internal-state bookkeeping. Cheap, context-only."""
    if isinstance(context.get("committed_goal"), dict) and context["committed_goal"]:
        return True
    wm = context.get("working_memory") or []
    for e in reversed(wm[-6:]):
        c = str(e.get("content", e) if isinstance(e, dict) else e)
        if "?" in c and not c.lstrip().startswith(("🧠", "✅", "⚠️", "[", "Chose:", "decision:")):
            return True
    return False


def curiosity_gap(context: Dict[str, Any]) -> float:
    """Is there something Orrin actually wants to know? [0..1]. Collapses reach_value
    to ~0 when there's nothing to ask (Loewenstein 1994 information gap)."""
    cs = ((context.get("affect_state") or {}).get("core_signals") or {})
    drive = float(cs.get("exploration_drive", 0.0) or 0.0)
    wonder = float(cs.get("wonder", 0.0) or 0.0)
    gap = max(drive, wonder)
    if _has_open_question(context):
        gap = max(gap, 0.6)
    return _clamp(gap)


def expected_novelty(fn: str, context: Dict[str, Any] = None) -> float:
    """How much new information THIS action has been paying lately = 1 − satiety.
    Cold actions read 1.0 (optimistic — worth trying). Habituation core."""
    return _clamp(1.0 - _decayed_satiety(fn))


def zone_for_fn(fn: str) -> str:
    """Classify an exploration action on the self→home→world slope."""
    if fn in _HOMEWARD_FNS:
        return "home"
    if fn in _WORLDWARD_FNS:
        return "world"
    return "self"


def zone_gradient(fn: str, context: Dict[str, Any] = None) -> float:
    """Prediction-error value multiplier by zone.

    Home gets a bounded, learnable reward. World gets the full external novelty
    reward. Self/internal functions do not receive outward reach value here.
    """
    return _ZONE_WEIGHT.get(zone_for_fn(fn), 0.0)


def _opportunity_cost(fn: str) -> float:
    """Marginal value theorem (Charnov 1976): penalise reaching when this action pays
    below the ambient reward rate across all actions. [0.._OPP_CAP]."""
    stats = _learned_stats()
    if not stats:
        return 0.0
    rewards = [float(v.get("avg_reward", 0.5)) for v in stats.values()]
    ambient = sum(rewards) / len(rewards) if rewards else 0.5
    mine = float((stats.get(fn) or {}).get("avg_reward", ambient))
    return _clamp(max(0.0, ambient - mine), 0.0, _OPP_CAP)


def _boredom_push(context: Dict[str, Any]) -> float:
    """Sustained internal monotony re-opens exploration (Bench & Lench 2013) — the
    anti-lockout term so habituation can't freeze Orrin into pure inward circling."""
    cs = ((context.get("affect_state") or {}).get("core_signals") or {})
    stag = float(cs.get("stagnation_signal", 0.0) or 0.0)
    outward_debt = int(context.get("_outward_debt", 0) or 0)
    push = 0.18 * stag + 0.12 * _clamp(outward_debt / 15.0)
    return _clamp(push, 0.0, _BOREDOM_CAP)


def reach_value(fn: str, context: Dict[str, Any]) -> float:
    """Explore/exploit value of taking outward action `fn` this cycle, as an additive
    selector term (≈ same scale as s_emo / s_outward). Fail-safe → 0.0.

        reach_value = W·zone_gradient·curiosity_gap·expected_novelty
                      − opportunity_cost + boredom_push

    Energy/effort cost is handled globally by select_function's s_evc (EVC), not here.
    """
    try:
        if fn not in _OUTWARD_FNS:
            return 0.0
        ctx = context or {}
        base = zone_gradient(fn, ctx) * curiosity_gap(ctx) * expected_novelty(fn, ctx)
        val = _W_NOVELTY * base - _opportunity_cost(fn) + _boredom_push(ctx)
        return float(round(val, 4))
    except Exception as e:
        record_failure("exploration_value.reach_value", e)
        return 0.0


# ── Outcome feedback (called from the action result paths) ─────────────────────

def _info_gain(result_text: str, kg_delta: Dict[str, int] | None) -> float:
    """Information gain of a completed reach, [0..1]. New knowledge-graph structure
    is strong novelty; an explicit 'nothing new' echo is zero (Sokolov comparator)."""
    kg_delta = kg_delta or {}
    added = int(kg_delta.get("entities_added", 0) or 0) + int(kg_delta.get("relations_added", 0) or 0)
    if added:
        return _clamp(added / 4.0)   # a few new nodes ⇒ high novelty
    low = (result_text or "").lower()
    if any(p in low for p in ("nothing new", "found nothing", "feels exhausted",
                              "no results", "no web search", "already reached",
                              "couldn't form")):
        return 0.0
    if len(low) > 250:
        return 0.5    # substantive external text (e.g. a real wiki summary)
    return 0.25       # produced output but no new knowledge structure ⇒ weak novelty


def record_reach_outcome(fn: str, result_text: str,
                         kg_delta: Dict[str, int] | None = None,
                         context: Dict[str, Any] = None) -> float:
    """Update `fn`'s habituation from the realized information gain of a reach. An
    uninformative reach raises satiety fast (drive self-suppresses); an informative
    one barely moves it (drive stays live)."""
    try:
        novelty = _info_gain(result_text, kg_delta)
        data = dict(_load_satiety())
        cur = _decayed_satiety(fn)   # decay-to-now before adding
        new_s = _clamp(cur + _ALPHA * (1.0 - novelty))
        data[fn] = {"satiety": round(new_s, 4), "cycle": int(get_cycle_count())}
        _save_satiety(data)
        if context is not None and novelty > 0.0:
            affect = context.get("affect_state") or {}
            core = affect.get("core_signals") or affect
            if isinstance(core, dict):
                current = float(core.get("exploration_drive", 0.0) or 0.0)
                core["exploration_drive"] = max(0.0, current - 0.20 * novelty)
            if context.get("committed_goal"):
                context["action_debt"] = 0
                context["__acted_this_tick__"] = True
            context["_reach_consumed_info_gain"] = round(novelty, 4)
            try:
                from brain.affect.reward_signals.reward_signals import release_reward_signal
                release_reward_signal(
                    context,
                    signal_type="novelty",
                    actual_reward=round(0.5 + 0.5 * novelty, 3),
                    expected_reward=0.5,
                    effort=0.2,
                    mode="phasic",
                    source=f"reach_consummation:{fn}",
                )
            except Exception as e:
                record_failure("exploration_value.reach_consummation", e)
        return novelty
    except Exception as e:
        record_failure("exploration_value.record_reach_outcome", e)
        return 0.0
