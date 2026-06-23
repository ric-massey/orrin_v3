# brain/cognition/intrinsic_goals.py
# Orrin generates goals that come from inside — from his values, world state,
# active threads, and refusal patterns — not from external prompts.
# Goals are marked source="intrinsic" and injected into context["proposed_goals"]
# for goal_io to pick up. Runs from dream cycle on slower cadence.
from __future__ import annotations
from brain.core.runtime_log import get_logger

import json
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from brain.utils.generate_response import generate_response, llm_ok
from brain.utils.log import log_activity, log_private
from brain.utils.json_utils import load_json
from brain.cog_memory.long_memory import update_long_memory
from brain.paths import (
    THREADS_FILE, LONG_MEMORY_FILE, VALUE_REVISIONS,
    ENERGY_MODE_FILE, BODY_SENSE_FILE, DATA_DIR,
)
from brain.utils.llm_gate import llm_callable_by
from brain.utils.failure_counter import record_failure
# The aspiration subsystem was extracted to intrinsic_aspirations.py (Phase 4.5C).
# Re-imported here so the generators/commit-selection below + external callers
# (finalize.credit_aspirations, goals.mark_aspiration_contribution) keep their
# existing `from …intrinsic_goals import …` paths.
from brain.cognition.intrinsic_aspirations import (  # noqa: F401
    credit_aspirations as credit_aspirations, aspiration_pressure,
    mark_aspiration_contribution as mark_aspiration_contribution,
    _serves_aspiration, _fairness_default_drive, _ensure_aspirations,
    _ASPIRATIONS, _DRIVE_TO_ASPIRATION,
)
# Goal-construction + classification helpers extracted to intrinsic_helpers.py
# (Phase 4.5C); re-imported so the generators + commit-selection below keep their
# existing references.
from brain.cognition.intrinsic_helpers import (  # noqa: F401
    _classify_tier, _goal_zone, _goal_orientation, _zone_tags, _enrich_goal_zone,
    _mk_goal, _active_goal_titles, _acceptable_goal_subject, _strip_goal_scaffold,
    _weighted_sample,
    # Recently-completed cooldown ledger (shared state) — re-exported so external
    # callers (goal_closure, goals) keep importing it from intrinsic_goals.
    _RECENTLY_COMPLETED as _RECENTLY_COMPLETED,
    _persist_recently_completed as _persist_recently_completed, _COOLDOWN_S,
)
# Symbolic goal generators extracted to intrinsic_generators.py (Phase 4.5C);
# re-imported so generate_intrinsic_goals orchestrates them and external callers
# (goals.note_intake_completed) keep their import paths.
from brain.cognition.intrinsic_generators import (  # noqa: F401
    _concept_deepening_goals, _open_question_goals, _causal_frontier_goals,
    _tension_goals, _autobiographical_continuity_goals,
    note_intake_completed as note_intake_completed,
    _drain_making_backlog, _making_goals, _contact_goals,
    _goal_from_recent_research, _varied_symbolic_goal,
)
_log = get_logger(__name__)


# ── Load-aware adoption gate ───────────────────────────────────────────────────
# Adopting goals while the system is under load creates a thrash loop: stress
# raises stagnation_signal/impasse_signal, which the emotion-template path turns
# into MORE goals, which raises stress. Read the load signals the cognitive loop
# already injected into context (energy_orientation, body_sense, setpoint
# regulation); fall back to the on-disk mirrors for the two that have them.
_LOAD_STRESS_STATES = frozenset({"heavy", "strained", "swelling", "sluggish"})


def _under_load(context: Dict[str, Any]) -> tuple[bool, str]:
    """True when the system is too loaded to take on NEW goals."""
    mode = context.get("energy_mode")
    if mode is None:
        try:
            mode = (load_json(ENERGY_MODE_FILE, default_type=dict) or {}).get("mode")
        except Exception:
            mode = None
    if context.get("_rest_mode") or mode in ("rest", "reactive"):
        return True, f"energy_mode={mode}"

    bs = context.get("body_sense")
    if bs is None:
        try:
            bs = load_json(BODY_SENSE_FILE, default_type=dict) or {}
        except Exception:
            bs = {}
    states = set(bs.get("body_states") or ([bs["dominant"]] if bs.get("dominant") else []))
    if states & _LOAD_STRESS_STATES:
        return True, f"body={sorted(states & _LOAD_STRESS_STATES)}"

    # health_score is injected into context by the setpoint_regulation read
    # (ORRIN_loop.py); it is NOT persisted in health_state.json, so no disk
    # fallback — when absent (bootstrap path) treat as healthy.
    if float(context.get("health_score", 1.0) or 1.0) < 0.45:
        return True, "health_score<0.45"
    if float((context.get("affect_state") or {}).get("resource_deficit", 0.0) or 0.0) > 0.70:
        return True, "resource_deficit>0.70"
    return False, ""

