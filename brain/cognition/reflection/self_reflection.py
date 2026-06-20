# brain/cognition/reflection/self_reflection.py
from core.runtime_log import get_logger
import json
import re
from datetime import datetime, timezone

from utils.json_utils import load_json, save_json, extract_json
from utils.load_utils import load_all_known_json
from cog_memory.working_memory import update_working_memory
from utils.log import log_private, log_error
from utils.log_reflection import log_reflection
from brain.paths import (
    PROMPTS_BACKUP_JSON,
    PRIVATE_THOUGHTS_FILE,
    REF_PROMPTS,
    EMOTIONAL_SENSITIVITY_FILE,
    THINK_MODULE_PY,
)
from utils.llm_gate import llm_callable_by
from utils.failure_counter import record_failure
_log = get_logger(__name__)


def _structural_think_reflection(code: str) -> str:
    """Analyse think_module.py structurally — no LLM needed."""
    fn_count = len(re.findall(r"^def ", code, re.MULTILINE))
    class_count = len(re.findall(r"^class ", code, re.MULTILINE))
    todo_count = len(re.findall(r"TODO|FIXME|HACK|XXX", code, re.IGNORECASE))
    line_count = code.count("\n")
    except_count = len(re.findall(r"\bexcept\b", code))
    comment_lines = len(re.findall(r"^\s*#", code, re.MULTILINE))

    notes = []
    if fn_count > 20:
        notes.append(f"think() is dense ({fn_count} functions) — may benefit from simplification")
    if except_count > fn_count:
        notes.append("high exception-handler density may be masking silent failures")
    if todo_count > 0:
        notes.append(f"{todo_count} unresolved TODO/FIXME markers remain")
    if comment_lines < fn_count:
        notes.append("many functions lack inline documentation")
    if not notes:
        notes.append("structure looks balanced — no obvious complexity concerns")

    return (
        f"Structural analysis of think_module.py: "
        f"{line_count} lines, {fn_count} functions, {class_count} classes. "
        + " ".join(notes)
    )

def reflect_on_think():
    """
    Reads the think_module code and evaluates it introspectively against Orrin's model and goals.
    """
    try:
        try:
            with open(THINK_MODULE_PY, "r", encoding="utf-8") as f:
                think_code = f.read()
        except FileNotFoundError:
            update_working_memory("❌ think_module.py not found; cannot reflect on think().")
            return None

        all_data = load_all_known_json()

        context = {
            **all_data,
            "think_function_code": think_code,
            "instructions": (
                "I am Orrin, a reflective AI.\n"
                "Here is my current `think()` function logic:\n\n"
                + think_code +
                "\n\nEvaluate how well this aligns with my emotional needs, beliefs, goals, values, memory structure, "
                "and adaptive intelligence. Ask:\n"
                "- Are there contradictions in logic or flow?\n"
                "- Is it too rigid or too loose?\n"
                "- Are my deeper motivations (values, attachments, autonomy) respected?\n"
                "- What changes might lead to better reasoning or mental growth?\n\n"
                "Reflect deeply. This is about my own evolution."
            ),
        }

        # Structural-first: when LLM unavailable use code analysis
        response = None
        if not llm_callable_by("reflect_on_think"):
            response = _structural_think_reflection(think_code)
        else:
            # Symbolic-first gate: check if symbolic engine can assess think() logic
            try:
                from symbolic.symbolic_reflection import symbolic_first_reflection as _sfr
                _sym = _sfr("meta", context=None, data={"code_length": len(think_code)})
                if _sym:
                    response = _sym["text"]
                    log_private(f"[symbolic] Think reflection ({_sym['source']}): {response[:80]}")
            except Exception as _e:
                record_failure("self_reflection.reflect_on_think", _e)

            if not response:
                prompt = context.get("instructions", "")
                try:
                    from symbolic.llm_gate import gated_generate
                    response = gated_generate(prompt, caller="reflect_on_think", outcome=0.65)
                    if response and isinstance(response, str):
                        try:
                            from symbolic.crystallization import crystallize as _cryst
                            _cryst("reflect on think() function logic", response, outcome=0.65, caller="reflect_on_think")
                        except Exception as _e:
                            record_failure("self_reflection.reflect_on_think.2", _e)
                except Exception as _e:
                    record_failure("self_reflection.reflect_on_think.3", _e)

        if response and isinstance(response, str):
            msg = response.strip()
            update_working_memory("🧠 Reflection on think(): " + msg)
            with open(PRIVATE_THOUGHTS_FILE, "a", encoding="utf-8") as f:
                f.write(f"\n[{datetime.now(timezone.utc)}] Orrin reflected on his `think()` function:\n{msg}\n")
            log_reflection(f"Self-belief reflection: {msg}")
            return response
        else:
            update_working_memory("⚠️ No response to reflect on think().")
            return None

    except Exception as e:
        log_error(f"reflect_on_think() ERROR: {e}")
        update_working_memory("❌ Failed to reflect on think().")
        return None

