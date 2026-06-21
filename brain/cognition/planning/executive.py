# brain/cognition/planning/executive.py
#
# Executive (System 1, procedural execution) — dual_process_loop.md §6.1.
#
# PHASE 1 STATUS: READ-ONLY DRY RUN.
# This implements `executive_tick` in observe-only mode: it inspects the committed
# goals, recognises the next pending plan step's action, and records what it WOULD
# advance — but it writes nothing, executes nothing, and emits no affect. Its sole
# output is a telemetry/diagnostic summary on context["_exec_dryrun"], so the
# Phase-0/1 baseline ("what would the background track be doing?") becomes visible
# before any behavior change lands (spec Phase 1; observability gate §19/O1).
#
# When promoted to Phase 2, the marked TODOs become real: execute_step_action via
# cheap energy (I9), advance the step through the GoalArbiter (so a Phase-5 daemon
# is a flip, not a rewrite), submit satisfaction affect (I8/I16), self-credit
# reward to lane="executive", reset agency (I13). None of that happens yet.
from __future__ import annotations

import os
import threading
from typing import Any, Dict, List, Optional

from core.runtime_log import get_logger
from cognition.planning.step_execution import recognise_step_action
from utils.log import log_private
from utils.failure_counter import record_failure

_log = get_logger(__name__)

# How many committed goals the (eventual) Executive queue advances per tick. Read
# from context so it can be tuned; bounded small to keep cycle time predictable
# (spec §6.4, K ≤ 3). In dry-run it only bounds how many we report on.
_DEFAULT_QUEUE_K = 3

# I9 — automaticity is cheap. An executive step charges a *reduced* resource_deficit
# increment vs a deliberate act (a deliberate cycle accrues +0.002 flat plus a usually-
# larger interoceptive cost nudge). This is ~⅓ of that flat floor, so running on
# autopilot still slowly tires him — but far slower than effortful deliberate work,
# which lets the deliberate lane narrow first under low energy while the Executive
# keeps ticking (§8). Routed through the AffectArbiter (executive lane, I16), so it is
# thread-safe from the daemon and clamped like every other write. Tunable.
_EXEC_STEP_DEFICIT = float(os.environ.get("ORRIN_EXEC_STEP_DEFICIT", "0.0006") or "0.0006")

# Multi-goal pursuit (docs/multi_goal_pursuit.md, Option A + B): the per-tick
# step budget across the whole queue. 0 (default) means "one step for EVERY
# queued goal each tick" (Option A: all K goals advance every tick instead of
# 1/K of the time). A non-zero value caps or raises the total; extras beyond
# one-each go to higher-tier goals first (Option B's weighted allocation).
_EXEC_STEP_BUDGET = int(os.environ.get("ORRIN_EXEC_STEP_BUDGET", "0") or "0")

# Tier → relative share of any extra budget (and priority when the budget is
# smaller than the queue). Same weighting the old single-goal rotation used.
_TIER_TURNS = {"existential": 3, "core": 3, "identity": 2, "growth": 2,
               "exploratory": 1, "minor": 1, "trivial": 1}


def _allocate_steps(queue: List[Dict], rr: int, budget: int) -> List[tuple]:
    """Allocate `budget` pursue-steps across the queue, tier-weighted.

    Pass 1 gives every goal one step (highest tier first; the rotating offset
    `rr` breaks ties so equal-tier goals share scarce budget fairly across
    ticks). Pass 2 hands any remaining budget to higher tiers as extra steps
    (a `core` goal may take 2–3 steps while a `minor` one takes 1 — Option B).
    Returns [(goal, n_steps), ...] in execution order; total Σn == min(budget,
    achievable)."""
    if not queue or budget <= 0:
        return []
    n = len(queue)
    weights = [max(1, _TIER_TURNS.get(str(g.get("tier") or g.get("kind") or "").lower(), 1))
               for g in queue]
    order = sorted(range(n), key=lambda i: (-weights[i], (i - rr) % n))
    counts = [0] * n
    remaining = budget
    for i in order:                      # pass 1 — one each (Option A)
        if remaining <= 0:
            break
        counts[i] += 1
        remaining -= 1
    while remaining > 0:                 # pass 2 — tier-weighted extras (Option B)
        gave = False
        for i in order:
            if remaining <= 0:
                break
            if counts[i] < weights[i]:
                counts[i] += 1
                remaining -= 1
                gave = True
        if not gave:
            break                        # every goal is at its weight cap
    return [(queue[i], counts[i]) for i in order if counts[i] > 0]


