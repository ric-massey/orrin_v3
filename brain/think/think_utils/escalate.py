from typing import Iterable, Optional, List, Dict, Any
from paths import BEHAVIORAL_FUNCTIONS_LIST_FILE
from utils.json_utils import load_json

_DEFAULT_ALLOWED = (
    "ask", "diagnose", "propose", "revise", "skip", "retry", "execute", "run", "tool"
)

def _iter_behaviors(raw: Iterable[Any]) -> Iterable[Dict[str, Any]]:
    """
    Normalize behaviors to dicts with at least: name, is_action, summary.
    Accepts elements that are either strings or dicts.
    """
    for b in raw:
        if isinstance(b, str):
            yield {"name": b, "is_action": True, "summary": ""}
        elif isinstance(b, dict):
            yield {
                "name": b.get("name") or b.get("type") or "",
                "is_action": bool(b.get("is_action", True)),
                "summary": b.get("summary", "")}
        # else: silently ignore invalid entries

def get_escalation_options_from_behavior_list(
    behavioral_functions_list: Iterable[Any],
    allowed_keywords: Optional[List[str]] = None
) -> List[Dict[str, str]]:
    """
    Return escalation candidates from the behavior registry.
    Filters to names containing any of `allowed_keywords` (case-insensitive).
    Accepts a list of strings or dicts.
    """
    keywords = tuple(allowed_keywords or _DEFAULT_ALLOWED)
    keywords_cf = tuple(k.casefold() for k in keywords)

    options: List[Dict[str, str]] = []
    for b in _iter_behaviors(behavioral_functions_list):
        name = (b.get("name") or "").strip()
        if not name or not b.get("is_action", True):
            continue
        n_cf = name.casefold()
        if any(kw in n_cf for kw in keywords_cf):
            options.append({
                "type": name,
                "description": b.get("summary", "") or "Escalation/utility action."
            })
    return options

def escalate_with_behavior_list(
    context: dict,
    action: dict,
    last_error: str,
    retries: int,
    *,
    behavioral_functions_list: Optional[Iterable[Any]] = None,
    allowed_keywords: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Load or use a provided behavior list, build escalation options,
    ask the LLM to choose, and enqueue the chosen action.
    """
    # 1) ensure queue exists
    context.setdefault("pending_actions", [])

    # 2) load list if not provided
    if behavioral_functions_list is None:
        behavioral_functions_list = load_json(BEHAVIORAL_FUNCTIONS_LIST_FILE, default_type=list)

    # 3) build candidate options
    options = get_escalation_options_from_behavior_list(behavioral_functions_list, allowed_keywords)

    if not options:
        # No options at all — bail early with a single ask_user rather than calling the LLM
        # with only one choice and then inserting it (which could produce a duplicate if ask_user
        # was already added by another path this cycle).
        if not any(a.get("type") == "ask_user" for a in context.get("pending_actions", [])[:1]):
            from think.think_utils.action_gate import propose_action
            propose_action(context, {
                "type": "ask_user",
                "content": "I'm stuck after multiple retries. Please advise.",
                "urgency": 1.0,
                "description": "No escalation options available."
            })
        return {"action": action, "decision": "escalate", "acted": False}

    # Always include ask_user as a selectable option so the LLM has a safe fallback.
    if not any(opt["type"] == "ask_user" for opt in options):
        options.append({"type": "ask_user", "description": "Ask the user for clarification or help."})

    # 4) LLM selection
    escalation_prompt = (
        f"I am stuck after {retries} attempts.\n"
        f"Action: {action}\n"
        f"Error: {last_error}\n"
        "Which of these escalation options should I try next and why?\n"
        + "\n".join(f"- {o['type']}: {o['description']}" for o in options)
        + "\n\nReply with the action type and a short reason."
    )
    from utils.generate_response import generate_response, llm_ok  # local import to avoid cycles
    choice = (llm_ok(generate_response(escalation_prompt, caller="escalate"), "escalate") or "").strip()

    # 5) Parse choice robustly (case-insensitive containment)
    choice_cf = choice.casefold()
    picked = None
    for o in options:
        if o["type"].casefold() in choice_cf:
            picked = o
            break
    if picked is None:
        picked = next((o for o in options if o["type"] == "ask_user"), options[0])
        reason = "Defaulted to asking the user for help."
    else:
        reason = (
            f"Escalated after multiple failed attempts. "
            f"{picked.get('description','').strip()}"
        ).strip()

    # 6) Enqueue chosen action (high urgency — resolved at the front next cycle)
    from think.think_utils.action_gate import propose_action
    propose_action(context, {
        "type": picked["type"],
        "content": reason,
        "urgency": 1.0,
        "description": f"Escalated after retries: {picked['type']}"
    })
    return {"action": action, "decision": "escalate", "acted": False}

def is_agentic_action(
    function_name: str,
    behavior_list_path: str = BEHAVIORAL_FUNCTIONS_LIST_FILE
) -> bool:
    """
    True if the function appears as an action in the registry.
    Supports registries that are lists of strings or dicts.
    """
    raw = load_json(behavior_list_path, default_type=list)
    if not raw:
        return False

    fname_cf = function_name.casefold()
    for b in _iter_behaviors(raw):
        name = (b.get("name") or "").casefold()
        if name == fname_cf:
            return bool(b.get("is_action", True))
    return False