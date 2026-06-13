from core.runtime_log import get_logger
import json
from datetime import datetime, timezone

from utils.json_utils import load_json, save_json
from utils.load_utils import load_all_known_json
from cog_memory.working_memory import update_working_memory
from utils.log import log_private, log_error
from utils.log_reflection import log_reflection
from paths import CASUAL_RULES
from utils.failure_counter import record_failure
_log = get_logger(__name__)


def reflect_on_rules_used():
    """
    Evolve the causal rule engine using symbolic analysis of firing history.
    Proposes and applies add/revise/remove directly — no LLM.
    gated_generate() only if there are genuine gaps that need language synthesis.
    """
    try:
        all_data = load_all_known_json()

        casual_rules = all_data.get("casual_rules")
        if not isinstance(casual_rules, dict):
            casual_rules = load_json(CASUAL_RULES, default_type=dict) or {}

        long_memory = all_data.get("long_memory", [])
        if not isinstance(long_memory, list):
            long_memory = []

        recent_outcomes = [
            {"task": str(m.get("content", ""))[:60], "outcome": "outcome", "reason": ""}
            for m in long_memory[-15:]
            if isinstance(m, dict) and "content" in m
            and ("result" in str(m.get("content", "")).lower()
                 or "outcome" in str(m.get("content", "")).lower())
        ]

        if not recent_outcomes:
            update_working_memory("No recent outcome data for rule analysis.")
            return

        # ── Symbolic rule health assessment ───────────────────────────────────
        sym_summary = ""
        try:
            from symbolic.symbolic_reflection import symbolic_first_reflection as _sfr
            _sym = _sfr("rules", context=None, data=recent_outcomes)
            if _sym:
                sym_summary = _sym["text"]
                log_private(f"[symbolic] Rules ({_sym['source']}): {sym_summary[:80]}")
        except Exception as _e:
            record_failure("rule_reflection.reflect_on_rules_used", _e)

        # ── Symbolic rule proposals (primary path — no LLM) ──────────────────
        try:
            from symbolic.symbolic_cognition import propose_rule_changes as _prc
            proposals = _prc(recent_outcomes)
        except Exception:
            proposals = {"add": [], "revise": [], "remove": []}

        updated = False

        # Apply revisions directly to symbolic rule engine
        try:
            from symbolic.rule_engine import get_all_rules, SYMBOLIC_RULES_FILE
            sym_rules = get_all_rules()
            for r_rev in proposals.get("revise", []):
                for rule in sym_rules:
                    if rule.get("id") == r_rev.get("id") and not rule.get("tombstone"):
                        old_conf = float(rule.get("confidence", 0.5))
                        rule["confidence"] = max(old_conf - 0.04, 0.10)
                        log_private(
                            f"[sym_cog] Revised rule {rule['id']}: "
                            f"conf {old_conf:.2f}→{rule['confidence']:.2f} "
                            f"({r_rev.get('reason', '')})"
                        )
                        updated = True
            if updated:
                save_json(SYMBOLIC_RULES_FILE, sym_rules)
                try:
                    from symbolic import rule_engine as _re
                    _re._rules_cache = []
                except Exception as _e:
                    record_failure("rule_reflection.reflect_on_rules_used.2", _e)
        except Exception as _e:
            record_failure("rule_reflection.reflect_on_rules_used.3", _e)

        # Apply adds to casual_rules (the legacy store)
        for rule in proposals.get("add", []):
            domain = rule.get("domain", "GENERAL")
            cond   = rule.get("if", "")
            then   = rule.get("then", "")
            if domain and cond and then:
                casual_rules.setdefault(domain, []).append({"if": cond, "then": then})
                updated = True

        # Apply removes to casual_rules
        for rule in proposals.get("remove", []):
            domain = rule.get("domain", "")
            rule_text = rule.get("rule", "") or rule.get("if", "")
            if domain and rule_text and domain in casual_rules:
                before = len(casual_rules[domain])
                casual_rules[domain] = [
                    r for r in casual_rules[domain] if r.get("if") != rule_text
                ]
                if len(casual_rules[domain]) < before:
                    updated = True

        if updated:
            save_json(CASUAL_RULES, casual_rules)
            summary = json.dumps(proposals, indent=2, ensure_ascii=False)
            log_private(f"[{datetime.now(timezone.utc)}] Symbolic rule updates:\n{summary}")
            log_reflection(f"Rule reflection: {summary[:300]}")
            update_working_memory(
                f"Orrin updated rules symbolically: "
                f"{len(proposals['add'])} added, "
                f"{len(proposals['revise'])} revised, "
                f"{len(proposals['remove'])} removed."
            )
        else:
            update_working_memory("Rule analysis complete — no changes warranted by data.")

        # ── gated_generate — only if there are genuine rule gaps needing synthesis
        gaps = proposals.get("add", [])
        if not gaps and not sym_summary:
            return  # nothing to synthesize

        if gaps and len(casual_rules) < 10:
            # Rule base is sparse — let the gate decide if LLM is warranted
            prompt = (
                "I am Orrin. My symbolic rule base is sparse. "
                f"Recent outcomes suggest these gaps:\n"
                + "\n".join(f"- {g.get('if', '')}: {g.get('then', '')}" for g in gaps[:3])
                + "\nSuggest 1-2 concrete if/then rules for these gaps. "
                "Respond as JSON: [{\"if\": \"...\", \"then\": \"...\", \"domain\": \"...\"}]"
            )
            try:
                from symbolic.llm_gate import gated_generate
                from utils.json_utils import extract_json
                raw      = gated_generate(prompt, caller="reflect_on_rules_used", outcome=0.60)
                llm_rules = extract_json(raw) or []
                if isinstance(llm_rules, list):
                    for lr in llm_rules:
                        if isinstance(lr, dict) and lr.get("if") and lr.get("then"):
                            dom = lr.get("domain", "GENERAL")
                            casual_rules.setdefault(dom, []).append(
                                {"if": lr["if"], "then": lr["then"]}
                            )
                    save_json(CASUAL_RULES, casual_rules)
                    log_private(f"[llm_gate] Added {len(llm_rules)} rules from synthesis.")
            except Exception as _e:
                record_failure("rule_reflection.reflect_on_rules_used.4", _e)

    except Exception as e:
        log_error(f"reflect_on_rules_used ERROR: {e}")
        update_working_memory("❌ Rule reflection failed.")
