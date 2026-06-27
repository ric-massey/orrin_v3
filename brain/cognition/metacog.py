# brain/cognition/metacog.py
# Metacognition channel: per-cycle reasoning trace + cross-cycle pattern detection.
#
# Per-cycle trace: phase notes accumulated during selection/action/cognition,
# flushed at cycle end into a working-memory introspection entry.
#
# Pattern detection (metacog_analyze): runs at flush time and looks for
# behavioral ruts, affective stagnation, goal avoidance, and oscillation
# across recent cycles. Surfaces observations as working-memory notes so
# the next cycle can actually see and respond to them.
#
# SCIENTIFIC BASIS:
#   Flavell (1979) — "Metacognition and cognitive monitoring: A new area of
#   cognitive-developmental inquiry." American Psychologist, 34(10), 906–911.
#   Metacognitive monitoring: observing one's own cognitive processes, detecting
#   failure patterns (ruts, oscillation), and regulating subsequent cognition.
#   Nelson & Narens (1990) — "Metamemory: A theoretical framework and new
#   findings." The Psychology of Learning and Motivation, 26, 125–173.
#   Meta-level monitoring → object-level control (suppression feedback loop).
from __future__ import annotations
from brain.core.runtime_log import get_logger

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

# Metacognitive pattern analysis, extracted to metacog_analyze.py (Phase 4.5C).
# Re-imported so metacog_flush + external callers (calibration,
# behavioral_adaptation, life_capsule_ingest) keep their reference.
from brain.cognition.metacog_analyze import metacog_analyze  # noqa: F401
from brain.utils.env import env_bool


def _hard_disengage_enabled() -> bool:
    """Fix 2 flag gate (house pattern). Default ON — the 133-failure rut is the
    documented catastrophic mode and its strongest defense should not require
    remembering an env var. Opt out with ORRIN_HARD_DISENGAGE=0."""
    return env_bool("ORRIN_HARD_DISENGAGE", True)

from brain.utils.log import log_private, log_activity
from brain.utils.json_utils import save_json, load_json
from brain.paths import METACOG_LOG, DATA_DIR
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)


# ── Init / note API (unchanged) ───────────────────────────────────────────────

def metacog_init(context: Dict[str, Any]) -> None:
    """Call at the top of each cognitive cycle to reset the trace buffer."""
    context["metacog"] = {
        "cycle_start": datetime.now(timezone.utc).isoformat(),
        "entries": [],
    }
    # Tick down the bandit's per-cycle suppression counters so muted actions
    # eventually return to the candidate pool.
    try:
        from brain.think.bandit.contextual_bandit import tick_suppression
        _remaining = tick_suppression()
        if _remaining:
            log_private(
                "[metacog/suppress] active mutes: "
                + ", ".join(f"{a}={n}" for a, n in _remaining.items())
            )
    except Exception as _e:
        record_failure("metacog.metacog_init", _e)


def metacog_note(context: Dict[str, Any], phase: str, note: str) -> None:
    """
    Append a reasoning note to the current cycle's trace.
    phase: e.g. "selection", "action", "cognition", "emotion"
    note:  brief why-string — what drove this choice
    """
    mc = context.get("metacog")
    if not isinstance(mc, dict):
        return
    mc.setdefault("entries", []).append({"phase": phase, "note": note[:200]})


# ── Metacognitive Monitor (the watcher) — dual_process_loop.md §6.2 / Phase 3 ──
# Observes the Executive's background progress and decides whether anything must
# reach consciousness. It only OFFERS candidates to the Global Workspace (I4) and
# nudges affect — it never preempts the current pick (I7) or executes (I5). A dumb
# structural watchdog (I12) escalates a stalled goal regardless of the Monitor's
# other judgments, so the regress terminates in hardware, not in cleverness.

_WATCHDOG_CYCLES = 12     # I12: a goal stalled this long auto-escalates
_HIJACK_SALIENCE = 0.85   # an offer this salient also recruits attention (next cycle)