def _emit_fn_executed(fn: Optional[str], context: Dict[str, Any]) -> None:
    """Gap 3 (UI_FIXES): fire `function_executed` with lane="executive" so the
    UI's fn_recent ring and lane badges actually contain executive entries.
    Routes through the loop's _push_event (the sole owner of the recent-fns
    ring) via sys.modules — never a fresh import, which would instantiate a
    second module with its own ring. Fail-safe; works from both the
    interleaved tick and the Phase-5 daemon thread."""
    if not fn:
        return
    try:
        import sys
        mod = sys.modules.get("brain.ORRIN_loop") or sys.modules.get("ORRIN_loop")
        push = getattr(mod, "_push_event", None) if mod is not None else None
        if push is None:
            return
        cyc = (context.get("cycle_count") or {}).get("count")
        push("function_executed", fn=fn, lane="executive", cycle=cyc)
    except Exception as exc:
        record_failure("executive.emit_fn_executed", exc)


def _record_history(summary: Dict[str, Any], reward: Optional[float] = None) -> None:
    """Gap 3 (UI_FIXES): persist the executive advance into
    cognition_history.json so the History tab shows BOTH lanes, not just
    think()'s deliberate picks. Slim entry, same shape /history reads
    (choice/timestamp/lane); capped like finalize's writer. Fail-safe —
    save_json is flock+atomic, so a daemon-thread write can't tear the file.
    `reward` is the executive-lane outcome reward (RUN_ISSUES_2026-06-10 §1:
    these entries used to persist reward=None, so a step that failed 133×
    in a row produced zero learning signal)."""
    try:
        from brain.paths import COGNITION_HISTORY_FILE
        from utils.json_utils import load_json, save_json
        from utils.timeutils import now_iso_z
        log = load_json(COGNITION_HISTORY_FILE, default_type=list)
        if not isinstance(log, list):
            log = []
        log.append({
            "choice": summary.get("active_fn"),
            "timestamp": now_iso_z(),
            "lane": "executive",
            "goal": summary.get("goal_title"),
            "step": summary.get("active_step"),
            "reward": reward,
        })
        save_json(COGNITION_HISTORY_FILE, log[-500:])
    except Exception as exc:
        record_failure("executive.record_history", exc)


def _outcome_reward(result: Any) -> float:
    """Map a pursue_committed_goal result to an observed (actual) reward.
    A blocked/retry/error outcome must register as LOW reward so the per-action
    EMA learns the action is failing — previously no reward was written at all
    and nothing ever learned that fetch_and_read could not succeed."""
    status = (result.get("status") if isinstance(result, dict) else None) or ""
    if status in ("retry", "blocked", "stalled", "error"):
        return 0.05
    if isinstance(result, dict) and result.get("skipped"):
        return 0.2   # no-op tick: neither success nor failure
    return 0.6       # the step advanced — real procedural progress


def _committed_goals(context: Dict[str, Any]) -> List[Dict]:
    """The goals the Executive would advance: the committed set if present, else
    the single committed goal. Read-only — no disk writes."""
    goals: List[Dict] = []
    cg = context.get("committed_goals")
    if isinstance(cg, list) and cg:
        goals = [g for g in cg if isinstance(g, dict)]
    else:
        one = context.get("committed_goal")
        if isinstance(one, dict):
            goals = [one]
    return goals[:_DEFAULT_QUEUE_K]


