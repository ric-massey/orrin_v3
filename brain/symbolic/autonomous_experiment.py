# brain/symbolic/autonomous_experiment.py
# High-exploration_drive sub-goals trigger safe sandbox experiments.
#
# An experiment is a read-only symbolic probe — no external calls, no
# writes to anything except the experiment log and the feedback files
# (causal_graph, ground_truth).
#
# Lifecycle:
#   1. design_experiment(goal)          → experiment dict
#   2. run_sandbox_experiment(exp)      → result dict
#   3. record_experiment_result(e, r)   → feeds causal_graph + ground_truth
#   4. run_experiment_cycle(context)    → batch entry point for ORRIN_loop
#
# Experiments target goals from context["proposed_goals"] or the goal file
# whose source is "intrinsic_motivation" or "domain_error_intrinsic".
# Only goals with exploration_drive_score ≥ 0.60 or error_rate ≥ 0.65 qualify.
#
# Safe probe types:
#   "rule_coverage"   — does the rule base cover the goal's query space?
#   "analogy_match"   — does any past analogue illuminate the goal?
#   "causal_probe"    — does the causal graph explain the goal's domain?
#   "prediction_test" — run symbolic predictions; check internal consistency
from __future__ import annotations
from core.runtime_log import get_logger

import hashlib
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from utils.json_utils import load_json, save_json
from utils.log import log_activity
from brain.paths import DATA_DIR
from utils.failure_counter import record_failure
_log = get_logger(__name__)

EXPERIMENT_LOG   = DATA_DIR / "experiments.json"
_MAX_EXPERIMENTS = 200
_MIN_EXPLORATION_DRIVE   = 0.60   # minimum score to warrant an experiment
_PROBE_QUERIES   = 5      # test queries generated per experiment


# ─── Public API ───────────────────────────────────────────────────────────────

def run_experiment_cycle(context: Optional[Dict] = None) -> Dict:
    """
    Main entry point — called from ORRIN_loop as a registered cognitive function.
    Picks pending high-exploration_drive goals, designs and runs one experiment each.
    """
    ctx = context or {}
    goals = _collect_experiment_goals(ctx)
    if not goals:
        return {"experiments_run": 0, "goals_checked": 0}

    run_count = 0
    for goal in goals[:3]:  # cap: 3 experiments per cycle
        try:
            exp    = design_experiment(goal)
            result = run_sandbox_experiment(exp)
            record_experiment_result(exp, result)
            run_count += 1
            log_activity(
                f"[experiment] Ran '{exp['probe_type']}' for goal "
                f"'{goal.get('title','?')[:50]}': "
                f"hits={result.get('symbolic_hits',0)} "
                f"rules_fired={len(result.get('rules_fired',[]))}"
            )
        except Exception as ex:
            log_activity(f"[experiment] Experiment failed: {ex}")

    return {"experiments_run": run_count, "goals_checked": len(goals)}


def design_experiment(goal: Dict) -> Dict:
    """
    Build an experiment spec from a goal dict.
    Generates test queries and selects a probe type.
    """
    title       = goal.get("title", "")
    description = goal.get("description", "")
    domain      = goal.get("domain", "")
    exploration_drive   = float(goal.get("exploration_drive_score") or goal.get("error_rate", 0.5))
    source      = goal.get("source", "")

    # Probe type selection
    if source == "domain_error_intrinsic" or domain:
        probe_type = "prediction_test"
    elif exploration_drive >= 0.85:
        probe_type = "causal_probe"
    elif exploration_drive >= 0.70:
        probe_type = "analogy_match"
    else:
        probe_type = "rule_coverage"

    # Generate test queries from goal content
    test_queries = _generate_test_queries(title, description, domain, _PROBE_QUERIES)

    exp_id = hashlib.md5(
        f"{title}{time.time()}".encode()
    ).hexdigest()[:10]

    return {
        "id":          exp_id,
        "goal_title":  title[:80],
        "domain":      domain,
        "probe_type":  probe_type,
        "exploration_drive":   exploration_drive,
        "test_queries": test_queries,
        "hypothesis":  _hypothesis_for(probe_type, title, domain),
        "created_at":  datetime.now(timezone.utc).isoformat(),
        "status":      "pending",
    }


