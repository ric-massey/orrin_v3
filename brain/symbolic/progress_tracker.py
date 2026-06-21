# brain/symbolic/progress_tracker.py
# Symbolic intelligence growth chart.
#
# Tracks, persists, and reports how the symbolic reasoning layer is growing
# over time.  Data is written to data/symbolic_progress.json — a time-series
# of daily snapshots.
#
# Metrics tracked per day:
#   symbolic_hits      — queries answered without LLM
#   llm_calls          — queries that needed LLM
#   symbolic_ratio     — symbolic_hits / total  (0–1)
#   rules_total        — total rules in symbolic_rules.json
#   rules_added_today  — new rules crystallized today
#   meta_rule_applications — how many times meta-rules fired
#   conflicts_detected — rule conflicts that fell through to LLM
#   avg_rule_depth     — average BFS depth to answer a query (proxy: conditions per winning rule)
#   exploration_drive_mean     — mean exploration_drive score across all routed queries
#   sub_goals_spawned  — investigation goals spawned by intrinsic motivation
#
# Rolling window: keeps 90 days of daily snapshots.
# Session metrics are accumulated in memory and flushed to disk on report().
from __future__ import annotations
from brain.core.runtime_log import get_logger

import threading
from datetime import date
from typing import Any, Dict

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_activity
from brain.paths import DATA_DIR
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

PROGRESS_FILE = DATA_DIR / "symbolic_progress.json"
_KEEP_DAYS = 90

_lock = threading.Lock()

# ─── In-session accumulators ──────────────────────────────────────────────────
_session: Dict[str, Any] = {
    "symbolic_hits":           0,
    "llm_calls":               0,
    "conflicts_detected":      0,
    "meta_rule_applications":  0,
    "sub_goals_spawned":       0,
    "experiments_run":         0,
    "experiments_succeeded":   0,
    "rules_forgotten":         0,   # decayed + pruned + retired this session
    "exploration_drive_scores":        [],   # list of floats for mean computation
    "rule_depths":             [],   # conditions count of winning rules
    "date":                    str(date.today()),
}


def _today() -> str:
    return str(date.today())


def _reset_session_if_new_day() -> None:
    with _lock:
        if _session["date"] != _today():
            _session.update({
                "symbolic_hits": 0, "llm_calls": 0,
                "conflicts_detected": 0, "meta_rule_applications": 0,
                "sub_goals_spawned": 0,
                "experiments_run": 0, "experiments_succeeded": 0,
                "rules_forgotten": 0,
                "exploration_drive_scores": [], "rule_depths": [],
                "date": _today(),
            })


# ─── Record individual events ─────────────────────────────────────────────────

def record_symbolic_hit(*, rule_depth: int = 0, exploration_drive: float = 0.0) -> None:
    _reset_session_if_new_day()
    with _lock:
        _session["symbolic_hits"] += 1
        if exploration_drive:
            _session["exploration_drive_scores"].append(exploration_drive)
        if rule_depth:
            _session["rule_depths"].append(rule_depth)


def record_llm_call(*, exploration_drive: float = 0.0) -> None:
    _reset_session_if_new_day()
    with _lock:
        _session["llm_calls"] += 1
        if exploration_drive:
            _session["exploration_drive_scores"].append(exploration_drive)


def record_conflict() -> None:
    _reset_session_if_new_day()
    with _lock:
        _session["conflicts_detected"] += 1


def record_meta_rule_application() -> None:
    _reset_session_if_new_day()
    with _lock:
        _session["meta_rule_applications"] += 1


def record_sub_goal_spawned() -> None:
    _reset_session_if_new_day()
    with _lock:
        _session["sub_goals_spawned"] += 1


def record_experiment(*, success: bool = False, domain: str = "") -> None:
    _reset_session_if_new_day()
    with _lock:
        _session["experiments_run"] += 1
        if success:
            _session["experiments_succeeded"] += 1


def record_forgetting(*, decayed: int = 0, pruned: int = 0, retired: int = 0) -> None:
    _reset_session_if_new_day()
    with _lock:
        _session["rules_forgotten"] += decayed + pruned + retired


# ─── Snapshot computation ─────────────────────────────────────────────────────

