# Orrin User Input Handling
# think/think_utils/user_input.py

from core.runtime_log import get_logger
import time
import random
import re

from utils.timing import update_last_active
from affect.reward_signals.reward_signals import release_reward_signal
from cog_memory.chat_log import (
    get_user_input,            # returns last non-empty line; does NOT clear file
    summarize_chat_to_long_memory,
)
from utils.log import read_recent_errors_txt, read_recent_errors_jsonl
from cognition.selfhood.boundary_check import check_violates_boundaries
from brain.paths import CHAT_LOG_FILE, ERROR_FILE, MODEL_FAILURES_FILE, LONG_MEMORY_FILE, LAST_SEEN_USER_INPUT
from utils.signal_utils import create_signal  # required to build signal dicts
from utils.failure_counter import record_failure
_log = get_logger(__name__)


_NOISE = {"—", "-", "--", "---"}
_LEADING_TS_RE = re.compile(r'^\[\d{4}-\d{2}-\d{2}T[^\]]+\]\s*')

# Rate limiter for error/tool-failure signals: a dead tool produces a fact,
# not a drumbeat. The error files keep their full history; this only gates how
# often the same line re-enters the signal stream (once per window per line).
_ERROR_SIGNAL_COOLDOWN_CYCLES = 50
_recent_error_signals: dict[str, int] = {}  # normalized line -> last cycle emitted


def _error_signal_allowed(content: str, cycle: int) -> bool:
    key = " ".join(str(content).split())[:300]
    if not key:
        return False
    last = _recent_error_signals.get(key)
    if last is not None and (cycle - last) < _ERROR_SIGNAL_COOLDOWN_CYCLES:
        return False
    if len(_recent_error_signals) > 500:  # bound the map
        _recent_error_signals.clear()
    _recent_error_signals[key] = cycle
    return True

def _normalize(text: str) -> str:
    """Strip a leading bracketed timestamp and trim whitespace."""
    if not isinstance(text, str):
        return ""
    return _LEADING_TS_RE.sub("", text).strip()


def _load_last_seen() -> str:
    """Read the crash-safe dedup file written before each cycle processes user input."""
    try:
        return LAST_SEEN_USER_INPUT.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _persist_last_seen(text: str) -> None:
    """Write immediately to disk so dedup survives mid-cycle crashes.

    Sole writer of LAST_SEEN_USER_INPUT. The file holds exactly one line:
    a multi-line marker would never match the single-line comparison in
    log_user_input_once, breaking dedup.
    """
    try:
        single_line = " ".join(str(text).splitlines()).strip()
        LAST_SEEN_USER_INPUT.write_text(single_line, encoding="utf-8")
    except Exception as _e:
        record_failure("user_input._persist_last_seen", _e)


def log_user_input_once(user_input: str, context: dict) -> bool:
    """
    Remember the last raw user input so we don't process exact duplicates across cycles.
    Checks both in-memory context (fast path) and a crash-safe disk file (covers restarts).
    Does NOT write to chat logs here.

    Returns True when this is NEW input (first time seen), False when it is a
    duplicate of the last processed line (or empty/noise). Callers must gate
    all input-driven processing on this — a duplicate line must produce the
    same behavior as silence.
    """
    if not user_input or not user_input.strip():
        return False
    stripped = _normalize(user_input)
    if not stripped or stripped in _NOISE:
        return False
    # Fast path: in-memory check (same cycle)
    if stripped == (context.get("last_logged_user_input", "") or "").strip():
        return False
    # Crash-safe path: disk check (covers mid-cycle crashes and restarts)
    if stripped == _load_last_seen():
        context["last_logged_user_input"] = stripped  # re-sync context
        return False
    context["last_logged_user_input"] = stripped
    _persist_last_seen(stripped)  # write immediately — don't wait for context save
    return True


def is_real_user_input(user_input: str) -> bool:
    if not user_input:
        return False
    test = _normalize(user_input)
    return bool(test) and test not in _NOISE


