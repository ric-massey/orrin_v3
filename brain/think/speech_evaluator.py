# think/speech_evaluator.py
#
# Conversation quality scorer.
#
# Called once per cycle when real new user input is detected.  Looks up the
# most recent unevaluated reply and scores it based on observable signals:
#
#   reply_length  — how many words the user wrote back (proxy for engagement)
#   reply_time    — how quickly they replied (proxy for interest)
#   asked_back    — whether the user asked a question (proxy for continuation)
#   one_word      — single-word reply signals low engagement
#
# Score formula (all weights are grounded in conversation analysis research):
#
#   base = 0.40  (they replied at all — above-chance engagement)
#
#   length_bonus  — up to +0.30 (scales linearly to 25 words, then flat)
#                   Rationale: longer replies = more cognitive investment
#                   (Clark & Schaefer, 1989 — grounding in conversation)
#
#   question_bonus — +0.15 if user asked something back
#                    Rationale: follow-up question = active topic pursuit
#                    (Stivers & Enfield, 2010 — sequence organisation in interaction)
#
#   speed_bonus   — +0.15 if reply < 45s, +0.05 if < 3min
#                   Rationale: inter-turn latency as an engagement proxy
#                   (Wilson & Zimmermann, 1986 — timing in conversation)
#
#   one_word_penalty — if words <= 2: score = max(0.10, score * 0.35)
#                      Rationale: backchannel = acknowledged but not engaged
#
# The score is stored on the speech_log entry and used to update the
# per-(response_type, tone) running average in speech_scores.json.
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from utils.log import log_activity, log_error


# ── Scoring constants ─────────────────────────────────────────────────────────

_BASE              = 0.40
_MAX_LENGTH_BONUS  = 0.30
_LENGTH_TARGET     = 25     # words at which length bonus maxes out
_QUESTION_BONUS    = 0.15
_SPEED_FAST_S      = 45     # seconds — "fast" reply
_SPEED_MED_S       = 180    # seconds — "medium" reply
_SPEED_FAST_BONUS  = 0.15
_SPEED_MED_BONUS   = 0.05
_ONE_WORD_MULT     = 0.35   # multiplier when reply is <= 2 words


def _score(
    user_reply:        str,
    reply_time_s:      float,
) -> tuple[float, int, float]:
    """
    Compute quality score.
    Returns (score, word_count, reply_time_s).
    """
    words      = len(user_reply.split())
    has_q      = "?" in user_reply

    # Length bonus: linear ramp to target
    length_bonus = min(_MAX_LENGTH_BONUS, (words / _LENGTH_TARGET) * _MAX_LENGTH_BONUS)

    # Speed bonus
    if reply_time_s <= _SPEED_FAST_S:
        speed_bonus = _SPEED_FAST_BONUS
    elif reply_time_s <= _SPEED_MED_S:
        speed_bonus = _SPEED_MED_BONUS
    else:
        speed_bonus = 0.0

    question_bonus = _QUESTION_BONUS if has_q else 0.0

    raw = _BASE + length_bonus + speed_bonus + question_bonus

    # One-word penalty
    if words <= 2:
        raw = max(0.10, raw * _ONE_WORD_MULT)

    score = min(1.0, max(0.0, raw))
    return round(score, 4), words, reply_time_s


# ── Public entry ──────────────────────────────────────────────────────────────

def evaluate_last_reply(
    user_reply: str,
    context:    Dict[str, Any],
) -> Optional[float]:
    """
    Score the most recent unevaluated reply using the current user message as
    the response signal.

    user_reply — the new message just received from the user
    context    — current cycle context (needs last_ai_timestamp)

    Returns the score (0.0–1.0) or None if nothing to evaluate.
    """
    if not user_reply or not user_reply.strip():
        return None

    try:
        from think.speech_log import get_pending_entry, score_reply

        pending = get_pending_entry()
        if not pending:
            return None

        # Measure time since the reply was emitted
        last_ai_ts  = float(context.get("last_ai_timestamp") or 0.0)
        now_ts      = time.time()
        reply_time  = (now_ts - last_ai_ts) if last_ai_ts > 0 else 999.0

        quality, word_count, rt = _score(user_reply.strip(), reply_time)

        # Theory of Mind misalignment penalty: if the user's new message
        # signals that the previous reply didn't land (correction, impasse_signal,
        # consecutive misalignments), reduce the quality score so the
        # construction grammar steers away from that (response_type, tone) pair.
        tom = context.get("theory_of_mind") or {}
        if tom.get("misaligned"):
            consec = int(tom.get("belief_model", {}).get("consecutive_misalignments", 1) or 1)
            # Penalty scales with consecutive misalignments: -0.15, -0.20, -0.25 (cap)
            penalty = min(0.25, 0.10 + consec * 0.05)
            quality = max(0.05, round(quality - penalty, 4))
            log_activity(
                f"[speech_eval] ToM misalignment penalty={penalty:.2f} "
                f"consec={consec} → adjusted q={quality:.3f}"
            )

        score_reply(
            entry_id          = pending["id"],
            quality_score     = quality,
            user_reply_words  = word_count,
            user_reply_time_s = rt,
        )

        log_activity(
            f"[speech_eval] scored id={pending['id'][:8]} "
            f"q={quality:.3f} words={word_count} time={rt:.0f}s "
            f"type={pending.get('response_type')} tone={pending.get('tone')}"
        )
        return quality

    except Exception as e:
        log_error(f"[speech_evaluator] evaluate_last_reply failed: {e}")
        return None
