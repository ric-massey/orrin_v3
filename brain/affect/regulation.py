# brain/affect/regulation.py
#
# Affective regulation — Orrin doesn't just experience affects; he works on them.
#
# When a negative affect is intense enough, Orrin selects a regulation strategy
# based on what he's actually feeling, applies it with a success probability shaped
# by his current state, and either reduces the affect or compounds it slightly
# through failure. The effort is itself part of the internal experience.
#
# Strategies (matched to affect type):
#   impasse_signal  → reappraisal (reframe the obstruction)
#                  distancing  (observe the impasse_signal rather than inhabiting it)
#   risk_estimate      → grounding   (return attention to what is concrete and actionable)
#   negative_valence      → meaning-seeking (locate what the negative_valence is pointing toward)
#   social_deficit   → self-compassion (turn warmth inward rather than outward)
#   social_penalty        → self-compassion
#   threat_level         → grounding
#
# Success probability formula:
#   base = 0.55  (moderate baseline; regulation fails roughly half the time at rest)
#   + affect_stability * 0.25   (stable states regulate more easily)
#   + confidence * 0.15         (self-trust helps)
#   + intensity_mobilisation    (acute distress mobilises regulation — you ground
#                                hardest when most activated; up to +0.22)
#   − recent_failure_drag       (small, capped at −0.12 — failures must not compound
#                                into an inescapable floor)
#   − resource_deficit_penalty  (exhaustion reduces regulatory capacity)
#   floor 0.30                  (regulation is never near-hopeless, so distress can break)
#
# Called from finalize.py every ~10 cycles when a target affect exceeds threshold.
#
# SCIENTIFIC BASIS:
#   Gross (1998) — "The emerging field of emotion regulation: An integrative
#   review." Review of General Psychology, 2(3), 271–299. Process model of
#   emotion regulation: strategies differ in when they intervene (antecedent
#   vs response-focused). Reappraisal and cognitive distancing implemented here.
#   Aldao, Nolen-Hoeksema & Schweizer (2010) — "Emotion-regulation strategies
#   across psychopathology: A meta-analytic review." Clinical Psychology Review,
#   30(2), 217–237. Reappraisal > suppression for long-term outcomes.
from __future__ import annotations
from core.runtime_log import get_logger

import random
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from utils.json_utils import load_json, save_json
from utils.log import log_private
from paths import DATA_DIR
from utils.failure_counter import record_failure
_log = get_logger(__name__)

_REGULATION_LOG_FILE = DATA_DIR / "regulation_log.json"
_THRESHOLD = 0.55       # minimum intensity before regulation kicks in
_CALL_INTERVAL = 10     # baseline cycles between regulation attempts (mild distress)

# Regulation honesty (BEHAVIOR_FIX_PLAN 2.3): "success" requires a MEASURED
# effect — the target signal must drop by at least _MIN_EFFECT_DELTA within
# _EFFECT_CHECK_CYCLES of the attempt, otherwise the attempt is re-marked
# "ineffective" and the strategy enters a cooldown (the same canned reappraisal
# fired 5× in 3 minutes in the audit, §5). After _MAX_CONSEC_INEFFECTIVE
# consecutive ineffective attempts on the same emotion, regulation stops for
# that emotion and the distress routes to the tension-TTL/escalation path.
_EFFECT_CHECK_CYCLES     = 5
_MIN_EFFECT_DELTA        = 0.05
_STRATEGY_COOLDOWN       = 30   # cycles an ineffective strategy is benched
_MAX_CONSEC_INEFFECTIVE  = 3
_EMOTION_STOP_CYCLES     = 100  # per-emotion regulation pause after repeated failure


