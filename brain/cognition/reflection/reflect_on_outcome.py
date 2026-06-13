from core.runtime_log import get_logger
import json

from utils.json_utils import load_json, save_json
from utils.self_model import get_self_model, save_self_model
from utils.load_utils import load_all_known_json
from cog_memory.working_memory import update_working_memory
from utils.log import log_private, log_error
from utils.log_reflection import log_reflection
from paths import (
    OUTCOMES_JSON, SELF_MODEL_BACKUP_JSON,
    PRIVATE_THOUGHTS_FILE, LONG_MEMORY_FILE, WORKING_MEMORY_FILE,
)
from utils.timeutils import now_iso_z
from utils.failure_counter import record_failure
_log = get_logger(__name__)



def _make_outcome_key(o: dict) -> tuple:
    return (
        str(o.get("task",      "")),
        str(o.get("reason",    "")),
        str(o.get("outcome",   "")),
        str(o.get("timestamp", "")),
    )


def reflect_on_outcomes():
    """
    Reflect on recent unreviewed outcomes using symbolic analysis first.
    LLM is called only via gated_generate() as a strict last resort.
    """
    try:
        data            = load_all_known_json()
        merged_outcomes = data.get("Outcomes", [])
        if not isinstance(merged_outcomes, list):
            merged_outcomes = []

        outcomes_full = load_json(OUTCOMES_JSON, default_type=list) or []
        reflected_keys = {
            _make_outcome_key(o)
            for o in outcomes_full
            if isinstance(o, dict) and o.get("reflected_on")
        }

        recent_unreviewed = []
        for o in reversed([o for o in merged_outcomes if isinstance(o, dict)]):
            if len(recent_unreviewed) >= 15:
                break
            if (_make_outcome_key(o) not in reflected_keys
                    and all(k in o for k in ("task", "outcome", "reason"))):
                recent_unreviewed.append(o)
        recent_unreviewed.reverse()

        if not recent_unreviewed:
            log_private("🧠 Outcome reflection: No unreviewed outcomes found.")
            return

        summary_lines = [
            f"- Task: {o['task']} | Outcome: {o['outcome']} | Reason: {o['reason']}"
            for o in recent_unreviewed
        ]

        # ── Symbolic analysis (primary path) ─────────────────────────────────
        from symbolic.symbolic_cognition import analyze_outcomes as _ao
        sym_result = _ao(recent_unreviewed)
        reflection = sym_result["narrative"] if sym_result.get("quality_score", 0) >= 0.3 else None

        if not reflection:
            try:
                from symbolic.symbolic_reflection import symbolic_first_reflection as _sfr
                _sym = _sfr("outcome", context=None, data=recent_unreviewed)
                if _sym:
                    reflection = _sym["text"]
                    log_private(f"🧠 [symbolic] Outcome ({_sym['source']}): {reflection[:80]}")
            except Exception as _e:
                record_failure("reflect_on_outcome.reflect_on_outcomes", _e)

        # ── gated_generate() — strict last resort ─────────────────────────────
        if not reflection:
            self_model      = get_self_model()
            current_beliefs = self_model.get("core_beliefs", [])
            prompt = (
                "I am Orrin, analyzing my own decision outcomes.\n"
                f"Recent outcomes:\n{chr(10).join(summary_lines)}\n\n"
                "Current core beliefs:\n"
                + "\n".join(f"- {b}" for b in current_beliefs) + "\n\n"
                "Are any motivations causing repeated failure? "
                "Did certain values correlate with success? "
                "Respond with a brief narrative insight."
            )
            try:
                from symbolic.llm_gate import gated_generate
                reflection = gated_generate(prompt, caller="reflect_on_outcome", outcome=0.65)
            except Exception as e:
                log_error(f"reflect_on_outcomes gated_generate error: {e}")

        if not reflection:
            log_private("🧠 Outcome reflection: No response generated.")
            return

        log_private(f"🧠 Outcome Reflection:\n{reflection}")
        with open(PRIVATE_THOUGHTS_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n[{now_iso_z()}] Reflection on outcomes:\n{reflection}\n")
        log_reflection(f"Outcome reflection: {reflection.strip()}")

        # ── Persist to long memory ─────────────────────────────────────────────
        try:
            from cog_memory.long_memory import update_long_memory as _ulm
            _ulm(reflection, emotion="reflective", event_type="reflection",
                 agent="orrin", importance=3, priority=2)
        except Exception:
            lm = load_json(LONG_MEMORY_FILE, default_type=list) or []
            lm.append({"type": "reflection", "source": "reflect_on_outcomes",
                       "content": reflection, "timestamp": now_iso_z()})
            save_json(LONG_MEMORY_FILE, lm)

        # ── Mark outcomes as reflected ─────────────────────────────────────────
        recent_keys = {_make_outcome_key(o) for o in recent_unreviewed}
        for o in outcomes_full:
            try:
                if _make_outcome_key(o) in recent_keys:
                    o["reflected_on"] = True
                    o.setdefault("reflected_timestamp", now_iso_z())
            except Exception:
                continue
        save_json(OUTCOMES_JSON, outcomes_full)

        # ── Repeated failure → directly revise rules symbolically ─────────────
        failures = [o for o in recent_unreviewed
                    if str(o.get("outcome", "")).lower() in ("failure", "failed")]
        if len(failures) >= 3:
            update_working_memory("⚠️ Repeated failures — revising symbolic rules directly.")
            try:
                from symbolic.symbolic_cognition import propose_rule_changes as _prc
                from symbolic.rule_engine import get_all_rules, SYMBOLIC_RULES_FILE
                from utils.json_utils import save_json as _sj
                proposals = _prc(recent_unreviewed)
                rules = get_all_rules()
                changed = False
                for r_rev in proposals.get("revise", []):
                    for rule in rules:
                        if rule.get("id") == r_rev.get("id") and not rule.get("tombstone"):
                            rule["confidence"] = max(float(rule.get("confidence", 0.5)) - 0.05, 0.10)
                            changed = True
                if changed:
                    _sj(SYMBOLIC_RULES_FILE, rules)
                    log_private(f"[sym_cog] Revised {len(proposals['revise'])} rules from failures.")
            except Exception as _e:
                record_failure("reflect_on_outcome.reflect_on_outcomes.2", _e)

        # ── Poor quality → update self-model from symbolic data ───────────────
        if sym_result.get("quality_score", 0.5) < 0.35:
            try:
                sm = get_self_model()
                from symbolic.symbolic_cognition import update_self_model_fields as _usf
                upd = _usf(sm)
                if upd["updated_fields"]:
                    sm.update(upd["updated_fields"])
                    save_self_model(sm)
                    save_json(SELF_MODEL_BACKUP_JSON, sm)
                    log_private(f"Self-model updated from outcome data: {upd['changes']}")
            except Exception as _e:
                record_failure("reflect_on_outcome.reflect_on_outcomes.3", _e)

    except Exception as e:
        log_error(f"reflect_on_outcomes() ERROR: {e}")
        update_working_memory("❌ Failed to reflect on outcomes.")


def evaluate_recent_cognition():
    """
    Evaluate recent cognition quality entirely from symbolic memory analysis.
    No LLM call.
    """
    try:
        wm = load_json(WORKING_MEMORY_FILE, default_type=list) or []
        lm = load_json(LONG_MEMORY_FILE,    default_type=list) or []

        from symbolic.symbolic_cognition import evaluate_cognition as _ec
        result = _ec(wm[-10:], lm[-20:])

        update_working_memory(
            f"Cognition eval: alignment={result['alignment_score']:.2f} | "
            f"insights={len(result['insights'])} | missteps={len(result['missteps'])} | "
            f"adjust: {'; '.join(result['recommended_adjustments'])}"
        )
        with open(PRIVATE_THOUGHTS_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n[{now_iso_z()}] Cognition evaluation:\n"
                    f"{json.dumps(result, indent=2)}\n")

    except Exception as e:
        log_error(f"evaluate_recent_cognition() ERROR: {e}")
        update_working_memory("❌ Failed to evaluate recent cognition.")
