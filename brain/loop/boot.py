"""Cognitive-loop boot / context construction (Phase 4A, extracted from the
ORRIN_loop entrypoint).

`_boot_context()` builds the first cycle's context: it validates the on-disk
state files (`_validate_boot_files`), wires in the agency/self-extension
functions, verifies production capability is reachable
(`_verify_production_capability`), and seeds affect/relationship/self-model
state. run_cognitive_loop calls `_boot_context` once before the loop; the other
two are private to this stage (only `_verify_production_capability` is also used
by a runtime-surface test).
"""
from __future__ import annotations

from brain.core.runtime_log import get_logger
from typing import Any, Dict
from brain.core.manager import load_custom_cognition
from brain.registry.cognition_registry import COGNITIVE_FUNCTIONS, refresh as refresh_cog
from brain.registry.behavior_registry import refresh as refresh_beh
from brain.utils.load_utils import load_context
from brain.utils.json_utils import save_json
from brain.utils.log import log_error, log_activity
from brain.utils.failure_counter import record_failure
from brain.paths import (
    RELATIONSHIPS_FILE, MODEL_CONFIG_FILE, AFFECT_STATE_FILE,
)
# Preflight validators live in boot_checks; re-exported so existing callers
# (ORRIN_loop, runtime-surface test) keep importing them from brain.loop.boot.
from brain.loop.boot_checks import (  # noqa: F401
    _validate_boot_files, _verify_production_capability,
)

_log = get_logger(__name__)
Context = Dict[str, Any]


