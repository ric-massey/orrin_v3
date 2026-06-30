"""
brain/control_signals/appraisal.py

Appraisal-theory affect generation. No LLM, no keyword lists.

Events from working memory are evaluated against active goals and current
coping capacity using five appraisal dimensions.

  relevance   — does this event matter to an active goal?
  congruence  — does it help (+) or block (-) the goal?
  agency      — who caused it: self | other | circumstance
  certainty   — how clear is the outcome?
  novelty     — how unexpected is this?

Output: list of {emotion, delta, cause} dicts ready to be applied to
affect_state.core_signals by update_signal_state.

SCIENTIFIC BASIS:
  Roseman (1996) — "Appraisal determinants of emotions: Constructing a more
  accurate and comprehensive theory." Cognition & Emotion, 10(3), 241–278.
  Smith & Ellsworth (1985) — "Patterns of cognitive appraisal in emotion."
  Journal of Personality and Social Psychology, 48(4), 813–838.
  Lazarus (1991) — "Emotion and Adaptation." Oxford University Press.
"""
from __future__ import annotations
import re
import time
from typing import Any, Dict, List

# Number-normalizing key so counter-style recurrences ("Goal avoidance: 54 / 55
# consecutive cycles") collapse to ONE habituation key.
_DIGIT_RE = re.compile(r"\d+")
_WS_RE = re.compile(r"\s+")


def _habituation_key(text: str) -> str:
    return _WS_RE.sub(" ", _DIGIT_RE.sub("#", (text or "").lower())).strip()[:80]

# ── Word sets for dimension detection ─────────────────────────────────────────

_BLOCK_WORDS = frozenset({
    "fail", "failed", "can't", "cannot", "blocked", "stuck", "error",
    "broken", "unable", "wrong", "problem", "issue", "refused", "denied",
    "prevented", "missing", "lost", "couldn't", "won't", "didn't work",
    # Stall / avoidance / stagnation markers — a self-report of "I'm thinking
    # but not doing" is a BLOCK, not a neutral event. Without these the metacog
    # avoidance/stagnation lines score 0 block-words, fall through to the
    # mood-bias branch, and (because mood is pinned positive) get read as
    # goal-CONGRUENT → reward/confidence/motivation boosts. That is the loop that
    # rewards paralysis. (RUN diagnosis 2026-06-29.)
    "avoidance", "avoiding", "not doing", "no action", "without taking action",
    "stagnation", "stagnant", "rumination", "ruminating", "going in circles",
    "💔", "gave up", "no progress", "spinning",
})
# Markers that a setback is a REPEAT / dead end (not a fresh, surmountable
# challenge). Used to deny the high-coping "challenge response" its motivation
# reward when the same thing keeps failing.
_REPEATED_FAILURE_WORDS = frozenset({
    "consecutive", "_3x", "3x", "again", "repeated", "repeatedly", "still ",
    "keeps", "kept", "every cycle", "over and over",
})
_HELP_WORDS = frozenset({
    "done", "finished", "completed", "achieved", "success", "solved",
    "found", "created", "built", "learned", "understood", "improved",
    "progress", "accomplished", "ready", "working", "fixed",
})
_SELF_WORDS = frozenset({
    " i ", "i've", "i'm", "i'd", "my ", " me ", "myself",
    "i failed", "i made", "i said", "i did", "i chose", "i tried",
})
_OTHER_WORDS = frozenset({
    "you ", "they ", " he ", " she ", "user", "person", "someone",
    "told me", "asked me", "they said",
})
_UNCERTAIN_WORDS = frozenset({
    "maybe", "might", "unclear", "don't know", "unsure", "perhaps",
    "could be", "possibly", "uncertain", "not sure", "hard to say",
})
_NOVEL_WORDS = frozenset({
    "unexpected", "surprising", "didn't expect", "unusual", "strange",
    "first time", "never before", "discovered", "realized", "interesting",
    "wait —", "huh,",
})

# ── Dimension extractors ───────────────────────────────────────────────────────