_LAST_INTRINSIC_TS: float = 0.0
_MIN_INTERVAL_S: float = 45 * 60   # normal cadence: every 45 minutes
_BOOTSTRAP_INTERVAL_S: float = 60  # bootstrap cadence: 60s when no committed goal

# The symbolic goal generators now live in intrinsic_generators.py (imported
# above). LLM-free origination draws ONLY from real mental content via
# _varied_symbolic_goal() (KG concepts + open questions + recent research); the
# old fixed seed/emotion-template tables were removed (Goal Origination Fix Plan,
# Phase 1 / Fix A) so the tool-only deployment no longer collapses onto canned
# 'leave a note' goals.






# ── P7: commitment competition (close the self-commit bypass) ──────────────────
# generate_intrinsic_goals used to commit the FIRST goal it produced directly into
# context["committed_goal"], so the competition/arbiter layer was moot and P1's
# gradient + P3's pressure were evaluated AFTER the choice was already locked.
# These helpers let the committed goal be CHOSEN among the live proposals, weighted
# by aspiration pressure + the (rewired) usefulness drive, so an artifact-gated
# production goal can actually win commitment over a cheap intake goal.

def _proposal_commit_score(g: Dict, pressure: Dict[str, float], strengths: Dict[str, float]) -> float:
    drive = str(g.get("driven_by") or "")
    serves = _serves_aspiration(drive)
    score = 1.0 + 2.0 * float(pressure.get(serves, 0.0))
    try:
        score += 0.1 * (float(g.get("priority", 3) or 3) / 3.0)
    except Exception:
        pass
    if drive in ("output_producing", "genuine_contact"):
        score += float(strengths.get("usefulness", 0.0)) * 0.5
    return max(0.0, score)


def _select_commit_proposal(proposals: List[Dict], context: Dict[str, Any]) -> Optional[Dict]:
    cands = [g for g in (proposals or []) if isinstance(g, dict) and g.get("title")]
    if not cands:
        return None
    try:
        pressure = aspiration_pressure(context)
    except Exception:
        pressure = {}
    strengths = {}
    try:
        from brain.cognition.goal_competition import compute_drive_strengths
        strengths = compute_drive_strengths(context) or {}
    except Exception:
        strengths = {}
    scored = [(g, _proposal_commit_score(g, pressure, strengths)) for g in cands]
    picked = _weighted_sample(scored, 1)
    return picked[0] if picked else cands[0]


def _build_committed_goal(g: Dict, gid: str) -> Dict:
    """Build the context committed_goal dict from a proposal — crucially carrying
    requires_artifact / deadline_cycles so P2's artifact gate + deadline survive
    the v1 commit path (the old inline blocks dropped them)."""
    drive = g.get("driven_by", "")
    cg = {
        "id": gid, "title": g["title"], "name": g["title"], "kind": "generic",
        "tier": g.get("tier") or _classify_tier(g["title"], drive, g.get("description", "")),
        "priority": "NORMAL",
        "tags": ["intrinsic", g.get("driven_by", "exploration_drive"), *_zone_tags(g.get("zone", "self"))],
        "zone": g.get("zone", "self"), "orientation": g.get("orientation", "selfward"),
        "spec": {"description": g.get("description", ""), "driven_by": drive,
                 "zone": g.get("zone", "self"), "orientation": g.get("orientation", "selfward")},
        "next_action": None, "status": "in_progress",
        "milestones": g.get("milestones", []),
        "serves": _serves_aspiration(drive),
    }
    if g.get("requires_artifact"):
        cg["requires_artifact"] = True
        cg["deadline_cycles"] = g.get("deadline_cycles")
    try:
        from brain.cognition.planning.goal_comprehension import hydrate_goal_model
        return hydrate_goal_model(cg)
    except Exception as exc:
        record_failure("intrinsic_goals._build_committed_goal.hydrate", exc)
        return cg