# ── §20.1 dismissal-recalibration: the watched governs the watcher ────────────
# When the Deliberate track DISMISSES a breakthrough (it won consciousness but the
# deliberate pick ignored its route), the Monitor learns that kind was "crying wolf"
# and quiets it (raises its threshold); honored breakthroughs restore the kind's
# voice. Persisted, adaptive — backstop #2 of "who watches the watcher" (§20.1).
# SAFETY: only SOFT (non-structural) offers are damped. The structural alarms
# (objective_unmet, stuck_step, release) and the dumb watchdog (I12) are NEVER
# quieted and still escalate (§20.2), and a floor keeps even a damped kind audible.
_KIND_BIAS_FILE = DATA_DIR / "monitor_kind_bias.json"
_KIND_BIAS_FLOOR = 0.40          # a damped kind never falls silent
_KIND_BIAS_DOWN = 0.07           # dismissed → raise threshold (quieter)
_KIND_BIAS_UP = 0.05             # honored → lower threshold (restore voice)
_kind_bias: Optional[Dict[str, float]] = None
_kind_bias_dirty = False


def _load_kind_bias() -> Dict[str, float]:
    global _kind_bias
    if _kind_bias is None:
        try:
            d = load_json(_KIND_BIAS_FILE, default_type=dict)
            _kind_bias = {str(k): float(v) for k, v in (d or {}).items()}
        except Exception:
            _kind_bias = {}
    return _kind_bias


def _persist_kind_bias() -> None:
    global _kind_bias_dirty
    if _kind_bias_dirty and _kind_bias is not None:
        try:
            save_json(_KIND_BIAS_FILE, _kind_bias)
        except Exception as exc:  # bias persist failed — record (recalibration may reset)
            record_failure("metacog._persist_kind_bias", exc)
        _kind_bias_dirty = False


def _recalibrate_from_outcome(context: Dict[str, Any]) -> None:
    """Consume the previous cycle's breakthrough verdict (recorded by select_function)
    and nudge that kind's bias: honored → restore voice, dismissed → quiet it."""
    global _kind_bias_dirty
    o = context.pop("_breakthrough_outcome", None)
    if not isinstance(o, dict):
        return
    kind = o.get("kind")
    if not kind:
        return
    kb = _load_kind_bias()
    cur = float(kb.get(kind, 1.0))
    if o.get("honored"):
        new = min(1.0, cur + _KIND_BIAS_UP)
    else:
        new = max(_KIND_BIAS_FLOOR, cur - _KIND_BIAS_DOWN)
    if abs(new - cur) > 1e-6:
        kb[kind] = round(new, 3)
        _kind_bias_dirty = True
        log_private(f"[monitor] dismissal-recalibration: '{kind}' threshold "
                    f"{'lowered' if o.get('honored') else 'raised'} → bias {kb[kind]:.2f}")
    # UI_FIXES Fix 4 step 5: persist EVERY verdict (not just bias moves) into a
    # rolling ledger so honored-vs-quieted is browsable over time, instead of a
    # single per-kind badge. Read by GET /api/verdicts. Fail-safe, capped.
    try:
        ledger_file = DATA_DIR / "monitor_verdicts.json"
        ledger = load_json(ledger_file, default_type=list)
        if not isinstance(ledger, list):
            ledger = []
        ledger.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "kind": str(kind),
            "honored": bool(o.get("honored")),
            "bias": float(kb.get(kind, 1.0)),
        })
        save_json(ledger_file, ledger[-300:])
    except Exception as _e:
        record_failure("metacog._recalibrate_from_outcome", _e)


def _plan_progress_sig(goal: Dict[str, Any]):
    """A signature of plan progress: (completed steps, met milestones, plan len,
    novel-observation count). Used to detect whether the Executive advanced the goal.

    Fix 3 (explore_loop_fix_plan.md / E4): the novel-observation count comes from
    Fix 4's novelty memory. It is the term that distinguishes REAL progress (new
    information surfaced) from step-completion CHURN (a re-planned plan re-completing
    the same search every cycle, which used to flip `done` 0→1 and falsely reset the
    stall watchdog)."""
    plan = goal.get("plan") or []
    done = sum(1 for s in plan if isinstance(s, dict) and s.get("status") == "completed")
    ms = goal.get("milestones") or []
    met = sum(1 for m in ms if isinstance(m, dict) and m.get("met"))
    novel = 0
    try:
        from brain.cognition import novelty_memory
        novel = novelty_memory.novel_count(
            str(goal.get("id") or goal.get("title") or "goal"))
    except Exception:
        novel = 0
    return (done, met, len(plan) if isinstance(plan, list) else 0, novel)