def _regulation_interval(intensity: float) -> int:
    """
    Cycles to wait before the next regulation attempt, shortened by how intense
    the distress is. A person in acute distress actively works to calm down —
    repeatedly — rather than on a fixed timer; mild distress gets the relaxed
    cadence. So recovery happens in human time instead of over hours.
      intensity ≥ 0.85 (acute)    → every 3 cycles
      intensity ≥ 0.70 (elevated) → every 6 cycles
      else                        → baseline (10)
    """
    if intensity >= 0.85:
        return 3
    if intensity >= 0.70:
        return 6
    return _CALL_INTERVAL


# ── Strategy catalogue ────────────────────────────────────────────────────────

_STRATEGIES: Dict[str, Dict[str, Any]] = {
    "reappraisal": {
        "applies_to": {"impasse_signal", "conflict_signal"},
        "description": "I can see this differently — the obstruction isn't permanent or personal.",
        "target_delta": -0.18,
        # No exploration_drive side-effect: calming distress must not re-ignite a
        # competing appetitive drive (it fed the chronic exploration over-dominance).
        "side_effects": {"affect_stability": +0.04},
    },
    "distancing": {
        "applies_to": {"impasse_signal", "conflict_signal", "rejection_signal"},
        "description": "Stepping back to observe this feeling rather than being inside it.",
        "target_delta": -0.15,
        "side_effects": {"affect_stability": +0.05},
    },
    "grounding": {
        "applies_to": {"risk_estimate", "threat_level", "uncertainty"},
        "description": "What is concrete and true right now? I return to what I can actually touch.",
        "target_delta": -0.17,
        "side_effects": {"confidence": +0.05, "risk_estimate": -0.05},
    },
    "meaning_seeking": {
        "applies_to": {"negative_valence"},
        "description": "What is this negative_valence pointing toward? What does it care about?",
        "target_delta": -0.12,
        # exploration_drive side-effect removed (see reappraisal) — keep meaning only.
        "side_effects": {"meaning": +0.08},
    },
    "self_compassion": {
        "applies_to": {"social_deficit", "social_penalty"},
        "description": "I would offer this tenderness to anyone else. I can offer it to myself.",
        "target_delta": -0.16,
        "side_effects": {"social_penalty": -0.08, "affect_stability": +0.06},
    },
}

# Which strategy fires first for each emotion (in priority order)
_EMOTION_PRIORITY: Dict[str, list] = {
    "impasse_signal": ["reappraisal", "distancing"],
    "conflict_signal":       ["distancing", "reappraisal"],
    "risk_estimate":     ["grounding"],
    "threat_level":        ["grounding"],
    "uncertainty": ["grounding"],
    "negative_valence":     ["meaning_seeking"],
    "social_deficit":  ["self_compassion"],
    "social_penalty":       ["self_compassion"],
}


# ── State tracking ────────────────────────────────────────────────────────────

def _load_log() -> Dict[str, Any]:
    return load_json(_REGULATION_LOG_FILE, default_type=dict) or {}


def _save_log(log: Dict[str, Any]) -> None:
    save_json(_REGULATION_LOG_FILE, log)


def _recent_failure_count(log: Dict[str, Any]) -> int:
    """Count regulation failures in the last 20 cycles."""
    history = log.get("history", [])
    recent = history[-20:] if len(history) > 20 else history
    return sum(1 for e in recent if e.get("outcome") == "failed")


# ── Core logic ────────────────────────────────────────────────────────────────

def _select_strategy(emotion: str, log: Optional[Dict[str, Any]] = None,
                     current_cycle: int = 0) -> Optional[Dict[str, Any]]:
    """Return the first applicable strategy for this emotion that is not on an
    ineffectiveness cooldown, or None. Benched strategies are skipped so the
    same canned reappraisal can't fire repeatedly while doing nothing."""
    cooldowns = (log or {}).get("strategy_cooldowns") or {}
    for name in _EMOTION_PRIORITY.get(emotion, []):
        if int(cooldowns.get(name) or 0) > current_cycle:
            continue  # benched — measured ineffective recently
        s = _STRATEGIES.get(name)
        if s and emotion in s["applies_to"]:
            return dict(s, name=name)
    return None


