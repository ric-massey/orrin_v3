# evaluation.py
from __future__ import annotations
from core.runtime_log import get_logger

import json
from typing import Any, Dict, List

from utils.generate_response import generate_response, get_thinking_model, llm_ok
from utils.log import utc_now as _utc_now
from utils.json_utils import load_json, save_json, safe_extract_json
from utils.log import log_error, log_activity
from cog_memory.working_memory import update_working_memory
from cog_memory.long_memory import update_long_memory
from utils.self_model import get_self_model
from paths import PROPOSED_TOOLS_JSON, TOOL_EVALUATIONS_JSON, LONG_MEMORY_FILE, IMPLEMENTED_TOOLS_FILE
from utils.llm_gate import llm_callable_by
from utils.failure_counter import record_failure
_log = get_logger(__name__)



def evaluate_new_abstractions() -> str:
    if not llm_callable_by("evaluation"):
        log_activity("[evaluation] evaluate_new_abstractions skipped — LLM unavailable")
        return ""
    try:
        # === Load context safely ===
        tools = load_json(PROPOSED_TOOLS_JSON, default_type=list)
        if not isinstance(tools, list):
            update_working_memory("⚠️ proposed_tools.json was not a list; treating as empty.")
            tools = []

        if not tools:
            update_working_memory("⚠️ No proposed tools to evaluate.")
            return "❌ No tools found."

        self_model = get_self_model()
        if not isinstance(self_model, dict):
            log_error("❌ self_model is not a dict. Aborting tool evaluation.")
            return "❌ Invalid self model."

        long_memory = load_json(LONG_MEMORY_FILE, default_type=list)
        if not isinstance(long_memory, list):
            update_working_memory("⚠️ LONG_MEMORY_FILE not a list; using empty.")
            long_memory = []

        prior = load_json(TOOL_EVALUATIONS_JSON, default_type=list)
        if not isinstance(prior, list):
            prior = []

        evaluations: List[Dict[str, Any]] = []
        recent_long = long_memory[-10:]

        for tool in tools:
            # Skip junk entries gracefully
            if not isinstance(tool, dict):
                update_working_memory("⚠️ Skipped non-dict tool entry during evaluation.")
                continue

            prompt = (
                "I am Orrin, a reflective AI evaluating a new tool.\n\n"
                f"My core directive is:\n\"{self_model.get('core_directive', {}).get('statement', 'No directive found.')}\"\n\n"
                f"My motivations:\n{json.dumps(self_model.get('core_directive', {}).get('motivations', []), ensure_ascii=False, indent=2)}\n\n"
                f"Tool proposed:\n{json.dumps(tool, ensure_ascii=False, indent=2)}\n\n"
                f"My relevant long-term memory:\n{json.dumps(recent_long, ensure_ascii=False, indent=2)}\n\n"
                "Evaluate this tool:\n"
                "- Is it original?\n"
                "- Is it useful for fulfilling my directive?\n"
                "- Are there similar tools I already use?\n"
                "- Should I refine, implement, or reject it?\n\n"
                "Respond in JSON:\n"
                '{ "evaluation": "", "action": "implement | refine | reject", "justification": "" }'
            )

            resp = llm_ok(generate_response(prompt, config={"model": get_thinking_model()}), "evaluation")
            parsed = safe_extract_json(resp or "", dict_only=True)

            name = tool.get("name", "[unnamed]")
            if parsed is not None:
                action = parsed.get("action", "unknown")
                evaluations.append({
                    "tool": tool,
                    "evaluation": parsed,
                    "timestamp": _utc_now(),
                })
                update_working_memory(f"🧠 Evaluated tool: {name} — {action}")
            else:
                update_working_memory(f"❌ Failed to parse evaluation for tool: {name}")

        # Merge with prior evaluations rather than overwriting
        if evaluations:
            save_json(TOOL_EVALUATIONS_JSON, prior + evaluations)

        # Track implemented tools for outcome assessment
        _track_implemented_tools(evaluations)

        # Inject a build signal for every tool marked "implement" so the
        # code_writer / agency functions can pick it up in the next cycle.
        _inject_implement_signals(evaluations)

        return f"✅ Evaluated {len(evaluations)} tool(s)."

    except Exception as e:
        log_error(f"evaluate_new_abstractions ERROR: {e}")
        return "❌ Tool evaluation failed."


def _inject_implement_signals(evaluations: List[Dict[str, Any]]) -> None:
    """
    For each evaluation where action='implement', write to working_memory and
    inject a signal so the agency / code_writer functions see the request and
    can act on it autonomously in the next cycle.
    """
    for ev in evaluations:
        if not isinstance(ev, dict):
            continue
        action = (ev.get("evaluation") or {}).get("action", "")
        if action != "implement":
            continue
        tool = ev.get("tool") or {}
        name = tool.get("name", "[unnamed]")
        desc = tool.get("description", "")
        justification = (ev.get("evaluation") or {}).get("justification", "")

        msg = (
            f"[implement_tool] Build new cognitive tool '{name}': {desc[:200]}"
            + (f" — {justification[:150]}" if justification else "")
        )
        try:
            update_working_memory(msg)
        except Exception as _e:
            record_failure("evaluation._inject_implement_signals", _e)

        try:
            from utils.signal_utils import create_signal
            from utils.json_utils import load_json as _lj, save_json as _sj
            from paths import CONTEXT
            _ctx = _lj(CONTEXT, default_type=dict) or {}
            _sig = create_signal(
                source="innovation_evaluation",
                content=f"implement_tool: {name} — {desc[:150]}",
                signal_strength=0.75,
                tags=["implement", "innovation", "code_writer", "tool"],
            )
            _ctx.setdefault("raw_signals", []).append(_sig)
            _sj(CONTEXT, _ctx)
        except Exception as _e:
            log_activity(f"[innovation] signal inject failed: {_e}")

        log_activity(f"[innovation] Implement signal injected for tool '{name}'.")