def metacog_monitor(context: Dict[str, Any], exec_summary: Optional[Dict[str, Any]] = None) -> None:
    """The watcher. Reads the Executive summary + goal/affect state and offers
    breakthrough candidates to the Global Workspace on stuck / objective-unmet /
    milestone / idle, with a dumb watchdog (I12) for stalls. Fail-safe; mutates no
    goal/reward state."""
    try:
        from brain.cognition.global_workspace import offer_to_workspace
    except ImportError:  # intentional: no workspace → the monitor can't offer; skip
        return
    try:
        from brain.control_signals.arbiter import submit_affect as _submit_affect
    except Exception:
        _submit_affect = None

    if not isinstance(exec_summary, dict):
        exec_summary = context.get("_exec_dryrun") or {}
    goal = context.get("committed_goal")
    goal = goal if isinstance(goal, dict) else None
    state = context.setdefault("_monitor_state", {})

    # §20.1: fold in the previous cycle's dismissal/honor verdict before offering,
    # then load the learned per-kind thresholds that shape this cycle's salience.
    _recalibrate_from_outcome(context)
    kbias = _load_kind_bias()

    # offers: (kind, content, salience, wants, affect_target, delta, structural)
    offers = []

    if goal is None:
        offers.append(("idle",
                       "No committed goal right now — capacity to choose what matters next.",
                       0.50, "pick-new-goal", "stagnation_signal", +0.03, False))
    else:
        gid = str(goal.get("id") or goal.get("title") or "goal")
        title = str(goal.get("title") or goal.get("name") or "")[:80]
        gs = state.setdefault(gid, {"sig": None, "stall": 0, "met": 0, "prog": None})
        sig = _plan_progress_sig(goal)
        done, met, total, novel = sig
        # Fix 3 (E4): real progress = milestones met / NEW observations / plan grew —
        # NOT mere step-completion churn. The old check reset `stall` whenever `done`
        # changed, so a re-planned plan re-completing the same search every cycle
        # looked like advancement and permanently defeated the I12 watchdog. Exclude
        # `done` from the advance signal; keep the full `sig` for telemetry.
        prog = (met, novel, total)
        advanced = gs.get("prog") is not None and prog != gs.get("prog")
        gs["stall"] = 0 if (advanced or gs.get("prog") is None) else gs["stall"] + 1
        gs["prog"] = prog

        # milestone_met (savor — keeps felt achievement, I8). I17: the savored joy is
        # scaled to the goal's significance, not a flat per-milestone drip.
        if met > int(gs.get("met", 0)):
            try:
                from brain.cognition.planning.goals import achievement_significance as _achv
                _msig = _achv(goal)
            except Exception:
                _msig = 1.0
            offers.append(("milestone_met", f"Progress on '{title}': a milestone was met.",
                           0.55, "savor", "reward_positive", round(0.04 * _msig, 4), False))
        gs["met"] = met
        gs["sig"] = sig

        ms = [m for m in (goal.get("milestones") or []) if isinstance(m, dict)]
        steps_done = bool(total) and done >= total
        if ms and steps_done and not all(m.get("met") for m in ms):
            offers.append(("objective_unmet",
                           f"'{title}': the plan is finished but the objective isn't met — what's missing?",
                           0.70, "re-plan", "impasse_signal", +0.04, True))

        attempts = int(goal.get("_completion_attempts", 0) or 0)
        sa = goal.get("_step_attempts")
        if isinstance(sa, dict) and sa:
            attempts = max(attempts, max(int(v or 0) for v in sa.values()))
        if attempts >= 2:
            offers.append(("stuck_step",
                           f"'{title}': a step keeps not taking hold ({attempts} attempts) — diagnose or route around it.",
                           min(0.90, 0.55 + 0.12 * attempts), "diagnose", "impasse_signal", +0.04, True))

        # Dumb structural watchdog (I12) — fires regardless of the Monitor's logic.
        if int(gs.get("stall", 0)) >= _WATCHDOG_CYCLES:
            offers.append(("stuck_step",
                           f"'{title}' has not advanced in {gs['stall']} cycles — re-plan it or let it go.",
                           min(0.97, 0.75 + 0.02 * gs["stall"]), "re-plan", "impasse_signal", +0.05, True))
        # Escalation: stuck far past the watchdog despite re-planning → offer to
        # let it go (routes to abandon_goal, which is itself guarded). Graceful
        # progression: stuck → re-plan → release, rather than spinning forever.
        if int(gs.get("stall", 0)) >= _WATCHDOG_CYCLES * 2:
            offers.append(("release",
                           f"'{title}' is still stuck after {gs['stall']} cycles despite re-planning — consider letting it go.",
                           min(0.98, 0.85 + 0.01 * gs["stall"]), "release", "impasse_signal", +0.03, True))

        # Fix 2 (explore_loop_fix_plan.md §5): HARD escalation actuator. Every offer
        # above is SOFT — it must win a single-winner workspace competition and then
        # only BIASES a deliberate pick that competes with everything and runs on a
        # different lane than the runaway (E8). When a goal has stalled far past even
        # the release escalation (3×), the soft path has provably failed for many
        # cycles, so take a hard, guarded action: mark it FAILED (which feeds the
        # self-repair loop) rather than emit yet another advisory. This is a narrow,
        # logged, flag-gated exception to "the Monitor mutates no goal state."
        if _hard_disengage_enabled() and int(gs.get("stall", 0)) >= _WATCHDOG_CYCLES * 3:
            _stalled = int(gs.get("stall", 0))
            try:
                from brain.cognition.planning.goals import mark_goal_failed, merge_updated_goal_into_tree
                from brain.cognition.planning import goal_arbiter
                mark_goal_failed(
                    goal,
                    reason=f"hard-disengage: {_stalled} cycles with no real progress, soft offers un-honored",
                    context=context,
                )
                goal_arbiter.apply(lambda _t: merge_updated_goal_into_tree(_t, goal),
                                   source="metacog.hard_disengage")
                if context.get("committed_goal") is goal or \
                   (isinstance(context.get("committed_goal"), dict) and
                    context["committed_goal"].get("id") == goal.get("id")):
                    context["committed_goal"] = None
                gs["stall"] = 0
                log_private(f"[monitor] HARD-DISENGAGE '{title}' after {_stalled} stalled "
                            f"cycles — released to self-repair (E8 backstop).")
                log_activity(f"[metacog] Hard-disengaged stuck goal '{title}' (stall backstop).")
            except Exception as _e:
                log_private(f"[monitor] hard-disengage failed: {_e}")

    # Comprehension bias (§6.3 / I15): when the Executive just used a productive
    # tool, invite the deliberate mind to MAKE MEANING of what it surfaced — the
    # court-read after the dribble. This is the focal work the freed slot exists
    # for. (Verifiability I15: a comprehension act only "counts" if it yields a
    # real artifact — enforced where comprehension acts are scored, not here.)
    _PRODUCTIVE_FNS = {"research_topic", "fetch_and_read", "wikipedia_search",
                       "search_own_files", "read_rss", "grep_files"}
    _ex_fn = exec_summary.get("active_fn") if isinstance(exec_summary, dict) else None
    if _ex_fn in _PRODUCTIVE_FNS:
        _csig = f"{exec_summary.get('goal_id')}|{_ex_fn}|{exec_summary.get('active_step')}"
        if context.get("_last_comprehend_sig") != _csig:
            context["_last_comprehend_sig"] = _csig
            offers.append(("comprehend",
                           f"The Executive just used {_ex_fn} on "
                           f"'{exec_summary.get('goal_title', '')}' — make meaning of what it surfaced.",
                           0.50, "comprehend", "exploration_drive", +0.02, False))

    # Apply the learned per-kind threshold (§20.1) to SOFT offers only; structural
    # alarms keep full salience and still escalate (§20.2). emitted: the effective
    # offer list (kind, content, eff_salience, wants), for telemetry.
    emitted = []
    for (kind, content, sal, wants, tgt, delta, structural) in offers:
        eff_sal = sal if structural else round(sal * float(kbias.get(kind, 1.0)), 3)
        if kind == "idle" and int(context.get("action_debt", 0) or 0) > 0:
            eff_sal = max(eff_sal, 0.70)
        offer_to_workspace(context, {
            "source": f"monitor:{kind}", "content": content, "salience": eff_sal,
            "wants": wants, "kind": kind, "exempt_habituation": bool(structural),
        })
        if _submit_affect:
            try:
                _submit_affect(context, tgt, delta, weight=0.6,
                               source=f"monitor:{kind}", ttl_cycles=4)
            except Exception as exc:  # affect nudge best-effort — record
                record_failure("metacog.metacog_monitor.affect", exc)
        if eff_sal >= _HIJACK_SALIENCE:
            try:
                from brain.cognition.attention import request_attention_hijack
                request_attention_hijack(context, content=content, intensity=eff_sal,
                                         tags=["monitor", kind], source="monitor")
            except Exception as exc:  # attention hijack best-effort — record
                record_failure("metacog.metacog_monitor.hijack", exc)
        emitted.append((kind, content, eff_sal, wants))

    _persist_kind_bias()  # flush any threshold change from this cycle's recalibration

    # §19.1 monitor telemetry block (recent breakthroughs + watchdog board).
    context["_monitor_breakthroughs"] = [
        {"kind": o[0], "salience": o[2], "wants": o[3],
         "threshold": round(float(kbias.get(o[0], 1.0)), 2)} for o in emitted
    ]
    context["_monitor_watchdog"] = [
        {"goal_id": k, "cycles_since_advance": int(v.get("stall", 0)),
         "armed": int(v.get("stall", 0)) >= _WATCHDOG_CYCLES}
        for k, v in state.items()
    ]
    if offers:
        try:
            log_private("[monitor] " + ", ".join(f"{o[0]}({o[2]:.2f}→{o[3]})" for o in offers))
        except Exception as exc:  # monitor summary log best-effort — record
            record_failure("metacog.metacog_monitor.log", exc)