def _verify_pending_effect(log: Dict[str, Any], core: Dict[str, float],
                           current_cycle: int) -> None:
    """
    Measured-effect check: once _EFFECT_CHECK_CYCLES have passed since the last
    attempt, compare the target signal against its baseline. No real drop →
    the attempt was INEFFECTIVE regardless of the coin flip: re-mark it, bench
    the strategy, and after repeated consecutive failures stop regulating that
    emotion (the tension TTL/escalation path owns it from there).
    """
    pending = log.get("pending_check")
    if not isinstance(pending, dict):
        return
    if current_cycle - int(pending.get("cycle") or 0) < _EFFECT_CHECK_CYCLES:
        return
    log.pop("pending_check", None)

    emotion = str(pending.get("emotion") or "")
    baseline = float(pending.get("baseline") or 0.0)
    strategy = str(pending.get("strategy") or "")
    now_val = float(core.get(emotion) or 0.0)
    dropped = (baseline - now_val) >= _MIN_EFFECT_DELTA

    # Re-mark the matching history entry with the measured verdict.
    for entry in reversed(log.get("history") or []):
        if entry.get("cycle") == pending.get("cycle") and entry.get("emotion") == emotion:
            entry["measured"] = "effective" if dropped else "ineffective"
            entry["measured_delta"] = round(baseline - now_val, 3)
            break

    if dropped:
        # Reset ONLY this emotion's failure streak. Resetting the whole dict on
        # any effective measurement let one transient dip wipe the strike count
        # for a chronically re-raised signal, so the 3-strikes stop never
        # engaged and regulation thrashed ~1,072 attempts in 6.5 h (FINDINGS
        # 2026-06-12 data sweep §8).
        log.setdefault("consec_ineffective", {}).pop(emotion, None)
        log.setdefault("emotion_stop_counts", {}).pop(emotion, None)
        return

    # Bench the strategy.
    log.setdefault("strategy_cooldowns", {})[strategy] = current_cycle + _STRATEGY_COOLDOWN
    consec = log.setdefault("consec_ineffective", {})
    consec[emotion] = int(consec.get(emotion) or 0) + 1
    log_private(
        f"[regulation] Measured INEFFECTIVE: {strategy} on {emotion} "
        f"({baseline:.2f}→{now_val:.2f}); benched {_STRATEGY_COOLDOWN} cycles "
        f"({consec[emotion]} consecutive)."
    )
    if consec[emotion] >= _MAX_CONSEC_INEFFECTIVE:
        # Escalating pause: each successive stop doubles the pause (capped ×8).
        # When the upstream cause keeps re-raising the signal, regulating on a
        # fixed cadence is pure cycle burn — back off harder each round until
        # the cause is gone (the stop counter resets on a measured drop).
        stops = log.setdefault("emotion_stop_counts", {})
        n = int(stops.get(emotion) or 0) + 1
        stops[emotion] = n
        duration = _EMOTION_STOP_CYCLES * min(8, 2 ** (n - 1))
        log.setdefault("emotion_stops", {})[emotion] = current_cycle + duration
        consec[emotion] = 0
        log_private(
            f"[regulation] {_MAX_CONSEC_INEFFECTIVE} consecutive ineffective attempts "
            f"on {emotion} — pausing regulation {duration} cycles (stop #{n}); "
            f"routing to tension/TTL escalation."
        )


