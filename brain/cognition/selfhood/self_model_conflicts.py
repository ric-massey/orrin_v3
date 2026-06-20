from core.runtime_log import get_logger
from datetime import datetime, timezone
import json
from typing import Any, Dict

from utils.json_utils import load_json, extract_json
from utils.self_model import get_self_model, save_self_model, ensure_self_model_integrity
from utils.log import log_model_issue, log_error
from brain.paths import LONG_MEMORY_FILE, PRIVATE_THOUGHTS_FILE, LOG_FILE
from cog_memory.working_memory import update_working_memory
from utils.failure_counter import record_failure
_log = get_logger(__name__)

# With the LLM tool down, gated_generate returns a truthy non-JSON echo that
# used to send extract_json into a `salvage failed` spin every ~13 s for hours.
# Gate the last-resort calls on llm_available() and keep the skip notice quiet
# (at most one per _SKIP_NOTICE_COOLDOWN_S, not per cycle).
import time as _time
_SKIP_NOTICE_COOLDOWN_S = 600.0
_last_skip_notice = 0.0


def _llm_ready(caller: str) -> bool:
    global _last_skip_notice
    try:
        from utils.llm_gate import llm_available
        if llm_available():
            return True
    except Exception:
        pass
    now = _time.monotonic()
    if now - _last_skip_notice >= _SKIP_NOTICE_COOLDOWN_S:
        _last_skip_notice = now
        _log.info("[%s] LLM unavailable — skipping last-resort generate (no update)", caller)
    return False


def _coerce_model_dict(x: Any) -> Dict[str, Any]:
    if isinstance(x, dict):
        return x
    if isinstance(x, (list, tuple)):
        for el in x:
            if isinstance(el, dict):
                return el
        return {"_tuple": list(x)}
    if isinstance(x, str):
        try:
            j = json.loads(x)
            return j if isinstance(j, dict) else {}
        except Exception:
            return {}
    return {}


def _clamp_text_fields(obj: Dict[str, Any], limits: Dict[str, int]) -> None:
    for k, lim in limits.items():
        if isinstance(obj.get(k), str) and len(obj[k]) > lim:
            obj[k] = obj[k][:lim]


def _normalize_internal_agents(sm: Dict[str, Any]) -> None:
    ia = sm.get("internal_agents")
    if not isinstance(ia, list):
        return
    normed = []
    for a in ia:
        if isinstance(a, dict):
            a.setdefault("name", "Unnamed")
            a.setdefault("beliefs", "")
            a.setdefault("values", [])
            a.setdefault("thought_log", [])
            a.setdefault("current_view", "")
            normed.append(a)
        else:
            normed.append({
                "name": str(a),
                "beliefs": "",
                "values": [],
                "thought_log": [],
                "current_view": ""
            })
    sm["internal_agents"] = normed


def _derive_recent_focus() -> list:
    """Mechanical recent_focus from live goal + working-memory state (Phase 4 /
    audit §9): what Orrin is focused on is read off what he's actually doing,
    not narrated. Deterministic, no LLM."""
    focus: list = []
    try:
        from cognition.planning.goals import load_goals
        for g in load_goals():
            if str(g.get("status", "")).lower() in ("active", "in_progress", "pending"):
                t = str(g.get("title") or g.get("name") or "").strip()
                if t and t not in focus:
                    focus.append(t)
            if len(focus) >= 3:
                break
    except Exception:
        pass
    try:
        from brain.paths import WORKING_MEMORY_FILE
        wm = load_json(WORKING_MEMORY_FILE, default_type=list) or []
        themes = [
            str(e.get("event_type"))
            for e in wm[-15:]
            if isinstance(e, dict) and e.get("event_type")
            not in (None, "", "system", "thought", "choice")
        ]
        for t in dict.fromkeys(reversed(themes)):
            if len(focus) >= 5:
                break
            label = f"recent activity: {t}"
            if label not in focus:
                focus.append(label)
    except Exception:
        pass
    return focus[:5]