# ── Pattern detection ─────────────────────────────────────────────────────────



# ── Pattern → rule distillation (#9 Phase 2, gated) ──────────────────────────
#
# Recurring metacog patterns are candidate rules — but only once the system has a
# grounded rule base AND enough behavioral history that the patterns are real, not
# noise. Until then this stays dormant (Phase 1's confirmed-prediction rules come
# first). Maturity gate, mirroring human development: learn grounded regularities
# before generalizing about your own behavior.

_METACOG_RULE_CANDIDATES_FILE = None
_METACOG_PATTERN_RECUR = 3          # a pattern type must recur this often past the gate
_GATE_MIN_CONFIRMED_RULES = 5       # need a grounded rule base first
_GATE_MIN_CYCLES = 300              # need a stable run length first

# pattern label prefix → (condition token, corrective conclusion)
_PATTERN_RULES = {
    "Cognitive rut":               ("pattern:rut",
        "When stuck repeating one function, force a different action."),
    "Oscillation":                 ("pattern:oscillation",
        "When oscillating between two functions, break it by choosing a third."),
    "Goal avoidance":              ("pattern:goal_avoidance",
        "When avoiding action on a committed goal, suppress substitutes and pursue the goal."),
    "Affective stagnation":        ("pattern:affect_stagnation",
        "When one affect dominates for many cycles, deliberately shift attention to change it."),
    "Reflection–action imbalance": ("pattern:reflect_imbalance",
        "When over-reflecting without action, force an outward action."),
}