def _hits(text: str, word_set: frozenset) -> int:
    return sum(1 for w in word_set if w in text)


def _goal_relevance(text: str, goal_titles: List[str], mood: float = 0.0) -> float:
    if not goal_titles or not text:
        return 0.0
    best = 0.0
    for title in goal_titles:
        words = [w for w in title.lower().split() if len(w) > 3]
        if not words:
            continue
        matches = sum(1 for w in words if w in text)
        score = matches / len(words)
        if score > best:
            best = score
    raw = min(1.0, best * 1.6)
    # Anxious hypervigilance: bad mood makes more things feel goal-relevant
    # Relaxed state: good mood means you don't over-read everything
    if mood < -0.20:
        raw = min(1.0, raw * 1.15)
    elif mood > 0.25:
        raw = raw * 0.95
    return raw


def _goal_congruence(text: str, mood: float = 0.0) -> float:
    """
    Returns congruence in [-1, +1]. Mood biases ambiguous events.

    Bad mood (negative valence): ambiguous events read as threats.
    Good mood: ambiguous events read as opportunities.
    Definite signals (clear help/block words) are amplified by same-direction mood.
    """
    help_h  = _hits(text, _HELP_WORDS)
    block_h = _hits(text, _BLOCK_WORDS)
    if help_h > block_h:
        raw = 1.0
    elif block_h > help_h:
        raw = -1.0
    else:
        raw = 0.0

    if raw == 0.0:
        # Ambiguous: mood tips the interpretation
        if abs(mood) > 0.12:
            return round(mood * 0.35, 2)   # [-0.35, +0.35] bias from mood
        return 0.0
    else:
        # Definite signal: mood amplifies if same direction, dampens if opposite
        return max(-1.0, min(1.0, raw * (1.0 + mood * raw * 0.18)))


def _agency(text: str) -> str:
    self_h  = _hits(text, _SELF_WORDS)
    other_h = _hits(text, _OTHER_WORDS)
    if self_h > other_h:
        return "self"
    if other_h > self_h:
        return "other"
    return "circumstance"


def _certainty(text: str) -> float:
    unc = _hits(text, _UNCERTAIN_WORDS)
    return max(0.0, 1.0 - unc * 0.25)


def _novelty(text: str) -> float:
    nov = _hits(text, _NOVEL_WORDS)
    return min(1.0, nov * 0.30)


def _coping(affect_state: Dict[str, Any]) -> float:
    emo  = affect_state or {}
    core = emo.get("core_signals") or emo
    conf = float(core.get("confidence", 0.5) or 0.5)
    mot  = float(core.get("motivation",  0.5) or 0.5)
    fat  = float(emo.get("resource_deficit",      0.0) or 0.0)
    return max(0.0, min(1.0, (conf * 0.5 + mot * 0.3) * (1.0 - fat * 0.4)))


# ── Appraisal → emotion deltas ────────────────────────────────────────────────

