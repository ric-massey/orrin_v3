# brain/cognition/planning/goal_types.py
"""
Goal-type taxonomy — the means-ends backbone for goal→action routing.

A goal describes a desired END-STATE; the TYPE names what kind of end-state it is,
and that determines which family of "doing" actions can actually produce it (Newell
& Simon means-ends analysis). Without this, function selection is a popularity
contest (emotion priors + novelty + bandit + weak keyword overlap) and a code-writing
action can "complete" a research goal — the differentiation the user asked for is
absent.

Kept dependency-free (stdlib only) so both select_function (gating) and the planner
can import it with no cycle. The keyword branches mirror pursue_goal._symbolic_plan
so classification and planning agree on what each goal type means.
"""
from __future__ import annotations
from typing import Any, Dict, Optional, FrozenSet

# Ordered most-specific → least-specific; first match wins.
_TYPE_RULES = (
    # (type, trigger substrings). A code-PRODUCTION goal needs a production verb AND
    # an artifact noun, so plain "write a note" doesn't read as code.
    ("produce_code", None),        # handled specially below (verb + artifact)
    ("self_understand", ("my own", "myself", "my code", "my system", "my architecture",
                         "how i work", "about myself", "my self", "my cognition", "my mind")),
    ("social", ("connect ", "relationship", "social", " person", "with ric", "with the user",
                "reach out", "talk to")),
    ("acquire_knowledge", ("understand", "research", "read about", "study", "investigate",
                           "find out", "look up", "dig into", "learn about", "learn ",
                           "knowledge", "what is", "who is", "history of", "about the")),
    ("explore", ("explore", "discover", "curious", "novel", "seek", "wander")),
    ("advance_idea", ("advance", "open thread", "idea", "thread", "dormant", "revisit")),
)

_PRODUCE_VERBS = ("write", "written", "create", "implement", "build", "code ",
                  "develop", "produce", "synthesi")
_PRODUCE_ARTIFACTS = ("function", "tool", "capability", "module", "code", "script")

# Exclusive "doing" actions per type: actions that ONLY make sense for that type of
# goal. select_function penalises an exclusive action when the committed goal is a
# DIFFERENT type, so code-writing can't win on a research goal and vice versa. Shared
# / reflective functions are intentionally NOT listed (they stay neutral).
EXCLUSIVE_DOING: Dict[str, FrozenSet[str]] = {
    "produce_code": frozenset({
        "decide_to_write_code", "write_cognitive_function", "write_tool",
        "synthesize_from_gap",
    }),
    "acquire_knowledge": frozenset({
        "research_topic", "wikipedia_search", "fetch_and_read", "read_rss",
        "read_a_book", "ask_llm_for_research",
    }),
}

# Capability each type needs to make REAL progress (for the feasibility check in
# Stage 2 / pursue). "llm" = the generative LLM tool (ask_llm); "web" = web/wiki.
REQUIRED_CAPABILITY: Dict[str, Optional[str]] = {
    "produce_code": "llm",
    "acquire_knowledge": "web",
}


def classify_goal_type(goal: Any) -> str:
    """Infer a goal's end-state type from its title/description. Returns one of the
    _TYPE_RULES types or 'general' when nothing matches."""
    if isinstance(goal, dict):
        text = f"{goal.get('title') or ''} {goal.get('name') or ''} " \
               f"{((goal.get('spec') or {}).get('description') if isinstance(goal.get('spec'), dict) else '') or goal.get('description') or ''}"
    else:
        text = str(goal or "")
    t = text.lower()
    if not t.strip():
        return "general"

    # Code production: a production verb AND an artifact noun.
    if any(v in t for v in _PRODUCE_VERBS) and any(a in t for a in _PRODUCE_ARTIFACTS):
        return "produce_code"

    for gtype, triggers in _TYPE_RULES:
        if triggers is None:
            continue
        if any(tr in t for tr in triggers):
            return gtype
    return "general"


def goal_type_of(goal: Any) -> str:
    """Prefer a stored goal['type'] (set at commit), else classify on the fly."""
    if isinstance(goal, dict):
        stored = goal.get("type")
        if isinstance(stored, str) and stored:
            return stored
    return classify_goal_type(goal)


def is_mismatched_doing_action(goal_type: str, fn_name: str) -> bool:
    """True if fn_name is an EXCLUSIVE doing-action of some type OTHER than
    goal_type — i.e. selecting it would be working on the wrong kind of goal.

    Only enforced when the CURRENT goal type has its own exclusive family (it's a
    strongly-typed goal — produce_code / acquire_knowledge). A 'general'/'explore'/
    'self_understand' goal isn't pinned to one family, so nothing is suppressed for
    it; the gate exists to keep the research↔code distinction crisp, not to straitjacket
    vague goals."""
    if not fn_name or goal_type not in EXCLUSIVE_DOING:
        return False
    for gtype, fns in EXCLUSIVE_DOING.items():
        if gtype != goal_type and fn_name in fns:
            return True
    return False


def required_capability(goal: Any) -> Optional[str]:
    """The capability a goal's type needs to make real progress, or None."""
    return REQUIRED_CAPABILITY.get(goal_type_of(goal))


def capability_available(cap: Optional[str], context: Any = None) -> bool:
    """Is `cap` available right now? Used to decide degrade-vs-pursue. A goal whose
    required capability is down can't be done as-is — better to reduce it to an
    achievable sub-goal or disengage than to nag/fake."""
    if not cap:
        return True
    ctx = context if isinstance(context, dict) else {}
    unhealthy = set(ctx.get("_unhealthy_capabilities") or [])
    if cap in unhealthy:
        return False
    if cap == "llm":
        # Code production reaches the LLM via the allow-listed ask_llm tool
        # (decide_to_write_code → ask_llm), so tool-only mode does NOT block it —
        # availability is simply whether the LLM is reachable right now. When it's
        # down (e.g. testing), produce_code goals degrade/disengage honestly.
        try:
            from brain.utils.llm_gate import llm_available
            return bool(llm_available())
        except ImportError:  # intentional: llm_gate optional → degrade/disengage honestly
            return False
    if cap == "web":
        # web/wiki tools are non-LLM and stay available unless flagged unhealthy.
        return not (unhealthy & {"web", "research_topic", "wikipedia_search", "internet"})
    return True


def reduced_goal_spec(goal: Any) -> Optional[Dict[str, Any]]:
    """A simpler, currently-achievable goal that still serves the same aspiration —
    means-ends reduction for when the full goal's capability is unavailable. Returns
    a {title, type, milestones} spec, or None when there's no sensible reduction
    (then the caller disengages)."""
    gtype = goal_type_of(goal)
    orig = ((goal.get("title") if isinstance(goal, dict) else str(goal)) or "the goal").strip()
    # NOTE-verifiable milestones on purpose: the reduced goal must be one the system
    # can actually close (the note gate ticks on a real note_written artifact), or it
    # would just stall again. "Write a note about X" is achievable with no LLM/web.
    if gtype == "produce_code":
        # Can't build it now → do the achievable groundwork: decide WHAT to build and
        # capture it as a note, ready to implement when the tool returns.
        return {
            "title": f"Note a specific improvement idea to build later (toward: {orig[:44]})",
            "type": "self_understand",
            "milestones": [
                {"text": "A note describing a specific improvement idea was written.", "met": False, "met_at": None},
            ],
        }
    if gtype == "acquire_knowledge":
        return {
            "title": f"Note what I already know about: {orig[:48]}",
            "type": "self_understand",
            "milestones": [
                {"text": "A note about my existing knowledge was written.", "met": False, "met_at": None},
            ],
        }
    return None