def _compute_snapshot() -> Dict:
    _reset_session_if_new_day()
    with _lock:
        hits = _session["symbolic_hits"]
        llm  = _session["llm_calls"]
        total = hits + llm
        ratio = round(hits / total, 3) if total else 0.0

        exploration_drive_scores    = _session["exploration_drive_scores"]
        rule_depths         = _session["rule_depths"]
        experiments_run     = _session["experiments_run"]
        experiments_ok      = _session["experiments_succeeded"]
        rules_forgotten     = _session["rules_forgotten"]

    # Rule set stats (read from disk)
    try:
        from brain.symbolic.rule_engine import get_all_rules
        rules = get_all_rules()
        rules_total = len(rules)
        # Rules added today
        today_iso = _today()
        rules_today = sum(
            1 for r in rules
            if r.get("created_at", "")[:10] == today_iso
        )
        # Average conditions per rule (proxy for rule depth)
        avg_conditions = (
            round(sum(len(r.get("conditions") or []) for r in rules) / len(rules), 2)
            if rules else 0.0
        )
    except Exception:
        rules_total, rules_today, avg_conditions = 0, 0, 0.0

    # Crystallized skills today
    try:
        cryst = load_json(DATA_DIR / "crystallized_skills.json", default_type=list) or []
        cryst_today = sum(
            1 for c in cryst
            if (c.get("timestamp") or "")[:10] == _today()
        )
    except Exception:
        cryst_today = 0

    # Meta-rule stats
    try:
        from brain.symbolic.meta_rules import get_meta_rule_stats
        meta_stats = get_meta_rule_stats()
        meta_apps_total = sum(m["applications"] for m in meta_stats)
        top_meta = max(meta_stats, key=lambda m: m["applications"], default={})
    except Exception:
        meta_apps_total = 0
        top_meta = {}

    # ── Long-term growth metrics ──────────────────────────────────────────────

    # Avg concept depth: mean number of active rules per concept
    avg_concept_depth = 0.0
    try:
        from brain.symbolic.concept_formation import get_concepts as _gac
        concepts = _gac() or []
        if concepts:
            from brain.symbolic.rule_engine import get_all_rules as _gar
            active_rules = _gar()
            depth_vals = []
            for c in concepts:
                cname = (c.get("name") or "").lower()
                support = sum(
                    1 for r in active_rules
                    if r.get("source") != "tombstoned"
                    and cname in str(r.get("conditions", "")).lower()
                )
                depth_vals.append(support)
            avg_concept_depth = round(sum(depth_vals) / len(depth_vals), 2) if depth_vals else 0.0
    except Exception as _e:
        record_failure("progress_tracker._compute_snapshot", _e)

    # Causal graph density: edges / unique nodes
    causal_density = 0.0
    try:
        from brain.symbolic.causal_graph import get_all_edges as _gae
        edges = _gae()
        if edges:
            nodes: set = set()
            for e in edges:
                nodes.add(e.get("cause", ""))
                nodes.add(e.get("effect", ""))
            causal_density = round(len(edges) / max(len(nodes), 1), 3)
    except Exception as _e:
        record_failure("progress_tracker._compute_snapshot.2", _e)

    # Autonomous goal completion rate (completed goals / total spawned goals)
    goal_completion_rate = 0.0
    try:
        goal_file = DATA_DIR / "goals.json"
        goals = load_json(goal_file, default_type=list) or []
        intrinsic = [g for g in goals if g.get("source") in ("intrinsic_motivation", "domain_error_intrinsic")]
        completed = [g for g in intrinsic if g.get("status") == "completed"]
        if intrinsic:
            goal_completion_rate = round(len(completed) / len(intrinsic), 3)
    except Exception as _e:
        record_failure("progress_tracker._compute_snapshot.3", _e)

    # Experiment success rate (from log)
    experiment_success_rate = 0.0
    try:
        from brain.symbolic.autonomous_experiment import get_experiment_stats as _ges
        _estats = _ges(days=7)
        experiment_success_rate = _estats.get("success_rate", 0.0)
    except Exception as _e:
        record_failure("progress_tracker._compute_snapshot.4", _e)

    # Forgetting rate: rules retired/decayed in last 7 days
    forgetting_rate_7d = 0
    try:
        from brain.symbolic.rule_forgetting import get_forgetting_stats as _gfs
        _fstats = _gfs(days=7)
        forgetting_rate_7d = _fstats.get("total_decayed", 0) + _fstats.get("total_pruned", 0)
    except Exception as _e:
        record_failure("progress_tracker._compute_snapshot.5", _e)

    return {
        "date":                       _today(),
        "symbolic_hits":              hits,
        "llm_calls":                  llm,
        "total_queries":              total,
        "symbolic_ratio":             ratio,
        "rules_total":                rules_total,
        "rules_added_today":          rules_today,
        "rules_forgotten_today":      rules_forgotten,
        "crystallized_today":         cryst_today,
        "avg_rule_conditions":        avg_conditions,
        "conflicts_detected":         _session["conflicts_detected"],
        "meta_rule_applications":     _session["meta_rule_applications"],
        "meta_rule_applications_total": meta_apps_total,
        "top_meta_rule":              top_meta.get("name", ""),
        "sub_goals_spawned":          _session["sub_goals_spawned"],
        "experiments_run":            experiments_run,
        "experiments_succeeded":      experiments_ok,
        "exploration_drive_mean":             round(
            sum(exploration_drive_scores) / len(exploration_drive_scores), 3
        ) if exploration_drive_scores else 0.0,
        "avg_rule_depth":             round(
            sum(rule_depths) / len(rule_depths), 2
        ) if rule_depths else 0.0,
        # Long-term growth metrics
        "avg_concept_depth":          avg_concept_depth,
        "causal_graph_density":       causal_density,
        "goal_completion_rate":       goal_completion_rate,
        "experiment_success_rate":    experiment_success_rate,
        "forgetting_rate_7d":         forgetting_rate_7d,
    }