def _next_pending_step(goal: Dict) -> Optional[Dict]:
    """First plan step not yet completed, or None when the plan is exhausted."""
    plan = goal.get("plan")
    if not isinstance(plan, list):
        return None
    for step in plan:
        if isinstance(step, dict) and step.get("status") != "completed":
            return step
    return None


def _build_queue(context: Dict[str, Any]) -> List[Dict]:
    """The Executive's ordered queue of background tasks (≤ _DEFAULT_QUEUE_K).
    Drawn from context["committed_goals"] (the loop pulls these priority-ordered
    from the GoalsAPI, limit=3); falls back to the single committed_goal. Only
    in-progress, titled, non-paused goals."""
    seen, queue = set(), []
    src = context.get("committed_goals")
    if not isinstance(src, list) or not src:
        one = context.get("committed_goal")
        src = [one] if isinstance(one, dict) else []
    for g in src:
        if not isinstance(g, dict):
            continue
        gid = g.get("id") or g.get("title") or g.get("name")
        if not gid or gid in seen:
            continue
        if not (g.get("title") or g.get("name")):
            continue
        if g.get("status") in ("paused", "completed", "failed"):
            continue
        seen.add(gid)
        queue.append(g)
        if len(queue) >= _DEFAULT_QUEUE_K:
            break
    return queue


