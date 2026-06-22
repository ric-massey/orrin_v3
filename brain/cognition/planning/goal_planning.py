"""Goal plan generation (Phase 4D, from pursue_goal.py).

The planning slice of goal pursuit: classify a goal's intent into a tool family
(_intent_candidates / _goal_topic / _search_needle), ground it against the
executable action vocabulary, propose a symbolic plan (_symbolic_plan), look up
a learned causal first step (_causal_first_step), and assemble the concrete plan
(_generate_plan). LLM/causal/capability lookups are imported at call time, so
this has no import cycle back to pursue_goal, which re-imports _symbolic_plan
(also imported externally) and _generate_plan.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from brain.core.runtime_log import get_logger
from brain.utils.log import log_activity
from brain.utils.failure_counter import record_failure
from brain.utils.generate_response import generate_response, llm_ok
from brain.utils.llm_gate import llm_callable_by

_log = get_logger(__name__)




# ── Plan generation ──────────────────────────────────────────────────────────

# Executable action vocabulary the planner grounds goals against — the SAME
# capability descriptions step_execution routes steps on (recognise_step_action),
# so any tool selected here is guaranteed recognisable and runnable. New tools
# added to the manifest become plannable automatically: this is general
# capability grounding, not a fixed goal→category table.
_PLANNABLE_ACTIONS = (
    "research_topic", "wikipedia_search", "fetch_and_read", "read_rss",
    "search_own_files", "grep_files", "list_directory",
    "look_outward", "look_around", "survey_environment", "read_clipboard",
    "seek_novelty", "leave_note", "write_desktop_note",
)
_FILE_TOOLS     = frozenset({"search_own_files", "grep_files", "list_directory"})
_RESEARCH_TOOLS = frozenset({"research_topic", "wikipedia_search"})
# Tools that need an input from a prior step (fetch_and_read wants a URL), so they
# are only ever a deepening step, never a cold lead.
_DEEPEN_ONLY    = frozenset({"fetch_and_read"})
# Below this capability↔goal match, no tool genuinely serves the goal → honest
# block (slightly under step_execution's _SEMANTIC_FLOOR so the planner is a
# touch more willing to propose than the executor is to auto-route).
_PLAN_FLOOR = 0.18

# Intent → candidate executable tools. The goal's intent VERB selects a tool
# family (reliable for the common goal shapes — "understand X" is a research
# intent even though it shares no words with research_topic's description); then
# capability_overlap picks the best-matching specific tool WITHIN the family, and
# goals with no recognised intent fall back to grounding over the whole vocabulary.
# This is intent classification + capability grounding — not canned per-goal plans.
# Order matters: explicit intents (self / outward / explore) are checked before
# the broad research family, so "look outward at what is happening" doesn't get
# swallowed by research's "what is" trigger.
_INTENT_FAMILIES = (
    (("my own", "myself", "my code", "my system", "my architecture", "how i work",
      "about myself", "my cognition", "my mind", "my memory", "audit my", "trace my",
      "my source", "my data"),
     ("search_own_files", "grep_files")),
    (("observe", "outward", "outside", "external world", "what's happening",
      "what is happening", "going on", "current events", "news", "rss"),
     ("look_outward", "read_rss", "look_around")),
    (("explore", "discover", "curious", "novel", "seek", "something new", "unfamiliar"),
     ("seek_novelty", "research_topic")),
    (("understand", "research", "learn", "study", "investigate", "read about",
      "find out", "look up", "dig into", "what is", "who is", "history of",
      "knowledge", "about the", "facts about"),
     ("research_topic", "wikipedia_search", "fetch_and_read")),
    (("note", "write to ric", "record", "message", "tell ric", "contact",
      "connect", "reach out", "leave a note"),
     ("leave_note", "write_desktop_note")),
)


def _intent_candidates(goal_title: str) -> tuple:
    """The candidate tool family for the goal's intent, or the full vocabulary
    when no intent verb is recognised. A bare 'find/locate' only routes to the
    file family when there's a file/string cue, so 'find out about X' stays
    research, not a file grep."""
    gl = (goal_title or "").lower()
    file_cue = any(w in gl for w in ("file", "files", "word ", "string", "code",
                                     "brain", "repo", "grep", "function", "class", "module"))
    if (("grep" in gl) or
            (any(w in gl for w in ("find", "locate", "search for", "look for")) and file_cue)):
        return ("search_own_files", "grep_files")
    for triggers, tools in _INTENT_FAMILIES:
        if any(t in gl for t in triggers):
            return tools
    return _PLANNABLE_ACTIONS


def _goal_topic(goal_title: str) -> str:
    """Strip goal scaffolding to the bare subject — 'Understand X more deeply' → 'X'
    — so the plan acts on the SUBJECT, not the literal goal sentence."""
    t = re.sub(r"^\s*(understand|learn about|find out|research|study|explore|look up|dig into|read about)\b\s*:?\s*",
               "", (goal_title or "").strip(), flags=re.I)
    t = re.sub(r"\s+more deeply\b\.?\s*$", "", t, flags=re.I).strip()
    return t or (goal_title or "").strip()


def _search_needle(goal_title: str, default: str) -> str:
    """For file/string-search goals the precise target is usually quoted
    ('Find the word ‹reaper›') — search for THAT, not the whole goal sentence."""
    m = re.search(r"['\"]([^'\"]{2,60})['\"]", goal_title or "")
    return m.group(1) if m else default


def _symbolic_plan(goal_title: str, context: Dict[str, Any]) -> List[str]:
    """Capability-grounded action planner (LLM-free).

    Scores the goal against the curated capability vocabulary — the same
    descriptions step_execution routes on — and builds an executable, topic-bound
    plan from the best-matching tool(s). General by construction: any goal a
    capability serves gets a plan, and a goal no capability serves returns []
    (the caller then blocks needs_capability — an honest gap, never a canned
    category template). Every emitted step names a real tool, so
    recognise_step_action can always map it to a runnable action.
    """
    topic = _goal_topic(goal_title)
    gl = (goal_title or "").lower()

    # Production intent (write/build a function/tool/code) → generative gateway,
    # mirroring step_execution's production gate so recognition and satisfaction agree.
    if (any(w in gl for w in ("write", "create", "build", "implement", "produce"))
            and any(w in gl for w in ("function", "tool", "capability", "module", "code"))):
        return [
            f"Use write_cognitive_function to build code for: {topic}",
            "Write what the new capability does to working memory",
        ]

    # Intent family narrows the candidates; capability_overlap picks the best
    # specific tool within it and grounds the choice in the goal's own words.
    candidates = _intent_candidates(goal_title)
    try:
        from brain.think.think_utils.select_function import _capability_descriptions, _capability_overlap
        descs = _capability_descriptions()
    except Exception:
        descs = {}
    primary_pool = [fn for fn in candidates if fn not in _DEEPEN_ONLY] or list(candidates)
    scores = {fn: _capability_overlap(descs.get(fn) or fn.replace("_", " "), goal_title or "")
              for fn in primary_pool}
    if not scores:
        return []
    best_score = max(scores.values())

    in_family = candidates is not _PLANNABLE_ACTIONS
    if in_family:
        # The curated family ORDER is itself a strong prior (it lists the canonical
        # lead tool first — research_topic before wikipedia_search), so prefer the
        # highest-priority tool whose score is within a margin of the best; overlap
        # only breaks genuine near-ties. The family is the grounding, so a weak
        # lexical score is fine here.
        primary = next((fn for fn in primary_pool if scores[fn] >= best_score - 0.10),
                       primary_pool[0])
    else:
        # Open-vocabulary fallback (no intent matched): pure capability grounding,
        # floor-gated so a random low-overlap pick becomes an honest block instead.
        if best_score < _PLAN_FLOOR:
            return []
        primary = max(primary_pool, key=lambda fn: scores[fn])
    is_file = primary in _FILE_TOOLS
    bind = _search_needle(goal_title, topic) if is_file else topic
    label = f"where '{bind}' appears" if is_file else f"about {topic}"

    steps = [f"Call {primary} to make progress on: {bind}"]
    # Natural deepening so the plan produces real findings, not a single touch.
    if primary in _RESEARCH_TOOLS:
        steps.append(f"Call fetch_and_read to read a full source about {topic}")
    elif primary in _FILE_TOOLS:
        other = "grep_files" if primary != "grep_files" else "search_own_files"
        steps.append(f"Call {other} to pin down the exact occurrences of '{bind}'")
    steps.append(f"Write one concrete thing learned {label} to working memory")
    return steps


_CAUSAL_LEAD_MIN_SCORE = 0.50   # only act on reasonably strong learned causes


def _causal_first_step(goal_title: str) -> Optional[str]:
    """
    Means-ends read of the causal graph: if Orrin has learned a strong cause of
    this goal's outcome, return a leading step that enacts it. Returns None when
    nothing confident is known (the common early case). Newell & Simon (1972).
    """
    title = (goal_title or "").strip()
    if len(title) < 5:
        return None
    try:
        from brain.symbolic.causal_graph import get_causes
        causes = get_causes(title, min_score=_CAUSAL_LEAD_MIN_SCORE) or []
        if not causes:
            return None
        top = max(causes, key=lambda e: float(e.get("causal_score", 0.0)))
        cause = str(top.get("cause", "")).strip()
        if len(cause) < 4:
            return None
        return f"Act on what I've learned brings this about: {cause[:120]}"
    except Exception:
        return None


def _generate_plan(goal: Dict[str, Any], context: Dict[str, Any]) -> list:
    """
    Ask the LLM for an ordered list of 3-5 concrete steps to accomplish this goal.
    Falls back to symbolic plan generation when LLM is unavailable.
    Returns a list of step strings, or [] on failure.
    """
    goal_title = goal.get("title", goal.get("name", ""))
    goal_desc  = (goal.get("spec") or {}).get("description", goal.get("description", ""))
    driven_by  = (goal.get("spec") or {}).get("driven_by", goal.get("driven_by", ""))

    # Workaround routing (problem_refocus): when a capability Orrin relies on is
    # down — flagged on the goal (_avoid_capability) or globally in context
    # (_unhealthy_capabilities) — plan around it. Avoiding the LLM means falling
    # straight to the symbolic plan (research_topic → DuckDuckGo/Wikipedia, etc.).
    _avoid = set(context.get("_unhealthy_capabilities") or [])
    if goal.get("_avoid_capability"):
        _avoid.add(goal.get("_avoid_capability"))
    if "llm" in _avoid:
        sym = _symbolic_plan(goal_title, context)
        log_activity(
            f"[pursue_goal] LLM unavailable — working around it with a symbolic "
            f"plan for '{goal_title[:60]}' ({len(sym)} steps)"
        )
        return sym

    # Means-ends read of learned structure (Newell & Simon 1972 means-ends
    # analysis; Pearl): if the causal graph has learned a strong cause of this
    # goal's outcome, lead the plan with it — do the thing that brings the goal
    # about. Usually a no-op early on; grows more useful as beliefs accumulate
    # (fed by confirmed experiments and successful repairs).
    _causal = _causal_first_step(goal_title)

    def _lead(steps: list) -> list:
        return ([_causal] + steps) if (_causal and steps) else steps

    wm_tail = (context.get("working_memory") or [])[-4:]
    wm_lines = [
        str(e.get("content", "") if isinstance(e, dict) else e)[:100]
        for e in wm_tail
    ]
    context_block = "\n".join(f"- {l}" for l in wm_lines if l.strip())

    # Symbolic-first planning. Use the symbolic planner when the LLM is down OR
    # when the caller demands symbolic-only (the background Executive daemon sets
    # context["_symbolic_only"] so it never calls the LLM — no contention with
    # think(), and faithful to §0.1 "Symbolic only. No 'ask an LLM to plan.'").
    if not llm_callable_by("pursue_goal/plan") or context.get("_symbolic_only"):
        sym = _symbolic_plan(goal_title, context)
        log_activity(f"[pursue_goal] Symbolic plan for '{goal_title[:60]}' ({len(sym)} steps)")
        return _lead(sym)

    prompt = (
        f"You are Orrin, an evolving autonomous AI.\n\n"
        f"Goal: {goal_title}\n"
        f"Description: {goal_desc or '(none)'}\n"
        f"Driven by: {driven_by or 'exploration_drive'}\n\n"
        f"Recent context:\n{context_block or '(none)'}\n\n"
        "Break this goal into 3-5 concrete, sequential steps. Each step should be "
        "completable in a single cognitive cycle. Output a JSON array of strings:\n"
        '[\"step 1\", \"step 2\", \"step 3\"]'
    )
    result = generate_response(prompt, config={"expect_json": True}, caller="pursue_goal/plan")
    raw = llm_ok(result, "pursue_goal/plan")
    if raw:
        try:
            import json
            steps = json.loads(raw)
            if isinstance(steps, list):
                parsed = [str(s).strip() for s in steps if isinstance(s, str) and s.strip()]
                if parsed:
                    return _lead(parsed)
        except Exception as _e:
            record_failure("pursue_goal._generate_plan", _e)

    # LLM unavailable or returned nothing — use symbolic plan
    sym = _symbolic_plan(goal_title, context)
    log_activity(f"[pursue_goal] Using symbolic plan for '{goal_title[:60]}' ({len(sym)} steps)")
    if not sym:
        # Honest blockage beats fake plans (BEHAVIOR_FIX_PLAN 2.2): no concrete
        # step can be produced symbolically — name the missing capability.
        goal["blocked"] = "needs_capability"
        goal["missing_capability"] = "plan_generation"
        log_activity(f"[pursue_goal] '{goal_title[:60]}' blocked: needs_capability (plan_generation)")
    return _lead(sym)