def _metacog_candidates_path():
    global _METACOG_RULE_CANDIDATES_FILE
    if _METACOG_RULE_CANDIDATES_FILE is None:
        from brain.paths import DATA_DIR
        _METACOG_RULE_CANDIDATES_FILE = DATA_DIR / "metacog_rule_candidates.json"
    return _METACOG_RULE_CANDIDATES_FILE


def _maturity_gate_open(context: Dict[str, Any]) -> bool:
    """True once the rule base is grounded AND the run is long enough."""
    cc = context.get("cycle_count") or 0
    cycle = int(cc.get("count", 0) if isinstance(cc, dict) else cc or 0)
    if cycle < _GATE_MIN_CYCLES:
        return False
    try:
        from brain.symbolic.rule_engine import get_all_rules
        n_confirmed = sum(
            1 for r in get_all_rules() if r.get("source") == "confirmed_prediction"
        )
        return n_confirmed >= _GATE_MIN_CONFIRMED_RULES
    except Exception as exc:  # rule base unavailable — record, gate stays closed
        record_failure("metacog._maturity_gate_open", exc)
        return False


def _distill_metacog_patterns(observations: List[str], context: Dict[str, Any]) -> None:
    """
    Track recurrence of metacog pattern TYPES; once the maturity gate is open and a
    type has recurred enough, distill it into a corrective symbolic rule.
    """
    if not observations or not _maturity_gate_open(context):
        return
    try:
        from brain.utils.json_utils import load_json, save_json
        cands = load_json(_metacog_candidates_path(), default_type=dict) or {}
        if not isinstance(cands, dict):
            cands = {}
        dirty = False
        for obs in observations:
            for prefix, (cond, conclusion) in _PATTERN_RULES.items():
                if obs.startswith(prefix):
                    rec = cands.get(prefix) or {"count": 0, "promoted": False}
                    rec["count"] = int(rec.get("count", 0)) + 1
                    if rec["count"] >= _METACOG_PATTERN_RECUR and not rec.get("promoted"):
                        try:
                            from brain.symbolic.rule_engine import add_rule
                            add_rule(
                                conditions=[cond],
                                conclusion=conclusion,
                                source="metacog",
                                confidence=0.6,
                            )
                            rec["promoted"] = True
                            log_private(
                                f"[metacog→rule] Distilled recurring '{prefix}' "
                                f"pattern into rule ({rec['count']} occurrences)."
                            )
                        except Exception as _e:
                            record_failure("metacog._distill_metacog_patterns", _e)
                    cands[prefix] = rec
                    dirty = True
                    break
        if dirty:
            save_json(_metacog_candidates_path(), cands)
    except Exception as _e:
        record_failure("metacog._distill_metacog_patterns.2", _e)


