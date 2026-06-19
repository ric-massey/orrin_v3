# brain/cognition/planning/outcome_metrics.py
# Thin closure/lifecycle outcome accumulator (Phase E of the reconciled
# remediation plan). NOT a cognitive subsystem — pure bookkeeping, modeled on
# symbolic/progress_tracker.py.
#
# Records goal closure outcomes at EXISTING chokepoints only (no new hooks):
#   - mark_goal_completed   → record_completion(significance, seconds_to_complete)
#   - mark_goal_failed      → record_failure()
#   - prune_goals caller    → record_retired(n)            (B1 maintenance)
#   - satiety maintenance   → record_satiety_closure()     (B3 maintenance)
#   - fade_goals dormant    → record_abandonment_closure() (B2 maintenance)
#   - maintenance pass      → record_goal_population(active, avg_age_seconds)
#                             record_maintenance_execution(kind)
#
# Data persisted to data/outcome_metrics.json — rolling 90-day daily snapshots.
from __future__ import annotations
from core.runtime_log import get_logger

import statistics
import threading
from datetime import date
from typing import Any, Dict

from utils.json_utils import load_json, save_json
from utils.log import log_activity
from paths import DATA_DIR, DECISION_STATS_FILE
_log = get_logger(__name__)

OUTCOME_METRICS_FILE = DATA_DIR / "outcome_metrics.json"
_KEEP_DAYS = 90

_lock = threading.Lock()

# Function-name buckets used to read selection pressure off decision_stats.json.
_EXPLORATION_FUNCS = frozenset({
    "research_topic", "seek_novelty", "search_own_files", "generate_intrinsic_goals",
})
_CLOSURE_FUNCS = frozenset({
    "fade_goals", "prune_goals", "pause_goal", "is_sated", "record_lifetime_progress",
})


def _new_session() -> Dict[str, Any]:
    return {
        # Cumulative counters (summed on merge)
        "goals_completed":       0,
        "goals_failed":          0,
        "goals_retired":         0,
        "satiety_closures":      0,
        "abandonment_closures":  0,
        "maintenance_executions": 0,
        "store_desyncs_repaired": 0,
        # Lists for averaging
        "significances":         [],
        "seconds_to_complete":   [],
        # Point-in-time gauges (overwritten with latest)
        "active_goals":          0,
        "average_goal_age":      0.0,
        "date":                  str(date.today()),
    }


_session: Dict[str, Any] = _new_session()


def _today() -> str:
    return str(date.today())


def _reset_session_if_new_day() -> None:
    with _lock:
        if _session["date"] != _today():
            _session.clear()
            _session.update(_new_session())


# ─── Record individual events ─────────────────────────────────────────────────

def record_completion(*, significance: float = 0.0, seconds_to_complete: float | None = None) -> None:
    _reset_session_if_new_day()
    with _lock:
        _session["goals_completed"] += 1
        if significance:
            _session["significances"].append(float(significance))
        if seconds_to_complete and seconds_to_complete > 0:
            _session["seconds_to_complete"].append(float(seconds_to_complete))


def record_failure() -> None:
    _reset_session_if_new_day()
    with _lock:
        _session["goals_failed"] += 1


def record_retired(n: int = 1) -> None:
    _reset_session_if_new_day()
    with _lock:
        _session["goals_retired"] += int(n)


def record_satiety_closure(n: int = 1) -> None:
    _reset_session_if_new_day()
    with _lock:
        _session["satiety_closures"] += int(n)


def record_abandonment_closure(n: int = 1) -> None:
    _reset_session_if_new_day()
    with _lock:
        _session["abandonment_closures"] += int(n)


def record_maintenance_execution(n: int = 1) -> None:
    _reset_session_if_new_day()
    with _lock:
        _session["maintenance_executions"] += int(n)


def record_store_desync_repair(n: int = 1) -> None:
    """P6 — count goal-store desync repairs (resurrection / orphan-RUNNING /
    double-home drift) made by reconcile_goal_stores. A counter that stays >0 cycle
    after cycle means a real desync source remains and the v1↔v2 unification (§4c)
    is no longer deferrable."""
    _reset_session_if_new_day()
    with _lock:
        _session["store_desyncs_repaired"] += int(n)


def record_goal_population(active_goals: int, average_goal_age: float) -> None:
    _reset_session_if_new_day()
    with _lock:
        _session["active_goals"] = int(active_goals)
        _session["average_goal_age"] = round(float(average_goal_age), 1)


# ─── Snapshot computation ─────────────────────────────────────────────────────

def _selection_counts() -> Dict[str, int]:
    """Read cumulative exploration/closure selection counts off decision_stats.json."""
    try:
        stats = load_json(DECISION_STATS_FILE, default_type=dict) or {}
    except Exception:
        stats = {}
    expl = sum(int((stats.get(fn) or {}).get("count", 0)) for fn in _EXPLORATION_FUNCS)
    clos = sum(int((stats.get(fn) or {}).get("count", 0)) for fn in _CLOSURE_FUNCS)
    return {"exploration_selections": expl, "closure_selections": clos}