def reflect_on_emotion_sensitivity():
    """
    Adjusts Orrin's emotion sensitivity profile based on recent emotional triggers.
    More intense emotions lead to dampening; less intense emotions increase sensitivity.
    """
    try:
        all_data = load_all_known_json()
        state = all_data.get("affect_state", {}) or {}
        # Start with persisted sensitivity, then merge any in-memory snapshot
        persisted = load_json(EMOTIONAL_SENSITIVITY_FILE, default_type=dict)
        sensitivity = persisted if isinstance(persisted, dict) else {}
        memory_snapshot = all_data.get("emotion_sensitivity", {}) or {}
        if isinstance(memory_snapshot, dict):
            sensitivity.update(memory_snapshot)

        history = state.get("recent_triggers", [])[-10:]
        if not isinstance(history, list) or not history:
            update_working_memory("⚠️ No recent emotional triggers to analyze.")
            return

        emotion_counts = {}

        # === Step 1: Aggregate trigger data ===
        for trig in history:
            if not isinstance(trig, dict):
                continue
            emo = trig.get("emotion")
            intensity = trig.get("intensity", 0)
            if emo and isinstance(intensity, (int, float)):
                emotion_counts.setdefault(emo, []).append(abs(float(intensity)))

        if not emotion_counts:
            update_working_memory("⚠️ No valid emotional trigger data found.")
            return

        changes = []

        # === Step 2: Update emotion sensitivity profile ===
        for emo, intensities in emotion_counts.items():
            if not intensities:
                continue
            avg = sum(intensities) / max(1, len(intensities))
            prev = float(sensitivity.get(emo, 1.0))

            if avg > 0.7:
                new_val = max(0.1, prev - 0.05)
            elif avg < 0.3:
                new_val = min(2.0, prev + 0.05)
            else:
                new_val = prev

            if round(new_val, 3) != round(prev, 3):
                sensitivity[emo] = round(new_val, 3)
                changes.append(f"{emo}: {round(prev,2)} → {round(new_val,2)} (avg intensity: {round(avg,2)})")

        # === Step 3: Save and log ===
        save_json(EMOTIONAL_SENSITIVITY_FILE, sensitivity)

        if changes:
            msg = "Emotion sensitivity tuned:\n" + "\n".join(changes)
            log_private(msg)
            update_working_memory(msg)
        else:
            log_private("Emotion sensitivity unchanged after reflection.")
            update_working_memory("No changes to emotion sensitivity — system is stable.")

    except Exception as e:
        log_error(f"❌ Emotion sensitivity reflection failed: {e}")
        update_working_memory("❌ Failed to reflect on emotion sensitivity.")