def run_sandbox_experiment(experiment: Dict) -> Dict:
    """
    Execute the experiment by routing each test query through the symbolic layer.
    Returns a result dict without making any external API calls.
    """
    queries      = experiment.get("test_queries", [])
    probe_type   = experiment.get("probe_type", "rule_coverage")
    domain       = experiment.get("domain", "")

    symbolic_hits = 0
    rules_fired: List[str] = []
    analogy_matches: List[str] = []
    causal_edges_found: List[str] = []
    evidence: List[Dict] = []

    for q in queries:
        try:
            from symbolic.reasoning_router import route as _route
            r = _route(q, context={})
            source = r.get("source", "llm_needed")
            if r.get("resolved") and source not in ("llm_needed", "suppressed"):
                symbolic_hits += 1
                if r.get("rule_id"):
                    rules_fired.append(r["rule_id"])
                evidence.append({
                    "query":  q[:80],
                    "source": source,
                    "answer": (r.get("answer") or "")[:120],
                })
        except Exception as _e:
            record_failure("autonomous_experiment.run_sandbox_experiment", _e)

    if probe_type in ("analogy_match", "causal_probe"):
        for q in queries[:3]:
            try:
                from symbolic.analogy_engine import find_analogues
                analogues = find_analogues(q, top_n=2, min_score=0.25)
                for a in analogues:
                    analogy_matches.append(a.get("mapped_solution", "")[:60])
            except Exception as _e:
                record_failure("autonomous_experiment.run_sandbox_experiment.2", _e)

    if probe_type in ("causal_probe", "prediction_test"):
        for q in queries[:3]:
            try:
                from symbolic.causal_graph import causal_explanation
                expl = causal_explanation(q)
                if expl:
                    causal_edges_found.append(expl[:80])
            except Exception as _e:
                record_failure("autonomous_experiment.run_sandbox_experiment.3", _e)

    # Domain-specific: check prediction error for the domain
    domain_error = 0.0
    if domain:
        try:
            from symbolic.prediction_engine import get_domain_error_rates
            domain_error = get_domain_error_rates().get(domain, 0.0)
        except Exception as _e:
            record_failure("autonomous_experiment.run_sandbox_experiment.4", _e)

    total = len(queries)
    hit_rate = round(symbolic_hits / total, 3) if total else 0.0

    return {
        "experiment_id":     experiment["id"],
        "symbolic_hits":     symbolic_hits,
        "total_queries":     total,
        "hit_rate":          hit_rate,
        "rules_fired":       list(set(rules_fired)),
        "analogy_matches":   analogy_matches,
        "causal_edges_found": causal_edges_found,
        "domain_error":      domain_error,
        "evidence":          evidence[:10],
        "success":           hit_rate >= 0.50,  # experiment "succeeded" = symbolic covers the space
    }


# ─── Active rule revision ─────────────────────────────────────────────────────

def _apply_rule_revision(
    experiment: Dict,
    result: Dict,
    hit_rate: float,
    rules_fired: List[str],
    domain: str,
    goal_text: str,
) -> None:
    """
    Directly adjust rule confidence and attempt crystallization based on
    experimental outcomes. This is the core learning feedback loop.
    """
    try:
        from symbolic.rule_engine import get_all_rules, SYMBOLIC_RULES_FILE
        from utils.json_utils import save_json as _sj
    except Exception:
        return

    rules = get_all_rules()
    changed = False

    if hit_rate >= 0.70 and rules_fired:
        # Strong symbolic coverage: reward all rules that fired
        _REWARD = 0.018
        for rule in rules:
            if rule.get("id") in rules_fired and rule.get("source") != "tombstoned":
                old = float(rule.get("confidence", 0.75))
                rule["confidence"] = round(min(old + _REWARD, 0.95), 4)
                changed = True
                log_activity(
                    f"[experiment] Rewarded rule '{rule['id']}': "
                    f"{old:.3f}→{rule['confidence']:.3f} (hit_rate={hit_rate:.2f})"
                )

    elif hit_rate <= 0.30:
        # Weak symbolic coverage: penalise the rules that attempted but failed
        _PENALTY = 0.015
        evidence_rule_ids = {
            ev.get("rule_id", "") for ev in result.get("evidence", [])
            if ev.get("source") == "rule"
        }
        for rule in rules:
            if rule.get("id") in evidence_rule_ids and rule.get("source") != "tombstoned":
                old = float(rule.get("confidence", 0.75))
                new = round(max(old - _PENALTY, 0.21), 4)
                rule["confidence"] = new
                changed = True
                log_activity(
                    f"[experiment] Penalised rule '{rule['id']}': "
                    f"{old:.3f}→{new:.3f} (low coverage, hit_rate={hit_rate:.2f})"
                )

        # Attempt to crystallize a bridging rule from the goal description
        _try_crystallize_from_gap(experiment, domain)

    if changed:
        _sj(SYMBOLIC_RULES_FILE, rules)
        try:
            from symbolic import rule_engine as _re
            _re._rules_cache = []
        except Exception as _e:
            record_failure("autonomous_experiment._apply_rule_revision", _e)


