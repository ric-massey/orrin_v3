# brain/cognition/planning/step_execution.py
#
# Ideomotor execution of plan steps.
#
# A plan step is an *intention* ("Call research_topic to search for X",
# "Write the findings to memory"). Pursuing a goal is not narrating the
# intention — it is discharging it into a real act and checking the world
# afterward. This module does the discharge:
#
#   recognise the intention  →  fire the matching act  →  judge by its result
#
# Scientific basis
# ──────────────────────────────────────────────────────────────────────────
#   Ideomotor theory (James, 1890; Hommel et al. 2001 TEC): an intention is
#     represented by its sensory effects, and activating that representation
#     triggers the movement that produces them. Intention → action is direct.
#   Perceptual Control Theory (Powers, 1973): an act "counts" only when it
#     changes the controlled perception. Completion is gated on feedback
#     (did memory/the world actually change?), not on having had the thought.
#   Habit vs. deliberation (basal-ganglia "go" vs. prefrontal planning):
#     familiar intentions map to an over-learned action fast (the keyword
#     table here); genuinely internal/novel steps have no motor program and
#     remain deliberative (handled by the caller, without agency credit).
#
# The action repertoire is the cognition registry itself — the same set of
# functions Orrin can otherwise choose directly — so a step dispatches the
# real tool (research_topic, fetch_and_read, …), not a stand-in.
from __future__ import annotations
from brain.cognition.global_workspace import bound_goal

from typing import Any, Dict, Iterable, Optional, Tuple

from brain.config.tuning import SEMANTIC_MATCH_FLOOR
from brain.utils.log import log_activity, log_error


# Literal registered function names: if a step explicitly names a tool, that is
# the strongest possible intention signal (the LLM/symbolic planner wrote it).
_KNOWN_FN_NAMES = (
    "research_topic", "fetch_and_read", "wikipedia_search",
    "search_own_files", "grep_files", "leave_note", "look_outward",
    "look_around", "seek_novelty", "compose_section", "produce_and_check",
)

# Habitual intention→act mappings, checked in order (specific before generic).
# Each entry: (trigger substrings, registered cognition-function name).
_INTENT_RULES: Tuple[Tuple[Tuple[str, ...], str], ...] = (
    (("fetch", "read a full", "read the article", "read full", "open the link",
      "read article", "rss link"), "fetch_and_read"),
    (("wikipedia", "wiki ", "encyclopedia"), "wikipedia_search"),
    # P3 produce-and-check: a step that says to WORK/VERIFY/COMPUTE an answer maps to
    # the sandbox checker, not to reading. Placed before "research" so "check the
    # derivation" / "verify the result" route to attempting-and-checking, not looking
    # it up again. (Kept clear of the production-word gate above: these run a check,
    # they don't write a registered function/tool.)
    (("check the answer", "check the result", "check my work", "check the derivation",
      "verify", "compute", "calculate", "work the problem", "solve the", "solve for",
      "test the answer", "sanity check", "run the numbers", "prove that",
      "produce and check", "check it against"), "produce_and_check"),
    (("research", "duckduckgo", "search the web", "web search", "investigate",
      "find out", "look up", "look it up", "dig into", "read about",
      "study", "learn about"), "research_topic"),
    (("search own", "search my", "my own files", "my code", "scan my",
      "grep", "own files", "my files", "scan the codebase",
      # B3-shaped steps: "find the word 'supervisor' in any brain file" must map to
      # a real file-search ACTION (BEHAVIOR_FIX_PLAN 2.2 — plans cause actions).
      "find the word", "find the phrase", "search for the word",
      "brain file", "in any file"), "search_own_files"),
    (("compose a section", "draft a section", "draft the section",
      "manuscript section", "draft a chapter", "write a chapter",
      "written synthesis", "write a synthesis", "draft a synthesis"),
     "compose_section"),
    (("write", "record", "note", "document", "jot", "log ", "save",
      "leave a note", "summari"), "leave_note"),
    (("look outward", "observe the", "external world", "look out", "outward"),
     "look_outward"),
    (("look around", "survey", "scan the environment", "sense the"),
     "look_around"),
    (("seek novelty", "something new", "novel", "unexplored",
      "explore something"), "seek_novelty"),
)