def executive_tick(context: Dict[str, Any]) -> Dict[str, Any]:
    """Procedural (System 1) background pass — dual_process_loop.md §6.1 / Phase 4.

    Advances committed goals' plans in the background, BEFORE think(), so the
    conscious slot is freed. It drives the proven step-runner
    `pursue_committed_goal` (plan-gen, execute_step_action, GoalArbiter advance,
    milestone gate, completion) — reused, not re-implemented. pursue is excluded
    from DELIBERATE selection so it runs ONLY here (no double execution, I3).

    Phase 4 multi-task: the Executive keeps a small ROUND-ROBIN queue
    (context["_executive_queue"], ≤ K) and advances ONE goal per cycle (rotating),
    so several goals progress across cycles WITHOUT a per-cycle tool blowup
    (≤1 step/cycle, bounds cycle time — §6.4, §13). The step-runner is keyed to
    context["committed_goal"], so the target is swapped in for the call and the
    deliberate focus is restored afterward, keeping one stable focus (I2) for the
    Monitor/Workspace/think while background tasks still advance. Sets
    _exec_last_result for the comprehension bias (§6.3). Fail-safe.
    """
    summary: Dict[str, Any] = {
        "mode": "active", "active_step": None, "active_fn": None,
        "goal_id": None, "goal_title": None, "queue": [],
        "last_result": context.get("_exec_last_result"),
    }
    try:
        queue = _build_queue(context)
        # Telemetry/queue block (§19.1) + reprioritization surface.
        summary["queue"] = [{
            "goal_id": g.get("id"),
            "title": str(g.get("title") or g.get("name") or "")[:120],
            "next_step": (str((_next_pending_step(g) or {}).get("step", ""))[:160] or None),
            "attempts": int(g.get("_completion_attempts", 0) or 0),
        } for g in queue]
        context["_executive_queue"] = summary["queue"]

        if not queue:
            context["_exec_dryrun"] = summary  # idle
            return summary

        # ── Multi-goal pursuit (docs/multi_goal_pursuit.md, Option A + B) ──────
        # Advance EVERY queued goal this tick (Option A), under a bounded
        # tier-weighted step budget (Option B), instead of advancing one rotating
        # goal per tick. With K=3 goals each used to receive a step only every
        # ~3 ticks (~21 s); now all three progress every tick while one conscious
        # focus is preserved (the deliberate slot is untouched — see the swap/
        # restore below). Single-threaded: no new concurrency hazards beyond what
        # one pursue call already had; all goal writes still go through the
        # GoalArbiter, per-goal finalize stays idempotent, and the daemon context
        # keeps its _procedural_only/_symbolic_only discipline.
        budget = _EXEC_STEP_BUDGET if _EXEC_STEP_BUDGET > 0 else len(queue)
        rr = int(context.get("_exec_rr", 0) or 0)
        context["_exec_rr"] = rr + 1     # rotates tie-breaking among equal tiers
        allocation = _allocate_steps(queue, rr, budget)

        from cognition.planning.pursue_goal import pursue_committed_goal as _pursue
        primary = context.get("committed_goal")
        primary_id = primary.get("id") if isinstance(primary, dict) else None
        advanced: List[Dict[str, Any]] = []

        for target, n_steps in allocation:
            target_id = target.get("id")
            for _step_i in range(max(1, n_steps)):
                step = _next_pending_step(target)
                step_text = step.get("step") if isinstance(step, dict) else None
                fn = recognise_step_action(step) if step else None

                # Swap the target in for the step-runner, then restore focus.
                context["committed_goal"] = target
                try:
                    result = _pursue(context)
                finally:
                    post = context.get("committed_goal")
                    if post is None:
                        # target completed (pursue clears it). Keep None only if
                        # the target WAS the deliberate focus; else restore it.
                        context["committed_goal"] = (None if (target_id == primary_id)
                                                     else primary)
                        if target_id == primary_id:
                            primary = None
                            primary_id = None
                    else:
                        context["committed_goal"] = primary  # restore focus

                status = (result.get("status") if isinstance(result, dict) else None) or ""
                rec = {
                    "goal_id": target_id,
                    "goal_title": str(target.get("title") or target.get("name") or "")[:120],
                    "step": str(step_text)[:160] if step_text else None,
                    "fn": fn,
                    "status": status or "ok",
                }
                advanced.append(rec)

                if fn:
                    # I9 — charge the (cheap) cost of one executive step. Only
                    # when a real procedural action ran; idle ticks are free. During
                    # the sleep phase this ordinary procedural cost must not fight
                    # the dream-rest recovery proposal.
                    try:
                        from cognition.dreaming.dream_cycle import dreaming_now
                        if not dreaming_now():
                            from affect.arbiter import submit_affect
                            submit_affect(context, "resource_deficit", _EXEC_STEP_DEFICIT,
                                          weight=1.0, source="executive_step", ttl_cycles=2)
                    except Exception as exc:
                        record_failure("executive.step_resource_cost", exc)
                    # Executive-lane learning signal (RUN_ISSUES_2026-06-10 §1
                    # fix 4): route the step outcome through the RewardEngine so
                    # the per-action EMA learns when a procedural action keeps
                    # failing. Affect rides the normal path (committed directly
                    # in interleaved mode, harvested to the arbiter inbox in
                    # daemon mode); the EMA file write is flock+atomic.
                    _reward: Optional[float] = None
                    try:
                        from affect.reward_signals.reward_engine import submit_reward
                        _reward = _outcome_reward(result)
                        submit_reward(context, actual=_reward, action_type=fn,
                                      kind="reward_signal", effort=0.3,
                                      source="executive_step")
                    except Exception as exc:
                        record_failure("executive.step_reward", exc)
                    # Gap 3 (UI_FIXES): this lane's advance becomes visible — a
                    # lane="executive" function_executed for the fn_recent ring,
                    # and a persisted history entry for /history.
                    _emit_fn_executed(fn, context)
                    # The UI's second light reads summary.active_fn — keep it on
                    # the most recent real act this tick.
                    summary["active_fn"] = fn
                    summary["active_step"] = rec["step"]
                    summary["goal_id"] = target_id
                    summary["goal_title"] = rec["goal_title"]
                    _record_history({**summary, "active_fn": fn,
                                     "active_step": rec["step"],
                                     "goal_title": rec["goal_title"]},
                                    reward=_reward)

                summary["last_result"] = {
                    "goal": target_id, "step": rec["step"],
                    "result": (result if isinstance(result, (dict, str)) else str(result)),
                }
                # A step that didn't take hold (blocked/retry/error) or a no-op
                # skip won't do better on an immediate same-tick retry — move to
                # the next goal rather than burning the budget on a wall.
                if status in ("retry", "blocked", "stalled", "error") or (
                        isinstance(result, dict) and result.get("skipped")):
                    break
                # Goal finished mid-tick — nothing left to advance.
                if not _next_pending_step(target) and target.get("status") in ("completed", "failed"):
                    break

        summary["advanced"] = advanced
        context["_exec_last_result"] = summary.get("last_result")
        context["_exec_dryrun"] = summary
        if advanced:
            log_private(
                "[executive] tick advanced "
                + "; ".join(f"'{a['goal_title'][:40]}'→{a['fn'] or 'thought'}({a['status']})"
                            for a in advanced)
                + f" (budget {budget}, queue {len(queue)})"
            )
    except Exception as exc:  # fail-safe — the Executive must never break the loop
        _log.warning("executive_tick failed: %s", exc)
        context["_exec_dryrun"] = summary
    return summary


