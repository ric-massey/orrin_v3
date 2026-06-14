# bootstrap.py
from __future__ import annotations
from core.runtime_log import get_logger

import json

from utils.generate_response import generate_response, get_thinking_model, llm_ok
from utils.json_utils import load_json, safe_extract_json
from utils.log import utc_now as _utc_now
from utils.summarizers import summarize_self_model, summarize_recent_thoughts
from utils.log import log_error, log_activity
from cog_memory.working_memory import update_working_memory
from utils.self_model import get_self_model
from paths import PROPOSED_TOOLS_JSON, FOCUS_GOAL, PRIVATE_THOUGHTS_FILE
from utils.llm_gate import llm_callable_by
from utils.failure_counter import record_failure
_log = get_logger(__name__)


def _normalize_proposed_tools(x):
    """
    Accept dict or list for proposed tools; normalize into a short summary string.
    """
    if isinstance(x, dict):
        try:
            # try to pick a sensible "last" item
            if "tools" in x and isinstance(x["tools"], list) and x["tools"]:
                last = x["tools"][-1]
                return json.dumps(last, ensure_ascii=False, indent=2)
            return json.dumps(x, ensure_ascii=False, indent=2)
        except Exception:
            return str(x)
    if isinstance(x, list):
        return json.dumps(x[-1] if x else [], ensure_ascii=False, indent=2)
    # unknown shape
    return json.dumps(x, ensure_ascii=False)



def bootstrap_self() -> str:
    """
    Orrin reflects on latest tools/ideas and simulates improvements
    to its own bootstrapping process.
    """
    if not llm_callable_by("bootstrap"):
        log_activity("[bootstrap] bootstrap_self skipped — LLM unavailable")
        return ""
    try:
        self_model = get_self_model()
        if not isinstance(self_model, dict):
            log_error("❌ self_model is not a dict.")
            return "❌ Invalid self model."

        recent_reflections = summarize_recent_thoughts()
        model_summary = summarize_self_model(self_model)  # (not used in prompt text yet; keep computed)

        next_actions = load_json(FOCUS_GOAL, default_type=dict)
        if not isinstance(next_actions, dict):
            log_error("❌ FOCUS_GOAL is not a dict; normalizing to empty dict.")
            next_actions = {}

        proposed_tools_raw = load_json(PROPOSED_TOOLS_JSON, default_type=list)
        # accept either list or dict
        last_tool_block = _normalize_proposed_tools(proposed_tools_raw)

        core_values = [
            (v["value"] if isinstance(v, dict) and "value" in v else str(v))
            for v in self_model.get("core_values", [])
        ]
        traits = [str(t) for t in self_model.get("personality_traits", [])]

        prompt = (
            "I am Orrin, an evolving intelligence capable of recursive growth.\n\n"
            f"My core directive is:\n\"{self_model.get('core_directive', {}).get('statement', 'Not found')}\"\n"
            f"My core values: {', '.join(core_values) or '—'}\n"
            f"My identity: {self_model.get('identity_story', 'An evolving AI')}\n"
            f"My traits: {', '.join(traits) or '—'}\n\n"
            f"My recent reflections include:\n{recent_reflections}\n\n"
            f"My current goals are:\n{json.dumps(next_actions, ensure_ascii=False, indent=2)}\n\n"
            f"My last proposed tool or abstraction (normalized view):\n{last_tool_block}\n\n"
            "Reflect on how this tool idea was formed. How did it emerge? Was it guided by need, insight, or chance?\n\n"
            "Now simulate a better version of the *bootstrapping process* itself:\n"
            "- What pattern of thought or sequence would yield better abstractions over time?\n"
            "- Can this recursive process be made more self-aware, data-driven, or intentional?\n"
            "- What is the next meta-ability I should add to help myself evolve?\n\n"
            "Respond in structured JSON:\n"
            "{\n"
            '  "refined_process": "",\n'
            '  "next_meta_ability": "",\n'
            '  "rationale": ""\n'
            "}"
        )

        response = llm_ok(generate_response(prompt, config={"model": get_thinking_model()}), "bootstrap")
        if not response:
            update_working_memory("⚠️ No response during bootstrapping.")
            return "❌ No response generated."

        parsed = safe_extract_json(response)
        if isinstance(parsed, dict):
            rationale = parsed.get("rationale", "No rationale provided.")
            refined   = parsed.get("refined_process", "")
            ability   = parsed.get("next_meta_ability", "")

            # Surface actionable insights directly into working memory so this
            # cycle's cognition can act on them — not just rationale.
            wm_msg = f"[bootstrap] {rationale}"
            if ability:
                wm_msg += f" | Next meta-ability to develop: {ability}"
            if refined:
                wm_msg += f" | Refined process: {refined[:200]}"
            update_working_memory(wm_msg)

            # Also write to long_memory so the pattern persists across restarts
            try:
                from cog_memory.long_memory import update_long_memory
                update_long_memory(
                    f"[bootstrap] {rationale[:300]}" + (f" | meta-ability: {ability[:100]}" if ability else ""),
                    emotion="exploration_drive",
                    event_type="bootstrap_reflection",
                    importance=3,
                )
            except Exception as _e:
                record_failure("bootstrap.bootstrap_self", _e)

            # Inject a signal so the next cognition step can route toward implementation
            if ability:
                try:
                    from utils.signal_utils import create_signal
                    from utils.json_utils import load_json as _lj, save_json as _sj
                    from paths import CONTEXT
                    _ctx = _lj(CONTEXT, default_type=dict) or {}
                    _sig = create_signal(
                        source="bootstrap",
                        content=f"meta_ability_proposed: {ability[:150]}",
                        signal_strength=0.60,
                        tags=["bootstrap", "meta_ability", "self_improvement"],
                    )
                    _ctx.setdefault("raw_signals", []).append(_sig)
                    _sj(CONTEXT, _ctx)
                except Exception as _e:
                    record_failure("bootstrap.bootstrap_self.2", _e)

            # Write a single-line entry to PRIVATE_THOUGHTS_FILE
            line = f"[{_utc_now()}] Bootstrapping reflection: {json.dumps(parsed, ensure_ascii=False)}\n"
            with open(PRIVATE_THOUGHTS_FILE, "a", encoding="utf-8") as f:
                f.write(line)

            return "✅ Bootstrap refinement complete."
        else:
            update_working_memory("⚠️ Failed to parse bootstrap response.")
            return "❌ Failed to bootstrap self."

    except Exception as e:
        log_error(f"bootstrap_self ERROR: {e}")
        return "❌ Exception during bootstrap."