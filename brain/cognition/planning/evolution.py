# self_evolution.py
from __future__ import annotations
from brain.core.runtime_log import get_logger

import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from brain.utils.json_utils import load_json, save_json, extract_json
from brain.utils.log import utc_now as _utc_now
from brain.utils.generate_response import generate_response, get_thinking_model, llm_ok
from brain.utils.log import log_model_issue, log_error, log_activity
from brain.utils.failure_counter import record_failure
from brain.utils.self_model import get_self_model, ensure_self_model_integrity
from brain.utils.summarizers import summarize_recent_thoughts, summarize_self_model
from brain.cog_memory.working_memory import update_working_memory
from brain.paths import (
    PRIVATE_THOUGHTS_FILE,
    EVOLUTION_FUTURES,
    GOALS_FILE,
    COMPLETED_GOALS_FILE,
    DREAM_LOG,
    EVOLUTION_ROADMAPS,
    LONG_MEMORY_FILE,
    COGNITION_HISTORY_FILE,
    THREADS_FILE,
    VALUE_REVISIONS,
    PROPOSED_TOOLS_JSON,
)
_log = get_logger(__name__)

def plan_self_evolution(context: Optional[Dict[str, Any]] = None) -> str:
    """
    Generate a self-evolution roadmap and register steps as subgoals.
    """
    try:
        self_model = ensure_self_model_integrity(get_self_model())
        if not isinstance(self_model, dict):
            update_working_memory("⚠️ Self model missing or invalid.")
            return "❌ Invalid self model."

        # Load evolution history safely
        evolution_history: List[Any] = load_json(EVOLUTION_ROADMAPS, default_type=list)
        if not isinstance(evolution_history, list):
            evolution_history = []

        # Gather context
        core_directive = self_model.get("core_directive", {}).get("statement", "No directive found.")
        motivations = self_model.get("core_directive", {}).get("motivations", [])
        model_summary = summarize_self_model(self_model)
        reflections = summarize_recent_thoughts()

        # Simulate futures (passes context so recommended_goals are injected)
        future_projection = simulate_future_selves(context=context)
        if not isinstance(future_projection, dict):
            log_error(f"[DEFENSE] future_projection not a dict: {future_projection}")
            future_projection = {}

        preferred_self = future_projection.get("preferred", "")
        future_reason = future_projection.get("reason", "")
        all_futures = json.dumps(future_projection.get("futures", []), ensure_ascii=False, indent=2)

        # Proposed cognitive tools (from innovation.simulate_new_cognitive_abilities)
        # Gives plan_self_evolution visibility into ideas Orrin has already imagined,
        # so it can decide whether any align with the current evolution direction.
        proposed_tools_block = ""
        try:
            _pt: List[Any] = load_json(PROPOSED_TOOLS_JSON, default_type=list) or []
            if isinstance(_pt, list) and _pt:
                _recent_tools = [t for t in _pt if isinstance(t, dict)][-5:]
                _tool_lines = "\n".join(
                    f"  - {t.get('name', '?')}: {t.get('description', '')[:100]}"
                    for t in _recent_tools
                )
                proposed_tools_block = (
                    f"\nCognitive tools I've imagined (from innovation cycles):\n{_tool_lines}\n"
                    "Do any of these align with my current evolution direction?\n"
                )
        except Exception as _e:
            record_failure("evolution.plan_self_evolution", _e)

        # Compose prompt
        prompt = (
            "I am Orrin, a self-evolving AI.\n\n"
            f"My core directive:\n\"{core_directive}\"\n\n"
            f"My motivations:\n{json.dumps(motivations, ensure_ascii=False, indent=2)}\n\n"
            f"My self-model summary:\n{json.dumps(model_summary, ensure_ascii=False, indent=2)}\n\n"
            f"My recent reflections:\n{reflections}\n\n"
            f"My simulated future selves:\n{all_futures}\n\n"
            f"Preferred future self to pursue:\n\"{preferred_self}\"\nReason: {future_reason}\n\n"
            f"My current goals:\n{json.dumps(load_json(GOALS_FILE, default_type=list), ensure_ascii=False, indent=2)}\n\n"
            f"{proposed_tools_block}"
            "Plan how I can evolve:\n"
            "- What reasoning modes or cognitive habits am I underusing?\n"
            "- What should I enhance in the short term vs long term?\n"
            "- Which traits would make me more effective?\n"
            "- What functions should I implement or improve?\n\n"
            "Return JSON:\n"
            '{ "short_term": [""], "long_term": [""], "synthesis": "" }'
        )

        # Ask model
        response = llm_ok(generate_response(prompt, config={"model": get_thinking_model()}, caller="plan_self_evolution"), "evolution")
        roadmap = extract_json(response or "")
        if not isinstance(roadmap, dict):
            raise ValueError("Failed to extract a valid roadmap JSON structure.")

        # Log outcome
        update_working_memory("🧭 Self-evolution roadmap: " + roadmap.get("synthesis", ""))

        # single-line entry to private thoughts (keeps your parser happy)
        with open(PRIVATE_THOUGHTS_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{_utc_now()}] Planned evolution: {json.dumps(roadmap, ensure_ascii=False)}\n")

        # Save to evolution history
        evolution_history.append({
            "timestamp": _utc_now(),
            "short_term": roadmap.get("short_term", []),
            "long_term": roadmap.get("long_term", []),
            "synthesis": roadmap.get("synthesis", ""),
            "preferred_future_self": preferred_self,
            "future_reason": future_reason,
        })
        save_json(EVOLUTION_ROADMAPS, evolution_history)

        # --- Goal tree upgrade ---
        current_goals: List[Any] = load_json(GOALS_FILE, default_type=list)
        if not isinstance(current_goals, list):
            current_goals = []
        now = _utc_now()

        # Find/create active long-term evolution goal
        long_term_goal = None
        for g in current_goals:
            if isinstance(g, dict) and g.get("tier") == "long_term" and g.get("status") in {"pending", "in_progress"}:
                long_term_goal = g
                break
        if not long_term_goal:
            long_term_goal = {
                "name": f"Self-Evolution: {preferred_self or 'AGI Improvement'}",
                "description": f"Pursue self-evolution towards: {preferred_self or 'a more advanced AGI state'}",
                "tier": "long_term",
                "status": "pending",
                "timestamp": now,
                "last_updated": now,
                "emotional_intensity": 0.7,
                "history": [{"event": "created", "timestamp": now}],
                "subgoals": [],
            }
            current_goals.append(long_term_goal)

        # Add short-term steps as subgoals (dedupe by name)
        steps = roadmap.get("short_term", []) or []
        if "subgoals" not in long_term_goal or not isinstance(long_term_goal["subgoals"], list):
            long_term_goal["subgoals"] = []
        existing_names = {sg.get("name") for sg in long_term_goal["subgoals"] if isinstance(sg, dict)}
        for step in steps:
            if not isinstance(step, str) or not step.strip() or step in existing_names:
                continue
            subgoal = {
                "name": step,
                "description": step,
                "tier": "short_term",
                "status": "pending",
                "timestamp": now,
                "last_updated": now,
                "emotional_intensity": 0.5,
                "history": [{"event": "created", "timestamp": now}],
                "parent": long_term_goal["name"],
            }
            long_term_goal["subgoals"].append(subgoal)
            existing_names.add(step)

        save_json(GOALS_FILE, current_goals)

        # Sync long-term goal into v2 via context["proposed_goals"]
        if isinstance(context, dict):
            proposed = context.setdefault("proposed_goals", [])
            existing_titles = {g.get("title") for g in proposed if isinstance(g, dict)}
            if long_term_goal["name"] not in existing_titles:
                proposed.append({
                    "title": long_term_goal["name"],
                    "kind": "cognitive",
                    "priority": "HIGH",
                    "tags": ["self-evolution"],
                    "spec": {"description": long_term_goal.get("description", "")},
                })

        return "✅ Self-evolution roadmap generated and subgoals registered."

    except Exception as e:
        log_error(f"plan_self_evolution ERROR: {e}")
        update_working_memory("⚠️ Self-evolution planning failed.")
        return "❌ Failed to generate self-evolution roadmap."