def appraise_event(
    event_text: str,
    goal_titles: List[str],
    affect_state: Dict[str, Any],
    mood: float = 0.0,
) -> List[Dict[str, Any]]:
    """
    Evaluate one event and return emotion adjustments.
    Each item: {emotion: str, delta: float, cause: str}
    Deltas are small nudges (0.02 – 0.25), not snaps.
    """
    if not event_text or len(event_text.strip()) < 12:
        return []

    text  = event_text.lower()
    rel   = _goal_relevance(text, goal_titles, mood=mood)
    cong  = _goal_congruence(text, mood=mood)
    who   = _agency(text)
    cert  = _certainty(text)
    nov   = _novelty(text)
    cope  = _coping(affect_state)

    cause = event_text[:80]
    out: List[Dict[str, Any]] = []

    # Did the congruence come from a REAL help-signal in the text, or only from a
    # mood bias on an ambiguous event? (raw==0 in _goal_congruence → mood inferred.)
    genuine_help = _hits(text, _HELP_WORDS) > _hits(text, _BLOCK_WORDS)

    # Goal-relevant events
    if rel >= 0.15:
        if cong > 0 and genuine_help:
            # Congruent by a real achievement signal: goal is genuinely being helped.
            positive_valence_d  = round(rel * cert * 0.22, 3)
            conf_d = round(rel * cert * 0.12, 3)
            mot_d  = round(rel        * 0.10, 3)
            if positive_valence_d  > 0.02: out.append({"emotion": "reward_positive",        "delta": positive_valence_d,  "cause": cause})
            if conf_d > 0.02: out.append({"emotion": "confidence", "delta": conf_d, "cause": cause})
            if mot_d  > 0.02: out.append({"emotion": "motivation", "delta": mot_d,  "cause": cause})

        elif cong > 0:
            # Congruence inferred from a positive MOOD on an ambiguous event (no real
            # help-word). Mood-congruent interpretation is fine (Bower 1981), but it
            # must NOT mint reward_positive/motivation out of nothing — that is the
            # runaway where good mood → "reward" → better mood, which kept his reward
            # pinned at ~0.89 on dream/analogy content while nothing was achieved
            # (RUN diag 2026-06-29). Allow only a faint exploration nudge.
            expl_d = round(rel * cert * 0.05, 3)
            if expl_d > 0.02:
                out.append({"emotion": "exploration_drive", "delta": expl_d, "cause": cause})

        elif cong < 0:
            # Incongruent: goal is being blocked
            intensity = rel * 0.85

            if who == "self":
                # Self-caused setback: impasse_signal + mild social_penalty
                out.append({"emotion": "impasse_signal", "delta": round(intensity * 0.18, 3), "cause": cause})
                if intensity > 0.35:
                    out.append({"emotion": "social_penalty",       "delta": round(intensity * 0.08, 3), "cause": cause})
                out.append({"emotion": "confidence",     "delta": round(-intensity * 0.07, 3), "cause": cause})

            elif who == "other":
                # Other-caused: impasse_signal, possible conflict_signal
                out.append({"emotion": "impasse_signal",   "delta": round(intensity * 0.16, 3), "cause": cause})
                if intensity > 0.45:
                    out.append({"emotion": "conflict_signal",         "delta": round(intensity * 0.10, 3), "cause": cause})

            else:
                # Circumstantial: risk_estimate (low coping) or challenge response (high coping)
                repeated = _hits(text, _REPEATED_FAILURE_WORDS) > 0
                if cope < 0.45:
                    out.append({"emotion": "risk_estimate",      "delta": round(intensity * 0.15, 3), "cause": cause})
                    if cert < 0.40:
                        out.append({"emotion": "threat_level",     "delta": round(intensity * 0.08, 3), "cause": cause})
                elif repeated:
                    # A REPEATED setback is a dead end, not a surmountable challenge:
                    # high coping must NOT turn it into a motivation reward (that is
                    # how a 3x-failed goal kept pinning motivation/reward high while
                    # nothing moved). Register it as impasse + a confidence dip so the
                    # stall actually creates pressure to disengage. (RUN diag 2026-06-29.)
                    out.append({"emotion": "impasse_signal", "delta": round(intensity * 0.16, 3), "cause": cause})
                    out.append({"emotion": "confidence",     "delta": round(-intensity * 0.06, 3), "cause": cause})
                else:
                    # Fresh, surmountable challenge: high coping reframes it as drive.
                    out.append({"emotion": "motivation",   "delta": round(intensity * 0.10, 3), "cause": cause})
                    out.append({"emotion": "impasse_signal",  "delta": round(intensity * 0.07, 3), "cause": cause})

    # Novelty is goal-independent: triggers exploration_drive / wonder
    if nov > 0.12:
        out.append({"emotion": "exploration_drive", "delta": round(nov * 0.18, 3), "cause": cause})
        if nov > 0.28:
            out.append({"emotion": "novelty_signal",    "delta": round(nov * 0.10, 3), "cause": cause})

    # Unresolvable uncertainty when event has no goal context
    if cert < 0.35 and rel < 0.15:
        out.append({"emotion": "uncertainty", "delta": round((1.0 - cert) * 0.07, 3), "cause": cause})

    # Mood modulates delta magnitudes: good mood amplifies positive, dampens negative
    if mood != 0.0:
        for r in out:
            d = r.get("delta", 0.0)
            if d > 0:
                r["delta"] = max(0.02, round(d * (1.0 + mood * 0.25), 3))
            elif d < 0:
                r["delta"] = min(-0.02, round(d * (1.0 - mood * 0.25), 3))

    # Filter near-zero deltas
    return [r for r in out if abs(r.get("delta", 0)) >= 0.02]