def _track_implemented_tools(evaluations: List[Dict[str, Any]]) -> None:
    """
    For any evaluation where action='implement', write a tracking record into
    implemented_tools.json so assess_innovation_outcomes() can later check whether
    the implementation actually changed behavior (via bandit usage and reward).
    """
    implemented = load_json(IMPLEMENTED_TOOLS_FILE, default_type=list)
    if not isinstance(implemented, list):
        implemented = []

    existing_names = {r.get("name") for r in implemented if isinstance(r, dict)}

    new_entries = []
    for ev in evaluations:
        if not isinstance(ev, dict):
            continue
        action = (ev.get("evaluation") or {}).get("action", "")
        if action != "implement":
            continue
        tool = ev.get("tool") or {}
        name = tool.get("name", "[unnamed]")
        if name in existing_names:
            continue
        new_entries.append({
            "name": name,
            "description": tool.get("description", ""),
            "implemented_ts": _utc_now(),
            "justification": (ev.get("evaluation") or {}).get("justification", ""),
            "bandit_uses_at_implement": _get_bandit_count(name),
            "reward_history": [],
            "outcome": None,   # filled by assess_innovation_outcomes()
        })
        existing_names.add(name)

    if new_entries:
        save_json(IMPLEMENTED_TOOLS_FILE, implemented + new_entries)
        log_activity(f"[innovation] Tracking {len(new_entries)} newly implemented tool(s).")


def _get_bandit_count(name: str) -> int:
    """Return how many times the bandit has selected this function name, or 0."""
    try:
        from think.bandit.contextual_bandit import get_state
        st = get_state()
        return int((st.get("counts") or {}).get(name, 0))
    except Exception:
        return 0


def assess_innovation_outcomes(context: Dict[str, Any] = None) -> str:
    """
    Cognition function: review implemented tools and check whether they actually
    changed behavior. Cross-references bandit usage counts and recent rewards.

    For each unresolved implementation:
    - If bandit count grew significantly → tool is being used → 'adopted'
    - If bandit count barely moved after many cycles → 'no_impact'
    - Write a long_memory entry and mark the record so it isn't re-evaluated.
    """
    context = context or {}

    implemented = load_json(IMPLEMENTED_TOOLS_FILE, default_type=list)
    if not isinstance(implemented, list) or not implemented:
        return "No implemented tools to assess."

    # Only consider records without a final outcome and at least 5 cycles old
    unresolved = [
        r for r in implemented
        if isinstance(r, dict) and r.get("outcome") is None
    ]
    if not unresolved:
        return "All implemented tools already assessed."

    try:
        from think.bandit.contextual_bandit import get_state
        bandit_st = get_state()
    except Exception:
        return "assess_innovation_outcomes: could not read bandit state."

    counts = bandit_st.get("counts") or {}
    weights = bandit_st.get("weights") or {}
    updated = False

    assessments = []
    for record in unresolved:
        name = record.get("name", "")
        baseline = int(record.get("bandit_uses_at_implement", 0) or 0)
        current = int(counts.get(name, 0))
        uses_since = current - baseline

        w = weights.get(name) or {}
        avg_weight = (sum(float(v) for v in w.values()) / len(w)) if w else 0.0

        if uses_since >= 3 and avg_weight > 0.3:
            outcome = "adopted"
            summary = f"Tool '{name}' adopted: used {uses_since}x since implementation, avg bandit weight {avg_weight:.2f}."
        elif uses_since >= 1 and avg_weight > 0.0:
            outcome = "partial"
            summary = f"Tool '{name}' partially used: {uses_since}x since implementation. Monitoring."
        else:
            outcome = "no_impact"
            summary = f"Tool '{name}' shows no behavioral impact: {uses_since}x uses, avg weight {avg_weight:.2f}."

        # Only finalize if enough cycles have passed (uses_since or baseline > 10 total)
        if current >= 5 or baseline >= 5:
            record["outcome"] = outcome
            record["outcome_ts"] = _utc_now()
            record["uses_since_implement"] = uses_since
            updated = True
            assessments.append(summary)
            update_long_memory(
                f"[innovation_outcome] {summary}",
                emotion="exploration_drive" if outcome == "adopted" else "stagnation_signal",
                event_type="innovation_assessment",
                importance=4 if outcome == "adopted" else 2,
                context=context,
            )
            log_activity(f"[innovation] {summary}")
        else:
            # Too early — check again next call
            assessments.append(f"Tool '{name}': {uses_since} uses so far — too early to assess.")

    if updated:
        save_json(IMPLEMENTED_TOOLS_FILE, implemented)

    if assessments:
        update_working_memory("🔬 Innovation outcomes: " + "; ".join(assessments[:3]))

    return f"Assessed {len(unresolved)} innovation(s): " + "; ".join(assessments[:2])