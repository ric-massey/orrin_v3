# brain/symbolic/embodied_actions.py
# Gentle embodiment — safe, read-only real-world actions that ground the
# symbolic layer in actual system state.
#
# Safety guarantees (hard constraints):
#   - No writes to any file outside DATA_DIR
#   - No network requests
#   - No subprocess spawning
#   - No eval / exec
#
# Action types:
#   "read_own_log"       — read recent activity log entries
#   "observe_data_dir"   — list files and sizes in DATA_DIR
#   "check_rule_health"  — count active / tombstoned rules right now
#   "read_working_memory"— sample recent WM entries
#   "check_time"         — current UTC time + elapsed since last dream
#   "read_predictions"   — check pending prediction count and oldest pending
#
# Each action produces an "observation" injected into WM and fed into the
# causal graph + ground truth, providing real grounding for symbolic rules.
#
# Entry point: run_embodied_cycle(context) — callable as a cognitive function.
from __future__ import annotations
from brain.core.runtime_log import get_logger

from datetime import datetime, timezone
from typing import Dict, List, Optional

from brain.utils.json_utils import load_json
from brain.utils.log import log_activity
from brain.paths import DATA_DIR, WORKING_MEMORY_FILE, PREDICTIONS_FILE
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

_SAFE_READ_ROOTS = {str(DATA_DIR)}   # only read from data dir and below
_MAX_ACTIONS_PER_CYCLE = 3


# ─── Entry point ──────────────────────────────────────────────────────────────

def run_embodied_cycle(context: Optional[Dict] = None) -> Dict:
    """
    Execute a small set of safe observational actions, feed results into WM
    and symbolic feedback systems. Called from ORRIN_loop or idle_consolidation_cycle.
    """
    ctx = context or {}
    actions = _select_actions(ctx)
    observations: List[Dict] = []

    for action_type in actions[:_MAX_ACTIONS_PER_CYCLE]:
        try:
            obs = _run_action(action_type, ctx)
            if obs:
                observations.append(obs)
                _ingest_observation(obs, ctx)
        except Exception as e:
            log_activity(f"[embodied] Action '{action_type}' failed: {e}")

    if observations:
        log_activity(f"[embodied] {len(observations)} observation(s) ingested.")

    return {"observations": len(observations), "actions_run": [o["action"] for o in observations]}


# ─── Action selection ─────────────────────────────────────────────────────────

def _select_actions(ctx: Dict) -> List[str]:
    """Pick actions based on what the system currently needs most."""
    actions = []

    # Always check rule health — low cost, high signal
    actions.append("check_rule_health")

    # If there are pending predictions, observe them
    actions.append("read_predictions")

    # Alternate between log and WM observation
    cycle = int(ctx.get("cycle_count", {}).get("count", 0)) if isinstance(
        ctx.get("cycle_count"), dict) else 0
    if cycle % 2 == 0:
        actions.append("read_own_log")
    else:
        actions.append("read_working_memory")

    return actions


# ─── Action implementations ───────────────────────────────────────────────────

def _run_action(action_type: str, ctx: Dict) -> Optional[Dict]:
    dispatch = {
        "read_own_log":        _act_read_log,
        "observe_data_dir":    _act_observe_data_dir,
        "check_rule_health":   _act_check_rule_health,
        "read_working_memory": _act_read_wm,
        "check_time":          _act_check_time,
        "read_predictions":    _act_read_predictions,
    }
    fn = dispatch.get(action_type)
    if not fn:
        return None
    result = fn(ctx)
    if result is None:
        return None
    return {
        "action":    action_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "result":    result,
    }


def _act_read_log(ctx: Dict) -> Optional[Dict]:
    log_file = DATA_DIR / "activity.log"
    if not log_file.exists():
        log_file = DATA_DIR.parent / "logs" / "activity.log"
    if not log_file.exists():
        return None
    try:
        lines = log_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        recent = [l.strip() for l in lines[-15:] if l.strip()]
        return {"recent_log_lines": len(recent), "sample": recent[-3:] if recent else []}
    except Exception as exc:  # log read failed — record, no observation
        record_failure("embodied_actions._act_read_log", exc)
        return None


def _act_observe_data_dir(ctx: Dict) -> Optional[Dict]:
    try:
        files = []
        for f in DATA_DIR.iterdir():
            if f.is_file():
                try:
                    files.append({"name": f.name, "size_kb": round(f.stat().st_size / 1024, 1)})
                except Exception as _e:
                    record_failure("embodied_actions._act_observe_data_dir", _e)
        files.sort(key=lambda x: x["size_kb"], reverse=True)
        return {"file_count": len(files), "largest": files[:5]}
    except Exception as exc:  # data-dir scan failed — record, no observation
        record_failure("embodied_actions._act_observe_data_dir.outer", exc)
        return None


def _act_check_rule_health(ctx: Dict) -> Optional[Dict]:
    try:
        from brain.symbolic.rule_engine import get_all_rules
        rules = get_all_rules()
        active     = [r for r in rules if r.get("source") != "tombstoned"]
        tombstoned = [r for r in rules if r.get("source") == "tombstoned"]
        zero_hit   = [r for r in active if r.get("hits", 0) == 0]
        mean_conf  = round(
            sum(r.get("confidence", 0.75) for r in active) / max(len(active), 1), 3
        )
        return {
            "active": len(active),
            "tombstoned": len(tombstoned),
            "zero_hit": len(zero_hit),
            "mean_confidence": mean_conf,
        }
    except Exception as exc:  # rule engine unavailable — record, no observation
        record_failure("embodied_actions._act_check_rule_health", exc)
        return None