def update_self_model():
    """Update self-model from symbolic data; gated_generate only as last resort."""
    self_model  = get_self_model()
    long_memory = load_json(LONG_MEMORY_FILE, default_type=list)
    if not isinstance(self_model, dict) or not isinstance(long_memory, list):
        return

    # recent_focus is maintained mechanically every consolidation pass.
    try:
        _focus = _derive_recent_focus()
        if _focus and _focus != self_model.get("recent_focus"):
            self_model["recent_focus"] = _focus
            save_self_model(self_model)
    except Exception as e:
        log_error(f"[update_self_model] recent_focus derivation error: {e}")

    # Primary: symbolic field update (no LLM)
    try:
        from symbolic.symbolic_cognition import update_self_model_fields as _usf
        upd = _usf(self_model)
        if upd["updated_fields"]:
            updated_model = dict(self_model)
            updated_model.update(upd["updated_fields"])
            _normalize_internal_agents(updated_model)
            updated_model = ensure_self_model_integrity(updated_model)
            save_self_model(updated_model)
            update_working_memory(f"Self-model updated (symbolic): {upd['changes']}")
            with open(PRIVATE_THOUGHTS_FILE, "a", encoding="utf-8") as f:
                f.write(f"\n[{datetime.now(timezone.utc)}] Symbolic self-model update:\n"
                        + "\n".join(f"- {c}" for c in upd["changes"]) + "\n")
            return
    except Exception as e:
        log_error(f"[update_self_model] symbolic path error: {e}")

    # Last resort: gated_generate when symbolic has no data
    if not _llm_ready("update_self_model"):
        return
    recent = [m.get("content") for m in long_memory[-10:]
              if isinstance(m, dict) and "content" in m]
    if not recent:
        return

    prompt = (
        "Based on these recent thoughts, produce a COMPACT JSON PATCH of only changed fields.\n"
        "Allowed fields: traits, core_beliefs, biases, recent_changes, emerging_conflicts.\n"
        'Schema: { "patch": { /* only changed keys */ } }\n'
        "Keep narrative fields under 800 chars. Return ONLY JSON.\n\n"
        f"Current model:\n{json.dumps(self_model, indent=2)[:1200]}\n\n"
        "Recent thoughts:\n" + "\n".join(f"- {r}" for r in recent)
    )

    try:
        from symbolic.llm_gate import gated_generate
        response = gated_generate(prompt, caller="update_self_model", outcome=0.65)
    except Exception as e:
        log_model_issue(f"[update_self_model] gated_generate error: {e}")
        return

    if not response:
        return

    try:
        parsed = extract_json(response)
        data   = _coerce_model_dict(parsed)
        if not data:
            return

        patch         = data.get("patch") if isinstance(data, dict) else None
        updated_model = dict(self_model)

        if isinstance(patch, dict):
            _clamp_text_fields(patch, {"identity": 800, "identity_story": 800})
            updated_model.update(patch)
        else:
            _clamp_text_fields(data, {"identity": 1200, "identity_story": 1200})
            updated_model = data

        _normalize_internal_agents(updated_model)
        updated_model = ensure_self_model_integrity(updated_model)
        save_self_model(updated_model)

        def _flat(beliefs):
            out = set()
            for b in (beliefs if isinstance(beliefs, list) else []):
                if isinstance(b, dict):
                    out.add(str(b.get("belief") or b.get("description") or json.dumps(b)).strip())
                else:
                    out.add(str(b).strip())
            return out

        changes = _flat(updated_model.get("core_beliefs", [])) - _flat(self_model.get("core_beliefs", []))
        if changes:
            update_working_memory("Orrin updated beliefs: " + ", ".join(sorted(changes)))
            with open(PRIVATE_THOUGHTS_FILE, "a", encoding="utf-8") as f:
                f.write(f"\n[{datetime.now(timezone.utc)}] Orrin revised beliefs:\n"
                        + "\n".join(f"- {c}" for c in sorted(changes)) + "\n")

    except Exception as e:
        log_model_issue(f"[update_self_model] Failed to apply patch: {e}")