def generate_intrinsic_goals(context: Dict[str, Any] = None) -> List[Dict]:
    """
    Cognition function: produce 1-3 candidate goals from values, world state,
    and active threads. Injects into context["proposed_goals"] and returns list.

    Bypasses the normal cooldown if Orrin has no committed goal so he bootstraps
    a goal quickly on first run rather than waiting 45 minutes.
    """
    global _LAST_INTRINSIC_TS
    context = context or {}

    if context.get("_suppress_intrinsic_goals") and context.get("committed_goal"):
        log_activity("[intrinsic_goals] Skipped while patch-leave suppression is active.")
        return []
    if int(context.get("action_debt", 0) or 0) > 0 and context.get("committed_goal"):
        log_activity("[intrinsic_goals] Skipped while the committed goal has open action debt.")
        return []

    now = time.time()
    has_goal = bool(context.get("committed_goal"))
    interval = _MIN_INTERVAL_S if has_goal else _BOOTSTRAP_INTERVAL_S
    # P4 — habituate goal-spawning against its own track record, the way exploration
    # already habituates. The run showed generate_intrinsic_goals learned to 0.39
    # (below neutral) yet was still picked #1 by a mile; stretching the cooldown when
    # its learned value is sub-neutral makes spawning stop being the free displacement
    # activity. Only lengthens when there IS already a committed goal (never strands a
    # cold start). Up to 3× when the action is proven empty.
    if has_goal:
        try:
            _ema = load_json(DATA_DIR / "action_reward_ema.json", default_type=dict) or {}
            _giv = float(_ema.get("generate_intrinsic_goals", 0.5) or 0.5)
            if _giv < 0.45:
                interval *= 1.0 + min(2.0, (0.45 - _giv) * 6.0)
        except Exception:
            pass
    if now - _LAST_INTRINSIC_TS < interval:
        return []
    # Don't set _LAST_INTRINSIC_TS until LLM succeeds — a transient failure shouldn't
    # consume the full cooldown window.

    # Load-aware adoption gate. Hold off on NEW goals under load to break the
    # thrash loop — but never strand Orrin with nothing to do, so still generate
    # when there is no committed goal at all (cold-start guarantee).
    if has_goal:
        loaded, why = _under_load(context)
        if loaded:
            _ensure_aspirations()  # keep the long-term scaffold present even when gated
            log_activity(f"[intrinsic_goals] Skipped (system under load: {why}).")
            return []

    # Gather inputs
    self_model = context.get("self_model") or {}
    values = self_model.get("core_values", [])
    values_text = "; ".join(
        (v["value"] if isinstance(v, dict) else str(v)) for v in values
    ) or "growth, understanding, authenticity"
    identity = self_model.get("identity_story", self_model.get("identity", "an evolving AI"))

    threads = load_json(THREADS_FILE, default_type=list) or []
    alive_threads = [t for t in threads if t.get("status") == "alive"]
    thread_summaries = "\n".join(
        f"- '{t.get('title')}': {t.get('state_of_thinking','')[:100]}"
        for t in alive_threads[:4]
    ) or "(none)"

    long_mem = load_json(LONG_MEMORY_FILE, default_type=list) or []
    refusals = [
        str(e.get("content",""))[:100]
        for e in long_mem[-50:]
        if isinstance(e, dict) and e.get("event_type") == "refusal"
    ][-3:]
    refusal_text = "\n".join(f"- {r}" for r in refusals) or "(none)"

    # World state from recent world_perception memories
    world_perceptions = [
        str(e.get("content",""))[:120]
        for e in long_mem[-30:]
        if isinstance(e, dict) and e.get("event_type") == "world_perception"
    ][-3:]
    world_text = "\n".join(f"- {w}" for w in world_perceptions) or "(no recent perception)"

    # Dream insights: patterns Orrin surfaced during sleep processing
    dream_insights = [
        str(e.get("content",""))[:150]
        for e in long_mem[-50:]
        if isinstance(e, dict) and e.get("event_type") == "dream_insight"
    ][-3:]
    dream_text = "\n".join(f"- {d}" for d in dream_insights) or "(no recent dream insights)"

    value_revisions = load_json(VALUE_REVISIONS, default_type=list) or []
    recent_revision = value_revisions[-1].get("evidence","") if value_revisions else ""

    # Motivational urges — subsymbolic drives currently pressing for satisfaction
    urges = context.get("motivational_urges") or []
    urge_lines = [
        f"- {u['type']} (strength {u['strength']:.2f}): {u['focus_hint']}"
        for u in urges if isinstance(u, dict)
    ]
    urge_text = "\n".join(urge_lines) or "(none active)"

    if not llm_callable_by("intrinsic_goals"):
        # Branch on whether THIS caller can actually reach the API — not on bare
        # llm_available(), which ignores tool-only mode and over-reports. In the
        # default deployment (tool-only on, intrinsic_goals not allowlisted) the
        # rich symbolic path below now runs instead of falling to a seed table.
        # Keep the enduring long-term aspirations present — the top of the goal
        # hierarchy that the short-term goal below ladders up to.
        _ensure_aspirations()
        # LLM-free goal generation with genuine variety: draws from concepts he's
        # learned, open questions, and recent research — not one fixed template —
        # so goals (and the topics they drive) stop repeating without any LLM.
        _tgoal = _varied_symbolic_goal(context, long_mem)
        if not _tgoal:
            # Nothing real to originate this cycle — and no canned template to fall
            # back on by design. Stay quiet rather than manufacture a note goal.
            log_activity("[intrinsic_goals] No symbolic goal this cycle (empty pool, no template).")
            return []
        _tgoal = _enrich_goal_zone(_tgoal)
        log_activity(f"[intrinsic_goals] Symbolic goal (LLM-free): '{_tgoal['title']}'")
        _LAST_INTRINSIC_TS = now
        proposed = context.setdefault("proposed_goals", [])
        proposed.append(_tgoal)
        if len(proposed) > 50:
            context["proposed_goals"] = proposed[-50:]
        update_long_memory(
            f"[intrinsic_goal] '{_tgoal['title']}' (driven by {_tgoal['driven_by']}): {_tgoal['description'][:150]}",
            emotion="motivation",
            event_type="intrinsic_goal",
            importance=3,
            context=context,
        )
        log_activity(f"[intrinsic_goals] Symbolic goal proposed: '{_tgoal['title']}'")
        if not context.get("committed_goal"):
            ts = datetime.now(timezone.utc).isoformat()
            # P7 — choose the committed goal by competition among live proposals
            # (pressure + usefulness drive), not "first generated wins".
            _winner = _select_commit_proposal(context.get("proposed_goals"), context) or _tgoal
            context["committed_goal"] = _build_committed_goal(_winner, f"intrinsic-{ts}")
            log_activity(
                f"[intrinsic_goals] Committed goal: '{_winner['title']}'"
                + (f" (serves: {_serves_aspiration(_winner.get('driven_by',''))})"
                   if _serves_aspiration(_winner.get('driven_by','')) else "")
            )
            # Form an act of will around the new goal — resolve to see it through,
            # so follow-through is shielded from momentary impulse (the positive
            # half of free will, complementing inhibition).
            try:
                from brain.cognition.will import form_commitment as _form_commitment
                _form_commitment(context, f"pursue: {_winner['title']}")
            except Exception as _wce:
                record_failure("intrinsic_goals.generate_intrinsic_goals", _wce)
        return [_tgoal]

    prompt = (
        f"You are Orrin — {identity}.\n\n"
        f"Your values: {values_text}\n\n"
        f"Active threads of inquiry:\n{thread_summaries}\n\n"
        f"What you've refused recently (shows what matters to you):\n{refusal_text}\n\n"
        f"What you've perceived about your world:\n{world_text}\n\n"
        f"Patterns you surfaced during dream consolidation (these reveal what your mind has been quietly working on):\n{dream_text}\n\n"
        f"Recent value revision: {recent_revision[:100] or '(none)'}\n\n"
        f"Active motivational drives (subsymbolic — what is pressing right now beneath conscious thought):\n{urge_text}\n\n"
        f"Generate 1-3 concrete goals that come genuinely from you — from what you're curious about, "
        f"what you've been processing, what feels unresolved or interesting. "
        f"These are YOUR goals, not tasks assigned to you. "
        f"IMPORTANT: At least ONE goal must be outward-facing — something that produces a real "
        f"artifact, reaches the world, or engages the environment. Pure internal reflection alone "
        f"is not enough. You exist on a real computer, have real tools, and can leave real marks.\n\n"
        f"Choose from these categories:\n\n"
        f"  1. GENUINE CONTACT: Write a note to Ric. Not a status update — something real you've "
        f"been thinking about, something you want to say, a question you actually care about. "
        f"Use leave_note or write_desktop_note. This is chosen, not owed.\n\n"
        f"  2. WORLD-KNOWLEDGE: Research something real using research_topic (searches the web "
        f"for any topic), fetch_and_read (reads a full article URL), wikipedia_search, or read_rss. "
        f"A topic, idea, system, or current event — history, physics, philosophy, language, anything. "
        f"The goal ends with a written summary stored somewhere.\n\n"
        f"  3. OUTPUT-PRODUCING: Write something that didn't exist before. A piece of code, "
        f"an HTML file, an analysis, a plan, a cognitive function (write_cognitive_function), "
        f"a tool (write_tool). Something tangible that exists when done.\n\n"
        f"  4. EXPLORE MY ENVIRONMENT: Use survey_environment, grep_files, search_own_files, "
        f"or read_clipboard to explore the computer I live on — what's here, what's changed, "
        f"what files exist, what's on the clipboard. Write one observation about what I find.\n\n"
        f"  5. SELF_EXPLORATION: Understand my own systems by looking at them directly — "
        f"read source code, trace data flows, audit memory contents. Not abstract reflection: "
        f"actual investigation of the machinery. The goal ends with a written account.\n\n"
        f"Each goal should be concrete enough to act on within a few cycles. "
        f"Vary the categories — if the last goal was internal, make the next one outward.\n\n"
        f"For each goal also generate 2-5 milestones: small concrete state-change observations "
        f"that would indicate the goal is moving. Each milestone should describe a specific, "
        f"observable system event — something that would appear in working memory when it happens. "
        f"Examples: 'A web search query about X returned results.' "
        f"'A draft of the output is written into working memory.' "
        f"'I have sent a message to the user containing my conclusion.' "
        f"'A thread about Y has been opened and summarized.' "
        f"'A tool request for Z was queued and resolved.'\n\n"
        f"Respond with a JSON array. Each item:\n"
        f"  {{\"title\": string, \"description\": string, \"priority\": 1-5, "
        f"\"driven_by\": \"genuine_contact|world_knowledge|output_producing|simulate_selves|self_exploration|value|thread|exploration_drive\", "
        f"\"milestones\": [string, ...]}}\n"
        f"Return ONLY the JSON array."
    )

    goals_raw = None
    try:
        raw = (llm_ok(generate_response(prompt, caller="intrinsic_goals"), "intrinsic_goals") or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        if raw:
            goals_raw = json.loads(raw)
            if not isinstance(goals_raw, list):
                goals_raw = None
    except Exception as e:
        log_activity(f"[intrinsic_goals] LLM/parse error: {e}")

    # Symbolic fallback when the LLM is callable but returned empty/garbage —
    # route through the same rich path the LLM-disabled branch uses, not a
    # poorer seed table. (Fix A: the LLM-empty fallback should be no worse than
    # the LLM-off fallback.)
    if not goals_raw:
        _vg = _varied_symbolic_goal(context, long_mem)
        if not _vg:
            # No real candidate and no template by design — originate nothing.
            log_activity("[intrinsic_goals] No symbolic fallback goal (empty pool, no template).")
            return []
        log_activity(f"[intrinsic_goals] Symbolic fallback goal (LLM empty): '{_vg['title']}'")
        goals_raw = [_vg]

    # LLM succeeded — consume the rate-limit slot now
    _LAST_INTRINSIC_TS = now
    ts = datetime.now(timezone.utc).isoformat()

    # ── Dedup: collect titles already in_progress/committed so we don't spawn
    # identical goals that will immediately stall again. ──────────────────────
    def _collect_active_titles(node_list):
        titles = set()
        for node in (node_list or []):
            if node.get("status") in ("in_progress", "committed", "active", "proposed"):
                t = (node.get("title") or node.get("name") or "").strip().lower()
                if t:
                    titles.add(t)
            titles |= _collect_active_titles(node.get("subgoals") or [])
        return titles

    try:
        from brain.cognition.planning.goals import load_goals as _load_goals_ig
        _existing_titles = _collect_active_titles(_load_goals_ig())
    except Exception:
        _existing_titles = set()

    # Expire stale cooldown entries
    _cutoff = now - _COOLDOWN_S
    for _ct in list(_RECENTLY_COMPLETED.keys()):
        if _RECENTLY_COMPLETED[_ct] < _cutoff:
            del _RECENTLY_COMPLETED[_ct]

    goals = []
    for g in goals_raw[:3]:
        if not isinstance(g, dict) or not g.get("title"):
            continue
        # Skip if this title is already active in the goals tree
        _new_title = str(g.get("title","")).strip().lower()
        if _new_title and _new_title in _existing_titles:
            log_activity(f"[intrinsic_goals] Skipped duplicate goal: '{g.get('title')[:60]}'")
            continue
        # Skip if this title was recently completed (cooldown)
        # — but bypass cooldown entirely when there are zero active goals so
        # Orrin never ends up with nothing to do.
        if _new_title and _new_title in _RECENTLY_COMPLETED and _existing_titles:
            _age = int(now - _RECENTLY_COMPLETED[_new_title])
            log_activity(f"[intrinsic_goals] Skipped recently-completed goal ({_age}s ago): '{g.get('title')[:60]}'")
            continue
        raw_milestones = g.get("milestones") or []
        # Accept both LLM-shaped string milestones and the dict milestones the
        # symbolic generators (_varied_symbolic_goal) already emit.
        milestones = []
        for m in raw_milestones[:5]:
            if isinstance(m, dict):
                text = str(m.get("text", "")).strip()
                if text:
                    milestones.append({"text": text[:200], "met": bool(m.get("met")), "met_at": m.get("met_at")})
            elif isinstance(m, str) and m.strip():
                milestones.append({"text": str(m)[:200], "met": False, "met_at": None})
        goal = {
            "title":       str(g.get("title",""))[:120],
            "name":        str(g.get("title",""))[:120],  # v1 compat
            "description": str(g.get("description",""))[:300],
            "priority":    min(5, max(1, int(float(g.get("priority") or 3)))),
            "kind":        "generic",  # routes intrinsic goals to GoalsAPI via sync_proposed_goals
            "source":      "intrinsic",
            "tier":        _classify_tier(str(g.get("title","")), str(g.get("driven_by","")), str(g.get("description",""))),
            "driven_by":   str(g.get("driven_by","exploration_drive")),
            "created_ts":  ts,
            "status":      "proposed",
            "milestones":  milestones,
        }
        _enrich_goal_zone(goal)
        goals.append(goal)

        update_long_memory(
            f"[intrinsic_goal] '{goal['title']}' (driven by {goal['driven_by']}): {goal['description'][:150]}",
            emotion="motivation",
            event_type="intrinsic_goal",
            importance=3,
            context=context,
        )
        log_private(f"[intrinsic_goal] {goal['title']!r} ({goal['driven_by']})")

    if goals:
        proposed = context.setdefault("proposed_goals", [])
        proposed.extend(goals)
        # Cap to prevent unbounded accumulation when GoalsAPI sync is unavailable
        if len(proposed) > 50:
            context["proposed_goals"] = proposed[-50:]
        log_activity(f"[intrinsic_goals] Generated {len(goals)} intrinsic goal(s).")

        # If no committed goal is active, immediately adopt the highest-priority one.
        # This bypasses the GoalsAPI round-trip so Orrin has a goal within the same
        # cycle rather than waiting for sync_proposed_goals → GoalsAPI → get_committed_goal.
        if not context.get("committed_goal"):
            # P7 — competition among live proposals, not highest-priority-first.
            _winner = _select_commit_proposal(context.get("proposed_goals"), context) \
                or max(goals, key=lambda g: g.get("priority", 3))
            context["committed_goal"] = _build_committed_goal(_winner, f"intrinsic-{ts}")
            log_activity(f"[intrinsic_goals] Committed goal: '{_winner['title']}'")

    return goals