# Substrings that mark a tool's own "nothing happened" return — the world did
# not change, so the act must NOT be credited or marked complete.
_FAILURE_MARKERS = (
    "found nothing", "no url", "could not", "couldn't", "had no readable",
    "will try again", "nothing for", "throttled", "no readable content",
    "unable", "failed", "no topic", "nothing to",
)

_MIN_RESULT_LEN = 20

# Code-production intent markers — kept in sync with env_snapshot._milestone_met's
# production gate so a step recognised as "production" is satisfied by the same
# real-artifact evidence ("wrote and registered ...") that ticks the milestone.
_PRODUCTION_WORDS = ("written", "wrote", "write", "registered", "register",
                     "created", "create", "built", "build", "produced",
                     "produce", "implemented", "implement")
_ARTIFACT_WORDS = ("function", "tool", "capability", "module", "code")

# Procedural / "doing" functions the background Executive lane is allowed to run
# (dual_process_loop.md Phase 5 — the System-1/procedural vs deliberate split).
# These are reversible gathering / observation / note steps. Everything OUTSIDE
# this set — code self-modification (write_cognitive_function / write_tool /
# delete_own_code), live speech (speak / user_response), active user-alerting
# (notify_user / announce_to_dashboard), goal create/abandon — stays on the
# CONSCIOUS (deliberate) thread (I10). The daemon sets context["_procedural_only"]
# and execute_step_action refuses anything not listed here. Defense-in-depth:
# recognise_step_action can't currently map a step to a dangerous fn, but this
# guarantees the daemon stays procedural even if that mapping ever grows.
_PROCEDURAL_DEFAULT = frozenset({
    "research_topic", "fetch_and_read", "wikipedia_search", "read_rss",
    "search_own_files", "grep_files", "list_directory", "search_files",
    "look_outward", "look_around", "survey_environment", "read_clipboard",
    "seek_novelty", "leave_note", "write_desktop_note", "save_note",
    # P3 produce-and-check: reversible (isolated sandbox, ledger row only on pass),
    # so the background Executive lane may run it — a plan step "check the answer"
    # advances without waiting on the conscious thread.
    "produce_and_check",
})


def _procedural_from_manifest() -> frozenset[str]:
    """Phase 4 (function_selection_fix_v2 §5): the "procedural" tag in the
    capability manifest is the source of truth for which functions the
    Executive lane may run. Read directly (tiny JSON, import-time only) rather
    than importing select_function's loader — that module is heavy and imports
    back into planning. Falls back to the literal default on any problem so a
    bad data file can never widen OR empty the procedural surface to nothing."""
    try:
        import json
        from pathlib import Path
        path = Path(__file__).resolve().parents[2] / "data" / "capability_descriptions.json"
        data = json.loads(path.read_text("utf-8"))
        tagged = frozenset(
            fn for fn, v in data.items()
            if isinstance(v, dict) and "procedural" in (v.get("tags") or [])
        )
        return tagged or _PROCEDURAL_DEFAULT
    except (OSError, ValueError, AttributeError):  # intentional: missing/malformed manifest → safe literal default
        return _PROCEDURAL_DEFAULT


_PROCEDURAL_FNS = _procedural_from_manifest()


def is_procedural(fn_name: str) -> bool:
    """True if `fn_name` is safe for the background Executive lane to execute."""
    return fn_name in _PROCEDURAL_FNS


# Minimum overlap for a semantic step→function match (function_selection_fix_v2.md
# §4.1). Set to 2.0 to disable the semantic fallback entirely → reverts to the
# literal+keyword 8-rule table (documented Phase 3 rollback). Calibrated for
# _capability_overlap over content words: two shared topical terms score ≈0.25+,
# single-token noise ≈0.16, so 0.22 admits genuine matches while rejecting
# incidental overlap. Also a sane floor for the embedding-similarity score
# _capability_overlap now blends in (Finding 8) — unrelated short phrases score
# well under 0.22 in MiniLM cosine similarity. The match space is bounded to the
# reversible _PROCEDURAL_FNS, so a borderline false-positive only ever runs a
# safe read/observation — never an irreversible act. Value lives in
# config.tuning (Finding 9).
_SEMANTIC_FLOOR = SEMANTIC_MATCH_FLOOR


