from core.runtime_log import get_logger
import json
from datetime import datetime, timezone

from utils.json_utils import load_json, save_json
from utils.self_model import get_self_model, save_self_model, ensure_self_model_integrity
from utils.log import log_error, log_private
from utils.log_reflection import log_reflection
from cog_memory.working_memory import update_working_memory
from affect.update_affect_state import update_affect_state
from cognition.maintenance.self_modeling import self_model_maintenance_cycle
from cognition.planning.goals import maybe_complete_goals
from affect.reward_signals.reward_signals import release_reward_signal
from brain.paths import (
    NEUTRAL_REFLECTION_COUNT_JSON,
    LONG_MEMORY_FILE,
    PRIVATE_THOUGHTS_FILE,
    REFLECTION,
    GOALS_FILE,
    SELF_BELIEF_REVISIONS_FILE,
)
from utils.failure_counter import record_failure
_log = get_logger(__name__)

NEUTRAL_REFLECT_FILE = NEUTRAL_REFLECTION_COUNT_JSON


def load_neutral_count() -> int:
    try:
        cnt = load_json(NEUTRAL_REFLECT_FILE, default_type=int)
        if isinstance(cnt, (int, float)):
            return int(cnt)
        if isinstance(cnt, str) and cnt.strip().isdigit():
            return int(cnt.strip())
    except Exception as _e:
        record_failure("reflect_on_self_belief.load_neutral_count", _e)
    return 0


def save_neutral_count(count: int) -> None:
    try:
        save_json(NEUTRAL_REFLECT_FILE, int(count))
    except Exception as _e:
        record_failure("reflect_on_self_belief.save_neutral_count", _e)


# ── Core value evolution — symbolic first, gated_generate last resort ─────────

def evolve_core_value(self_model: dict) -> str:
    try:
        old_values = self_model.get("core_values", [])
        if isinstance(old_values, list):
            old_values = [{"value": v} if isinstance(v, str) else dict(v) for v in old_values]
            self_model["core_values"] = old_values
        else:
            old_values = []
            self_model["core_values"] = old_values

        # Primary: derive value from causal graph (no LLM)
        from symbolic.symbolic_cognition import derive_core_value as _dcv
        out = _dcv()

        # Last resort: gated_generate
        if not out or not out.get("value"):
            prompt = (
                "You are an AGI designed for self-growth. "
                "Invent a new core value (short phrase) or mutate an existing one, justify briefly.\n"
                f"Current values: {json.dumps(old_values)}\n"
                'Respond as JSON: {"value": "...", "justification": ""}'
            )
            try:
                from symbolic.llm_gate import gated_generate
                from utils.json_utils import extract_json
                raw = gated_generate(prompt, caller="evolve_core_value", outcome=0.70)
                out = extract_json(raw) or {}
            except Exception:
                out = {}

        value         = str(out.get("value", "")).strip()
        justification = str(out.get("justification", "")).strip()

        if not value:
            return "⚠️ No new value produced."

        values_only = [v.get("value", "") for v in old_values]
        if value not in values_only:
            self_model["core_values"].append({"value": value, "justification": justification})
        else:
            for v in self_model["core_values"]:
                if v.get("value") == value:
                    v["justification"] = justification

        save_self_model(self_model)
        update_working_memory(f"🌱 Value evolved: '{value}' — {justification}")
        release_reward_signal({}, signal_type="novelty", actual_reward=1.2,
                              expected_reward=0.6, effort=0.8, mode="phasic",
                              source="evolved core value")
        return f"🌱 Evolved: {value} — {justification}"
    except Exception:
        return "⚠️ Failed to evolve value."


# ── Main reflection ────────────────────────────────────────────────────────────