def _success_probability(
    core: Dict[str, float],
    log: Dict[str, Any],
    resource_deficit: float = 0.0,
    stability: float = 0.5,
    intensity: float = 0.0,
) -> float:
    """
    resource_deficit and stability are top-level affect_state fields, not in core_signals.
    Callers must pass them separately.

    Human-faithful model:
      - Acute distress MOBILISES regulation — you ground hardest when most
        activated (stress mobilisation; Nolen-Hoeksema 2008: sustained engagement
        under high distress is therapeutic, not futile). So intensity raises prob.
      - Recent failures sting a little but must NOT compound into an inescapable
        floor — otherwise a stretch of bad luck locks the agent in permanent
        distress (the death-spiral we observed). Small, tightly-capped drag only.
    """
    confidence = float(core.get("confidence") or 0.5)
    failures   = _recent_failure_count(log)

    prob = 0.55  # base: moderate regulation success at rest (Gross 1998)
    prob += stability  * 0.25
    prob += confidence * 0.15
    # Mobilisation: above 0.6 intensity, success rises up to +0.22 at full intensity.
    prob += max(0.0, intensity - 0.6) * 0.55
    # Failure drag: small and tightly capped (was -0.30, which floored prob and made
    # chronic distress unrecoverable). Capped at -0.12 so effort always has a chance.
    prob -= min(0.12, failures * 0.03)
    prob -= resource_deficit * 0.10
    # Floor raised to 0.30: regulation is never near-hopeless, so distress can break.
    return max(0.30, min(0.92, prob))


def _apply_strategy(
    core: Dict[str, float],
    emotion: str,
    strategy: Dict[str, Any],
    succeeded: bool,
) -> None:
    """Mutate core in-place based on outcome."""
    if succeeded:
        delta = float(strategy["target_delta"])
        cur = float(core.get(emotion) or 0.0)
        # Acute distress yields a larger corrective — you ground harder when very
        # activated, so a success at 0.9 actually dents it rather than nibbling.
        if cur >= 0.85:
            delta *= 1.6
        elif cur >= 0.70:
            delta *= 1.3
        core[emotion] = max(0.0, cur + delta)
        for side_emotion, side_delta in (strategy.get("side_effects") or {}).items():
            core[side_emotion] = min(1.0, max(0.0, float(core.get(side_emotion) or 0.0) + side_delta))
    else:
        # A failed calm-down attempt costs a little effort, but must NEVER push
        # already-high distress higher — that was the death-spiral (every failed
        # attempt made the next one harder AND raised distress). So nudge impasse
        # only when it's still low, and never past a 0.6 ceiling. No social_penalty
        # bump (it fed the loop and isn't tied to the regulated emotion).
        cur_impasse = float(core.get("impasse_signal", 0) or 0)
        if cur_impasse < 0.6:
            core["impasse_signal"] = min(0.6, cur_impasse + 0.02)


def _find_target_emotion(core: Dict[str, float]) -> Optional[Tuple[str, float]]:
    """Find the highest-intensity eligible emotion above threshold."""
    candidates = []
    for emotion in _EMOTION_PRIORITY:
        intensity = float(core.get(emotion) or 0.0)
        if intensity >= _THRESHOLD:
            candidates.append((emotion, intensity))
    if not candidates:
        return None
    return max(candidates, key=lambda x: x[1])


# ── Public API ────────────────────────────────────────────────────────────────