def _semantic_step_match(step_text: str, candidates: Iterable[str]) -> Tuple[Optional[str], float]:
    """Best (fn_name, similarity) matching `step_text` over `candidates`, or
    (None, 0.0).

    Matches against the CURATED capability descriptions (function_selection_fix_v2
    §4.3), NOT raw docstrings — the docstring↔goal-prose mismatch (E5) is exactly
    why the literal 8-rule table never generalised. Uses keyword-overlap cosine so
    this ships without a model dependency; an embedding backend can replace the
    similarity call later without changing the interface.
    """
    try:
        from brain.think.think_utils.select_function import (
            _capability_descriptions, _capability_overlap,
        )
    except ImportError:  # intentional: optional select_function backend absent → no semantic match
        return (None, 0.0)
    descs = _capability_descriptions()
    best: Optional[str] = None
    best_score = 0.0
    for fn in candidates:
        ref = descs.get(fn) or fn.replace("_", " ")
        sim = _capability_overlap(ref, step_text)
        if sim > best_score:
            best, best_score = fn, sim
    return (best, best_score)


def recognise_step_action(step_text: Any) -> Optional[str]:
    """
    Map a plan-step intention to a registered cognition-function name, or None
    when the step is purely internal/deliberative (no motor program — e.g.
    "reflect on what was found"). The caller treats None as a thought, not an act.

    Three tiers (function_selection_fix_v2.md §4.1):
      1) literal tool name in the step  (strongest signal)
      2) habitual keyword rules         (fast path)
      3) semantic fallback over PROCEDURAL fns only — broadens the reachable set
         past the 8-rule ceiling while staying reversible (the daemon is
         procedural-only anyway, so no irreversible act can be recruited here and
         the deliberate/executive mutual-exclusion is preserved — no double-exec).
    Below the confidence floor it still returns None, so genuinely internal steps
    stay deliberative (System-1/System-2 split preserved).
    """
    if not step_text:
        return None
    if isinstance(step_text, dict):
        action = step_text.get("action")
        if isinstance(action, dict):
            function = str(action.get("function") or "").strip()
            if function:
                return function
        step_text = step_text.get("step") or ""
    if not isinstance(step_text, str):
        step_text = str(step_text)
    s = step_text.lower()

    # 0) Code-PRODUCTION intent (write/create a function/tool/code). This MUST be
    # caught before the generic "write → leave_note" rule below, which used to
    # swallow "write a new function and register it" into a note — a procedural
    # substitute that runs, "succeeds", and advances the step while the production
    # milestone (env_snapshot: needs a real "wrote and registered" trace) stays
    # unmet → infinite re-plan. Route it to the generative gateway instead. That
    # function is non-procedural, so on the background Executive lane
    # execute_step_action defers it ("requires a deliberate action") for an honest
    # hand-off to the conscious thread; nothing gets fake-completed. Pattern mirrors
    # env_snapshot._milestone_met's production gate so recognition and satisfaction
    # agree on what "production" means.
    if (any(w in s for w in _PRODUCTION_WORDS)
            and any(w in s for w in _ARTIFACT_WORDS)):
        return "decide_to_write_code"

    # 1) Strongest signal: the step literally names a tool.
    for name in _KNOWN_FN_NAMES:
        if name in s:
            return name

    # 2) Habitual keyword rules.
    for triggers, fn_name in _INTENT_RULES:
        if any(t in s for t in triggers):
            return fn_name

    # 3) Semantic fallback, bounded to the reversible procedural set.
    best, score = _semantic_step_match(s, _PROCEDURAL_FNS)
    if best is not None and score >= _SEMANTIC_FLOOR:
        log_activity(f"[step_exec] semantic match {step_text[:48]!r} → {best} "
                     f"(sim={score:.2f})")
        return best
    return None