# ── Phase 5: continuous Executive daemon (Option B) ───────────────────────────
# Runs the Executive on its own thread (Layer-0 style), decoupled from the ~20s
# cognitive cycle, so goal steps advance CONTINUOUSLY — the true "dribbling."
#
# GATED OFF by default (ORRIN_EXECUTIVE_DAEMON=1 to enable). The interleaved
# Phase-4 executive_tick remains the production default. When the daemon is ON the
# loop skips its interleaved call (mutual exclusion → no double execution, I3).
#
# Why it's safe to run concurrently with the main loop:
#   * Every goal write goes through the GoalArbiter (one in-process lock).
#   * Every disk write is fcntl-flock + atomic temp/rename (utils/json_utils), so
#     goals / working_memory / long_memory / context never tear or lose writes.
#   * The daemon operates on its OWN context snapshot (load_context each tick); it
#     never mutates the main loop's live context dict.
#
# KNOWN LIMITATION (why it's not yet the default): affect emitted by cognitive
# functions that a step runs (submit_affect on the daemon's private context) is not
# committed into the main affect state — the goal/WM/long-memory artifacts persist,
# but affect fidelity from daemon-run steps is reduced. Enable only experimentally
# until that path routes daemon affect through the thread-safe arbiter inbox.

_DAEMON_INTERVAL_S = float(os.environ.get("ORRIN_EXECUTIVE_DAEMON_INTERVAL", "7") or "7")
_daemon_thread: Optional[threading.Thread] = None
_daemon_stop: Optional[threading.Event] = None
_daemon_running = False


def is_daemon_running() -> bool:
    """True when the continuous Executive daemon owns step execution (so the main
    loop must skip its interleaved executive_tick to avoid double execution)."""
    return _daemon_running


def _harvest_daemon_affect(ctx: Dict[str, Any]) -> None:
    """Route affect produced by the daemon's step into the AffectArbiter's
    thread-safe inbox (submit_affect with context=None) so the MAIN loop's
    commit_affect applies it. Without this the daemon's private context is
    discarded and the affect — including the goal-COMPLETION reward (felt
    achievement) — leaks (dual_process_loop.md I8/§9). Captures BOTH pipelines:
    arbiter proposals (submit_affect → _affect_proposals) and the reward buffer
    (release_reward_signal → queue_affect_change → affect_state['_emotion_queue']).
    Caller clears these collections BEFORE the tick, so only this tick's affect is
    harvested (never the loop's pending affect carried in the loaded snapshot)."""
    try:
        from affect.arbiter import submit_affect
    except Exception as exc:
        record_failure("executive.harvest_daemon_affect.import", exc)
        return
    for p in (ctx.get("_affect_proposals") or []):
        if not isinstance(p, dict):
            continue
        try:
            submit_affect(None, p.get("target"), float(p.get("delta") or 0.0),
                          weight=float(p.get("weight") or 1.0),
                          source=f"daemon:{p.get('source', '')}"[:48],
                          ttl_cycles=int(p.get("ttl") or 3))
        except Exception as exc:
            record_failure("executive.harvest_daemon_affect.proposal", exc)
    st = ctx.get("affect_state")
    if isinstance(st, dict):
        for e in (st.get("_emotion_queue") or []):
            if not isinstance(e, dict):
                continue
            total = float(e.get("per_cycle") or 0.0) * int(e.get("cycles_left") or 3)
            if abs(total) < 1e-4:
                continue
            try:
                submit_affect(None, e.get("emotion"), total, weight=1.0,
                              source=f"daemon:{e.get('source', 'reward')}"[:48],
                              ttl_cycles=int(e.get("cycles_left") or 3))
            except Exception as exc:
                record_failure("executive.harvest_daemon_affect.reward", exc)


