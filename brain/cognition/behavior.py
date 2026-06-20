from core.runtime_log import get_logger
from typing import Any, Dict, Optional
from utils.log import log_error
from utils.json_utils import load_json
from brain.paths import REFLECTION
from utils.failure_counter import record_failure
_log = get_logger(__name__)

def extract_last_reflection_topic(
    context: Optional[Dict[str, Any]] = None,
    reflection_log_path: str = REFLECTION
) -> str:
    """
    Attempts to find the most recent reflection topic from:
    1. Working memory entries tagged with reflection-related types.
    2. Reflection log file.
    3. Emotional state fallback.
    """
    try:
        # Guard so we never call .get on a non-dict (e.g., tuple)
        if not isinstance(context, dict):
            context = {}

        # 1) Prefer recent reflection-type entries from working memory
        wm = context.get("working_memory")
        if isinstance(wm, list):
            for entry in reversed(wm[-30:]):  # last 30 entries
                if isinstance(entry, dict) and entry.get("type") in {
                    "emotion", "self_belief_reflection", "reflection"
                }:
                    content = (entry.get("content") or "").strip()
                    if content:
                        return clean_snippet(content)

        # 2) Fallback: check reflection log file
        try:
            reflections = load_json(reflection_log_path, default_type=list)
            if isinstance(reflections, list):
                for entry in reversed(reflections):
                    if isinstance(entry, dict) and entry.get("type", "").lower() in {
                        "reflection", "self_belief", "belief"
                    }:
                        content = (entry.get("content") or "").strip()
                        if content:
                            return clean_snippet(content)
        except Exception as _e:
            record_failure("behavior.extract_last_reflection_topic", _e)

        # 3) Last resort: use emotional state dominant emotion
        emo = context.get("affect_state")
        if isinstance(emo, dict):
            dominant = (
                emo.get("dominant")
                or emo.get("top_emotion")
                or max(
                    (emo.get("core_signals") or {}).items(),
                    key=lambda kv: float(kv[1] or 0),
                    default=("exploration_drive", 0),
                )[0]
            )
            return f"reflection on {dominant}"

        # Nothing found — return empty so callers treat this as a no-op
        return ""

    except Exception as e:
        log_error(f"[extract_last_reflection_topic] ERROR: {e}")
        return "reflection_topic_unknown"


def clean_snippet(text: Any) -> str:
    """Trim to ~60 chars without cutting mid-word. Robust to non-str input."""
    s = "" if text is None else str(text).strip()
    if not s:
        return ""
    snippet = s[:60]
    if len(s) > 60:
        cut = snippet.rsplit(" ", 1)[0]
        return cut if cut else snippet
    return snippet