# ─── Persist / flush ──────────────────────────────────────────────────────────

def flush() -> Dict:
    """
    Write today's snapshot to disk.  Called at session end or periodically.
    Merges with any existing today-entry (session may have been restarted).
    """
    snap = _compute_snapshot()
    existing = load_json(PROGRESS_FILE, default_type=list) or []

    today = _today()
    merged = False
    for i, entry in enumerate(existing):
        if entry.get("date") == today:
            # Merge: sum counters, take latest ratios/averages
            existing[i] = _merge_entries(entry, snap)
            merged = True
            break
    if not merged:
        existing.append(snap)

    # Keep rolling window
    existing = existing[-_KEEP_DAYS:]
    save_json(PROGRESS_FILE, existing)
    return snap


def _merge_entries(old: Dict, new: Dict) -> Dict:
    merged = dict(old)
    for key in ("symbolic_hits", "llm_calls", "total_queries", "conflicts_detected",
                "meta_rule_applications", "sub_goals_spawned", "crystallized_today",
                "experiments_run", "experiments_succeeded", "rules_forgotten_today"):
        merged[key] = old.get(key, 0) + new.get(key, 0)
    total = merged["symbolic_hits"] + merged["llm_calls"]
    merged["symbolic_ratio"] = round(merged["symbolic_hits"] / total, 3) if total else 0.0
    # Overwrite with latest measured values (point-in-time metrics)
    for key in ("rules_total", "rules_added_today", "avg_rule_conditions",
                "exploration_drive_mean", "avg_rule_depth", "top_meta_rule",
                "meta_rule_applications_total", "avg_concept_depth",
                "causal_graph_density", "goal_completion_rate",
                "experiment_success_rate", "forgetting_rate_7d"):
        if key in new:
            merged[key] = new[key]
    return merged


# ─── Report ───────────────────────────────────────────────────────────────────

def report(days: int = 7) -> Dict:
    """
    Return a human-readable growth report for the last N days.
    Flushes current session data first.
    """
    flush()
    history = load_json(PROGRESS_FILE, default_type=list) or []
    recent = history[-days:]

    if not recent:
        return {"summary": "No symbolic progress data yet.", "days": []}

    total_sym = sum(d.get("symbolic_hits", 0) for d in recent)
    total_llm = sum(d.get("llm_calls", 0) for d in recent)
    total_q   = total_sym + total_llm
    overall_ratio = round(total_sym / total_q, 3) if total_q else 0.0

    rules_start = recent[0].get("rules_total", 0)
    rules_end   = recent[-1].get("rules_total", 0)
    rules_growth = rules_end - rules_start

    latest = recent[-1]
    total_experiments = sum(d.get("experiments_run", 0) for d in recent)
    total_exp_ok      = sum(d.get("experiments_succeeded", 0) for d in recent)
    exp_rate = round(total_exp_ok / total_experiments, 2) if total_experiments else 0.0

    # Benchmark trend
    bm_str = ""
    try:
        from brain.symbolic.benchmark import get_benchmark_trend as _gbt
        _bt = _gbt(days=days)
        bm_str = f" | Benchmark: {_bt.get('latest', 0):.2f} ({_bt.get('trend','?')})"
    except Exception as _e:
        record_failure("progress_tracker.report", _e)

    # Intuition stats
    pattern_stats_str = ""
    try:
        from brain.symbolic.pattern_scorer import get_pattern_stats as _gis
        _is = _gis()
        pattern_stats_str = (
            f" | Intuition: {_is['total_pattern_tokens']} tokens "
            f"across {len(_is['pattern_domains'])} domains, "
            f"{len(_is['grounded_domains'])} grounded"
        )
    except Exception as _e:
        record_failure("progress_tracker.report.2", _e)

    summary = (
        f"{days}-day symbolic intelligence report | "
        f"{total_sym}/{total_q} queries resolved symbolically ({overall_ratio:.1%}) | "
        f"Rules: {rules_start}→{rules_end} (+{rules_growth}) | "
        f"Forgotten: {sum(d.get('rules_forgotten_today',0) for d in recent)} | "
        f"Concept depth: {latest.get('avg_concept_depth', 0):.2f} | "
        f"Causal density: {latest.get('causal_graph_density', 0):.3f} | "
        f"Goal completion: {latest.get('goal_completion_rate', 0):.1%} | "
        f"Experiments: {total_experiments} ({exp_rate:.0%} success) | "
        f"Sub-goals: {sum(d.get('sub_goals_spawned',0) for d in recent)} | "
        f"Conflicts: {sum(d.get('conflicts_detected',0) for d in recent)}"
        f"{bm_str}{pattern_stats_str}"
    )

    log_activity(f"[progress] {summary}")
    return {"summary": summary, "days": recent, "overall_ratio": overall_ratio}
