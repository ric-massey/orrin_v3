# brain/loop/production_telemetry.py
#
# F6 — durable production-loop telemetry (PRODUCTION_LOOP_CLOSURE), extracted
# from finalize.py. The goal-lens and production signals live only on the
# transient cycle context; a verdict on whether the comprehension→production
# loop closed has to be computable from a run ARCHIVE, not process memory (D7).
# finalize is the loop's post-cycle telemetry owner and calls
# emit_production_telemetry() once per cycle. Counts are process-cumulative
# (a run == a process life), so the last line gives run totals and any line
# gives that cycle's commitment/lens coverage. Not a competing goal summarizer —
# it only records signals other stages already computed.
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from brain.cognition.global_workspace import bound_goal
from brain.paths import DATA_DIR
from brain.utils.failure_counter import record_failure
from brain.utils.get_cycle_count import get_cycle_count
from brain.utils.json_utils import cap_jsonl

Context = Dict[str, Any]

PRODUCTION_LOOP_LOG = DATA_DIR / "production_loop.jsonl"
_handoff_total = 0
_attempt_total = 0
_success_total = 0
_bookkeeping_total = 0
_note_total = 0
_reuse_total = 0
_attempt_goals: set = set()

# B28 (Run 13): "production attempt" counted any cycle with any ledger row — 948
# self notes and 833 reuse rows included — so 1,275 attempts sat beside 164
# producer runs and the two could not be compared. An attempt is now a MAKING row
# (a file, a manuscript section, a symbolic artifact, a tool run); notes and reuse
# are counted on their own, and attempt goals are counted once per goal — the
# funnel's producer_ran unit.
_MAKING_KINDS = frozenset({"file_write", "tracked_work", "symbolic_artifact", "tool_run_effect"})
_NOTE_KINDS = frozenset({"note_novel", "message_answered", "satiety_learned_note"})


def _effect_rejection_reason(rows: List[Any]) -> Optional[str]:
    """Why this cycle's production effect earned nothing, read from the ledger rows
    (the effect ledger's own novelty/dedupe verdict). None when something qualified."""
    for r in rows:
        if not isinstance(r, dict):
            continue
        if float(r.get("significance") or 0.0) > 0.0:
            return None
        if r.get("dedupe"):
            return "duplicate"
        if float(r.get("novelty") or 0.0) <= 0.0:
            return "low_novelty_or_boilerplate"
        return "low_significance"
    return None


def emit_production_telemetry(context: Context) -> None:
    """Persist one durable, bounded production-loop record for this cycle (F6)."""
    global _handoff_total, _attempt_total, _success_total, _bookkeeping_total
    global _note_total, _reuse_total
    try:
        goal = bound_goal(context)
        goal = goal if isinstance(goal, dict) else {}
        gid = str(goal.get("id") or goal.get("title") or "") or None
        hydrated = bool(goal.get("grounded_parts") and goal.get("definition_of_done"))

        lens = context.get("_goal_lens_telemetry")
        lens = lens if isinstance(lens, dict) else {}
        # A2.3: a staged production handoff (make-shaped act dispatched with a
        # committed make-goal, set by step_execution) counts alongside the
        # older "needs deliberate action" marker. Popped — one handoff per stage.
        pending = (context.pop("pending_production_action", None)
                   or goal.get("_needs_deliberate_action") or None)

        # S7 lane bridge: the ledger drain sees every recorded effect from every
        # lane (conscious, symbolic engine, goals-daemon runner); the context
        # list only ever saw two conscious-lane writers. Merge both, dedupe by
        # content_hash (context rows are ledger rows too).
        rows = context.get("_effect_rows_this_cycle")
        rows = list(rows) if isinstance(rows, list) else []
        try:
            from brain.agency.effect_ledger import drain_recent_rows
            _seen_h = {r.get("content_hash") for r in rows if isinstance(r, dict)}
            for r in drain_recent_rows():
                if isinstance(r, dict) and r.get("content_hash") not in _seen_h:
                    rows.append(r)
        except Exception as _dre:
            record_failure("ORRIN_loop.production_telemetry.drain", _dre)
        # Fix 5 (RUN6_FIX_PLAN §3): self-model bookkeeping rows (causal-edge
        # establishments) are not production attempts — counted separately so
        # the funnel reads made things only (Run 5: they were 76 % of credits).
        n_book = sum(1 for r in rows if isinstance(r, dict) and r.get("kind") == "bookkeeping")
        rows = [r for r in rows if not (isinstance(r, dict) and r.get("kind") == "bookkeeping")]
        making = [r for r in rows if isinstance(r, dict) and r.get("kind") in _MAKING_KINDS]
        notes = [r for r in rows if isinstance(r, dict) and r.get("kind") in _NOTE_KINDS]
        reuse = [r for r in rows if isinstance(r, dict) and r.get("kind") == "reuse"]
        attempt = bool(making)
        for r in making:
            if r.get("goal_id"):
                _attempt_goals.add(str(r["goal_id"]))
        success = any(float(r.get("significance") or 0.0) > 0.0 for r in making)
        rejection = _effect_rejection_reason(making) if (attempt and not success) else None

        if pending:
            _handoff_total += 1
        if attempt:
            _attempt_total += 1
        if notes:
            _note_total += 1
        if reuse:
            _reuse_total += 1
        if success:
            _success_total += 1
        _bookkeeping_total += n_book

        record = {
            "cycle": int(get_cycle_count() or 0),
            "committed_goal_present": bool(goal),
            "committed_goal_id": gid,
            "goal_model_hydrated": hydrated,
            "goal_lens_active": bool(context.get("goal_lens")),
            "goal_lens_top_signal_relevance": round(float(lens.get("top_signal_relevance", 0.0) or 0.0), 3),
            "goal_lens_retrieval_mean_relevance": round(float(lens.get("retrieval_mean_relevance", 0.0) or 0.0), 3),
            "pending_production_action": pending,
            "production_attempt": attempt,
            "production_success": success,
            "effect_rejection": rejection,
            "production_handoff_count": _handoff_total,
            "production_attempt_count": _attempt_total,
            "production_attempt_goal_count": len(_attempt_goals),
            "note_cycle_count": _note_total,
            "reuse_cycle_count": _reuse_total,
            "production_success_count": _success_total,
            "bookkeeping_count": _bookkeeping_total,
        }
        PRODUCTION_LOOP_LOG.parent.mkdir(parents=True, exist_ok=True)
        with PRODUCTION_LOOP_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        cap_jsonl(PRODUCTION_LOOP_LOG, max_lines=20000)
    except Exception as _e:
        record_failure("ORRIN_loop.production_telemetry", _e)