def _try_crystallize_from_gap(experiment: Dict, domain: str) -> None:
    """
    When an experiment finds no symbolic coverage, attempt to synthesize a
    bridging rule from the goal description using the crystallization pipeline.
    """
    goal_text   = experiment.get("goal_title", "")
    description = (experiment.get("hypothesis") or "")
    if not goal_text or len(goal_text) < 10:
        return

    # Build a synthetic "LLM response" from the hypothesis and goal
    synthetic_response = (
        f"When investigating {goal_text.lower()}: {description} "
        f"This is a {domain.lower() if domain else 'general'} domain concern."
    )

    try:
        from symbolic.crystallization import crystallize
        crystallize(
            prompt=goal_text,
            response=synthetic_response,
            outcome_score=0.60,   # moderate confidence — experiment-derived
            caller="autonomous_experiment",
        )
        log_activity(
            f"[experiment] Attempted crystallization from gap: '{goal_text[:50]}'"
        )
    except Exception as e:
        log_activity(f"[experiment] Crystallization from gap failed: {e}")


def record_experiment_result(experiment: Dict, result: Dict) -> None:
    """
    Feed results back into the symbolic learning systems AND actively revise rules.

    Active revision logic:
      hit_rate ≥ 0.70 → rules that fired were genuinely useful: reward their confidence
      hit_rate ≤ 0.30 → symbolic coverage is thin: penalise matched rules + attempt
                         to crystallize a bridging rule from the goal description
      0.30 < hit_rate < 0.70 → ambiguous: only update causal/ground truth, no rule change
    """
    domain    = experiment.get("domain", "")
    goal_text = experiment.get("goal_title", "")
    success   = result.get("success", False)
    hit_rate  = result.get("hit_rate", 0.0)
    rules_fired = result.get("rules_fired", [])

    # ── Active rule revision ───────────────────────────────────────────────────
    _apply_rule_revision(experiment, result, hit_rate, rules_fired, domain, goal_text)

    # ── Causal graph: experiment as coverage evidence ──────────────────────────
    try:
        from symbolic.causal_graph import update_edge as _ue
        cause  = f"investigation:{domain or 'general'}"
        effect = "symbolic_coverage_improved"
        _ue(cause, effect, confirmed=success, counterfactual=(not success), source="experiment")
    except Exception as _e:
        record_failure("autonomous_experiment.record_experiment_result", _e)

    # ── Ground truth: rules that fired get an outcome stamp ───────────────────
    if rules_fired:
        try:
            from symbolic.ground_truth import record_action_result as _rar
            for rule_id in rules_fired:
                _rar(
                    action_type="experiment_probe",
                    success=success,
                    rule_id=rule_id,
                    context={"domain": domain, "hit_rate": hit_rate},
                    output_snippet=goal_text[:80],
                )
        except Exception as _e:
            record_failure("autonomous_experiment.record_experiment_result.2", _e)

    # Progress tracker
    try:
        from symbolic.progress_tracker import record_experiment as _rexp
        _rexp(success=success, domain=domain)
    except Exception as _e:
        record_failure("autonomous_experiment.record_experiment_result.3", _e)

    # Intuition world model — record experiment outcome per domain
    try:
        from symbolic.pattern_scorer import update_world_model, update_pattern_weights, tokenize_query
        update_world_model(domain or "GENERAL", "experiment", success)
        if goal_text:
            _tokens, _dom = tokenize_query(goal_text)
            update_pattern_weights(_dom, _tokens, hit_rate)
    except Exception as _e:
        record_failure("autonomous_experiment.record_experiment_result.4", _e)

    # Persist experiment with result
    _save_experiment({**experiment, "result": result, "status": "completed"})


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _collect_experiment_goals(ctx: Dict) -> List[Dict]:
    """Gather goals worth experimenting on from context and goal file."""
    candidates: List[Dict] = []

    # Proposed goals injected by intrinsic_motivation this cycle
    for g in (ctx.get("proposed_goals") or []):
        score = float(g.get("exploration_drive_score") or g.get("error_rate", 0))
        if score >= _MIN_EXPLORATION_DRIVE:
            candidates.append(g)

    # Also check the persisted goals file for uninvestigated high-exploration_drive goals
    try:
        from brain.paths import DATA_DIR as _DD
        goal_file = _DD / "goals.json"
        stored = load_json(goal_file, default_type=list) or []
        already_run = {e.get("goal_title", "") for e in (load_json(EXPERIMENT_LOG, default_type=list) or [])}
        for g in stored:
            if g.get("source") not in ("intrinsic_motivation", "domain_error_intrinsic"):
                continue
            if g.get("title", "") in already_run:
                continue
            score = float(g.get("exploration_drive_score") or g.get("error_rate", 0))
            if score >= _MIN_EXPLORATION_DRIVE:
                candidates.append(g)
    except Exception as _e:
        record_failure("autonomous_experiment._collect_experiment_goals", _e)

    return candidates