# Habituation window: a recurring event re-appraised within this many seconds is
# damped (you stop reacting to the same standing condition). Re-sensitizes once the
# event has been gone this long. Mirrors emotional habituation/adaptation.
_HABITUATION_WINDOW_S = 90.0
_HABITUATION_MAX = 96          # bound the per-state recency map


def appraise_working_memory(
    working_memory: List[Dict[str, Any]],
    goal_titles: List[str],
    affect_state: Dict[str, Any],
    lookback: int = 6,
    mood: float = 0.0,
    habituation: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    """
    Appraise recent working memory entries.
    Skips emotion-bookkeeping entries to avoid feedback loops.
    Returns merged list of {emotion, delta, cause}.

    HABITUATION (RUN diag 2026-06-29). update_signal_state appraises the last
    `lookback` WM entries EVERY cycle and ACCUMULATES the deltas into core signals.
    Without habituation a persistent/recurring thought ("Goal avoidance: N
    consecutive cycles", a lingering dream) is re-appraised every cycle and pumps
    its emotion to saturation — the mechanism that pinned reward at ~0.89 and then
    impasse at ~0.84. When a `habituation` dict is supplied (persisted on
    affect_state), a repeated number-normalized event is damped by 0.5 per recent
    repeat (down to 1/16), so the FIRST few appraisals land but a standing condition
    stops pumping. Re-sensitizes after `_HABITUATION_WINDOW_S` of absence.
    """
    _skip_types = frozenset({
        "affect_analysis", "unexplained_affect_reflection",
        "affect_cause", "oscillation_detected",
    })
    out: List[Dict[str, Any]] = []
    recent = [
        e for e in (working_memory or [])[-lookback:]
        if isinstance(e, dict)
        and e.get("event_type") not in _skip_types
        and e.get("content")
    ]

    _now = time.time()
    if isinstance(habituation, dict):
        for _k in list(habituation.keys()):
            _e = habituation.get(_k)
            if not isinstance(_e, dict) or (_now - float(_e.get("ts", 0) or 0)) > _HABITUATION_WINDOW_S:
                habituation.pop(_k, None)

    for entry in recent:
        text = str(entry.get("content", "") or "").strip()
        if len(text) < 15:
            continue
        deltas = appraise_event(text, goal_titles, affect_state, mood=mood)
        if not deltas:
            continue
        if isinstance(habituation, dict):
            key = _habituation_key(text)
            seen = habituation.get(key)
            count = int(seen.get("count", 0)) if isinstance(seen, dict) else 0
            habituation[key] = {"ts": _now, "count": count + 1}
            factor = 0.5 ** min(count, 4)   # full, then halve each repeat → 1/16 floor
            if factor < 1.0:
                damped = []
                for d in deltas:
                    nd = round(float(d.get("delta", 0.0)) * factor, 3)
                    if abs(nd) >= 0.02:
                        damped.append({**d, "delta": nd})
                deltas = damped
        out.extend(deltas)

    if isinstance(habituation, dict) and len(habituation) > _HABITUATION_MAX:
        for _k in sorted(habituation, key=lambda k: habituation[k].get("ts", 0))[: len(habituation) - _HABITUATION_MAX]:
            habituation.pop(_k, None)
    return out