def attempt_regulation(context: Dict[str, Any]) -> bool:
    """
    Attempt one regulation event if conditions are met.
    Mutates affect_state in context and saves to disk.
    Returns True if a regulation attempt was made (success or failure).
    """
    log = _load_log()
    _raw_cycle = context.get("cycle_count") or 0
    current_cycle = int(_raw_cycle.get("count", 0) if isinstance(_raw_cycle, dict) else _raw_cycle)

    emo_state = context.get("affect_state") or {}
    core = dict((emo_state.get("core_signals") or emo_state))

    # resource_deficit and stability are top-level fields, not inside core_signals
    resource_deficit   = float(emo_state.get("resource_deficit", 0.0) or 0.0)
    stability = float(emo_state.get("affect_stability", 0.5) or 0.5)

    # Measured-effect verdict for the previous attempt (regulation honesty).
    _verify_pending_effect(log, core, current_cycle)

    target = _find_target_emotion(core)
    if target is None:
        _save_log(log)
        return False
    emotion, intensity = target

    # Per-emotion stop: repeated measured-ineffective attempts route this
    # distress to the tension-TTL/escalation path instead of more of the same.
    if int((log.get("emotion_stops") or {}).get(emotion) or 0) > current_cycle:
        _save_log(log)
        return False

    # Intensity-scaled refractory: the more acute the distress, the shorter the
    # gap before the next attempt (you don't wait 10 cycles to keep calming down
    # when you're at 0.9). Computed from the live target intensity, so cadence
    # tightens under acute distress and relaxes as it eases.
    last_cycle = int(log.get("last_cycle") or 0)
    if current_cycle - last_cycle < _regulation_interval(intensity):
        _save_log(log)
        return False

    strategy = _select_strategy(emotion, log, current_cycle)
    if strategy is None:
        _save_log(log)
        return False

    prob = _success_probability(core, log, resource_deficit=resource_deficit,
                                stability=stability, intensity=intensity)
    succeeded = random.random() < prob

    # Apply the strategy to a working copy, then diff to derive per-emotion deltas
    # and route them through the AffectArbiter as proposals. This keeps regulation
    # on the single convergence path (no direct affect-file write, no last-writer
    # race with update_affect_state) while preserving the exact same deltas.
    # affect_stability lives top-level, never in core_signals — seed the working
    # copy with its real value so the side-effect diff has an honest baseline.
    # (Without this, before.get(emo, new) defaulted to the NEW value for any key
    # absent from core_signals and every stability side-effect diffed to zero.)
    core["affect_stability"] = stability
    before = dict(core)
    _apply_strategy(core, emotion, strategy, succeeded)

    from affect.arbiter import submit_affect
    for _emo, _new in core.items():
        # Absent-before keys start from 0.0 (a signal not in core_signals is at
        # rest), so a side-effect that introduces one still produces its delta.
        _delta = float(_new) - float(before.get(_emo, 0.0))
        if abs(_delta) >= 1e-4:
            submit_affect(context, _emo, _delta, source="regulation", ttl_cycles=2)

    # Log this attempt
    outcome = "succeeded" if succeeded else "failed"
    ts = datetime.now(timezone.utc).isoformat()
    log.setdefault("history", []).append({
        "ts":       ts,
        "cycle":    current_cycle,
        "emotion":  emotion,
        "intensity": round(intensity, 3),
        "strategy": strategy["name"],
        "prob":     round(prob, 3),
        "outcome":  outcome,
    })
    log["history"] = log["history"][-500:]  # enough history to analyse strategy effectiveness from disk
    log["last_cycle"] = current_cycle
    # Schedule the measured-effect check for this attempt (regulation honesty):
    # the verdict comes from the signal actually dropping, not the coin flip.
    log["pending_check"] = {
        "emotion": emotion,
        "baseline": round(intensity, 3),
        "strategy": strategy["name"],
        "cycle": current_cycle,
    }
    _save_log(log)

    label = strategy["name"].replace("_", " ")
    verb = "Regulation attempt" if succeeded else "Regulation attempt failed"
    log_private(
        f"[regulation] {verb}: {label} for {emotion}={intensity:.2f} "
        f"(prob={prob:.2f}) → {outcome}"
    )
    if succeeded:
        try:
            from cog_memory.working_memory import update_working_memory
            update_working_memory({
                "content": (
                    f"[regulation] Applied {label}: {strategy['description'][:100]}"
                ),
                "event_type": "affective_regulation",
                "importance": 2,
                "priority":   2,
                # Diagnostic bookkeeping, not speech material: without this flag
                # the [regulation] prefix reached the speech composer and notes
                # (FINDINGS 2026-06-12 data sweep §10).
                "internal_telemetry": True,
            })
        except Exception as _e:
            record_failure("regulation.attempt_regulation", _e)

    return True