# ── Flush ─────────────────────────────────────────────────────────────────────

def metacog_flush(context: Dict[str, Any]) -> str:
    """
    Called at cycle end. Condenses the trace into a single introspection entry,
    runs pattern analysis, writes both to working memory, persists to METACOG_LOG.
    Returns the introspection string.
    """
    mc = context.get("metacog")
    if not isinstance(mc, dict):
        # The flush was registered as a callable cognitive function AND is run
        # at cycle end. When the LLM-selection picks `metacog_flush` mid-cycle,
        # it pops "metacog" from context. The end-of-cycle flush then arrives
        # with nothing to flush — that's expected, just no-op silently instead
        # of re-initialising a trace buffer that will never be filled.
        return ""

    entries = mc.get("entries", [])
    lines = [
        f"[{e.get('phase', '?')}] {e.get('note', '')}"
        for e in entries
        if isinstance(e, dict) and e.get("note")
    ]

    introspection = ("This cycle I: " + "; ".join(lines)) if lines else ""
    observations: List[str] = []

    try:
        from brain.cog_memory.working_memory import update_working_memory

        # Write the per-cycle trace (low importance — it's plumbing)
        if introspection:
            update_working_memory({
                "content": f"[metacog] {introspection}",
                "event_type": "metacog_trace",
                "importance": 1,
                "priority": 1,
            })

        # Run pattern analysis and write any observations (higher importance)
        observations = metacog_analyze(context)
        for obs in observations:
            update_working_memory({
                "content": f"[metacog/pattern] {obs}",
                "event_type": "metacog_pattern",
                "importance": 3,
                "priority": 3,
            })
            log_private(f"[metacog/pattern] {obs[:200]}")

        # Close the observation→behavior loop: translate patterns into concrete
        # context mutations so insight actually changes what runs next.
        # Carver & Scheier (1982): discrepancy → corrective output, not just belief.
        if observations:
            try:
                from brain.cognition.behavioral_adaptation import apply_behavioral_adaptations
                apply_behavioral_adaptations(context, observations)
            except Exception as _e:
                record_failure("metacog.metacog_flush", _e)

            # Convert observations into structured causal knowledge (Layer 3).
            # Stores the explanation, not just the label.
            # Mitchell et al. (1986) EBL; Tulving (1972) episodic→semantic.
            try:
                from brain.cognition.knowledge_formation import form_from_observations
                form_from_observations(observations, context)
            except Exception as _e:
                record_failure("metacog.metacog_flush.2", _e)

            # Distill recurring patterns into corrective rules (#9 Phase 2, gated).
            _distill_metacog_patterns(observations, context)

    except Exception as _e:
        record_failure("metacog.metacog_flush.3", _e)

    # Append to rolling metacog log
    try:
        from brain.utils.json_utils import load_json
        existing = load_json(METACOG_LOG, default_type=list) or []
        existing.append({
            "ts":       mc.get("cycle_start", ""),
            "trace":    introspection,
            "entries":  entries,
            "patterns": observations,
        })
        save_json(METACOG_LOG, existing[-200:])
    except Exception as _e:
        record_failure("metacog.metacog_flush.4", _e)

    if introspection:
        log_private(f"[metacog] {introspection[:200]}")

    context.pop("metacog", None)
    return introspection