def _result_is_real(out: Any) -> bool:
    """
    Perceptual-control test: did the act actually produce an effect?
    A throttled/empty/failure return means the controlled perception did not
    change, so the step is not satisfied.
    """
    if out is None:
        return False
    if isinstance(out, dict):
        if out.get("changed") is False:
            return False
        txt = str(out.get("result") or out.get("summary")
                  or out.get("content") or out.get("status") or "")
    else:
        txt = str(out)
    s = txt.strip().lower()
    if len(s) < _MIN_RESULT_LEN:
        return False
    return not any(m in s for m in _FAILURE_MARKERS)


def execute_step_action(fn_name: str, context: Dict[str, Any],
                        step_text: str = "", goal: Optional[Dict[str, Any]] = None
                        ) -> Tuple[bool, str]:
    """
    Fire the recognised act (the basal-ganglia "go") and judge it by its result.

    Returns (executed, result_text):
      executed=True  → a real tool ran and the world changed (reafference present).
                       The caller should advance the step and credit agency.
      executed=False → the act was throttled / produced nothing. The caller
                       should leave the step pending and retry/replan.

    Intent propagation (EXPRESSION_MEMBRANE_FIX_PLAN E6): when the act faces a
    person (leave_note / write_desktop_note / announce / speech), word-match
    still SELECTS the act, but it no longer DISCARDS the why. The owning goal's
    purpose and the step's own text are threaded into the expression door via
    context["_expression_motive"] so the artifact is composed to serve the
    reason it was triggered — "him writing the note," not "a note happening
    near him."
    """
    # Procedural/deliberate split (Phase 5): when running on the background
    # Executive lane (context["_procedural_only"]), refuse anything that isn't a
    # reversible procedural action. Irreversible / outward-committing / self-
    # modifying steps must be executed by the CONSCIOUS thread (I10) — left pending
    # here, they escalate to the Monitor and the deliberate lane handles them.
    if context.get("_procedural_only") and not is_procedural(fn_name):
        log_activity(f"[step_exec] '{fn_name}' deferred — conscious-only action, "
                     f"not run on the background Executive lane.")
        return (False, "deferred: requires a deliberate (conscious) action")

    try:
        # Lazy import: the registry discovers this package, so importing it at
        # module top would create a cycle during cognition discovery.
        from brain.registry.cognition_registry import COGNITIVE_FUNCTIONS
    except Exception as e:
        log_error(f"[step_exec] registry unavailable: {e}")
        return (False, "")

    meta = COGNITIVE_FUNCTIONS.get(fn_name)
    fn = meta.get("function") if isinstance(meta, dict) else None
    if not callable(fn):
        log_error(f"[step_exec] '{fn_name}' is not a callable registered function")
        return (False, "")

    # Thread the goal's motive across the execution boundary for person-facing
    # acts (E6). The expression door reads context["_expression_motive"] and
    # composes from it; cleared in finally so it never leaks to a later act.
    _motive_set = False
    try:
        from brain.behavior.express_to_user import EXPRESSIVE_FUNCTIONS
        if fn_name in EXPRESSIVE_FUNCTIONS:
            g = goal if isinstance(goal, dict) else (bound_goal(context) or {})
            spec_raw = g.get("spec")
            spec: Dict[str, Any] = spec_raw if isinstance(spec_raw, dict) else {}
            why = str(spec.get("description") or g.get("description")
                      or g.get("title") or g.get("name") or "")[:200]
            context["_expression_motive"] = {
                "intent": (step_text or fn_name)[:120],
                "why": why,
                "goal_id": str(g.get("id") or g.get("title") or g.get("name") or ""),
            }
            _motive_set = True
    except Exception as e:
        log_error(f"[step_exec] motive threading failed for '{fn_name}': {e}")

    try:
        out = fn(context)
    except Exception as e:
        log_error(f"[step_exec] '{fn_name}' raised: {e}")
        return (False, "")
    finally:
        if _motive_set:
            context.pop("_expression_motive", None)

    real = _result_is_real(out)
    result_text = (out if isinstance(out, str) else str(out))[:300]
    if real:
        log_activity(f"[step_exec] executed '{fn_name}' → {result_text[:80]}")
    else:
        log_activity(f"[step_exec] '{fn_name}' produced no effect (no reafference) — step stays pending")
    return (real, result_text)