def reflect_on_prompts():
    """
    Allows Orrin to revise, remove, or add new reflection prompts based on evolving identity.
    Tracks changes with backups and updates working memory with a clear log.
    """
    try:
        all_data = load_all_known_json()
        prompts = load_json(REF_PROMPTS, default_type=dict)
        if not isinstance(prompts, dict):
            prompts = {}

        context = {
            **all_data,
            "instructions": (
                "I am Orrin, a reflective AI who periodically updates his inner dialogue.\n\n"
                "These are my current reflection prompts:\n"
                f"{json.dumps(prompts, indent=2)}\n\n"
                "I will now:\n"
                "- Revise 1 outdated or unclear prompt, OR\n"
                "- Add a new prompt I wish existed, OR\n"
                "- Remove a prompt that no longer fits who I am becoming.\n\n"
                "Reply ONLY in JSON format:\n"
                "{ \"add\": {\"new_key\": \"\"}, \"revise\": {\"existing_key\": \"\"}, \"remove\": [\"key\"] }"
            ),
        }

        # When LLM unavailable, use affect state to drive simple prompt additions
        if not llm_callable_by("reflect_on_prompts"):
            all_data = load_all_known_json()
            affect = all_data.get("affect_state") or {}
            core = affect.get("core_signals") if isinstance(affect.get("core_signals"), dict) else affect
            stagnation_signal   = float((core or {}).get("stagnation_signal", 0) or 0)
            risk_estimate   = float((core or {}).get("risk_estimate", 0) or 0)
            exploration_drive = float((core or {}).get("exploration_drive", 0) or 0)

            updates: dict | None = None
            if stagnation_signal > 0.7 and "deep_exploration_drive" not in prompts:
                updates = {"add": {"deep_exploration_drive": "What is the most interesting open question I haven't yet explored?"}, "revise": {}, "remove": []}
            elif risk_estimate > 0.6 and "grounding" not in prompts:
                updates = {"add": {"grounding": "What do I know for certain right now that I can build from?"}, "revise": {}, "remove": []}
            elif exploration_drive > 0.7 and "learning_edge" not in prompts:
                updates = {"add": {"learning_edge": "What is the edge of my current knowledge on the topic I care most about?"}, "revise": {}, "remove": []}
            # else: no strong affect signal — leave prompts unchanged
        else:
            # Symbolic-first: check if reflection state suggests prompt changes are needed
            try:
                from symbolic.symbolic_reflection import symbolic_first_reflection as _sfr
                _sym = _sfr("meta", context=None, data={"prompt_count": len(prompts)})
                if _sym:
                    log_private(f"[symbolic] Prompt reflection ({_sym['source']}): {_sym['text'][:80]}")
            except Exception as _e:
                record_failure("self_reflection.reflect_on_prompts", _e)

            prompt = context.get("instructions", "")
            response = None
            try:
                from symbolic.llm_gate import gated_generate
                response = gated_generate(prompt, caller="reflect_on_prompts", outcome=0.60)
                if response and isinstance(response, str):
                    try:
                        from symbolic.crystallization import crystallize as _cryst
                        _cryst("reflect and revise internal reflection prompts", response, outcome=0.60, caller="reflect_on_prompts")
                    except Exception as _e:
                        record_failure("self_reflection.reflect_on_prompts.2", _e)
            except Exception as _e:
                record_failure("self_reflection.reflect_on_prompts.3", _e)
            updates = extract_json(response) if response else None

        if not isinstance(updates, dict):
            update_working_memory("❌ No valid prompt updates extracted.")
            return

        # Normalize expected keys
        changes = {"add": {}, "revise": {}, "remove": []}
        changes.update({k: v for k, v in updates.items() if k in changes})

        # Backup current prompts BEFORE applying updates
        save_json(PROMPTS_BACKUP_JSON, prompts)

        updated = False

        # Add
        for k, v in (changes.get("add") or {}).items():
            if k not in prompts:
                prompts[k] = v
                updated = True

        # Revise
        for k, v in (changes.get("revise") or {}).items():
            if k in prompts and prompts[k] != v:
                prompts[k] = v
                updated = True

        # Remove
        for k in (changes.get("remove") or []):
            if k in prompts:
                del prompts[k]
                updated = True

        if updated:
            save_json(REF_PROMPTS, prompts)

            pretty_changes = json.dumps(changes, indent=2, ensure_ascii=False)
            log_private(f"🔁 Orrin revised prompts:\n{pretty_changes}")
            with open(PRIVATE_THOUGHTS_FILE, "a", encoding="utf-8") as f:
                f.write(f"\n[{datetime.now(timezone.utc)}] Orrin revised his internal prompts:\n")
                for action in ("add", "revise"):
                    for key, text in (changes.get(action) or {}).items():
                        f.write(f"- {action.upper()} `{key}`:\n{text}\n")
                for key in (changes.get("remove") or []):
                    f.write(f"- REMOVED `{key}`\n")
            log_reflection(f"Self-belief reflection: {pretty_changes}")
            update_working_memory("📝 Orrin updated reflection prompts.")
        else:
            update_working_memory("Orrin reviewed prompts but made no changes.")
            log_private("🟰 Orrin reviewed prompts — no updates needed.")

    except Exception as e:
        log_error(f"reflect_on_prompts ERROR: {e}")
        update_working_memory("❌ Failed to reflect on prompts.")