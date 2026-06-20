# brain/cognition/planning/pursue_goal.py
"""
Active goal pursuit with adaptive reasoning depth, plan versioning, and
inner-loop-powered drift recovery.

pursue_committed_goal():
  - Reads the stored plan on context["committed_goal"]["plan"] if it exists.
  - Executes the next pending step directly (no replanning needed).
  - Only replans when:
      - The goal has no plan yet  (first run)
      - The plan is exhausted     (all steps completed)
      - assess_goal_progress() detected drift (drift_score > 0.15)
  - Drift severity determines replan depth:
      - drift_score 0.15–0.40 → lightweight replan (_generate_plan)
      - drift_score > 0.40    → deep replan through run_inner_loop
  - Plan history is versioned; rollback available via _rollback_plan_version().

assess_goal_progress():
  - Evaluates recent pursuit history using 3-step reasoning.
  - Stores both _drift_detected (bool) and _drift_score (float 0.0–1.0).
"""
from __future__ import annotations
from core.runtime_log import get_logger

import copy
import json as _json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from utils.generate_response import generate_response, generate_reasoning_chain, llm_ok
from utils.json_utils import load_json
from utils.log import log_activity, log_error
from cog_memory.working_memory import update_working_memory
from cog_memory.long_memory import update_long_memory
from brain.paths import LONG_MEMORY_FILE
from cognition.planning.thinking_depth import choose_depth
from cognition.planning.goals import (
    get_goal_plan, get_next_pending_step, advance_goal_plan,
    set_goal_plan, insert_plan_step, prune_satisfied_steps,
    reprioritize_pending_steps, unmet_milestone_texts, _plan_step_tokens,
)
from utils.llm_gate import llm_callable_by
from utils.failure_counter import record_failure
_log = get_logger(__name__)


# ── LLM gate ─────────────────────────────────────────────────────────────────

# ── Drift severity scorer ─────────────────────────────────────────────────────

_DRIFT_STRONG   = frozenset({"completely off track", "fundamentally wrong", "abandon",
                              "wrong direction", "stalled completely", "no progress",
                              "going nowhere", "hopeless", "irrelevant"})
_DRIFT_MODERATE = frozenset({"off track", "stalled", "not converging", "drift",
                              "not working", "replanning", "blocked", "failed",
                              "pivot", "reconsi", "ineffective", "slow progress"})
_DRIFT_MILD     = frozenset({"minor issue", "slight", "could improve", "somewhat",
                              "not ideal", "room for improvement"})


def _score_drift(assessment_text: str) -> float:
    """
    Return drift severity in [0.0, 1.0].
    0.0 = on track, 1.0 = completely derailed.
    """
    lower = (assessment_text or "").lower()
    if any(s in lower for s in _DRIFT_STRONG):
        return 0.85
    if any(s in lower for s in _DRIFT_MODERATE):
        return 0.55
    if any(s in lower for s in _DRIFT_MILD):
        return 0.22
    return 0.0


# ── Plan versioning ───────────────────────────────────────────────────────────

_MAX_PLAN_VERSIONS = 5


def _save_plan_version(goal: Dict[str, Any], reason: str = "") -> None:
    """Snapshot current plan into goal["_plan_versions"] before overwriting."""
    current_plan = list(goal.get("plan") or [])
    if not current_plan:
        return
    versions: List[Dict] = list(goal.get("_plan_versions") or [])
    versions.append({
        "version":    len(versions),
        "steps":      current_plan,
        "saved_at":   datetime.now(timezone.utc).isoformat(),
        "reason":     reason,
    })
    goal["_plan_versions"] = versions[-_MAX_PLAN_VERSIONS:]


def _rollback_plan_version(goal: Dict[str, Any], version_idx: int = -1) -> bool:
    """
    Restore a previous plan version.
    version_idx=-1 (default) restores the most recent snapshot.
    Returns True on success.
    """
    versions: List[Dict] = goal.get("_plan_versions") or []
    if not versions:
        return False
    target = versions[version_idx]
    goal["plan"] = list(target.get("steps") or [])
    goal["_rollback_from"] = target.get("version")
    log_activity(
        f"[pursue_goal] Rolled back plan to version {target.get('version')} "
        f"({target.get('reason', '?')})"
    )
    return True

_last_pursuit_ts: float = 0.0
# Refractory period between pursuit acts. A short refractory is plausible (you
# don't re-fire the same motor program instantly), but 90s was long enough that,
# at ~10s/cycle, most pursuit picks returned "cooldown" and did nothing —
# starving the forced-action path. 30s lets a forced pursuit actually act.
_COOLDOWN_S: float = 30.0
_pursuit_call_count: int = 0   # incremented each successful pursuit; drives long-memory cadence
# Goal IDs finalized recently (id → ts), to stop the same goal closing twice across
# its several in-flight dict copies (committed_goal / committed_goals / store pull).
_FINALIZED_IDS: Dict[str, float] = {}
# Give a recognised-but-ineffective step this many tries before advancing past
# it, so one unreachable step cannot hard-stall the whole plan.
_STEP_MAX_ATTEMPTS: int = 3

# Honest hand-off / disengagement (dual_process Phase 5 + Wrosch goal disengagement):
# how many cognitive cycles the conscious mind is given to perform a deliberate/
# generative step the Executive can't run, before the goal is disengaged. Counted
# at most once per cognitive cycle (not per Executive tick) so it tracks real
# conscious opportunities, not daemon frequency.
_DELIBERATE_MAX_ROUNDS: int = 30


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
        from think.think_utils.select_function import _capability_descriptions, _capability_overlap
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
        from symbolic.causal_graph import get_causes
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


# ── Deliberate goal-attention (does NOT execute) ──────────────────────────────

def attend_goal(context: Optional[Dict[str, Any]] = None) -> str:
    """Thin DELIBERATE act (dual_process_loop.md §6.3): consciously focus on the
    committed goal WITHOUT executing its steps. Step execution is owned by the
    Executive (which runs pursue_committed_goal in the background) — so this keeps
    "deciding to concentrate" available to the conscious slot without double
    execution (I3). Surfaces the goal and its next step into working memory so the
    deliberate mind can think about, supervise, or recommit to it.
    """
    context = context or {}
    goal = context.get("committed_goal")
    if not isinstance(goal, dict):
        return "No committed goal to attend to."
    title = goal.get("title") or goal.get("name") or "(untitled)"
    step = get_next_pending_step(goal)
    step_text = step.get("step") if isinstance(step, dict) else None
    msg = (f"[attend_goal] Holding focus on '{title}'. "
           + (f"Next step (the Executive is advancing it): {step_text}"
              if step_text else "Plan complete — awaiting objective check."))
    update_working_memory(msg)
    return msg


# ── Deliberate SUPERVISION of the Executive (I6 — the supervisor steers the
#    autopilot). Goal writes go through the GoalArbiter (Phase 1). ──────────────

def _stuck_enough(goal: Dict[str, Any]) -> bool:
    """True only when a goal is genuinely struggling — guards destructive commands
    so an exploratory pick can't kill a goal that's progressing fine."""
    if int(goal.get("_completion_attempts", 0) or 0) >= 2:
        return True
    sa = goal.get("_step_attempts")
    return isinstance(sa, dict) and any(int(v or 0) >= _STEP_MAX_ATTEMPTS for v in sa.values())


def redirect_goal_plan(context: Optional[Dict[str, Any]] = None) -> str:
    """Deliberate command (§6.3/I6): regenerate the committed goal's plan — the
    conscious mind steering the autopilot when the current approach isn't working.
    Non-destructive (re-plans, never kills)."""
    context = context or {}
    goal = context.get("committed_goal")
    if not isinstance(goal, dict):
        return "No committed goal to redirect."
    title = goal.get("title") or goal.get("name") or "(untitled)"
    new_plan = _symbolic_plan(title, context)
    if not new_plan:
        return f"Could not generate a new plan for '{title}'."
    set_goal_plan(goal, new_plan)
    goal.pop("_step_attempts", None)
    goal.pop("_completion_attempts", None)
    try:
        from cognition.planning.goals import merge_updated_goal_into_tree
        from cognition.planning import goal_arbiter
        goal_arbiter.apply(lambda _t: merge_updated_goal_into_tree(_t, goal),
                           source="redirect_goal_plan")
    except Exception as _e:
        record_failure("pursue_goal.redirect_goal_plan", _e)
    update_working_memory(f"[redirect_goal_plan] Re-planned '{title}' — {len(new_plan)} new step(s).")
    return f"Re-planned '{title}' with {len(new_plan)} steps."