def _compute_snapshot() -> Dict:
    _reset_session_if_new_day()
    with _lock:
        completed   = _session["goals_completed"]
        failed      = _session["goals_failed"]
        retired     = _session["goals_retired"]
        satiety     = _session["satiety_closures"]
        abandonment = _session["abandonment_closures"]
        maint       = _session["maintenance_executions"]
        desyncs     = _session["store_desyncs_repaired"]
        sigs        = list(_session["significances"])
        secs        = list(_session["seconds_to_complete"])
        active      = _session["active_goals"]
        avg_age     = _session["average_goal_age"]

    mean_significance = round(sum(sigs) / len(sigs), 3) if sigs else 0.0
    median_seconds = round(statistics.median(secs), 1) if secs else 0.0

    total_closes = completed + failed + retired + satiety + abandonment
    completion_rate  = round(completed / total_closes, 3) if total_closes else 0.0
    abandonment_rate = round((abandonment + satiety) / total_closes, 3) if total_closes else 0.0
    closure_frequency = retired + satiety + abandonment

    snap = {
        "date":                       _today(),
        "active_goals":               active,
        "average_goal_age":           avg_age,
        "goals_completed":            completed,
        "goals_failed":               failed,
        "goals_retired":              retired,
        "satiety_closures":           satiety,
        "abandonment_closures":       abandonment,
        "maintenance_selections":     maint,
        "store_desyncs_repaired":     desyncs,
        "mean_significance":          mean_significance,
        "median_seconds_to_complete": median_seconds,
        "completion_rate":            completion_rate,
        "abandonment_rate":           abandonment_rate,
        "closure_frequency":          closure_frequency,
    }
    snap.update(_selection_counts())
    return snap


# ─── Persist / flush ──────────────────────────────────────────────────────────

def flush() -> Dict:
    """Write today's snapshot to disk, merging with any existing today-entry."""
    snap = _compute_snapshot()
    existing = load_json(OUTCOME_METRICS_FILE, default_type=list) or []
    if not isinstance(existing, list):
        existing = []

    today = _today()
    merged = False
    for i, entry in enumerate(existing):
        if entry.get("date") == today:
            existing[i] = _merge_entries(entry, snap)
            merged = True
            break
    if not merged:
        existing.append(snap)

    existing = existing[-_KEEP_DAYS:]
    save_json(OUTCOME_METRICS_FILE, existing)
    return snap


_SUMMED = (
    "goals_completed", "goals_failed", "goals_retired", "satiety_closures",
    "abandonment_closures", "maintenance_selections", "store_desyncs_repaired",
)
_LATEST = (
    "active_goals", "average_goal_age", "mean_significance",
    "median_seconds_to_complete", "exploration_selections", "closure_selections",
)


def _merge_entries(old: Dict, new: Dict) -> Dict:
    merged = dict(old)
    for key in _SUMMED:
        merged[key] = old.get(key, 0) + new.get(key, 0)
    for key in _LATEST:
        if key in new:
            merged[key] = new[key]
    total_closes = sum(merged.get(k, 0) for k in
                       ("goals_completed", "goals_failed", "goals_retired",
                        "satiety_closures", "abandonment_closures"))
    completed = merged.get("goals_completed", 0)
    merged["completion_rate"] = round(completed / total_closes, 3) if total_closes else 0.0
    merged["abandonment_rate"] = round(
        (merged.get("abandonment_closures", 0) + merged.get("satiety_closures", 0)) / total_closes, 3
    ) if total_closes else 0.0
    merged["closure_frequency"] = (
        merged.get("goals_retired", 0) + merged.get("satiety_closures", 0)
        + merged.get("abandonment_closures", 0)
    )
    return merged


# ─── Report ───────────────────────────────────────────────────────────────────

def report(days: int = 7) -> Dict:
    """Human-readable closure outcome report for the last N days. Flushes first."""
    flush()
    history = load_json(OUTCOME_METRICS_FILE, default_type=list) or []
    recent = history[-days:]
    if not recent:
        return {"summary": "No outcome metrics data yet.", "days": []}

    latest = recent[-1]
    total_completed = sum(d.get("goals_completed", 0) for d in recent)
    total_retired   = sum(d.get("goals_retired", 0) for d in recent)
    total_satiety   = sum(d.get("satiety_closures", 0) for d in recent)
    total_abandon   = sum(d.get("abandonment_closures", 0) for d in recent)

    summary = (
        f"{days}-day closure report | "
        f"active_goals={latest.get('active_goals', 0)} "
        f"(avg_age={latest.get('average_goal_age', 0.0):.0f}s) | "
        f"completed={total_completed} retired={total_retired} "
        f"satiety={total_satiety} abandoned={total_abandon} | "
        f"completion_rate={latest.get('completion_rate', 0.0):.1%} "
        f"abandonment_rate={latest.get('abandonment_rate', 0.0):.1%} | "
        f"exploration_sel={latest.get('exploration_selections', 0)} "
        f"closure_sel={latest.get('closure_selections', 0)} "
        f"maintenance_exec={sum(d.get('maintenance_selections', 0) for d in recent)}"
    )

    log_activity(f"[outcome_metrics] {summary}")
    return {"summary": summary, "days": recent}