def _daemon_loop(stop_event: "threading.Event") -> None:
    from utils.load_utils import load_context
    while not stop_event.is_set():
        try:
            ctx = load_context()
            if isinstance(ctx, dict):
                # Daemon lane discipline (Phase 5):
                #   _symbolic_only  → plan with _symbolic_plan, never the LLM (no
                #                     contention with think(); honors §0.1 "symbolic only").
                #   _procedural_only → execute only reversible procedural steps;
                #                     irreversible/outward/self-modifying steps defer
                #                     to the conscious thread (I10).
                ctx["_symbolic_only"] = True
                ctx["_procedural_only"] = True
                # Clear affect collections so the harvest captures ONLY this tick's
                # affect (the loaded snapshot may carry the loop's pending affect;
                # re-injecting that would double-count). Ensuring core_signals is
                # present keeps release_reward_signal from reloading affect_state
                # from disk (which would defeat the pre-clear).
                ctx["_affect_proposals"] = []
                _st = ctx.get("affect_state")
                if isinstance(_st, dict) and _st.get("core_signals") is not None:
                    _st["_emotion_queue"] = []
                executive_tick(ctx)         # own snapshot; goals persist via GoalArbiter
                _harvest_daemon_affect(ctx)  # daemon affect → arbiter inbox (no leak)
                # Daemon-on telemetry (UI_FIXES Fix 1): the main loop skips its
                # interleaved tick while we own execution, so its `executive`
                # block would go stale. Push our summary to the bridge directly —
                # same forwarded/mapped key, no new contract. Fail-safe.
                try:
                    from backend.telemetry_bridge import get_bridge
                    _summary = ctx.get("_exec_dryrun")
                    if isinstance(_summary, dict):
                        get_bridge().update(executive=_summary)
                except Exception as exc:
                    record_failure("executive.daemon_telemetry", exc)
        except Exception as exc:
            _log.warning("executive daemon tick failed: %s", exc)
        stop_event.wait(_DAEMON_INTERVAL_S)


def start(stop_event: "Optional[threading.Event]" = None) -> Optional["threading.Thread"]:
    """Start the continuous Executive daemon IFF ORRIN_EXECUTIVE_DAEMON is set.
    Returns the thread, or None when disabled/already running. Mirrors the Layer-0
    daemon start() pattern."""
    global _daemon_thread, _daemon_stop, _daemon_running
    flag = os.environ.get("ORRIN_EXECUTIVE_DAEMON", "").strip().lower()
    if flag not in ("1", "true", "yes", "on"):
        return None
    if _daemon_running:
        return _daemon_thread
    _daemon_stop = stop_event or threading.Event()
    _daemon_thread = threading.Thread(
        target=_daemon_loop, args=(_daemon_stop,), name="orrin-executive", daemon=True
    )
    _daemon_running = True
    _daemon_thread.start()
    log_private(f"[executive] continuous daemon started (interval={_DAEMON_INTERVAL_S}s)")
    return _daemon_thread


def stop() -> None:
    global _daemon_running
    if _daemon_stop is not None:
        _daemon_stop.set()
    _daemon_running = False