def reflect_on_self_beliefs():
    try:
        self_model     = ensure_self_model_integrity(get_self_model())
        long_memory    = load_json(LONG_MEMORY_FILE, default_type=list) or []
        reflection_log = load_json(REFLECTION,       default_type=list) or []
        neutral_count  = load_neutral_count()

        belief_types = {"self_belief_reflection", "self_model_update", "core_value_update"}
        recent_belief_events = [
            m.get("content") for m in reversed(long_memory)
            if isinstance(m, dict) and m.get("event_type") in belief_types
        ][:10]

        # ── Step 1: Symbolic belief assessment (primary path) ─────────────────
        response = None
        try:
            from symbolic.symbolic_cognition import assess_beliefs as _ab
            sym = _ab(self_model)
            if sym.get("narrative") and "insufficient" not in sym["narrative"]:
                response = sym["narrative"]
                log_private(f"[sym_cog] Belief assessment: {response[:80]}")
        except Exception as _e:
            record_failure("reflect_on_self_belief.reflect_on_self_beliefs", _e)

        # ── Step 2: symbolic_reflection engine ────────────────────────────────
        if not response:
            try:
                from symbolic.symbolic_reflection import symbolic_first_reflection as _sfr
                _sym = _sfr("self_belief", context=None, data={
                    "self_model": self_model,
                    "recent_belief_events": recent_belief_events,
                })
                if _sym:
                    response = _sym["text"]
                    log_private(f"[sym_reflect] Self-belief ({_sym['source']}): {response[:80]}")
            except Exception as _e:
                record_failure("reflect_on_self_belief.reflect_on_self_beliefs.2", _e)

        # ── Step 3: gated_generate — strict last resort ───────────────────────
        if not response:
            sm_short     = json.dumps(self_model, ensure_ascii=False)[:1200]
            events_short = "\n".join(f"- {e}" for e in recent_belief_events[:6])
            prompt = (
                "I am Orrin. In 3-4 sentences: review my self-model for contradiction, "
                "tension, or drift. Say 'beliefs are stable' if none found.\n\n"
                f"SELF MODEL:\n{sm_short}\n\nRECENT BELIEF EVENTS:\n{events_short}"
            )
            try:
                from symbolic.llm_gate import gated_generate
                response = gated_generate(prompt, caller="reflect_on_self_belief", outcome=0.70)
            except Exception as e:
                log_error(f"LLM failure in reflect_on_self_beliefs: {e}")
                update_working_memory("❌ LLM error during self-belief reflection.")
                return "❌ LLM error."

        if not response or not response.strip():
            update_working_memory("⚠️ No valid output from self-belief reflection.")
            return "❌ Invalid output."

        response = response.strip()
        update_working_memory(f"🧭 Self-belief reflection:\n{response}")
        log_reflection(f"Self-belief reflection: {response}")
        try:
            with open(PRIVATE_THOUGHTS_FILE, "a", encoding="utf-8") as f:
                f.write(f"\n[{datetime.now(timezone.utc)}] Self-belief reflection:\n{response}\n")
        except Exception as _e:
            record_failure("reflect_on_self_belief.reflect_on_self_beliefs.3", _e)

        now_iso = datetime.now(timezone.utc).isoformat()
        reflection_log.append({
            "type": "self-belief",
            "timestamp": now_iso,
            "content": response,
        })
        save_json(REFLECTION, reflection_log)

        # ── Write to self_belief_revisions ledger ─────────────────────────────
        # The ledger is a list of structured belief-reflection events so the
        # self-authorship chain (tensions, autobiography) has something to read.
        # Only written when reflection is non-trivial (not a "stable" no-op).
        _STABLE_PHRASES = ("beliefs are stable", "no change needed", "in alignment",
                           "no contradiction", "appears consistent")
        _is_trivial = any(p in response.lower() for p in _STABLE_PHRASES)
        if not _is_trivial:
            try:
                sbr = load_json(SELF_BELIEF_REVISIONS_FILE, default_type=list)
                if not isinstance(sbr, list):
                    sbr = []
                sbr.append({
                    "timestamp":  now_iso,
                    "source":     "reflect_on_self_beliefs",
                    "reflection": response[:500],
                    "status":     "recorded",
                })
                # Keep last 100 entries
                save_json(SELF_BELIEF_REVISIONS_FILE, sbr[-100:])
                log_private(f"[self_belief] Ledger entry written ({len(response)} chars)")
            except Exception as _e:
                _log.warning("self_belief_revisions write failed: %s", _e)

        # ── Step 4: Self-model update — symbolic only, no LLM ────────────────
        try:
            from symbolic.symbolic_cognition import update_self_model_fields as _usf
            upd = _usf(self_model)
            if upd["updated_fields"]:
                self_model.update(upd["updated_fields"])
                save_self_model(self_model)
                update_working_memory(f"🔁 Self-model updated: {upd['changes']}")
                log_private(f"🔁 Symbolic self-model update: {upd['changes']}")
        except Exception as _e:
            record_failure("reflect_on_self_belief.reflect_on_self_beliefs.4", _e)

        # ── Step 5: Goal generation — symbolic only, no LLM ──────────────────
        try:
            goals = load_json(GOALS_FILE, default_type=list) or []
            from symbolic.symbolic_cognition import generate_goals as _gg
            new_goals    = _gg(self_model)
            now          = datetime.now(timezone.utc).isoformat()
            existing     = {g.get("name", "") for g in goals if isinstance(g, dict)}
            for ng in new_goals:
                if ng["name"] not in existing and "contradiction" not in ng["name"].lower():
                    goals.append({**ng, "status": "active", "timestamp": now,
                                  "last_updated": now, "emotional_intensity": 0.5,
                                  "history": [{"event": "created", "timestamp": now}]})
                    update_working_memory(f"🌱 New symbolic goal: {ng['name']}")
            save_json(GOALS_FILE, goals)
        except Exception as _e:
            record_failure("reflect_on_self_belief.reflect_on_self_beliefs.5", _e)

        # ── Step 6: Contradiction detection and resolution goal ───────────────
        try:
            goals = load_json(GOALS_FILE, default_type=list) or []
            from symbolic.symbolic_cognition import detect_rule_contradictions as _dc
            contradictions = _dc(self_model)
            has_contra_goal = any(
                isinstance(g, dict)
                and g.get("name") == "Resolve self-model contradiction"
                and g.get("status") in {"pending", "in_progress", "active"}
                for g in goals
            )
            if contradictions and not has_contra_goal:
                now    = datetime.now(timezone.utc).isoformat()
                detail = (contradictions[0].get("reason")
                          or contradictions[0].get("belief", ""))[:80]
                goals.append({
                    "name": "Resolve self-model contradiction",
                    "tier": "short_term",
                    "description": f"Symbolic conflict: {detail}",
                    "status": "active",
                    "timestamp": now, "last_updated": now,
                    "emotional_intensity": 0.6,
                    "history": [{"event": "created", "timestamp": now}],
                })
                save_json(GOALS_FILE, goals)
                update_working_memory("📌 Contradiction-resolution goal created (symbolic).")
        except Exception as _e:
            record_failure("reflect_on_self_belief.reflect_on_self_beliefs.6", _e)

        # ── Long-term memory ───────────────────────────────────────────────────
        try:
            from cog_memory.remember import remember
            remember({
                "type": "self_belief_reflection",
                "reflection": response,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as _e:
            record_failure("reflect_on_self_belief.reflect_on_self_beliefs.7", _e)

        # ── Neutral streak logic ───────────────────────────────────────────────
        neutral_triggers = ("beliefs are stable", "no change needed", "in alignment")
        if any(p in response.lower() for p in neutral_triggers):
            neutral_count += 1
            save_neutral_count(neutral_count)
            update_working_memory("😐 No meaningful belief update.")
            update_affect_state(trigger="reflection_stagnation")
        else:
            neutral_count = 0
            save_neutral_count(neutral_count)

        if neutral_count >= 3:
            update_working_memory("🔥 Neutral streak — forcing symbolic value evolution.")
            msg = evolve_core_value(self_model)
            update_working_memory(msg)
            save_neutral_count(0)

        self_model_maintenance_cycle()
        maybe_complete_goals()
        return "✅ Self-belief reflection complete."

    except Exception as e:
        log_error(f"reflect_on_self_beliefs ERROR: {e}")
        update_working_memory("❌ Reflection process failed.")
        return "❌ Reflection error."
