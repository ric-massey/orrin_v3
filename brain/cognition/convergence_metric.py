# brain/cognition/convergence_metric.py
# Convergence-spiral metric: the ratio of reflection-on-reflection edges to
# reflection-on-experience edges in the rule provenance graph. A rising ratio
# means the self-model is citing its own conclusions rather than experience —
# each layer resolving more uncertainty into more confidence (the mechanism
# behind the self-echo bug family). Pure telemetry: no behavior change, no
# Goodhart surface; report per-life in the run verdict alongside occupancy.
#
# Adapted from the Athena-Class Cognitive Architecture (Vesper & Hypatia,
# Project Anamnesis, v1.0, 2026-06-07): their measure of Tier-4 entries citing
# other Tier-4 entries rather than Tier-2/3 experience.
#
# Scope note: this reads RULE provenance only. The memo/memory half of the
# metric waits on the §2.0 `origin` field (RUN12 plan A.1.2 / 2.0 sequencing).
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict

from brain.paths import DATA_DIR
from brain.utils.json_utils import load_json, save_json
from brain.utils.failure_counter import record_failure

_SPIRAL_LOG = DATA_DIR / "convergence_spiral.json"
_LOG_CAP = 90   # mirrors forgetting_log retention


def convergence_spiral_report() -> Dict[str, Any]:
    """Compute the spiral ratio from the current rule set.

    An "edge" is a derived rule citing one of its evidence rules. The edge is
    reflection-on-REFLECTION when the cited rule is itself derived
    (inference_distance >= 1), reflection-on-EXPERIENCE when the cited rule is
    experience-grounded (distance 0). Derived rules with no resolvable citation
    are counted separately — they contribute depth without an edge.
    """
    try:
        from brain.symbolic.rule_engine import get_all_rules, rule_inference_distance
    except ImportError:  # intentional: rule engine optional — nothing to measure
        return {"available": False}

    rules = [r for r in get_all_rules() if r.get("source") != "tombstoned"]
    by_id = {r.get("id"): r for r in rules}

    on_reflection = 0
    on_experience = 0
    uncited_reflection = 0
    distances = []
    histogram: Dict[str, int] = {}

    for rule in rules:
        d = rule_inference_distance(rule, by_id)
        distances.append(d)
        histogram[str(d)] = histogram.get(str(d), 0) + 1
        if d < 1:
            continue
        cited = [by_id[e] for e in (rule.get("evidence_ids") or []) if e in by_id]
        if not cited:
            uncited_reflection += 1
            continue
        for parent in cited:
            if rule_inference_distance(parent, by_id) >= 1:
                on_reflection += 1
            else:
                on_experience += 1

    return {
        "available": True,
        "reflection_on_reflection_edges": on_reflection,
        "reflection_on_experience_edges": on_experience,
        # The spiral signal. 0.0 with no edges at all — an edgeless rule set
        # cannot be spiraling, and a 0/0 must not read as one.
        "spiral_ratio": round(on_reflection / on_experience, 4) if on_experience
                        else (float(on_reflection) if on_reflection else 0.0),
        "uncited_reflection_rules": uncited_reflection,
        "mean_inference_distance": round(sum(distances) / len(distances), 4) if distances else 0.0,
        "distance_histogram": histogram,
        "rule_count": len(rules),
    }


def record_convergence_spiral() -> None:
    """Append a timestamped report to the bounded telemetry series. Called from
    run_forgetting_cycle each dream pass; fail-safe."""
    try:
        report = convergence_spiral_report()
        if not report.get("available"):
            return
        report["timestamp"] = datetime.now(timezone.utc).isoformat()
        report["ts"] = time.time()
        series = load_json(_SPIRAL_LOG, default_type=list) or []
        series.append(report)
        save_json(_SPIRAL_LOG, series[-_LOG_CAP:])
    except Exception as e:
        record_failure("convergence_metric.record", e)