def _act_read_wm(ctx: Dict) -> Optional[Dict]:
    try:
        wm = load_json(WORKING_MEMORY_FILE, default_type=list) or []
        recent = wm[-8:]
        event_types = [e.get("event_type", "unknown") for e in recent if isinstance(e, dict)]
        return {"wm_size": len(wm), "recent_event_types": event_types}
    except Exception as exc:  # working-memory read failed — record, no observation
        record_failure("embodied_actions._act_read_wm", exc)
        return None


def _act_check_time(ctx: Dict) -> Optional[Dict]:
    now_utc = datetime.now(timezone.utc)
    last_dream = ctx.get("_last_dream", {})
    last_ts    = last_dream.get("ts", "")
    hours_since_dream = None
    if last_ts:
        try:
            delta = now_utc.timestamp() - datetime.fromisoformat(last_ts).timestamp()
            hours_since_dream = round(delta / 3600, 1)
        except Exception as _e:
            record_failure("embodied_actions._act_check_time", _e)
    return {
        "utc_now": now_utc.isoformat(),
        "hour_of_day": now_utc.hour,
        "hours_since_dream": hours_since_dream,
    }


def _act_read_predictions(ctx: Dict) -> Optional[Dict]:
    try:
        preds = load_json(PREDICTIONS_FILE, default_type=list) or []
        pending   = [p for p in preds if p.get("status") == "pending"]
        resolved  = [p for p in preds if p.get("resolved")]
        correct   = [p for p in resolved if p.get("correct")]
        acc = round(len(correct) / max(len(resolved), 1), 3)
        oldest_pending = pending[0].get("created_ts", "") if pending else None
        return {
            "pending_count":  len(pending),
            "resolved_count": len(resolved),
            "accuracy":       acc,
            "oldest_pending": oldest_pending,
        }
    except Exception as exc:  # predictions read failed — record, no observation
        record_failure("embodied_actions._act_read_predictions", exc)
        return None


# ─── Observation ingestion ────────────────────────────────────────────────────

def _ingest_observation(obs: Dict, ctx: Dict) -> None:
    """Write observation to WM and feed symbolic feedback."""
    action = obs["action"]
    result = obs["result"] or {}

    # Build a summary sentence for WM
    summary = _summarise(action, result)
    if not summary:
        return

    try:
        from brain.cog_memory.working_memory import update_working_memory as _uwm
        _uwm({
            "content":    f"[embodied:{action}] {summary}",
            "event_type": "embodied_observation",
            "importance": 2,
            "priority":   2,
        })
    except Exception as _e:
        record_failure("embodied_actions._ingest_observation", _e)

    # Feed rule health into ground truth if rule check ran
    if action == "check_rule_health":
        _ground_rule_health(result)

    # Feed prediction accuracy into causal graph
    if action == "read_predictions" and result.get("resolved_count", 0) >= 5:
        _ground_prediction_accuracy(result)


def _summarise(action: str, result: Dict) -> str:
    if action == "check_rule_health":
        return (
            f"Rule health: {result.get('active')} active, "
            f"{result.get('tombstoned')} tombstoned, "
            f"mean_conf={result.get('mean_confidence')}, "
            f"{result.get('zero_hit')} unfired."
        )
    if action == "read_predictions":
        return (
            f"Predictions: {result.get('pending_count')} pending, "
            f"accuracy={result.get('accuracy'):.0%} over {result.get('resolved_count')} resolved."
        )
    if action == "read_working_memory":
        types = result.get("recent_event_types", [])
        return f"WM: {result.get('wm_size')} entries; recent types: {', '.join(types[:5])}."
    if action == "read_own_log":
        return f"Log: {result.get('recent_log_lines')} recent lines observed."
    if action == "check_time":
        h = result.get("hours_since_dream")
        return f"Time: {result.get('utc_now','?')[:16]} UTC; {h}h since last dream." if h else ""
    return ""


def _ground_rule_health(result: Dict) -> None:
    """If many rules are unfired, register it as low symbolic coverage evidence."""
    try:
        active   = int(result.get("active", 0))
        zero_hit = int(result.get("zero_hit", 0))
        if active < 1:
            return
        unfired_ratio = zero_hit / active
        # Treat high unfired ratio as counterfactual evidence for "rules are useful"
        from brain.symbolic.causal_graph import update_edge as _ue
        _ue(
            "symbolic_rules_present", "symbolic_coverage",
            confirmed=(unfired_ratio < 0.5),
            counterfactual=(unfired_ratio >= 0.5),
            source="embodied_observation",
        )
    except Exception as _e:
        record_failure("embodied_actions._ground_rule_health", _e)


def _ground_prediction_accuracy(result: Dict) -> None:
    try:
        acc = float(result.get("accuracy", 0.5))
        from brain.symbolic.causal_graph import update_edge as _ue
        _ue(
            "symbolic_prediction_active", "prediction_accuracy_high",
            confirmed=(acc >= 0.6),
            counterfactual=(acc < 0.4),
            source="embodied_observation",
        )
    except Exception as _e:
        record_failure("embodied_actions._ground_prediction_accuracy", _e)