def abandon_goal(context: Optional[Dict[str, Any]] = None) -> str:
    """Deliberate command (§6.3/I6/I10): let go of the committed goal. Guarded — only
    abandons a genuinely-stuck goal, so an exploratory pick can't kill a healthy one.
    Marking-failed feeds the self-repair loop and is a CONSCIOUS decision, never the
    Executive's."""
    context = context or {}
    goal = context.get("committed_goal")
    if not isinstance(goal, dict):
        return "No committed goal to abandon."
    title = goal.get("title") or goal.get("name") or "(untitled)"
    if not _stuck_enough(goal):
        return f"'{title}' is still progressing — not abandoning it."
    try:
        from cognition.planning.goals import mark_goal_failed, merge_updated_goal_into_tree
        from cognition.planning import goal_arbiter
        mark_goal_failed(goal, reason="released by deliberate decision (stuck)", context=context)
        goal_arbiter.apply(lambda _t: merge_updated_goal_into_tree(_t, goal),
                           source="abandon_goal")
    except Exception as _e:
        record_failure("pursue_goal.abandon_goal", _e)
    context["committed_goal"] = None
    context["_last_bootstrap_ts"] = 0.0  # let a fresh goal spawn
    update_working_memory(f"[abandon_goal] Let go of '{title}' (stuck) — making room for what's next.")
    return f"Abandoned '{title}'."


# ── Fix 1 (explore_loop_fix_plan.md §5): tier-aware objective closure ─────────

def _tier_closure_enabled() -> bool:
    """Flag gate (house pattern). OFF ⇒ legacy plan-completion gate only."""
    return os.environ.get("ORRIN_TIER_CLOSURE", "").strip().lower() in ("1", "true", "yes", "on")


def _survival_preempt_enabled() -> bool:
    return os.environ.get("ORRIN_SURVIVAL_PREEMPT", "").strip().lower() in ("1", "true", "yes", "on")


def _survival_critical(context: Dict[str, Any]) -> Tuple[bool, str]:
    """Fix 2 / §4.5 — is a survival/homeostatic drive at a level that must PREEMPT
    goal pursuit? Strict thresholds (stricter than the new-goal `_under_load` gate):
    this overrides even an "urgent" stuck goal, enforcing "a never-ending goal can't
    get in the way of survival." Pursuit YIELDS for the cycle (transient, resumable —
    not a failure). Fail-safe: any error ⇒ not critical."""
    try:
        if context.get("_setpoint_critical") or context.get("health_critical"):
            return True, "setpoint_critical"
        if float(context.get("health_score", 1.0) or 1.0) < 0.35:
            return True, "health<0.35"
        af = context.get("affect_state") or {}
        if float(af.get("resource_deficit", 0.0) or 0.0) > 0.85:
            return True, "resource_deficit>0.85"
    except Exception:
        return False, ""
    return False, ""


def _finalize_goal_completion(goal: Dict[str, Any], goal_title: str,
                              context: Dict[str, Any], reason: str = "plan complete") -> None:
    """Single, idempotent goal-completion path (Fix 1d). Fires the achievement
    reward, marks the goal completed through the GoalArbiter, clears the slot, and
    records the spawn cooldown. Shared by the plan-completion gate AND the Fix-1
    satiety/tier short-circuit so the reward can never double-fire.

    Honours mark_goal_completed's hollow-completion guard: if the objective is not
    actually met it does NOT persist/clear (the goal keeps going)."""
    if goal.get("status") in ("completed", "abandoned", "failed"):
        return  # idempotency guard — never reward/close twice
    # Cross-COPY idempotency (Fix 1d, hardened after live double-close): the same goal
    # can exist as several dicts at once — context["committed_goal"], the
    # context["committed_goals"] queue, and a fresh pull from the store — each still
    # "in_progress", so the per-dict status check above passes for each and the reward
    # double-fires. Guard on the goal ID across all copies within a short window.
    _gid = str(goal.get("id") or goal.get("title") or goal.get("name") or "")
    _nowt = time.time()
    # Keep finalized IDs for an hour (a completed goal re-appearing minutes later is
    # a stale copy still being pursued, observed live at 141s — well past a short
    # window). Cap the dict so it stays bounded.
    for _k in [k for k, t in _FINALIZED_IDS.items() if _nowt - t > 3600]:
        _FINALIZED_IDS.pop(_k, None)
    if len(_FINALIZED_IDS) > 256:
        for _k in sorted(_FINALIZED_IDS, key=_FINALIZED_IDS.get)[:64]:
            _FINALIZED_IDS.pop(_k, None)
    if _gid and _gid in _FINALIZED_IDS:
        goal["status"] = "completed"   # reflect the already-done close on this stale copy
        context["committed_goal"] = None
        return
    if _gid:
        _FINALIZED_IDS[_gid] = _nowt
    try:
        from cognition.planning.goals import mark_goal_completed, merge_updated_goal_into_tree
        from cognition.planning import goal_arbiter
        # completion_signal fires BEFORE mark_goal_completed so the achievement is
        # attributed to THIS goal, not the next one spawned by the continuity hook
        # inside mark_goal_completed (Berridge 1996 — liking at arrival).
        try:
            from affect.reward_signals.reward_signals import release_reward_signal as _rrs
            from cognition.planning.goals import achievement_significance as _achv
            _sig = _achv(goal)   # I17 — felt achievement ∝ significance, not flat
            _rrs(context, signal_type="completion_signal", actual_reward=round(1.0 * _sig, 3),
                 expected_reward=0.5, effort=0.8, mode="phasic", source="goal_completion")
        except Exception as _ee:
            log_activity(f"[pursue_goal] completion_signal release failed: {_ee}")
        mark_goal_completed(goal, context=context)
        # mark_goal_completed refuses hollow completion (goals.py:575). Only persist
        # and clear the slot if the close actually took.
        if goal.get("status") != "completed":
            log_activity(f"[pursue_goal] '{goal_title}': close ({reason}) blocked — "
                         f"objective not met; continuing to pursue.")
            return
        goal_arbiter.apply(lambda _t: merge_updated_goal_into_tree(_t, goal),
                           source="pursue_goal.completion")
        context["committed_goal"] = None
        context["_last_bootstrap_ts"] = 0.0
        log_activity(f"[pursue_goal] Goal '{goal_title}' closed ({reason}).")
        try:
            from cognition.intrinsic_goals import _RECENTLY_COMPLETED, _persist_recently_completed
            _RECENTLY_COMPLETED[goal_title.strip().lower()] = time.time()
            _persist_recently_completed()
        except Exception as _e:
            record_failure("pursue_goal._finalize_goal_completion", _e)
    except Exception as _e:
        log_activity(f"[pursue_goal] Could not close goal '{goal_title}': {_e}")