def handle_user_input(
    context: dict,
    cycle_count: dict,
    long_memory,      # kept for signature parity; paths are used instead
    working_memory,   # kept for signature parity
    relationships: dict | None,
    speaker=None,
):
    """
    Pull the latest user input (last non-empty line), create signals, and update a few
    context timestamps/flags. This function NEVER clears user_input.txt.
    """
    user_input_raw = get_user_input()
    user_input = _normalize(user_input_raw)

    # De-dupe back-to-back identical lines across cycles (normalized).
    # get_user_input() returns the last non-empty chat line without clearing
    # the file, so the same line reappears every cycle until the user speaks
    # again — only the FIRST sighting counts as input; afterwards it is silence.
    is_new_input = log_user_input_once(user_input, context)
    fresh_user_input = is_new_input and is_real_user_input(user_input)

    # Downstream consumers (speaker, select_function, workspace…) read
    # latest_user_input as "the user spoke this turn" — populate it only on
    # the first sighting so a stale chat-log line can't re-trigger replies,
    # rewards, or attention every cycle.
    context["latest_user_input_raw"] = user_input_raw if fresh_user_input else ""
    context["latest_user_input"] = user_input if fresh_user_input else ""

    # Timing markers that OrrinSpeaker uses to throttle talking
    if fresh_user_input:
        context["last_user_timestamp"] = time.time()
    context.setdefault("last_ai_timestamp", 0.0)

    raw_signals = []

    # Relationship features (safe defaults)
    rel_map = relationships or {}
    user_id = context.get("user_id", "user")
    rel_data = rel_map.get(user_id, {"influence_score": 0.5, "recent_emotional_effect": "neutral"})
    influence = float(rel_data.get("influence_score", 0.5) or 0.5)
    emotional_effect = rel_data.get("recent_emotional_effect", "")

    # Surface user's last perceived emotion to the speaker for tone shaping
    if emotional_effect:
        context["last_user_emotion"] = emotional_effect

    _emo_raw = context.get("affect_state") or {}
    _core_raw = _emo_raw.get("core_signals") or _emo_raw
    exploration_drive = float(_core_raw.get("exploration_drive", 0.5) or 0.5)
    dynamic_signal_strength = round(0.3 + 0.4 * exploration_drive + 0.2 * influence, 3)

    if fresh_user_input:
        # Score the previous reply using this new message as the feedback signal
        try:
            from think.speech_evaluator import evaluate_last_reply as _eval_reply
            _eval_reply(user_input, context)
        except Exception as _e:
            record_failure("user_input.handle_user_input", _e)

        # Reward for human engagement
        release_reward_signal(
            context,
            signal_type="connection",
            actual_reward=1.0,
            expected_reward=0.4,
            effort=0.2,
            mode="phasic",
            source="user_input_received",
        )

        raw_signals.append(
            create_signal(
                source="user_input",
                content=user_input,
                signal_strength=min(dynamic_signal_strength, 1.0),
                tags=["user_input", "human_contact", "high_importance", "novelty"],
            )
        )

        # Summarize chat into long memory periodically (uses file paths)
        count = int((cycle_count or {}).get("count", 0) or 0)
        summarize_chat_to_long_memory(count, CHAT_LOG_FILE, LONG_MEMORY_FILE)

    # If we got nothing meaningful from the user, add a low-strength internal stagnation_signal prompt
    if not raw_signals:
        stagnation_signal_prompt = random.choice([
            "There’s been no input lately. Should I reflect, dream, or create something new?",
            "Silence again. What internal need should I act on?",
            "I'm alone with my thoughts. How should I use this time?",
        ])
        raw_signals.append(
            create_signal(
                source="internal",
                content=stagnation_signal_prompt,
                signal_strength=0.3,
                tags=["no_input", "internal_thought", "stagnation_signal"],
            )
        )

    # Surface recent error lines as low/medium-strength signals — rate-limited:
    # the same error line enters the signal stream at most once per cooldown
    # window, so one dead tool can't dominate attention with a failure drumbeat.
    _cycle_now = int((cycle_count or {}).get("count", 0) or 0)
    try:
        txt_errors = read_recent_errors_txt(ERROR_FILE, max_lines=5) or []
        for e in txt_errors:
            if not _error_signal_allowed(e, _cycle_now):
                continue
            raw_signals.append(
                create_signal(
                    source="system",
                    content=e.strip(),
                    signal_strength=0.4,
                    tags=["error", "penalty_signal", "system"],
                )
            )

        # error_router appends events to model_failures.jsonl (DATA_DIR); the old
        # logs/model_failures.json had no writer anywhere — map-drift fix,
        # DATA_FILE_AUDIT 2026-06-11 §7.
        json_errors = read_recent_errors_jsonl(MODEL_FAILURES_FILE, max_items=5) or []
        for err in json_errors:
            msg = (err or {}).get("msg") or (err or {}).get("error") or "Unknown model failure."
            if not _error_signal_allowed(str(msg), _cycle_now):
                continue
            raw_signals.append(
                create_signal(
                    source="system",
                    content=str(msg).strip(),
                    signal_strength=0.4,
                    tags=["error", "penalty_signal", "model"],
                )
            )
    except Exception as e:
        raw_signals.append(
            create_signal(
                source="self_monitoring",
                content=f"⚠️ Failed to read error files: {e}",
                signal_strength=0.3,
                tags=["internal", "monitoring"],
            )
        )

    # ── Values-check stage: can Orrin refuse this? ────────────────────────
    if fresh_user_input:
        try:
            # Wonder trigger detection — runs on every user input
            try:
                from cognition.wonder import detect_wonder_trigger as _dwt
                _dwt(user_input, context)
            except Exception as _e:
                record_failure("user_input.handle_user_input.2", _e)

            # Comprehension layer — parse user input into structured state events.
            # This replaces raw contagion + keyword detection with structured parsing.
            # Contagion is called inside comprehend() using the parsed emotion signal.
            try:
                from cognition.comprehension import comprehend as _comprehend
                _comprehend(user_input, context)
            except Exception:
                # Fallback: raw contagion if comprehension unavailable
                try:
                    from cognition.contagion import apply_emotional_contagion
                    apply_emotional_contagion(user_input, context, influence=influence)
                except Exception as _e:
                    record_failure("user_input.handle_user_input.3", _e)

            from cognition.selfhood.values_check import evaluate_input_against_self, handle_refusal
            from utils.self_model import get_self_model as _gsm
            _self_model = context.get("self_model") or _gsm()
            _emo = context.get("affect_state", {})
            _should_refuse, _reason = evaluate_input_against_self(user_input, _self_model, _emo, context)
            if _should_refuse:
                _refuse_sig = handle_refusal(user_input, _reason, context, _emo)
                if _refuse_sig:
                    # Refuse signal wins — inject it as the only signal this cycle
                    raw_signals = [_refuse_sig]
        except Exception as _e:
            record_failure("user_input.handle_user_input.4", _e)

    # Boundary filter
    signals = []
    for signal in raw_signals:
        content = signal.get("content", "")
        if check_violates_boundaries(content):
            from cog_memory.working_memory import update_working_memory
            update_working_memory({
                "content": "⚠️ Input violated boundaries. Skipped.",
                "event_type": "system",
                "importance": 2,
                "priority": 2,
            })
            continue
        signals.append(signal)

    # Touch last-active if anything survived filtering
    if signals:
        update_last_active()

    # JSON-safe container if the context is serialized later
    context["_logged_system_signals"] = []

    return signals, context