def resolve_conflicts():
    """Resolve emerging self-model conflicts symbolically; gated_generate as last resort."""
    self_model = get_self_model()
    if not isinstance(self_model, dict):
        return

    conflicts = self_model.get("emerging_conflicts", [])
    if not isinstance(conflicts, list) or not conflicts:
        return

    response   = None
    resolved   = set()

    # Primary: symbolic contradiction detection + direct resolution
    try:
        from symbolic.symbolic_cognition import detect_rule_contradictions as _dc
        contradictions = _dc(self_model)
        if contradictions:
            # Mark contradictions that match known conflicts as resolvable
            contra_texts = {
                (c.get("belief", "") or c.get("reason", ""))[:80]
                for c in contradictions
            }
            resolved = {c for c in conflicts
                        if any(t in c for t in contra_texts)}
            narrative_parts = [
                f"Symbolic contradiction: {c.get('belief', '')} — {c.get('reason', '')}"
                for c in contradictions[:3]
            ]
            response = " | ".join(narrative_parts) if narrative_parts else None
    except Exception as e:
        log_error(f"[resolve_conflicts] symbolic contradiction check error: {e}")

    # Secondary: symbolic_reflection engine
    if not response:
        try:
            from symbolic.symbolic_reflection import symbolic_first_reflection as _sfr
            _sym = _sfr("meta", context=None, data={"conflicts": conflicts, "self_model": self_model})
            if _sym:
                response = _sym["text"]
        except Exception as _e:
            record_failure("self_model_conflicts.resolve_conflicts", _e)

    # Last resort: gated_generate
    if not response and not _llm_ready("resolve_conflicts"):
        return
    if not response:
        prompt = (
            "I am a reflective AI.\n"
            "Here are my current internal conflicts:\n"
            + "\n".join(f"- {c}" for c in conflicts)
            + "\n\nReflect on these tensions. Do any indicate value misalignment? "
            "Epistemic doubt? Emotional contradiction?\n"
            "If you propose concrete updates, reply as JSON:\n"
            '{ "updated_self_model": { ...optional partial fields... }, '
            '"resolved": ["conflict a"], "unresolved": ["conflict b"] }\n'
            "If you cannot change anything now, reply with a short paragraph (no JSON)."
        )
        try:
            from symbolic.llm_gate import gated_generate
            response = gated_generate(prompt, caller="resolve_conflicts", outcome=0.65)
        except Exception as e:
            log_error(f"[resolve_conflicts] gated_generate error: {e}")

    if not response:
        return

    # Log the reflection
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.now(timezone.utc)}] Conflict reflection:\n{response}\n")
        with open(PRIVATE_THOUGHTS_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.now(timezone.utc)}] Conflict reflection: {response}\n")
    except Exception as e:
        log_error(f"[resolve_conflicts] Failed to append logs: {e}")

    # Parse structured updates if LLM responded with JSON
    try:
        parsed = extract_json(response)
    except Exception:
        parsed = None

    if isinstance(parsed, dict):
        updated_fields = parsed.get("updated_self_model")
        if isinstance(updated_fields, dict):
            _clamp_text_fields(updated_fields, {"identity": 1200, "identity_story": 1200})
            _normalize_internal_agents(updated_fields)
            self_model.update(updated_fields)

        llm_resolved = parsed.get("resolved", [])
        if isinstance(llm_resolved, list):
            resolved |= set(llm_resolved)

    if resolved:
        self_model["emerging_conflicts"] = [c for c in conflicts if c not in resolved]

    self_model = ensure_self_model_integrity(self_model)
    save_self_model(self_model)
    update_working_memory(
        f"Conflict resolution: {len(resolved)} resolved, "
        f"{len(self_model.get('emerging_conflicts', []))} remaining."
    )