def _maybe_close_on_tier(goal: Dict[str, Any], goal_title: str, next_step: str,
                         remaining: int, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Fix 1: close a goal by its OBJECTIVE rather than its plan, scaled by tier.
      • trivial/minor  → close on met process-milestones (the act IS the goal).
      • growth/core/…  → close on SATIETY (novelty exhausted / info-gap closed, §4.2);
                          mark_goal_completed still gates on milestones, so this never
                          fakes a hollow success.
      • aspiration/long_term → never (and they're never committed anyway).
    Returns a result dict if it closed (caller should return it), else None.
    Flag-gated; only runs while steps remain (remaining != 0 is the legacy path)."""
    if not _tier_closure_enabled() or remaining == 0:
        return None
    if goal.get("status") in ("completed", "abandoned", "failed"):
        return None
    tier = str(goal.get("tier") or goal.get("kind") or "").lower()
    # (b) see just-met milestones before deciding.
    try:
        from cognition.planning.env_snapshot import apply_milestone_updates
        apply_milestone_updates(context)
    except Exception as _e:
        record_failure("pursue_goal._maybe_close_on_tier", _e)
    _ms = [m for m in (goal.get("milestones") or []) if isinstance(m, dict)]

    close, why = False, ""
    if tier in ("trivial", "minor"):
        # (a) explicit milestones, all met — never empty (vacuous all([])).
        if _ms and all(m.get("met") for m in _ms):
            close, why = True, f"trivial objective met ({tier or 'trivial'})"
    elif tier in ("aspiration", "long_term"):
        pass   # directional/never-ending goals never close here (and aren't committed)
    else:
        # growth / core / exploratory / identity / existential / generic / "" AND any
        # legacy or unknown tier (e.g. the pre-existing "short_term" goals already in
        # the store) → satiety-gated. `growth` is the unknown-tier fallback (Fix 1
        # decision box), so anything not explicitly trivial/aspiration lands here.
        from cognition.planning.goal_satiety import is_sated
        sated, sreason = is_sated(goal, context)
        if sated:
            close, why = True, f"satiety:{sreason}"

    if not close:
        return None
    _finalize_goal_completion(goal, goal_title, context, reason=why)
    if goal.get("status") == "completed":
        return {"status": "ok", "next_step": next_step, "goal": goal_title,
                "steps_remaining": remaining, "closed": True, "reason": why}
    return None  # close was blocked (hollow) — keep pursuing via the normal path


def _degrade_or_disengage(goal: Dict[str, Any], context: Dict[str, Any],
                          goal_title: str, reason: str) -> Optional[Dict[str, Any]]:
    """A goal that can't proceed — because a needed capability is down OR because it's
    making no progress. FIRST time: reduce it to a simpler achievable sub-goal that
    still serves the aspiration (means-ends — "go simpler"). If already reduced or no
    reduction exists: disengage (Wrosch — "abandon"). Never stub/fake. `reason` is a
    short human cue (e.g. "needs llm (unavailable)" or "no progress"). Returns a status
    dict, or None to fall through to normal handling."""
    try:
        from cognition.planning.goal_types import reduced_goal_spec
        from cognition.planning.goals import merge_updated_goal_into_tree, mark_goal_failed
        from cognition.planning import goal_arbiter
    except Exception:
        return None

    if not goal.get("_degraded"):
        spec = reduced_goal_spec(goal)
        if spec:
            goal["_degraded"] = True
            goal["_original_title"] = goal.get("title")
            # Snapshot the full pre-degrade form so it can be restored verbatim when
            # the capability recovers (see _repromote_if_recovered). A degrade is a
            # TEMPORARY means-ends reduction, not a permanent demotion — without this
            # snapshot a transient outage converts the goal to a note for good.
            goal["_predegrade"] = {
                "title":      goal.get("title"),
                "name":       goal.get("name"),
                "type":       goal.get("type"),
                "milestones": copy.deepcopy(goal.get("milestones")),
            }
            goal["title"] = spec["title"]
            goal["name"]  = spec["title"]
            goal["type"]  = spec["type"]
            goal["milestones"] = spec["milestones"]
            goal["_needs_deliberate_action"] = None
            goal["_deliberate_rounds"] = 0
            goal["_last_progress_cycle"] = None   # fresh progress clock for the new form
            set_goal_plan(goal, [])   # force a fresh plan for the new, achievable form
            context["committed_goal"] = goal
            update_working_memory(
                f"[goal_degraded] '{(goal.get('_original_title') or goal_title)[:40]}' ({reason}) "
                f"— pursuing a simpler achievable step instead: {spec['title'][:50]}",
                event_type="goal_degraded", importance=3,
            )
            log_activity(f"[pursue_goal] Degraded goal ({reason}) → {spec['title'][:50]}")
            try:
                goal_arbiter.apply(lambda _t: merge_updated_goal_into_tree(_t, goal),
                                   source="pursue_goal.degrade")
            except Exception as _e:
                record_failure("pursue_goal.degrade.persist", _e)
            return {"status": "degraded", "goal": spec["title"]}

    # Already reduced (or no reduction available) → disengage honestly.
    mark_goal_failed(goal, reason=f"unworkable:{reason}", context=context)
    context["committed_goal"] = None
    update_working_memory(
        f"[goal_disengaged] Releasing '{(goal.get('_original_title') or goal_title)[:40]}' — "
        f"{reason}, and no simpler version left. Moving on.",
        event_type="goal_disengaged", importance=3,
    )
    log_activity(f"[pursue_goal] Disengaged goal ({reason}, no reduction): {goal_title[:40]}")
    return {"status": "disengaged", "goal": goal_title, "reason": reason}


def _repromote_if_recovered(goal: Dict[str, Any], context: Dict[str, Any]) -> bool:
    """Restore a degraded goal to its full form once the capability it needed is
    available again. A degrade (means-ends reduction → "Note what I know about X")
    is meant to be temporary; nothing else ever reverts it, so without this a single
    transient web/LLM outage permanently rewrites real goals into notes. Returns True
    if the goal was restored."""
    if not isinstance(goal, dict) or not goal.get("_degraded"):
        return False
    try:
        from cognition.planning.goal_types import required_capability, capability_available
    except Exception:
        return False

    snap = goal.get("_predegrade") if isinstance(goal.get("_predegrade"), dict) else {}
    orig_title = snap.get("title") or goal.get("_original_title")
    if not orig_title:
        return False

    # What did the ORIGINAL (full) form need? Probe with its title/type/description so
    # the classifier sees the real research goal, not the degraded note form.
    probe = {
        "title": orig_title,
        "name": snap.get("name") or orig_title,
        "type": snap.get("type"),
        "spec": goal.get("spec"),
        "description": goal.get("description"),
    }
    cap = required_capability(probe)
    if not capability_available(cap, context):
        return False  # still down → stay in the achievable degraded form

    # Restore the full form.
    goal["title"] = orig_title
    goal["name"]  = snap.get("name") or orig_title
    if snap.get("type") is not None:
        goal["type"] = snap["type"]
    else:
        goal.pop("type", None)           # let it re-derive from title/description
    if snap.get("milestones") is not None:
        goal["milestones"] = copy.deepcopy(snap["milestones"])
    else:
        # Legacy degrade (pre-snapshot): synthesise an honest acquire-knowledge
        # milestone so the restored goal closes on a real finding, not on a note.
        subj = orig_title.split(":", 1)[-1].strip() or orig_title
        goal["milestones"] = [
            {"text": f"A finding about {subj[:60]} was written to long memory.",
             "met": False, "met_at": None},
        ]
    goal["_degraded"] = False
    goal.pop("_predegrade", None)
    goal.pop("_original_title", None)
    goal["_last_progress_cycle"] = None   # fresh progress clock for the restored form
    goal["_needs_deliberate_action"] = None
    goal["_deliberate_rounds"] = 0
    set_goal_plan(goal, [])               # force a fresh plan for the full form
    context["committed_goal"] = goal
    update_working_memory(
        f"[goal_repromoted] '{orig_title[:50]}' — the capability it needs is back, "
        f"restoring the full goal instead of the note stand-in.",
        event_type="goal_repromoted", importance=3,
    )
    log_activity(f"[pursue_goal] Re-promoted recovered goal → {orig_title[:50]}")
    try:
        from cognition.planning.goals import merge_updated_goal_into_tree
        from cognition.planning import goal_arbiter
        goal_arbiter.apply(lambda _t: merge_updated_goal_into_tree(_t, goal),
                           source="pursue_goal.repromote")
    except Exception as _e:
        record_failure("pursue_goal.repromote.persist", _e)
    return True


# ── Main entry ───────────────────────────────────────────────────────────────

def pursue_committed_goal(context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Advance the active committed goal by one concrete step.

    Flow:
      1. Check cooldown
      2. Load or generate the goal's step plan
      3. Execute the next pending step (no LLM call if plan exists)
      4. If plan exhausted → replan
      5. If drift detected → replan
      6. Update depth bandit with dual-signal reward
    """
    global _last_pursuit_ts
    context = context or {}

    now = time.time()
    # Publish the cooldown window so the SELECTOR can yield the turn to other
    # cognition instead of repeatedly picking pursue only to no-op here — that
    # spinning is ~1/3 of his pursue picks (the low-reward ones).
    context["_pursue_cooldown_until"] = _last_pursuit_ts + _COOLDOWN_S
    if now - _last_pursuit_ts < _COOLDOWN_S:
        return {"status": "ok", "skipped": True, "reason": "cooldown"}

    goal = context.get("committed_goal")
    if not isinstance(goal, dict) or not (goal.get("title") or goal.get("name")):
        return {"status": "ok", "skipped": True, "reason": "no_committed_goal"}

    # Release a goal that was already completed/abandoned/failed elsewhere
    # (e.g. goal_io/GoalsAPI marked it done but context still holds the old dict).
    if goal.get("status") in ("completed", "abandoned", "failed"):
        context["committed_goal"] = None
        log_activity(f"[pursue_goal] Released '{goal.get('title', '')[:60]}' — status={goal.get('status')}.")
        update_working_memory(
            f"[goal_released] '{goal.get('title', '')}' was already {goal.get('status')} — clearing active slot."
        )
        return {"status": "ok", "skipped": True, "reason": "goal_already_done"}

    # A goal that was degraded to a note while a capability was down is restored to
    # its full form as soon as that capability is back — before we plan/act, so we
    # pursue the real goal, not the leftover note stand-in.
    if goal.get("_degraded"):
        _repromote_if_recovered(goal, context)

    goal_title  = goal.get("title") or goal.get("name", "")

    # ── Survival preemption (Fix 2 / §4.5) ───────────────────────────────────
    # Survival is strict precedence: when a homeostatic/survival drive is critical,
    # YIELD this cycle's pursuit — even for an "urgent" goal — so a long-running or
    # never-ending goal can't crowd out staying alive. Transient and resumable: it
    # does NOT fail or pause the goal, just declines to advance it now; next cycle,
    # if the drive has cleared, pursuit proceeds. Checked BEFORE _last_pursuit_ts is
    # stamped so yielding doesn't consume the pursue cooldown. Flag-gated.
    if _survival_preempt_enabled():
        _crit, _why = _survival_critical(context)
        if _crit:
            log_activity(f"[pursue_goal] survival preemption ({_why}) — yielding pursuit "
                         f"of '{goal_title[:60]}' this cycle (resumable).")
            return {"status": "ok", "skipped": True, "reason": "survival_preempt",
                    "detail": _why, "goal": goal_title}

    _last_pursuit_ts = now
    context["_pursue_cooldown_until"] = now + _COOLDOWN_S

    # ── Energy-aware gate ────────────────────────────────────────────────────
    # High energy → pursue eagerly (shorter effective cooldown).
    # Rest / low energy → soften pursuit unless there's an urgent flag
    # (drift detected, goal stalled, or imminent deadline).
    energy_state = str(context.get("energy_state") or "medium")
    rest_mode    = bool(context.get("_rest_mode"))
    if energy_state == "high":
        pass   # no gate; proceed immediately
    elif rest_mode or energy_state == "low":
        _urgent = (
            bool(goal.get("_drift_detected"))
            or bool(goal.get("_stalled"))
            or bool((context.get("_temporal_pressure") or {}).get("deadline_alerts"))
        )
        if not _urgent:
            log_activity(
                "[pursue_goal] rest_mode/low-energy: no urgent signal — "
                "softening pursuit to allow reflection"
            )
            return {
                "status": "ok",
                "skipped": True,
                "reason":  "rest_mode_soft",
                "goal":    goal_title,
            }

    # ── Milestone gate: goals must have a plan before any step executes ──────
    # If this goal was just adopted with no plan, generate one immediately and
    # write a prominent WM note so the adoption is visible and auditable.
    if not get_goal_plan(goal):
        from cognition.planning.step_execution import recognise_step_action
        _milestone_texts = [
            str(m.get("text", m) if isinstance(m, dict) else m).strip()
            for m in (goal.get("milestones") or [])
            if (m.get("text") if isinstance(m, dict) else m)
            and not (m.get("met") if isinstance(m, dict) else False)
        ]
        # Only promote milestones to plan steps when they are actually ACTIONABLE
        # (map to a real tool / imperative). Milestones are usually success
        # CRITERIA phrased as outcomes ("A written summary was stored") — using
        # those verbatim as steps lets the goal "complete" by narration without
        # doing anything, which spins the loop (14 hollow completions/min). When
        # they are not actionable, generate a real action plan instead (symbolic,
        # no LLM) and let the milestones tick from the observed outcomes.
        _actionable_ms = [t for t in _milestone_texts if recognise_step_action(t)]
        _use_milestones = bool(_milestone_texts) and len(_actionable_ms) * 2 >= len(_milestone_texts)
        if _use_milestones:
            # Milestones are actionable — use them directly as plan steps (no LLM needed)
            set_goal_plan(goal, _milestone_texts)
            context["committed_goal"] = goal
            update_working_memory(
                f"[goal_adopted] '{goal_title}' — using {len(_milestone_texts)} milestone(s) as plan: "
                + " → ".join(s[:50] for s in _milestone_texts[:3])
            )
            log_activity(
                f"[pursue_goal] Milestone gate: promoted {len(_milestone_texts)} actionable milestone(s) "
                f"to plan steps for '{goal_title[:60]}' (no LLM needed)"
            )
        else:
            # No actionable milestones — generate a real action plan
            _gate_steps = _generate_plan(goal, context)
            if _gate_steps:
                set_goal_plan(goal, _gate_steps)
                context["committed_goal"] = goal
                update_working_memory(
                    f"[goal_adopted] '{goal_title}' committed — generated initial "
                    f"{len(_gate_steps)}-step action plan: "
                    + " → ".join(s[:60] for s in _gate_steps[:3])
                )
                log_activity(
                    f"[pursue_goal] Milestone gate: generated plan for '{goal_title[:60]}' "
                    f"({len(_gate_steps)} steps)"
                )
            else:
                # Could not build a plan — track failures and abandon after 3 attempts
                fail_count = int(goal.get("_plan_fail_count", 0) or 0) + 1
                goal["_plan_fail_count"] = fail_count
                context["committed_goal"] = goal

                if fail_count >= 3:
                    # Give up — use mark_goal_failed for proper emotion/memory handling
                    from cognition.planning.goals import mark_goal_failed
                    mark_goal_failed(goal, reason=f"plan_generation_failed_{fail_count}x", context=context)
                    context["committed_goal"] = None
                    update_working_memory(
                        f"[goal_abandoned] '{goal_title}' failed to generate a plan after "
                        f"{fail_count} attempts — releasing so I can move on."
                    )
                    log_activity(f"[pursue_goal] Abandoned '{goal_title[:60]}' — plan generation failed {fail_count}x.")
                else:
                    update_working_memory(
                        f"[goal_blocked] '{goal_title}' has no plan (attempt {fail_count}/3). "
                        "Will retry next cycle."
                    )
                    log_activity(f"[pursue_goal] Milestone gate: could not plan '{goal_title[:60]}' (attempt {fail_count}/3).")

                # ── CRITICAL: persist the updated fail count / failed status to disk ──
                # Without this save the count resets to 0 every cycle and the goal
                # is never abandoned.
                try:
                    from cognition.planning.goals import merge_updated_goal_into_tree
                    from cognition.planning import goal_arbiter
                    goal_arbiter.apply(lambda _t: merge_updated_goal_into_tree(_t, goal),
                                       source="pursue_goal.plan_fail_count")
                except Exception as _pf_e:
                    log_activity(f"[pursue_goal] Could not persist plan-fail count: {_pf_e}")

                return {"status": "blocked", "reason": "no_plan_generated", "goal": goal_title}

    # ── Drift check: replan if last assessment flagged off-track ────────────
    if goal.get("_drift_detected"):
        goal.pop("_drift_detected", None)
        drift_score   = float(goal.pop("_drift_score", 0.55))
        replan_count  = int(goal.get("_replan_count") or 0) + 1
        goal["_replan_count"] = replan_count

        if replan_count >= 3:
            goal["_stalled"] = True
            context["committed_goal"] = goal
            try:
                update_long_memory(
                    f"[goal_stalled] '{goal_title}' has been replanned {replan_count}× "
                    "without convergence. Needs genuine reconsideration.",
                    emotion="impasse_signal",
                    event_type="goal_stalled",
                    importance=4,
                    context=context,
                )
            except Exception as _e:
                record_failure("pursue_goal.pursue_committed_goal", _e)
            log_activity(f"[pursue_goal] '{goal_title[:60]}' stalled after {replan_count} replans.")
            return {"status": "stalled", "goal": goal_title, "replan_count": replan_count}

        log_activity(
            f"[pursue_goal] Drift detected (score={drift_score:.2f}) — "
            f"replan #{replan_count} for '{goal_title[:60]}'"
        )

        # Version the current plan before discarding it
        _save_plan_version(goal, reason=f"drift_replan_{replan_count}")

        if drift_score > 0.40:
            # Deep drift: use inner_loop for a reasoned replan
            try:
                from think.inner_loop import run_inner_loop as _ril
                from think.scratchpad import scratchpad_init as _sci
                _sci(context)

                goal_desc = (goal.get("spec") or {}).get("description", goal.get("description", ""))
                wm_tail   = (context.get("working_memory") or [])[-4:]
                wm_block  = "\n".join(
                    str(e.get("content", e) if isinstance(e, dict) else e)[:80]
                    for e in wm_tail
                ) or "(none)"
                il_result = _ril(
                    topic=(
                        f"Revise the plan for goal: {goal_title}\n"
                        f"Description: {goal_desc or '(none)'}\n"
                        f"This plan has drifted (severity {drift_score:.2f}). "
                        f"Recent steps:\n{wm_block}"
                    ),
                    context_text=(
                        f"Goal driven by: {goal.get('driven_by', 'exploration_drive')}\n"
                        f"Previous plan version archived. Produce a fresh 3-5 step plan."
                    ),
                    context=context,
                    max_rounds=4,
                )
                # inner_loop either deferred (no llm, symbolic mode off) or ran in
                # symbolic mode — in both cases its output is NOT JSON plan steps:
                # a typed defer is empty, and symbolic deliberation yields reasoning
                # text / KG facts, not a plan. Either way, drop to the lightweight
                # symbolic replan below rather than misparsing it into a bad plan.
                _typed_defer = (il_result.get("meta_decision") == "defer"
                                and il_result.get("reason") == "deliberation requires llm tool")
                if _typed_defer or il_result.get("mode") == "symbolic":
                    log_activity(
                        f"[pursue_goal] inner_loop {'deferred' if _typed_defer else 'symbolic'} "
                        f"(no llm) — using symbolic replan for '{goal_title[:60]}'"
                    )
                    goal["plan"] = []
                    revised_text = ""
                else:
                    revised_text = il_result.get("content", "")
                # Try to parse as JSON steps
                deep_steps: List[str] = []
                try:
                    maybe = _json.loads(revised_text)
                    if isinstance(maybe, list):
                        deep_steps = [str(s) for s in maybe if isinstance(s, str) and s.strip()]
                except Exception:
                    # Split by newline/period if JSON parse fails
                    for line in revised_text.split("\n"):
                        clean = line.strip().lstrip("0123456789.-) ")
                        if len(clean) > 10:
                            deep_steps.append(clean)

                if deep_steps:
                    set_goal_plan(goal, deep_steps)
                    context["committed_goal"] = goal
                    log_activity(
                        f"[pursue_goal] Deep replan via inner_loop: "
                        f"{len(deep_steps)} steps for '{goal_title[:60]}'"
                    )
                    update_working_memory(
                        f"[goal_replan_deep] '{goal_title}' replanned (drift={drift_score:.2f}) "
                        f"via inner_loop: " + " → ".join(s[:50] for s in deep_steps[:3])
                    )
                    # Don't fall through — execute fresh plan below
                    next_step_dict = get_next_pending_step(goal)
                    if next_step_dict is not None:
                        # jump straight to execution
                        pass  # falls through to the step execution block
                    else:
                        goal["plan"] = []   # still empty → lightweight replan below
                else:
                    goal["plan"] = []  # inner_loop parse failed → lightweight replan
            except Exception as _ile:
                log_error(f"[pursue_goal] inner_loop replan failed: {_ile}")
                goal["plan"] = []
        else:
            goal["plan"] = []  # mild drift → lightweight replan below

    # ── Passive subgoal adaptation ──────────────────────────────────────────
    # Never re-execute a step whose outcome was already achieved (its milestone
    # ticked as a side effect of earlier work). Cheap, symbolic, progress-
    # preserving — the heavier reshaping lives in adapt_subgoals().
    try:
        _pruned = prune_satisfied_steps(goal, context)
        if _pruned:
            context["committed_goal"] = goal
            log_activity(
                f"[pursue_goal] Skipped {_pruned} already-satisfied step(s) "
                f"for '{goal_title[:60]}'"
            )
    except Exception as _e:
        record_failure("pursue_goal.pursue_committed_goal.2", _e)

    # ── Plan: load existing or generate new ─────────────────────────────────
    next_step_dict = get_next_pending_step(goal)

    if next_step_dict is None:
        # Plan exhausted or missing — generate a new one
        steps = _generate_plan(goal, context)
        if not steps:
            # Fallback: single-step shallow plan (symbolic when LLM is down OR the
            # caller demands symbolic-only — the background Executive daemon).
            if not llm_callable_by("pursue_goal/fallback") or context.get("_symbolic_only"):
                concept_text = context.get("_concept_text", "")
                fallback_step = f"{goal_title}: {next_step_dict['step'] if next_step_dict else 'reflect and take one concrete action'}{(' — ' + concept_text[:100]) if concept_text else ''}".strip()[:300]
            else:
                depth = choose_depth()
                if depth >= 3:
                    result_chain = generate_reasoning_chain(
                        topic=goal_title,
                        context_text=f"Goal driven by: {goal.get('driven_by', 'exploration_drive')}",
                        caller="pursue_goal",
                    )
                    fallback_step = (result_chain.get("content") or "").strip()[:300]
                else:
                    prompt = (
                        f"You are Orrin.\n\nActive goal: \"{goal_title}\"\n\n"
                        "What is the SINGLE most concrete, actionable next step? "
                        "One sentence. Start with an action verb."
                    )
                    fallback_step = (llm_ok(generate_response(prompt, caller="pursue_goal/fallback"), "pursue_goal") or "").strip()[:300]
            if not fallback_step:
                return {"status": "error", "error": "could not generate plan or fallback step"}
            steps = [fallback_step]

        set_goal_plan(goal, steps)
        context["committed_goal"] = goal
        log_activity(f"[pursue_goal] Generated {len(steps)}-step plan for '{goal_title[:60]}'")
        next_step_dict = get_next_pending_step(goal)

    if next_step_dict is None:
        return {"status": "error", "error": "plan empty after generation"}

    next_step = next_step_dict["step"]

    # ── Discharge the step as a real act (ideomotor execution) ───────────────
    # A plan step is an intention. Pursuing the goal means firing the act that
    # realises it and checking the world afterward — not narrating the intention
    # and marking it done. James (1890) ideomotor; Powers (1973) perceptual
    # control: the step is satisfied only if the act produced an effect.
    global _pursuit_call_count
    from cognition.planning.step_execution import recognise_step_action, execute_step_action

    _act_fn = recognise_step_action(next_step)
    _executed = False
    _result_text = ""
    if _act_fn:
        # Pass the step text + owning goal so a person-facing act composes to
        # serve the reason it was triggered (EXPRESSION_MEMBRANE_FIX_PLAN E6).
        _executed, _result_text = execute_step_action(
            _act_fn, context, step_text=next_step, goal=goal)

    # ── Honest hand-off: a step the Executive must NOT run (generative / outward /
    # self-modifying — execute_step_action returns a "deferred" marker). Do NOT
    # advance it (no fake completion) and do NOT treat it as a throttled procedural
    # retry. Surface it to the conscious workspace so the deliberate mind can see
    # and act on it (the impasse signal biases the selector toward it), and count
    # conscious opportunities so a genuinely un-doable goal disengages adaptively
    # (Wrosch) instead of nagging forever.
    if _act_fn and not _executed and str(_result_text).lower().startswith("deferred"):
        # Feasibility first: if the capability this goal needs is unavailable right
        # now, don't nag the conscious mind toward an impossible act — reduce to an
        # achievable sub-goal (go simpler) or disengage (abandon). Never stub.
        try:
            from cognition.planning.goal_types import required_capability, capability_available
            _cap = required_capability(goal)
            if _cap and not capability_available(_cap, context):
                _handled = _degrade_or_disengage(goal, context, goal_title, f"needs {_cap} (unavailable)")
                if _handled is not None:
                    return _handled
        except Exception as _fe:
            record_failure("pursue_goal.feasibility", _fe)

        cc = context.get("cycle_count") or {}
        _cyc = int(cc.get("count", 0) if isinstance(cc, dict) else cc or 0)
        if goal.get("_last_deliberate_cycle") != _cyc:
            goal["_last_deliberate_cycle"] = _cyc
            _rounds = int(goal.get("_deliberate_rounds", 0) or 0) + 1
        else:
            _rounds = int(goal.get("_deliberate_rounds", 0) or 0)
        goal["_deliberate_rounds"] = _rounds
        goal["_needs_deliberate_action"] = _act_fn   # e.g. "decide_to_write_code"
        context["committed_goal"] = goal

        if _rounds >= _DELIBERATE_MAX_ROUNDS:
            from cognition.planning.goals import mark_goal_failed
            mark_goal_failed(goal, reason=f"unmet_after_{_rounds}_deliberate_rounds", context=context)
            context["committed_goal"] = None
            update_working_memory(
                f"[goal_disengaged] '{goal_title}' — the deliberate action it needs "
                f"({_act_fn}) never happened after {_rounds} cycles. Letting it go so I can move on.",
                event_type="goal_disengaged", importance=3,
            )
            log_activity(f"[pursue_goal] Disengaged '{goal_title[:60]}' — {_act_fn} unmet after {_rounds} rounds.")
            return {"status": "disengaged", "goal": goal_title, "rounds": _rounds}

        update_working_memory(
            f"[goal_needs_deliberate_action] '{goal_title}' is blocked on a step my "
            f"background mind can't do: {next_step[:80]}. The deliberate mind needs to "
            f"run {_act_fn} to move it forward (round {_rounds}/{_DELIBERATE_MAX_ROUNDS}).",
            event_type="goal_needs_deliberate_action", importance=3,
        )
        try:
            from cognition.planning.goals import merge_updated_goal_into_tree
            from cognition.planning import goal_arbiter
            goal_arbiter.apply(lambda _t: merge_updated_goal_into_tree(_t, goal),
                               source="pursue_goal.awaiting_deliberate")
        except Exception as _e:
            record_failure("pursue_goal.pursue_committed_goal.deferred", _e)
        return {"status": "awaiting_deliberate", "goal": goal_title,
                "next_step": next_step, "needs": _act_fn, "round": _rounds}

    _attempts_map = goal.setdefault("_step_attempts", {})
    _step_key = next_step[:120]

    if _act_fn and not _executed:
        # The act was recognised but produced no effect (throttled, no URL,
        # nothing found). Leave the step pending and retry — unless we have tried
        # enough times, in which case advance with an honest blocker note so
        # adapt_subgoals / drift can route around the unreachable step.
        _n = int(_attempts_map.get(_step_key, 0)) + 1
        _attempts_map[_step_key] = _n
        context["committed_goal"] = goal
        if _n < _STEP_MAX_ATTEMPTS:
            update_working_memory(
                f"[goal_blocked] '{goal_title}': step did not take hold "
                f"(attempt {_n}/{_STEP_MAX_ATTEMPTS}) — {next_step[:80]}"
            )
            try:
                from cognition.planning.goals import merge_updated_goal_into_tree
                from cognition.planning import goal_arbiter
                # Atomic load→merge→save through the GoalArbiter (no uncoordinated
                # load_goals/save_goals race; daemon-ready). dual_process_loop.md Phase 1.
                goal_arbiter.apply(lambda _t: merge_updated_goal_into_tree(_t, goal),
                                   source="pursue_goal.blocked_retry")
            except Exception as _e:
                record_failure("pursue_goal.pursue_committed_goal.3", _e)
            return {"status": "retry", "goal": goal_title, "next_step": next_step, "attempt": _n}
        update_working_memory(
            f"[goal_blocked] '{goal_title}': could not execute after {_n} "
            f"attempts — {next_step[:80]}. Moving on."
        )

    # ── Advance: the act took hold, OR the step is internal, OR we gave up ────
    log_activity(f"[pursue_goal] Executing step: {next_step[:80]}")
    advance_goal_plan(goal, next_step_dict)
    _attempts_map.pop(_step_key, None)
    # Real progress resets the stall/replan state so a future drift doesn't
    # inherit a stale counter from an unrelated earlier replan cycle.
    goal.pop("_replan_count", None)
    goal.pop("_stalled", None)
    context["committed_goal"] = goal

    # Sense of agency (efference copy): a real act discharged this cycle. This is
    # the signal that tells the loop "I acted" — it resets action_debt and earns
    # agentic reward. Internal/deliberative steps (no act fired) deliberately do
    # NOT set it, so narrating a thought never counts as doing.
    if _executed:
        context["__acted_this_tick__"] = True

    # Persist mid-pursuit step progress to disk so it survives restarts.
    try:
        from cognition.planning.goals import merge_updated_goal_into_tree
        from cognition.planning import goal_arbiter
        # Atomic load→merge→save through the GoalArbiter (daemon-ready). Phase 1.
        goal_arbiter.apply(lambda _t: merge_updated_goal_into_tree(_t, goal),
                           source="pursue_goal.step_progress")
    except Exception as _pg_e:
        log_activity(f"[pursue_goal] Could not persist step progress: {_pg_e}")

    # Working-memory record: the real result when an act fired, else narration.
    if _executed:
        update_working_memory(f"[Goal pursuit] {goal_title}: {next_step} → {_result_text[:200]}")
    elif not llm_callable_by("pursue_goal"):
        _concept_text = context.get("_concept_text", "")
        _step_output = (
            f"{goal_title} | {next_step}"
            + (f" | {_concept_text[:120]}" if _concept_text else "")
        )
        update_working_memory(f"[Goal pursuit] {_step_output}")
        _step_lower = next_step.lower()
        _WRITE_KEYWORDS = ("write", "record", "note", "observ", "document", "jot", "log")
        if any(k in _step_lower for k in _WRITE_KEYWORDS):
            try:
                from cognition.leave_note import leave_note as _ln
                _note_result = _ln(context) or ""
                # A note actually written to the outbox is an external act — it
                # must discharge action_debt like any other act, or symbolic-mode
                # goal work registers as "thinking but not doing" forever and
                # debt grows without bound (FINDINGS 2026-06-12 data sweep §7).
                if _note_result.startswith("Left a note"):
                    context["__acted_this_tick__"] = True
            except Exception as _e:
                record_failure("pursue_goal.pursue_committed_goal.4", _e)
    else:
        update_working_memory(f"[Goal pursuit] {goal_title}: {next_step}")

    # Choose depth for this step and stash it; ORRIN_loop will call
    # update_depth(depth, env_delta_reward) after the env snapshot is taken.
    depth = choose_depth()
    context["_pursue_goal_depth"] = depth

    _pursuit_call_count += 1

    # Record to long memory every 3rd successful pursuit call
    # Fix 5 (explore_loop_fix_plan.md §5): a plan step that maps to no tool — a
    # "thought, not an act" (e.g. "Reflect on what I found") — never completes, so it
    # used to deadlock the plan-completion gate forever (E2). For goals WITHOUT
    # milestones (which can't satiety-close via Fix 1), don't count such thought-steps
    # toward `remaining`, so the plan can still finish. Goals WITH milestones keep
    # counting them (Fix 1's tier/satiety path governs their closure, not the plan
    # gate — excluding here would let them close on raw process-milestones). Flag-gated.
    _has_ms = any(isinstance(m, dict) for m in (goal.get("milestones") or []))
    if _tier_closure_enabled() and not _has_ms:
        remaining = sum(
            1 for s in get_goal_plan(goal)
            if s.get("status") == "pending" and recognise_step_action(s.get("step")) is not None
        )
    else:
        remaining = sum(1 for s in get_goal_plan(goal) if s.get("status") == "pending")

    # Fix 1 (explore_loop_fix_plan.md §5): before the legacy plan-completion gate,
    # check whether the OBJECTIVE is already satisfied (tier-scaled) even though plan
    # steps remain — the case that trapped the live "Explore" goal (E1). Flag-gated.
    _tier_close = _maybe_close_on_tier(goal, goal_title, next_step, remaining, context)
    if _tier_close is not None:
        return _tier_close

    if _pursuit_call_count % 3 == 0:
        update_long_memory(
            f"[goal_pursuit] Working on '{goal_title}' — step: {next_step} "
            f"({remaining} steps remaining)",
            emotion="motivation",
            event_type="goal_pursuit",
            importance=3,
            context=context,
        )

    # When all plan steps are done, only close the goal if its OBJECTIVE (its success
    # milestones) was actually met — finishing the steps is necessary but NOT
    # sufficient. The old code marked goals "completed" the moment steps ran, so 12/12
    # completed goals had unmet objectives. Steps done + milestones met → complete;
    # steps done + milestones unmet → re-plan once, then mark FAILED (which feeds the
    # self-repair loop) — never a false success.
    if remaining == 0:
        try:
            from cognition.planning.env_snapshot import apply_milestone_updates
            apply_milestone_updates(context)
        except Exception as _e:
            record_failure("pursue_goal.pursue_committed_goal.5", _e)
        _ms = [m for m in (goal.get("milestones") or []) if isinstance(m, dict)]
        if _ms and not all(m.get("met") for m in _ms):
            _attempts = int(goal.get("_completion_attempts", 0)) + 1
            goal["_completion_attempts"] = _attempts
            _unmet = [m.get("text", "?") for m in _ms if not m.get("met")]
            try:
                # NB: set_goal_plan is already a module-level import (top of file) —
                # don't re-import it here or it becomes a function-local and shadows
                # the earlier uses (UnboundLocalError).
                from cognition.planning.goals import merge_updated_goal_into_tree, mark_goal_failed
                from cognition.planning import goal_arbiter
                if _attempts < 2:
                    set_goal_plan(goal, _symbolic_plan(goal_title, context))
                    log_activity(f"[pursue_goal] '{goal_title}': steps done but {len(_unmet)} "
                                 f"milestone(s) unmet — re-planning (attempt {_attempts}).")
                else:
                    mark_goal_failed(goal, reason=f"objective unmet after {_attempts} attempts: {_unmet[:2]}", context=context)
                    context["committed_goal"] = None
                    context["_last_bootstrap_ts"] = 0.0
                    log_activity(f"[pursue_goal] '{goal_title}': objective unmet after "
                                 f"{_attempts} attempts — FAILED (feeds self-repair).")
                # Atomic load→merge→save through the GoalArbiter (failure/objective-
                # unmet persist). dual_process_loop.md Phase 1.
                goal_arbiter.apply(lambda _t: merge_updated_goal_into_tree(_t, goal),
                                   source="pursue_goal.milestone_gate")
            except Exception as _e:
                log_activity(f"[pursue_goal] milestone-gate failed: {_e}")
            return {"status": "ok", "next_step": next_step, "goal": goal_title,
                    "steps_remaining": 0, "objective_met": False}

        # Objective genuinely met (or no milestones) → close the goal so Signal B
        # fires. Single idempotent path shared with the Fix-1 satiety short-circuit.
        _finalize_goal_completion(goal, goal_title, context, reason="plan complete")

    return {
        "status":          "ok",
        "next_step":       next_step,
        "goal":            goal_title,
        "steps_remaining": remaining,
    }


# ── Progress assessment ──────────────────────────────────────────────────────

def assess_goal_progress(context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Review recent pursuit steps and self-assess whether the goal is converging.
    Sets goal["_drift_detected"] = True if assessment signals off-track, which
    causes pursue_committed_goal() to replan on the next call.
    """
    context = context or {}
    goal    = context.get("committed_goal")
    if not isinstance(goal, dict) or not goal.get("title"):
        return {"status": "ok", "skipped": True}

    goal_title = goal.get("title", "")

    long_mem = load_json(LONG_MEMORY_FILE, default_type=list)
    if not isinstance(long_mem, list):
        return {"status": "ok", "skipped": True, "reason": "no_long_memory"}

    pursuit_entries = [
        e for e in long_mem
        if isinstance(e, dict)
        and e.get("event_type") == "goal_pursuit"
        and goal_title.lower() in str(e.get("content", "")).lower()
    ][-8:]

    if len(pursuit_entries) < 2:
        return {"status": "ok", "skipped": True, "reason": "insufficient_history"}

    steps_text = "\n".join(
        f"  {i+1}. {e.get('content','')[:120]}"
        for i, e in enumerate(pursuit_entries)
    )

    plan_summary = ""
    plan = get_goal_plan(goal)
    if plan:
        done    = sum(1 for s in plan if s.get("status") == "completed")
        pending = sum(1 for s in plan if s.get("status") == "pending")
        plan_summary = f"Plan: {done} completed, {pending} pending of {len(plan)} steps."

    context_text = (
        f"Recent pursuit steps:\n{steps_text}\n\n"
        f"Goal kind: {goal.get('kind', '')}\n"
        f"Goal source: {goal.get('source', 'unknown')}\n"
        f"{plan_summary}"
    )

    try:
        result = generate_reasoning_chain(
            topic=f"Assess progress on goal: {goal_title}",
            context_text=context_text,
            caller="goal_progress_assess",
        )
        assessment = (result.get("content") or "").strip()
        scratchpad  = result.get("scratchpad", {})

        if assessment:
            update_working_memory({
                "content":    f"[Goal assessment] {goal_title}: {assessment[:300]}",
                "event_type": "goal_assessment",
                "importance": 3, "priority": 2,
            })
            if scratchpad.get("reasoning"):
                update_long_memory(
                    f"[goal_assessment_reasoning] '{goal_title}': {scratchpad['reasoning'][:200]}",
                    emotion="exploration_drive",
                    event_type="goal_assessment",
                    importance=2,
                    context=context,
                )

            # Score drift severity and signal if above detection threshold (0.15)
            drift_score = _score_drift(assessment)
            if drift_score > 0.15:
                goal["_drift_detected"] = True
                goal["_drift_score"]    = round(drift_score, 3)
                context["committed_goal"] = goal
                log_activity(
                    f"[goal_progress] Drift flagged for '{goal_title}' "
                    f"(score={drift_score:.2f}) — will replan"
                )
                if drift_score > 0.70:
                    # Severe drift → immediate long-memory escalation
                    try:
                        update_long_memory(
                            f"[goal_severe_drift] '{goal_title}' — assessment signals severe drift "
                            f"(score={drift_score:.2f}): {assessment[:200]}",
                            emotion="impasse_signal",
                            event_type="goal_drift",
                            importance=4,
                            context=context,
                        )
                    except Exception as _e:
                        record_failure("pursue_goal.assess_goal_progress", _e)

            log_activity(f"[goal_progress] assessed '{goal_title}' drift={drift_score:.2f}")
            return {
                "status":     "ok",
                "assessment": assessment,
                "drift":      goal.get("_drift_detected", False),
                "drift_score": round(drift_score, 3),
            }

    except Exception as e:
        log_error(f"[goal_progress] assess error: {e}")

    return {"status": "ok"}


# ── Dynamic subgoal adaptation ─────────────────────────────────────────────────

_last_adapt_ts: float = 0.0
_ADAPT_COOLDOWN_S: float = 60.0

# Words/phrases in working memory that signal an emergent blocker — something
# that must be handled before the rest of the plan can make progress.
_BLOCKER_TERMS = (
    "blocked", "cannot", "can't", "unable to", "missing", "prerequisite",
    "requires", "depends on", "need to first", "failed to", "stuck on",
    "obstacle", "waiting on", "not available",
)
_MAX_GAP_FILL = 2  # cap new steps generated per adaptation pass


def _detect_blocker(context: Dict[str, Any], goal: Dict[str, Any]) -> str:
    """
    Scan recent working memory for a freshly surfaced blocker. Returns a short
    description, or "" if none found or one is already being addressed.
    Skips the pursuit loop's own bookkeeping entries to avoid false positives.
    """
    plan = get_goal_plan(goal)
    if any(
        isinstance(s, dict) and s.get("status") == "pending"
        and "resolve blocker" in str(s.get("step", "")).lower()
        for s in plan
    ):
        return ""  # a remediation step is already queued

    wm = context.get("working_memory") or []
    for entry in reversed(wm[-8:]):
        if isinstance(entry, dict):
            etype = str(entry.get("event_type", "")).lower()
            text = str(entry.get("content", ""))
        else:
            etype, text = "", str(entry)
        low = text.lower()
        # Skip our own pursuit/adaptation notes — they aren't real blockers.
        if low.startswith("[goal pursuit]") or low.startswith("[subgoal_adapt]"):
            continue
        if etype in ("goal_blocked", "goal_failure") or any(t in low for t in _BLOCKER_TERMS):
            return _strip_blocker_prefixes(text)[:140]
    return ""


# Self-nesting guard (BEHAVIOR_FIX_PLAN 2.2): WM text that surfaces as a blocker
# may itself be a previous blocker step or status note ("Resolve blocker: I am
# blocked: …"). Build remediation steps from the RAW reason only — strip any
# accumulated prefixes, repeatedly, before re-wrapping.
_BLOCKER_PREFIX_RE = re.compile(
    r"^\s*(?:resolve blocker\s*:\s*|i am blocked\s*:?\s*|blocked\s*:\s*)+",
    re.IGNORECASE,
)


def _strip_blocker_prefixes(text: str) -> str:
    out = str(text or "").strip()
    for _ in range(8):
        new = _BLOCKER_PREFIX_RE.sub("", out).strip()
        if new == out:
            break
        out = new
    return out


def _fill_milestone_gaps(goal: Dict[str, Any]) -> int:
    """
    For each unmet milestone with no pending plan step covering it, append a
    concrete step so the milestone is actually worked toward. Symbolic, capped.
    Returns the number of steps added.
    """
    plan = get_goal_plan(goal)
    pending_token_sets = [
        _plan_step_tokens(s.get("step"))
        for s in plan
        if isinstance(s, dict) and s.get("status") == "pending"
    ]
    added = 0
    for text in unmet_milestone_texts(goal):
        if added >= _MAX_GAP_FILL:
            break
        ms_tokens = _plan_step_tokens(text)
        if len(ms_tokens) < 2:
            continue
        covered = any(len(ms_tokens & pts) >= 2 for pts in pending_token_sets)
        if covered:
            continue
        new = insert_plan_step(
            goal, f"Work toward milestone: {text}", position=None,
            reason="milestone_gap",
        )
        if new:
            pending_token_sets.append(_plan_step_tokens(new.get("step")))
            added += 1
    return added


def adapt_subgoals(context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Dynamically adapt the committed goal's breakdown to current conditions.

    Surgical, progress-preserving complement to the drift→full-replan path in
    pursue_committed_goal(): instead of discarding the plan, it
      1. ticks milestones newly observable in working memory,
      2. skips pending steps whose work is already done (milestone-covered),
      3. inserts a remediation step when a blocker surfaces in working memory,
      4. reprioritizes the pending tail toward still-unmet milestones,
      5. fills coverage gaps for unmet milestones that have no pending step.

    Every operation is symbolic (no LLM) so it works with the LLM gate closed.
    The plan is versioned before mutation so a bad adaptation can be rolled back.
    """
    global _last_adapt_ts
    context = context or {}

    goal = context.get("committed_goal")
    if not isinstance(goal, dict) or not (goal.get("title") or goal.get("name")):
        return {"status": "ok", "skipped": True, "reason": "no_committed_goal"}
    if goal.get("status") in ("completed", "abandoned", "failed"):
        return {"status": "ok", "skipped": True, "reason": "goal_already_done"}

    now = time.time()
    if now - _last_adapt_ts < _ADAPT_COOLDOWN_S:
        return {"status": "ok", "skipped": True, "reason": "cooldown"}
    _last_adapt_ts = now

    goal_title = goal.get("title") or goal.get("name", "")
    changes: List[str] = []

    # Snapshot the current plan so adapt_subgoals is reversible like a replan.
    _save_plan_version(goal, reason="adapt_subgoals")

    # 1. Tick any milestones now satisfied in working memory.
    try:
        from cognition.planning.env_snapshot import apply_milestone_updates
        ticked = apply_milestone_updates(context)
        if ticked:
            changes.append(f"ticked {ticked} milestone(s)")
    except Exception as _e:
        log_error(f"[adapt_subgoals] milestone update failed: {_e}")

    # 2. Skip pending steps already satisfied by a met milestone.
    skipped = prune_satisfied_steps(goal, context)
    if skipped:
        changes.append(f"skipped {skipped} satisfied step(s)")

    # 3. Insert a remediation step for a freshly surfaced blocker.
    blocker = _detect_blocker(context, goal)
    if blocker:
        ins = insert_plan_step(
            goal, f"Resolve blocker: {blocker}", reason="blocker_detected",
        )
        if ins:
            changes.append("inserted blocker-remediation step")

    # 4. Reprioritize the pending tail toward still-unmet milestones.
    unmet_tokens: set = set()
    for text in unmet_milestone_texts(goal):
        unmet_tokens |= _plan_step_tokens(text)
    if unmet_tokens:
        if reprioritize_pending_steps(
            goal, lambda s: len(_plan_step_tokens(s.get("step")) & unmet_tokens)
        ):
            changes.append("reprioritized pending steps")

    # 5. Fill coverage gaps for unmet milestones with no pending step.
    added = _fill_milestone_gaps(goal)
    if added:
        changes.append(f"added {added} step(s) for uncovered milestone(s)")

    # Persist: context (live slot) + goal tree (survives restart).
    context["committed_goal"] = goal
    try:
        from cognition.planning.goals import merge_updated_goal_into_tree
        from cognition.planning import goal_arbiter
        goal_arbiter.apply(lambda _t: merge_updated_goal_into_tree(_t, goal),
                           source="adapt_subgoals")
    except Exception as _e:
        log_activity(f"[adapt_subgoals] could not persist goal tree: {_e}")

    if changes:
        summary = "; ".join(changes)
        update_working_memory(f"[subgoal_adapt] '{goal_title[:60]}': {summary}")
        log_activity(f"[adapt_subgoals] '{goal_title[:60]}': {summary}")
        return {"status": "ok", "goal": goal_title, "changes": changes}

    return {"status": "ok", "goal": goal_title, "changes": [], "note": "no adaptation needed"}