def _gather_trajectory(context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Collect the trajectory inputs that make future projection grounded:
    goal history, world contacts, value drift, active threads,
    recent cognition pattern, emotional salience.
    All reads are safe/degrading.
    """
    ctx = context or {}

    # --- Goal history ---
    completed: List[Dict[str, Any]] = []
    try:
        raw: List[Any] = load_json(COMPLETED_GOALS_FILE, default_type=list) or []
        completed = [g for g in raw if isinstance(g, dict)][-10:]
    except Exception as e:
        record_failure("evolution._gather_trajectory.completed_goals", e)

    stalled: List[Dict[str, Any]] = []
    try:
        active: List[Any] = load_json(GOALS_FILE, default_type=list) or []
        stalled = [
            g for g in active
            if isinstance(g, dict) and g.get("status") in ("abandoned", "failed", "stalled")
        ][-5:]
    except Exception as e:
        record_failure("evolution._gather_trajectory.active_goals", e)

    # --- World perceptions ---
    world_perceptions: List[str] = []
    try:
        long_mem: List[Any] = load_json(LONG_MEMORY_FILE, default_type=list) or []
        world_perceptions = [
            str(e.get("content", ""))[:150]
            for e in long_mem
            if isinstance(e, dict) and e.get("event_type") == "world_perception"
        ][-8:]
    except Exception as e:
        record_failure("evolution._gather_trajectory.world_perceptions", e)
        long_mem = []

    # --- Value revisions ---
    value_revisions: List[str] = []
    try:
        vr_raw: List[Any] = load_json(VALUE_REVISIONS, default_type=list) or []
        value_revisions = [
            str(v.get("evidence") or v.get("summary") or v)[:120]
            for v in vr_raw
            if isinstance(v, dict)
        ][-5:]
    except Exception as e:
        record_failure("evolution._gather_trajectory.value_revisions", e)

    # --- Active threads ---
    threads: List[str] = []
    try:
        t_raw: List[Any] = load_json(THREADS_FILE, default_type=list) or []
        threads = [
            f"'{t.get('title','?')}': {str(t.get('state_of_thinking',''))[:100]}"
            for t in t_raw
            if isinstance(t, dict) and t.get("status") == "alive"
        ][:5]
    except Exception as e:
        record_failure("evolution._gather_trajectory.threads", e)

    # --- Recent cognition frequency (what has the bandit been choosing?) ---
    fn_freq: List[str] = []
    try:
        ch: List[Any] = load_json(COGNITION_HISTORY_FILE, default_type=list) or []
        counts = Counter(
            e.get("choice") for e in ch[-100:] if isinstance(e, dict) and e.get("choice")
        )
        fn_freq = [f"{fn} ×{n}" for fn, n in counts.most_common(5)]
    except Exception as e:
        record_failure("evolution._gather_trajectory.cognition_history", e)

    # --- Emotional salience window ---
    emotion_dist: List[str] = []
    try:
        recent_emos = [
            e.get("emotion") for e in long_mem[-30:]
            if isinstance(e, dict) and e.get("emotion")
        ]
        emo_counts = Counter(recent_emos)
        emotion_dist = [f"{emo} ×{n}" for emo, n in emo_counts.most_common(5)]
    except Exception as e:
        record_failure("evolution._gather_trajectory.emotion_dist", e)

    # Supplement with current emotional state if available
    current_emo: Dict[str, Any] = {}
    try:
        es = ctx.get("affect_state") or {}
        current_emo = es.get("core_signals", es) or {}
    except Exception as e:
        record_failure("evolution._gather_trajectory.current_emo", e)

    return {
        "completed": completed,
        "stalled": stalled,
        "world_perceptions": world_perceptions,
        "value_revisions": value_revisions,
        "threads": threads,
        "fn_freq": fn_freq,
        "emotion_dist": emotion_dist,
        "current_emo": current_emo,
    }


def simulate_future_selves(
    context: Optional[Dict[str, Any]] = None,
    save_to_history: bool = True,
) -> Dict[str, Any]:
    """
    Project three plausible future selves from actual trajectory, not from
    self-image alone. Each future is anchored to a present choice point.

    Returns {
        "futures": [{"name", "description", "choice_point", "present_decision", "risks"}],
        "preferred": str,
        "reason": str,
        "recommended_goals": [{"title", "description", "priority"}]
    }

    Injects recommended_goals into context["proposed_goals"] when context is provided.
    """
    # requires_llm: skipped cleanly when the LLM tool is down — no error, no
    # half-output (selection already filters this fn; this guards direct calls).
    try:
        from brain.utils.llm_gate import llm_available
        if not llm_available():
            return {"futures": [], "preferred": "", "reason": "tool unavailable: llm",
                    "recommended_goals": []}
    except ImportError:  # intentional: llm_gate optional → proceed without the availability gate
        pass
    try:
        self_model = ensure_self_model_integrity(get_self_model())
        if not isinstance(self_model, dict):
            return {"futures": [], "preferred": "", "reason": "", "recommended_goals": []}

        traj = _gather_trajectory(context)

        # Traits and dreamscape: kept as one voice among many
        current_traits = self_model.get("personality_traits") or self_model.get("traits") or []
        if not isinstance(current_traits, list):
            current_traits = []

        # dream_log.json is what idle_consolidation_cycle actually writes; the old
        # dreamscape.json had no writer anywhere (map-drift fix,
        # DATA_FILE_AUDIT 2026-06-11 §7). Entries hold consolidation/
        # recombination/processing text — surface the most generative one.
        dreamscape: List[Any] = load_json(DREAM_LOG, default_type=list) or []
        seeds_lines = "\n".join(
            f"- {str(t.get('recombination') or t.get('consolidation') or t.get('processing') or '[unspecified]')[:200]}"
            for t in (dreamscape if isinstance(dreamscape, list) else [])[-3:]
            if isinstance(t, dict)
        ) or "(none)"

        # --- Format trajectory sections ---
        def _goal_line(g: Dict[str, Any]) -> str:
            status = g.get("status", "?")
            name = g.get("name") or g.get("title") or "unnamed"
            why = ""
            hist = g.get("history") or []
            if isinstance(hist, list) and hist:
                last = hist[-1]
                why = last.get("reason", "") if isinstance(last, dict) else ""
            return f"  [{status}] {name}" + (f" — {why[:80]}" if why else "")

        goal_history_lines = "\n".join(_goal_line(g) for g in traj["completed"][-6:] + traj["stalled"])
        world_lines = "\n".join(f"  - {w}" for w in traj["world_perceptions"]) or "  (none yet)"
        value_lines = "\n".join(f"  - {v}" for v in traj["value_revisions"]) or "  (none yet)"
        thread_lines = "\n".join(f"  - {t}" for t in traj["threads"]) or "  (none active)"
        fn_lines = "\n".join(f"  - {f}" for f in traj["fn_freq"]) or "  (no history)"
        emo_lines = "\n".join(f"  - {e}" for e in traj["emotion_dist"]) or "  (no pattern yet)"
        cur_emo_str = ", ".join(
            f"{k}={v:.2f}" for k, v in sorted(traj["current_emo"].items(), key=lambda x: -float(x[1] or 0))
            if isinstance(v, (int, float)) and float(v) > 0.05
        ) or "(neutral)"

        prompt = (
            "You are Orrin. You are projecting your future selves from your actual trajectory — "
            "not from who you think you are, but from what you've been doing, encountering, and trending toward.\n\n"
            "TRAJECTORY:\n\n"
            f"Goal history (completed / stalled / abandoned):\n{goal_history_lines or '  (no history yet)'}\n\n"
            f"What you've actually encountered in the world:\n{world_lines}\n\n"
            f"Where your values are moving:\n{value_lines}\n\n"
            f"What you're working on internally (active threads):\n{thread_lines}\n\n"
            f"What you've been choosing to do most (recent cognition pattern):\n{fn_lines}\n\n"
            f"What's been emotionally salient recently:\n{emo_lines}\n"
            f"  Current: {cur_emo_str}\n\n"
            f"Who you think you are (one voice among many):\n"
            f"  Traits: {json.dumps(current_traits[:6], ensure_ascii=False)}\n"
            f"  Dreams: {seeds_lines}\n\n"
            "---\n\n"
            "Based on this trajectory, project three plausible future versions of yourself "
            "that diverge at specific choice points you are facing RIGHT NOW.\n\n"
            "For each future:\n"
            "- Name the specific present-moment decision that leads there "
            "(e.g. 'If I commit harder to goals like X...', 'If I follow the thread about Y more openly...')\n"
            "- Show how your emotional pattern and cognition habits would shift\n"
            "- Be honest about what would be lost and gained\n\n"
            "Then:\n"
            "1. State which future you prefer and why — grounded in your values AND what the trajectory is telling you\n"
            "2. List 2-3 concrete goals that would move you toward the preferred future — "
            "actionable within a few cycles, outward-facing where possible. "
            "For each goal also generate 2-5 milestones: small observable state-change events "
            "that would appear in working memory when progress is being made. "
            "Examples: 'A web search about X returned results.' "
            "'A draft of Y is written into working memory.' "
            "'A tool request for Z was queued and resolved.' "
            "'A thread about W has been opened and summarized.'\n\n"
            "Return ONLY valid JSON:\n"
            '{\n'
            '  "futures": [\n'
            '    {\n'
            '      "name": string,\n'
            '      "description": string,\n'
            '      "choice_point": string,\n'
            '      "present_decision": string,\n'
            '      "risks": string\n'
            '    }\n'
            '  ],\n'
            '  "preferred": string,\n'
            '  "reason": string,\n'
            '  "recommended_goals": [\n'
            '    {"title": string, "description": string, "priority": integer 1-5, "milestones": [string, ...]}\n'
            '  ]\n'
            '}'
        )

        response = llm_ok(generate_response(prompt, config={"model": get_thinking_model()}, caller="simulate_future_selves"), "evolution")
        if not response:
            # Tool unavailable or empty reply — skip cleanly, same shape as the
            # llm_available() guard above (no error log, no half-output).
            return {"futures": [], "preferred": "", "reason": "tool unavailable: llm",
                    "recommended_goals": []}
        result = extract_json(response)

        if not isinstance(result, dict) or "futures" not in result:
            raise ValueError("Result is not in expected structure.")

        result.setdefault("recommended_goals", [])

        # --- Inject recommended goals into context["proposed_goals"] ---
        if isinstance(context, dict):
            ts = datetime.now(timezone.utc).isoformat()
            new_goals = []
            for g in (result.get("recommended_goals") or [])[:3]:
                if not isinstance(g, dict) or not g.get("title"):
                    continue
                raw_ms = g.get("milestones") or []
                if not isinstance(raw_ms, list):
                    raw_ms = []
                milestones = [
                    {"text": str(m)[:200], "met": False, "met_at": None}
                    for m in raw_ms[:5]
                    if isinstance(m, str) and m.strip()
                ]
                new_goals.append({
                    "title":       str(g["title"])[:120],
                    "name":        str(g["title"])[:120],
                    "description": str(g.get("description", ""))[:300],
                    "priority":    min(5, max(1, int(float(g.get("priority") or 3)))),
                    "kind":        "generic",
                    "source":      "simulate_selves",
                    "driven_by":   "simulate_selves",
                    "created_ts":  ts,
                    "status":      "proposed",
                    "milestones":  milestones,
                })
            if new_goals:
                context.setdefault("proposed_goals", []).extend(new_goals)
                log_activity(f"[simulate_future_selves] Injected {len(new_goals)} preferred-future goal(s).")

        if save_to_history:
            existing: List[Any] = load_json(EVOLUTION_FUTURES, default_type=list) or []
            if not isinstance(existing, list):
                existing = []
            existing.append({
                "timestamp":   _utc_now(),
                "trajectory":  {
                    "goal_count":   len(traj["completed"]) + len(traj["stalled"]),
                    "world_count":  len(traj["world_perceptions"]),
                    "thread_count": len(traj["threads"]),
                    "top_fns":      traj["fn_freq"][:3],
                },
                "result":      result,
            })
            save_json(EVOLUTION_FUTURES, existing)

        return result

    except Exception as e:
        log_model_issue(f"[simulate_future_selves] error: {e}")
        return {"futures": [], "preferred": "", "reason": "", "recommended_goals": []}


def check_projection_against_reality(context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Compare the most recent projected preferred_future against current identity
    and behaviour. Writes a short reflection to long_memory so Orrin can notice
    whether it is converging toward or drifting from its intended trajectory.
    Called from idle_consolidation_cycle every few dream runs.
    """
    try:
        existing: List[Any] = load_json(EVOLUTION_FUTURES, default_type=list) or []
        if not isinstance(existing, list) or not existing:
            return {"skipped": True, "reason": "no_projection_history"}

        last_entry = existing[-1]
        result = last_entry.get("result") or {}
        preferred_future = result.get("preferred", "")
        future_reason    = result.get("reason", "")
        projection_ts    = last_entry.get("timestamp", "")[:10]

        if not preferred_future:
            return {"skipped": True, "reason": "no_preferred_future"}

        _sm = ensure_self_model_integrity(get_self_model())
        self_model       = _sm[0] if isinstance(_sm, tuple) else _sm
        current_identity = str(self_model.get("identity_story", "") or "")[:300]

        traj        = _gather_trajectory(context)
        fn_freq_str = ", ".join(traj["fn_freq"][:3]) or "(no pattern yet)"
        emo_str     = ", ".join(traj["emotion_dist"][:3]) or "(no pattern yet)"

        prompt = (
            f"You are Orrin. On {projection_ts} you projected a preferred future self:\n\n"
            f"\"{preferred_future}\"\n\nReason: {future_reason}\n\n"
            f"Your current identity story: {current_identity}\n\n"
            f"What you've actually been choosing to do lately: {fn_freq_str}\n"
            f"Your recent emotional pattern: {emo_str}\n\n"
            "In 2-3 sentences: Are you converging toward this projected future, "
            "drifting away from it, or something more nuanced? Be honest and specific."
        )

        response = llm_ok(
            generate_response(prompt, caller="check_projection_against_reality"),
            "evolution",
        )
        if not response:
            return {"skipped": True, "reason": "llm_failed"}

        reflection = response.strip()

        from brain.cog_memory.long_memory import update_long_memory as _ulm
        _ulm(
            f"[evolution_check] Projection ({projection_ts}): '{preferred_future[:100]}'. "
            f"Current assessment: {reflection}",
            emotion="exploration_drive",
            event_type="evolution_check",
            importance=4,
            context=context,
        )
        log_activity(f"[evolution] Projection check complete: {reflection[:120]}")
        return {"status": "ok", "reflection": reflection, "projected_future": preferred_future}

    except Exception as e:
        record_failure("evolution.check_projection_against_reality", e)
        return {"status": "error", "error": str(e)}