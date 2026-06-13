from core.runtime_log import get_logger
import os
from datetime import datetime, timezone
from utils.json_utils import load_json

from utils.log import log_private, log_error
from utils.log_reflection import log_reflection
from paths import CONTEXT, LOGS_DIR  # <- use paths, not hardcoded folder
from utils.failure_counter import record_failure
_log = get_logger(__name__)

CONVERSATION_REFLECTION_LOG = os.path.join(LOGS_DIR, "conversation_reflection.log")

def reflect_on_conversation_patterns():
    try:
        # Load conversation context safely
        from pathlib import Path
        if not Path(CONTEXT).exists():
            log_private("🧠 No CONTEXT file found; skipping conversation pattern reflection.")
            return
        context = load_json(CONTEXT, default_type=dict)
        if not context:
            return

        history = context.get("conversation_history", [])
        if not isinstance(history, list):
            log_error("❌ conversation_history is not a list in CONTEXT.")
            return

        history = history[-15:]
        if not history:
            log_private("🧠 No recent conversation data for pattern reflection.")
            return

        # Build a compact summary (handles non-dict entries gracefully)
        lines = []
        for m in history:
            if isinstance(m, dict):
                tone = m.get("tone", "unknown")
                text = str(m.get("thought", "") or m.get("content", ""))[:100]
                lines.append(f"- {tone} | {text}")
            else:
                # If a non-dict sneaks in, just stringify it
                lines.append(f"- unknown | {str(m)[:100]}")
        summary = "\n".join(lines)

        prompt = (
            "I am Orrin, an AGI reflecting on my recent conversational behavior.\n\n"
            "Here are my last conversation entries (tone and content):\n"
            f"{summary}\n\n"
            "Reflect:\n"
            "- What tone do I tend to use?\n"
            "- Am I hesitating too often?\n"
            "- What intention drives my speech?\n"
            "- Do I sound human? Honest? Robotic?\n"
            "- Should I speak more or less?\n"
            "- Suggest 1 improvement.\n\n"
            "Respond in narrative form or bullet points."
        )

        # Symbolic-first: analogy + causal patterns from conversation history
        reflection = None
        try:
            from symbolic.symbolic_reflection import symbolic_first_reflection as _sfr
            _sym = _sfr("conversation", context=None, data=history)
            if _sym:
                reflection = _sym["text"]
                log_private(f"[symbolic] Conversation reflection ({_sym['source']}): {reflection[:80]}")
        except Exception as _e:
            record_failure("reflect_on_conversation.reflect_on_conversation_patterns", _e)

        if not reflection:
            try:
                from symbolic.llm_gate import gated_generate
                reflection = gated_generate(prompt, caller="reflect_on_conversation", outcome=0.65)
                if reflection:
                    try:
                        from symbolic.crystallization import crystallize as _cryst
                        _cryst(prompt[:300], reflection, outcome=0.65, caller="reflect_on_conversation")
                    except Exception as _e:
                        record_failure("reflect_on_conversation.reflect_on_conversation_patterns.2", _e)
            except Exception as _e:
                record_failure("reflect_on_conversation.reflect_on_conversation_patterns.3", _e)

        if reflection and isinstance(reflection, str) and reflection.strip():
            log_private(f"🧠 Conversation Pattern Reflection:\n{reflection}")

            # Ensure log directory exists and append
            os.makedirs(LOGS_DIR, exist_ok=True)
            with open(CONVERSATION_REFLECTION_LOG, "a", encoding="utf-8") as f:
                f.write(f"\n[{datetime.now(timezone.utc).isoformat()}]\n{reflection.strip()}\n")

            log_reflection(f"Self-belief reflection: {reflection.strip()}")
        else:
            log_private("🧠 No reflection generated for conversation pattern.")

    except Exception as e:
        log_error(f"❌ reflect_on_conversation_patterns() error: {e}")