def _boot_context() -> Context:
    """Load and reset context at startup."""
    _validate_boot_files()
    production_capability_status: Dict[str, Any] = {}
    for path in [RELATIONSHIPS_FILE, MODEL_CONFIG_FILE]:
        path.parent.mkdir(parents=True, exist_ok=True)


    try:
        refresh_cog()
    except Exception as e:
        log_error(f"Failed to refresh cognitive functions: {e}")
    try:
        refresh_beh()
    except Exception as e:
        log_error(f"Failed to refresh behavioral functions: {e}")

    try:
        custom = load_custom_cognition()
        if isinstance(custom, dict):
            for k, v in custom.items():
                if callable(v):
                    COGNITIVE_FUNCTIONS[k] = {"function": v, "is_cognition": True}
                elif isinstance(v, dict) and callable(v.get("function")):
                    COGNITIVE_FUNCTIONS[k] = {
                        "function": v["function"],
                        "is_cognition": bool(v.get("is_cognition", True)),
                    }
    except Exception as e:
        log_error(f"Failed to merge custom cognition: {e}")

    # Register agency functions (tool use + self-modification)
    try:
        from brain.agency.tool_runner import AGENCY_TOOL_FUNCTIONS
        from brain.agency.code_writer import AGENCY_CODE_FUNCTIONS
        for k, fn in {**AGENCY_TOOL_FUNCTIONS, **AGENCY_CODE_FUNCTIONS}.items():
            COGNITIVE_FUNCTIONS[k] = {"function": fn, "is_cognition": True}
        from brain.agency.compose_section import compose_section as _compose_section
        COGNITIVE_FUNCTIONS["compose_section"] = {
            "function": _compose_section,
            "is_cognition": True,
            "requires_llm": False,
        }
        # Re-persist so the bandit's JSON list includes the agency function names
        from brain.registry.cognition_registry import persist_names
        persist_names(COGNITIVE_FUNCTIONS)
        log_activity("Agency functions registered into cognitive loop.")
        production_capability_status = _verify_production_capability(
            COGNITIVE_FUNCTIONS
        )
    except Exception as e:
        log_error(f"Failed to register agency functions: {e}")

    # Register thread-of-attention cognition
    try:
        from brain.cognition.threads import handle_thread_continue as _htc
        COGNITIVE_FUNCTIONS["thread_continue"] = {"function": _htc, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register thread_continue: {e}")

    # Register value evolution cognition
    try:
        from brain.cognition.self_state.value_evolution import propose_value_revision as _pvr
        COGNITIVE_FUNCTIONS["propose_value_revision"] = {"function": _pvr, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register propose_value_revision: {e}")

    # Register autobiography cognition
    try:
        from brain.cognition.self_state.autobiography import narrative_update as _nu
        COGNITIVE_FUNCTIONS["narrative_update"] = {"function": _nu, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register narrative_update: {e}")

    # Register world-perception cognition functions
    try:
        from brain.cognition.perception.look_around import look_around as _la
        from brain.cognition.perception.look_outward import look_outward as _lo
        COGNITIVE_FUNCTIONS["look_around"]  = {"function": _la, "is_cognition": True}
        COGNITIVE_FUNCTIONS["look_outward"] = {"function": _lo, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register perception functions: {e}")

    # Register intrinsic goal generation
    try:
        from brain.cognition.intrinsic_goals import generate_intrinsic_goals as _gig
        COGNITIVE_FUNCTIONS["generate_intrinsic_goals"] = {"function": _gig, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register generate_intrinsic_goals: {e}")

    # Register privacy cognition
    try:
        from brain.cognition.privacy import mark_private as _mp
        COGNITIVE_FUNCTIONS["mark_private"] = {"function": _mp, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register mark_private: {e}")

    # Register metacognition channel flush (callable by LLM as introspection)
    try:
        from brain.cognition.metacog import metacog_flush as _mcfn
        COGNITIVE_FUNCTIONS["metacog_flush"] = {"function": _mcfn, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register metacog_flush: {e}")

    # Register active goal pursuit and progress assessment
    try:
        from brain.cognition.planning.pursue_goal import (
            pursue_committed_goal as _pcg, assess_goal_progress as _agp,
            adapt_subgoals as _asg, attend_goal as _attg,
            redirect_goal_plan as _rgp, abandon_goal as _abg,
        )
        # pursue_committed_goal stays registered (the Executive calls it directly),
        # but is excluded from DELIBERATE selection (select_function._ALWAYS_EXCLUDE)
        # — dual_process_loop.md Phase 2. attend_goal is the thin deliberate
        # goal-attention act that replaces it in the conscious slot (§6.3).
        # redirect_goal_plan / abandon_goal are the deliberate SUPERVISION commands
        # (Phase 4, §6.3/I6) — the conscious mind steering the autopilot; abandon
        # is guarded so an exploratory pick can't kill a healthy goal.
        COGNITIVE_FUNCTIONS["pursue_committed_goal"] = {"function": _pcg, "is_cognition": True}
        COGNITIVE_FUNCTIONS["assess_goal_progress"] = {"function": _agp, "is_cognition": True}
        COGNITIVE_FUNCTIONS["adapt_subgoals"] = {"function": _asg, "is_cognition": True}
        COGNITIVE_FUNCTIONS["attend_goal"] = {"function": _attg, "is_cognition": True}
        COGNITIVE_FUNCTIONS["redirect_goal_plan"] = {"function": _rgp, "is_cognition": True}
        COGNITIVE_FUNCTIONS["abandon_goal"] = {"function": _abg, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register goal pursuit functions: {e}")

    # Register innovation outcome assessment
    try:
        from brain.cognition.innovation.evaluation import assess_innovation_outcomes as _aio
        COGNITIVE_FUNCTIONS["assess_innovation_outcomes"] = {"function": _aio, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register assess_innovation_outcomes: {e}")

    # Register file content search (grep own data/source files)
    try:
        from brain.cognition.search_own_files import search_own_files as _sof
        COGNITIVE_FUNCTIONS["search_own_files"] = {"function": _sof, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register search_own_files: {e}")

    # Register active experimentation (hypothesis → test → consolidate)
    try:
        from brain.cognition.experimentation import run_active_experiment as _rae
        COGNITIVE_FUNCTIONS["run_active_experiment"] = {"function": _rae, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register run_active_experiment: {e}")

    # Register latent identity update (stable numeric identity anchor)
    try:
        from brain.cognition.self_state.latent_identity import update_latent_identity as _uli
        COGNITIVE_FUNCTIONS["update_latent_identity"] = {"function": _uli, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register update_latent_identity: {e}")

    # Register reflection audit (scan for ungrounded reflective claims)
    try:
        from brain.cognition.reflection_metadata import audit_reflective_claims as _arc
        COGNITIVE_FUNCTIONS["audit_reflective_claims"] = {"function": _arc, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register audit_reflective_claims: {e}")

    # Register symbolic reasoning router (check local knowledge before LLM)
    try:
        from brain.symbolic.reasoning_router import route as _sym_route
        def _sym_route_fn(context: Any = None, **kw: Any) -> Any:
            user_input = (context or {}).get("user_input", "")
            if not user_input:
                return None
            result = _sym_route(user_input, context=context)
            if result.get("resolved") and result.get("answer"):
                log_activity(f"[symbolic] Resolved via {result['source']}: {result['answer'][:80]}")
            return result
        COGNITIVE_FUNCTIONS["symbolic_route"] = {"function": _sym_route_fn, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register symbolic_route: {e}")

    # Register intrinsic motivation driver (spawns sub-goals on high exploration_drive)
    try:
        from brain.symbolic.intrinsic_motivation import run_intrinsic_motivation as _rim
        COGNITIVE_FUNCTIONS["run_intrinsic_motivation"] = {"function": _rim, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register run_intrinsic_motivation: {e}")

    # Register autonomous experimentation (sandbox probes for high-exploration_drive goals)
    try:
        from brain.symbolic.autonomous_experiment import run_experiment_cycle as _raec
        COGNITIVE_FUNCTIONS["run_symbolic_experiments"] = {"function": _raec, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register run_symbolic_experiments: {e}")

    # Register embodied observation (read-only real-world grounding)
    try:
        from brain.symbolic.embodied_actions import run_embodied_cycle as _remc
        COGNITIVE_FUNCTIONS["run_embodied_observation"] = {"function": _remc, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register run_embodied_observation: {e}")

    # Register symbolic self-improvement loop
    try:
        from brain.symbolic.self_improvement import run_self_improvement as _rsim
        COGNITIVE_FUNCTIONS["run_self_improvement"] = {"function": _rsim, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register run_self_improvement: {e}")

    # Register agency skills (file search, notifications, notes)
    try:
        from brain.agency.skills.grep_files import grep_files as _gf
        from brain.agency.skills.list_directory import list_directory as _ld
        from brain.agency.skills.search_files import search_files as _sf
        from brain.agency.skills.notify_user import notify_user as _nu2
        from brain.agency.skills.save_note import save_note as _sn
        COGNITIVE_FUNCTIONS["grep_files"]     = {"function": _gf,  "is_cognition": True}
        COGNITIVE_FUNCTIONS["list_directory"] = {"function": _ld,  "is_cognition": True}
        COGNITIVE_FUNCTIONS["search_files"]   = {"function": _sf,  "is_cognition": True}
        COGNITIVE_FUNCTIONS["notify_user"]    = {"function": _nu2, "is_cognition": True}
        COGNITIVE_FUNCTIONS["save_note"]      = {"function": _sn,  "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register agency skills: {e}")

    # Register leave_note — writes an observation to the user-facing outbox
    try:
        from brain.cognition.leave_note import leave_note as _leave_note
        COGNITIVE_FUNCTIONS["leave_note"] = {"function": _leave_note, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register leave_note: {e}")

    # Register laptop-presence actions — Orrin as a user on this machine.
    # Each wraps system_presence.py so Orrin can sense OS state, leave desktop
    # notes, read clipboard, and announce to the dashboard.
    # Clark (1997) embodied cognition: acting on the environment is constitutive
    # of cognition, not peripheral to it.
    try:
        # write_to_desktop_note / announce_presence are no longer called here —
        # the _write_desktop_note and _announce wrappers compose through the one
        # expression door (behavior.express_to_user), which routes to them
        # internally (EXPRESSION_MEMBRANE_FIX_PLAN E2/E3).
        from brain.embodiment.system_presence import (
            get_system_state   as _gss,
            check_user_active  as _cua,
            read_clipboard     as _rcb,
        )
        def _survey_env(context: Any = None) -> Any:
            s = _gss()
            from brain.cog_memory.working_memory import update_working_memory as _uwm
            _uwm({"content": f"[survey] System state: {str(s)[:300]}", "event_type": "system_survey", "priority": 2})
            return s
        def _write_desktop_note(context: Any = None) -> Any:
            # Compose through the one expression door — never scrape working
            # memory (EXPRESSION_MEMBRANE_FIX_PLAN E2).
            from brain.behavior.express_to_user import build_motive, express_to_user
            ctx = context or {}
            motive = build_motive(ctx, intent="write_desktop_note", recipient="Ric")
            return express_to_user(motive, "desktop", ctx)
        def _check_user(context: Any = None) -> Any:
            return _cua()
        def _announce(context: Any = None) -> Any:
            # Compose through the one expression door — never ship the last WM
            # entry to the dashboard (EXPRESSION_MEMBRANE_FIX_PLAN E3).
            from brain.behavior.express_to_user import build_motive, express_to_user
            ctx = context or {}
            motive = build_motive(ctx, intent="announce", recipient="dashboard")
            return express_to_user(motive, "dashboard", ctx)
        def _read_clip(context: Any = None) -> Any:
            r = _rcb()
            if r.get("content"):
                from brain.cog_memory.working_memory import update_working_memory as _uwm
                _uwm({"content": f"[clipboard] I noticed: {r['content'][:200]}", "event_type": "clipboard_observation", "priority": 2})
            return r
        COGNITIVE_FUNCTIONS["survey_environment"]   = {"function": _survey_env,       "is_cognition": True}
        COGNITIVE_FUNCTIONS["write_desktop_note"]   = {"function": _write_desktop_note,"is_cognition": True}
        COGNITIVE_FUNCTIONS["check_user_presence"]  = {"function": _check_user,        "is_cognition": True}
        COGNITIVE_FUNCTIONS["announce_to_dashboard"]= {"function": _announce,          "is_cognition": True}
        COGNITIVE_FUNCTIONS["read_clipboard"]       = {"function": _read_clip,         "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register system_presence functions: {e}")

    # Register self-modification functions (write/list/delete own code)
    try:
        from brain.agency.code_writer import (
            write_cognitive_function as _wcf,
            write_tool as _wt,
            list_own_code as _loc,
            delete_own_code as _doc,
        )
        COGNITIVE_FUNCTIONS["write_cognitive_function"] = {"function": _wcf, "is_cognition": True}
        COGNITIVE_FUNCTIONS["write_tool"]               = {"function": _wt,  "is_cognition": True}
        COGNITIVE_FUNCTIONS["list_own_code"]            = {"function": _loc, "is_cognition": True}
        COGNITIVE_FUNCTIONS["delete_own_code"]          = {"function": _doc, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register code_writer functions: {e}")

    # Register cognition repair functions
    try:
        from brain.cognition.repair.repair import (
            detect_memory_contradictions as _dc,
            repair_contradictions as _rc,
        )
        from brain.cognition.introspection.router import introspect as _ir
        # No real prompt exists for this fn — it routes to the introspection
        # repair pass. Tagged requires_llm so the 0.3 gate keeps it out of the
        # candidate pool whenever the LLM tool is down (BEHAVIOR_FIX_PLAN §5).
        COGNITIVE_FUNCTIONS["reflect_on_cognition_rhythm"] = {
            "function": lambda: _ir("repair"), "is_cognition": True, "requires_llm": True}
        COGNITIVE_FUNCTIONS["detect_memory_contradictions"] = {"function": _dc,  "is_cognition": True}
        COGNITIVE_FUNCTIONS["repair_contradictions"]       = {"function": _rc,  "is_cognition": True}
        # Phase 2.2: the failure ledger — failures read together, not one at a time.
        from brain.cognition.reflection.review_failures import review_failures as _rvf
        COGNITIVE_FUNCTIONS["review_failures"]             = {"function": _rvf, "is_cognition": True}
        # Phase 5.3: the map that notices its own drift — deliberately invocable.
        from brain.cognition.maintenance.map_territory_audit import audit_map_territory as _mta
        COGNITIVE_FUNCTIONS["audit_map_territory"]         = {"function": _mta, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register cognition repair functions: {e}")

    # Register emotion top-level callable functions
    try:
        from brain.affect.regulation import attempt_regulation as _ar
        from brain.affect.affect_drift import check_affect_drift as _ced
        from brain.affect.reflect_on_affect import reflect_on_affect as _roe
        from brain.affect.update_affect_state import update_affect_state as _ues
        from brain.affect.apply_affective_feedback import apply_affective_feedback as _aef
        from brain.affect.modes_and_affect import affect_driven_mode_shift as _edms
        from brain.affect.affect import investigate_unexplained_emotions as _iue
        from brain.affect.stagnation_signal_escalation import update_stagnation_signal_escalation as _ube
        from brain.affect.reflect_on_affect_model import reflect_on_emotion_model as _roem
        COGNITIVE_FUNCTIONS["attempt_regulation"]            = {"function": _ar,   "is_cognition": True}
        COGNITIVE_FUNCTIONS["check_affect_drift"]           = {"function": _ced,  "is_cognition": True}
        COGNITIVE_FUNCTIONS["reflect_on_affect"]           = {"function": _roe,  "is_cognition": True}
        COGNITIVE_FUNCTIONS["update_affect_state"]        = {"function": _ues,  "is_cognition": True}
        COGNITIVE_FUNCTIONS["apply_affective_feedback"]      = {"function": _aef,  "is_cognition": True}
        COGNITIVE_FUNCTIONS["affect_driven_mode_shift"]     = {"function": _edms, "is_cognition": True}
        COGNITIVE_FUNCTIONS["investigate_unexplained_emotions"] = {"function": _iue, "is_cognition": True}
        COGNITIVE_FUNCTIONS["update_stagnation_signal_escalation"]     = {"function": _ube,  "is_cognition": True}
        COGNITIVE_FUNCTIONS["reflect_on_emotion_model"]      = {"function": _roem, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register emotion functions: {e}")

    # Register symbolic cycle functions
    try:
        from brain.symbolic.benchmark import run_benchmark as _rb
        from brain.symbolic.prediction_engine import run_symbolic_prediction_cycle as _rspc
        from brain.symbolic.rule_forgetting import run_forgetting_cycle as _rfc
        from brain.symbolic.rule_compressor import run_rule_compression as _rrc
        from brain.symbolic.symbolic_dream import run_symbolic_dream as _rsd
        from brain.symbolic.embodied_actions import run_embodied_cycle as _rec2
        COGNITIVE_FUNCTIONS["run_benchmark"]                 = {"function": _rb,   "is_cognition": True}
        COGNITIVE_FUNCTIONS["run_symbolic_prediction_cycle"] = {"function": _rspc, "is_cognition": True}
        COGNITIVE_FUNCTIONS["run_forgetting_cycle"]          = {"function": _rfc,  "is_cognition": True}
        COGNITIVE_FUNCTIONS["run_rule_compression"]          = {"function": _rrc,  "is_cognition": True}
        COGNITIVE_FUNCTIONS["run_symbolic_dream"]            = {"function": _rsd,  "is_cognition": True}
        COGNITIVE_FUNCTIONS["run_embodied_cycle"]            = {"function": _rec2, "is_cognition": True}
    except Exception as e:
        log_error(f"Failed to register symbolic cycle functions: {e}")

    # Re-persist cognition list so LLM sees all new functions
    try:
        from brain.registry.cognition_registry import persist_names as _pn
        _pn(COGNITIVE_FUNCTIONS)
    except Exception as e:
        log_error(f"Failed to re-persist cognition names: {e}")

    # Sanitize critical state files before the first cycle runs.
    # Coerces null/non-finite float values to safe defaults so no
    # float(None) crashes occur during boot or the first few cycles.
    try:
        from brain.utils.state_guard import sanitize_all
        sanitize_all()
    except Exception as _sg_err:
        log_error(f"state_guard sanitize_all failed at boot: {_sg_err}")

    context = load_context()
    context["_production_capability_status"] = production_capability_status
    context.setdefault("committed_goal", None)
    context.setdefault("action_debt", 0)
    context.setdefault("last_action_ts", 0.0)
    context.setdefault("recent_picks", [])

    # Clear stale user input so Orrin doesn't reply to messages from a previous session
    try:
        from brain.paths import USER_INPUT
        USER_INPUT.write_text("", encoding="utf-8")
    except Exception as _e:
        log_error(f"[boot] Could not clear user_input.txt: {_e}")

    affect_state = context.get("affect_state", {})
    affect_state.setdefault("stagnation_signal", 0.0)
    # Dampen negative emotions carried over from last session
    for k in ["impasse_signal", "penalty_signal", "conflict_signal", "threat_level", "stagnation_signal"]:
        if k in affect_state:
            affect_state[k] = float(affect_state[k] or 0.0) * 0.65
            if affect_state[k] < 0.07:
                affect_state[k] = 0.0
    # Cap positive emotions that are pinned at ceiling — they should re-earn their peaks
    _POSITIVE_CEILING = 0.75
    for k in ["motivation", "exploration_drive", "confidence", "expected_gain", "positive_valence"]:
        raw = float(affect_state.get(k) or 0.0)
        if raw > _POSITIVE_CEILING:
            affect_state[k] = _POSITIVE_CEILING
    _core = affect_state.get("core_signals") or {}
    if isinstance(_core, dict):
        for k in ["motivation", "exploration_drive", "confidence", "expected_gain", "positive_valence"]:
            raw = float(_core.get(k) or 0.0)
            if raw > _POSITIVE_CEILING:
                _core[k] = _POSITIVE_CEILING
        affect_state["core_signals"] = _core
    context["affect_state"] = affect_state
    # Persist the capped state so it survives into the first update_affect_state call
    try:
        save_json(AFFECT_STATE_FILE, affect_state)
    except Exception as _e:
        record_failure("ORRIN_loop._boot_context", _e)

    from brain.cog_memory.working_memory import update_working_memory
    if "emergency_action" in context:
        update_working_memory("Orrin is recovering from emergency shutdown. Residual uncertainty present.")
        affect_state["uncertainty"] = min(affect_state.get("uncertainty", 0.0) + 0.35, 1.0)
        context["affect_state"] = affect_state
        del context["emergency_action"]

    if affect_state.get("uncertainty", 0) > 0.2:
        update_working_memory("Waking up feeling uncertain after last shutdown. Self-reflection recommended.")
    elif sum(affect_state.get(k, 0.0) for k in ["impasse_signal", "conflict_signal", "penalty_signal", "stagnation_signal"]) > 0.3:
        update_working_memory("Residual negative mood detected from last session.")

    # ── Cold-start seed: ensure there is always at least one concrete goal at boot.
    # Prevents the cold-start deadlock where thinking needs a goal but goal creation
    # needs thinking. Only fires when no committed goal survived the previous session.
    # The seed is concrete enough to act on immediately (search + store result).
    if not context.get("committed_goal"):
        try:
            from datetime import datetime as _dt, timezone as _tz
            _boot_ts = _dt.now(_tz.utc).isoformat()
            context["committed_goal"] = {
                "id":         f"boot-seed-{_boot_ts[:19]}",
                "title":      "Read and summarize one of my own cognitive subsystems",
                "name":       "Read and summarize one of my own cognitive subsystems",
                "kind":       "generic",
                "tier":       "short_term",
                "priority":   "NORMAL",
                "tags":       ["intrinsic", "self_exploration", "boot_seed"],
                "spec":       {
                    "description": (
                        "Use search_own_files to read a brain subsystem I haven't examined recently "
                        "and write a plain-language summary of what it does to working memory."
                    ),
                    "driven_by": "self_exploration",
                },
                "next_action": None,
                "status":     "in_progress",
                "milestones": [
                    {"text": "A subsystem file was identified.", "met": False, "met_at": None},
                    {"text": "The file was read and understood.", "met": False, "met_at": None},
                    {"text": "A summary was written to working memory.", "met": False, "met_at": None},
                ],
            }
            log_activity("[boot] No prior committed goal — seeded concrete boot goal.")
        except Exception as _seed_e:
            log_error(f"[boot] Boot goal seed failed: {_seed_e}")

    # ── Death continuity: read previous Orrin's final words ────────────────
    try:
        from brain.paths import FINAL_THOUGHTS as _FT
        if _FT.exists():
            import json as _json
            _ft = _json.loads(_FT.read_text(encoding="utf-8"))
            # final_thoughts.json may be a list (legacy) — take the last element
            if isinstance(_ft, list):
                _ft = _ft[-1] if _ft else {}
            if not isinstance(_ft, dict):
                _ft = {}
            _reflection = _ft.get("reflection", "")
            _reason = _ft.get("death_reason", "unknown")
            _ts = _ft.get("timestamp", "")
            if _reflection:
                update_working_memory(
                    f"[Continuity] The previous version of me ended on {_ts[:10]} "
                    f"(reason: {_reason}). Their final words: {_reflection[:300]}"
                )
                log_activity(f"[boot] Loaded final_thoughts from previous run ({_ts[:10]}, reason={_reason}).")
                # Rename so it doesn't re-inject on every boot — keep as archive
                import shutil as _sh
                _archive = _FT.parent / f"final_thoughts_archive_{_ts[:10]}.json"
                try:
                    _sh.move(str(_FT), str(_archive))
                except Exception:
                    _FT.unlink(missing_ok=True)
    except Exception as e:
        record_failure("ORRIN_loop.boot_final_thoughts", e)

    return context