def _generate_test_queries(title: str, description: str, domain: str, n: int) -> List[str]:
    """Generate N test queries from goal content using simple token extraction."""
    import re
    words = re.findall(r"[a-z][a-z0-9]+", (title + " " + description).lower())
    # Filter stop words
    stops = {"the", "and", "for", "are", "was", "has", "how", "why", "what",
             "with", "this", "that", "from", "into", "when", "its", "not"}
    keywords = [w for w in words if len(w) > 3 and w not in stops]

    queries = []
    # Sliding window of 3 keywords each
    step = max(1, len(keywords) // n)
    for i in range(0, min(len(keywords), n * step), step):
        chunk = keywords[i:i + 3]
        if chunk:
            queries.append(" ".join(chunk))

    # Always include domain as a seed query
    if domain and domain.lower() not in [q.lower() for q in queries]:
        queries.insert(0, f"{domain.lower()} prediction error")

    return queries[:n]


def _hypothesis_for(probe_type: str, title: str, domain: str) -> str:
    if probe_type == "prediction_test":
        return f"High prediction error in {domain or 'this domain'} stems from insufficient symbolic rules."
    if probe_type == "causal_probe":
        return f"A causal explanation exists for '{title[:50]}' in the current causal graph."
    if probe_type == "analogy_match":
        return f"A past analogous situation illuminates '{title[:50]}'."
    return f"The rule base covers the query space described by '{title[:50]}'."


def _save_experiment(exp: Dict) -> None:
    existing = load_json(EXPERIMENT_LOG, default_type=list) or []
    existing.append(exp)
    save_json(EXPERIMENT_LOG, existing[-_MAX_EXPERIMENTS:])


def get_experiment_stats(days: int = 7) -> Dict:
    """Return experiment success rate and domain breakdown for recent experiments."""
    cutoff = time.time() - days * 86400
    entries = load_json(EXPERIMENT_LOG, default_type=list) or []
    recent = []
    for e in entries:
        try:
            ts = datetime.fromisoformat(e.get("created_at", "")).timestamp()
            if ts >= cutoff:
                recent.append(e)
        except Exception as _e:
            record_failure("autonomous_experiment.get_experiment_stats", _e)
    total   = len(recent)
    success = sum(1 for e in recent if (e.get("result") or {}).get("success"))
    return {
        "total":        total,
        "succeeded":    success,
        "success_rate": round(success / total, 3) if total else 0.0,
    }
