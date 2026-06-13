from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Union
import re
import textwrap

from utils.affect_utils import detect_affect_keyword
import paths
from utils.append import append_to_json
# generate_response/llm_ok are imported deferred inside summarize_chat_to_long_memory
# so this L2 storage module does not transitively load cognition (via
# generate_response → cognition.selfhood.identity) at import time.
from utils.json_utils import load_json, save_json
from utils.log import log_error
from utils.timeutils import now_iso_z

# Tokens that will cause an entry to be ignored when logging (case-insensitive)
_NOISE_TOKENS = {
    "—", "-", "--", "---",
    "(no user input)", "no user input",
    "(none)", "(null)"
}

# Strip a leading "[...]" timestamp prefix if present (e.g., "[2025-08-21T20:04:42.123Z] hello")
_LEADING_TS_RE = re.compile(r'^\[\d{4}-\d{2}-\d{2}T[^\]]+\]\s*')

def _to_dt(ts: str) -> datetime:
    """Parse ISO-8601 allowing trailing 'Z'."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))

def _to_iso_z(dt: datetime) -> str:
    """Serialize datetime to ISO-8601 with 'Z' suffix."""
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

def _clean_content(s: str) -> str:
    """Remove leading bracketed timestamp and trim whitespace."""
    s = s or ""
    return _LEADING_TS_RE.sub("", s).strip()

def get_user_input() -> str:
    """
    Return ONLY the last non-empty line from USER_INPUT without clearing the file.
    """
    try:
        p = Path(paths.USER_INPUT)
        txt = p.read_text(encoding="utf-8")
    except Exception:
        return ""
    lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
    return lines[-1] if lines else ""

def _is_noise(content: str) -> bool:
    """
    Return True if the content is empty or consists solely of noise tokens.
    """
    stripped = (content or "").strip()
    if not stripped:
        return True
    return stripped.lower() in _NOISE_TOKENS

def _create_chat_entry(
    speaker: str, content: str, timestamp: Optional[str] = None
) -> Dict[str, Any]:
    """
    Construct a chat log entry with speaker, role (compat with UI),
    content, detected emotion, and timestamp.
    """
    ts = (timestamp or now_iso_z())
    # Map internal 'speaker' to UI-friendly 'role'
    role = "assistant" if speaker.lower() in {"orrin", "assistant", "bot"} else "user"
    clean = _clean_content(content)
    return {
        "speaker": speaker,
        "role": role,            # compatibility for renderer/main.js
        "content": clean,
        "emotion": detect_affect_keyword(clean),
        # Keep both fields for compatibility, but they will be strictly monotonic across entries
        "timestamp": ts,
        "ts": ts,
    }

def log_user_message(content: str) -> None:
    """
    Append a single user message to the chat log if it is not noise.
    (Kept for compatibility, but dispatcher below will IGNORE string-only writes.)
    """
    clean = _clean_content(content)
    if not _is_noise(clean):
        append_to_json(paths.CHAT_LOG_FILE, _create_chat_entry("user", clean))

def log_dialogue_pair(user: str, orrin: str, timestamp: Optional[str] = None) -> None:
    """
    Append a user/orrin dialogue pair to the chat log. Messages that are empty,
    consist only of dashes, or where Orrin’s reply is '(no reply)' are skipped.

    Ensures STRICTLY MONOTONIC timestamps:
      - user entry gets base ts
      - orrin entry gets base ts + 1 microsecond (or more if needed)
    """
    # Base ts for this pair
    base_ts = timestamp or now_iso_z()

    # Prepare cleaned texts
    user_clean = _clean_content(user)
    orrin_clean = _clean_content(orrin or "")

    def _mirror_chat(who: str, text: str) -> None:  # → Brain Memory Inspector (conversation)
        try:
            from backend.telemetry_bridge import mirror_memory as _mm
            _mm("write", store="conversation", key=who, summary=text)
        except Exception:
            pass

    # Write user only if it's meaningful
    wrote_user = False
    if not _is_noise(user_clean):
        append_to_json(paths.CHAT_LOG_FILE, _create_chat_entry("user", user_clean, base_ts))
        _mirror_chat("user", user_clean)
        wrote_user = True

    # Consider Orrin's side independently
    if orrin_clean.lower() not in {"(no reply)", ""} and not _is_noise(orrin_clean):
        # Make assistant ts strictly greater than user ts when user was written
        if wrote_user:
            try:
                dt = _to_dt(base_ts) + timedelta(microseconds=1)
                asst_ts = _to_iso_z(dt)
            except Exception:
                asst_ts = base_ts  # fallback: still write; upstream should be robust
        else:
            # No user written; still give the assistant a valid ts (base_ts)
            asst_ts = base_ts

        append_to_json(paths.CHAT_LOG_FILE, _create_chat_entry("orrin", orrin_clean, asst_ts))
        _mirror_chat("orrin", orrin_clean)

def log_raw_user_input(entry: Union[str, Dict[str, str]]) -> None:
    """
    Dispatch logging based on the type of entry provided.

    **Finalized-pair only policy**:
      - If `entry` is a dict with 'user' and 'orrin', write the dialogue pair.
      - If `entry` is a string (early/raw user input), IGNORE to prevent duplicates.
      - Any other format is ignored (non-fatal).
    """
    try:
        if isinstance(entry, dict) and {"user", "orrin"}.issubset(entry):
            log_dialogue_pair(entry.get("user", ""), entry.get("orrin", ""), entry.get("timestamp"))
        else:
            # Ignore single-message or malformed writes to keep chat_log.json clean.
            if isinstance(entry, dict):
                log_error(f"[chat_log] log_raw_user_input called with dict missing 'user'/'orrin' keys: {list(entry.keys())}")
            return
    except Exception as exc:
        log_error(f"Error logging user input: {exc}")

def summarize_chat_to_long_memory(
    cycle_count: int,
    chat_log_file: Union[str, Path],
    long_memory_file: Union[str, Path],
) -> None:
    """
    Every 5 cycles, summarize the last 20 chat messages into a single long-term memory entry.
    After summarizing, the oldest 10 chat entries are trimmed from the log.
    """
    if cycle_count % 5:
        return

    from utils.generate_response import generate_response, llm_ok  # deferred (keeps cog_memory L2 at load)
    try:
        chat_log: list[dict[str, Any]] = load_json(chat_log_file, default_type=list)
        if not isinstance(chat_log, list):
            chat_log = []
        if len(chat_log) < 20:
            return

        recent_chats = chat_log[-20:]
        chat_text = "\n".join(str(entry.get("content", "")) for entry in recent_chats)

        prompt = (
            "Summarize the following recent conversation concisely and meaningfully, "
            "capturing main topics, emotions, and insights:\n\n"
            f"{chat_text}\n\nSummary:"
        )
        summary = llm_ok(generate_response(prompt), "chat_log")
        if not summary:
            return

        # Determine the most frequent emotion label across recent chats
        labels: list[str] = []
        for e in (entry.get("emotion") for entry in recent_chats):
            if isinstance(e, dict):
                val = e.get("emotion")
                if val:
                    labels.append(str(val))
            elif isinstance(e, str):
                labels.append(e)
        dominant_emotion = max(set(labels), key=labels.count) if labels else "neutral"

        # Route through update_long_memory for dedup and size enforcement
        from cog_memory.long_memory import update_long_memory
        update_long_memory(
            str(summary).strip(),
            emotion=dominant_emotion,
            event_type="chat_summary",
            agent="orrin",
            importance=2,
            priority=2,
            referenced=sum(int(entry.get("referenced", 0) or 0) for entry in recent_chats),
            related_memory_ids=[entry.get("id") for entry in recent_chats if entry.get("id")],
        )

        # Trim the oldest 10 entries from the chat log
        save_json(chat_log_file, chat_log[10:])

    except Exception as exc:
        log_error(f"Error summarizing chat to long memory: {exc}")

def wrap_text(text: str, width: int = 85) -> str:
    """
    Return text wrapped to the specified width. Useful for formatting console output or logs.
    """
    return "\n".join(textwrap.wrap(text, width))
