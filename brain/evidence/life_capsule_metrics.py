# brain/evidence/life_capsule_metrics.py
# The derived -> interpreted layer of the Life Capsule (Phase 4.5C, from
# life_capsule.py): compute the run metrics from the cleaned tables
# (_compute_metrics + its helpers _signal_followthrough / _early_vs_late), turn
# them into a falsifiable claims ledger (_build_claims / _render_claims_report),
# and assemble the token-budgeted LLM bundle (_llm_context_summary / _llm_index /
# _important_windows). Imports the ingest leaf; the builder imports from here.
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from brain.evidence.life_capsule_ingest import (
    _iso_to_epoch, _FOLLOWTHROUGH_WINDOW, _SIGNAL_EXPECTED_CLASS,
)


# ──────────────────────────────────────────────────────────────────────────────
# Metrics (Part IV/VII) — pure numbers, no prose.
# ──────────────────────────────────────────────────────────────────────────────
def _safe_div(a: float, b: float) -> float:
    return (a / b) if b else 0.0


def _compute_metrics(tables: Dict[str, List[dict]]) -> Dict[str, Any]:
    cycles = tables["cycles"]
    rewards = tables["rewards"]
    artifacts = tables["artifacts"]
    behavior = tables["behavior_changes"]
    goals = tables["goals"]

    n = len(cycles)
    actions = sum(1 for c in cycles if c.get("is_action"))
    # The `is_action` flag is unreliable in some runs (it rode on `tools_used`, which
    # has gone empty). The R1 action-class lens is the robust signal: an outward act is
    # one whose class is productive/communicative (or one the flag did catch).
    outward = sum(
        1 for c in cycles
        if c.get("is_action") or c.get("action_class") in ("productive", "communicative")
    )
    class_dist: Dict[str, int] = {}
    choice_dist: Dict[str, int] = {}
    for c in cycles:
        class_dist[c.get("action_class") or "unknown"] = class_dist.get(c.get("action_class") or "unknown", 0) + 1
        if c.get("choice"):
            choice_dist[c["choice"]] = choice_dist.get(c["choice"], 0) + 1

    rsig = [r["reward_signal"] for r in rewards if isinstance(r.get("reward_signal"), (int, float))]
    credited = sum(1 for a in artifacts if (a.get("novelty") or 0) > 0)

    cyc_nums = [c["cycle"] for c in cycles if isinstance(c.get("cycle"), (int, float))]
    run_summary = {
        "cycles_recorded": n,
        "cycle_min": min(cyc_nums) if cyc_nums else None,
        "cycle_max": max(cyc_nums) if cyc_nums else None,
        "action_count": actions,
        "action_rate": round(_safe_div(actions, n), 4),
        "outward_action_count": outward,
        "outward_action_rate": round(_safe_div(outward, n), 4),
        "distinct_choices": len(choice_dist),
        "distinct_action_classes": len(class_dist),
    }
    action_distribution = {
        "by_class": dict(sorted(class_dist.items(), key=lambda kv: -kv[1])),
        "by_choice": dict(sorted(choice_dist.items(), key=lambda kv: -kv[1])),
    }
    reward_summary = {
        "samples": len(rsig),
        "mean": round(sum(rsig) / len(rsig), 4) if rsig else None,
        "min": round(min(rsig), 4) if rsig else None,
        "max": round(max(rsig), 4) if rsig else None,
    }
    artifact_summary = {
        "logged": len(artifacts),
        "credited_novel": credited,
        "dedupe_rate": round(_safe_div(sum(1 for a in artifacts if a.get("dedupe")), len(artifacts)), 4),
        "by_kind": _count_by(artifacts, "kind"),
    }
    goal_summary = {
        "total": len(goals),
        "by_status": _count_by(goals, "status"),
        "by_kind": _count_by(goals, "kind"),
        "unique_titles": len({g.get("title") for g in goals if g.get("title")}),
    }

    return {
        "run_summary": run_summary,
        "action_distribution": action_distribution,
        "reward_summary": reward_summary,
        "artifact_summary": artifact_summary,
        "goal_summary": goal_summary,
        "signal_followthrough": _signal_followthrough(cycles, behavior),
        "early_vs_late": _early_vs_late(cycles, rewards),
    }


def _count_by(rows: List[dict], key: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for r in rows:
        k = r.get(key)
        if k is None:
            k = "null"
        out[str(k)] = out.get(str(k), 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def _signal_followthrough(cycles: List[dict], behavior: List[dict]) -> Dict[str, Any]:
    """For each corrective pattern, did the expected action class rise in the K cycles
    after it armed? (R1 follow-through.) behavior_changes are ts-stamped; cycles are
    ts-stamped too, so we map each change to the nearest cycle by timestamp."""
    cyc_by_ts: List[Tuple[float, int]] = []
    for c in cycles:
        e = _iso_to_epoch(c.get("ts"))
        if e is not None and isinstance(c.get("cycle"), (int, float)):
            cyc_by_ts.append((e, int(c["cycle"])))
    cyc_by_ts.sort()
    cyc_index = {int(c["cycle"]): i for i, c in enumerate(cycles) if isinstance(c.get("cycle"), (int, float))}

    def nearest_cycle(epoch: Optional[float]) -> Optional[int]:
        if epoch is None or not cyc_by_ts:
            return None
        best = min(cyc_by_ts, key=lambda x: abs(x[0] - epoch))
        return best[1]

    out: Dict[str, Dict[str, Any]] = {}
    for bc in behavior:
        pat = bc.get("pattern")
        if not pat:
            continue
        expected = _SIGNAL_EXPECTED_CLASS.get(pat)
        if not expected:
            continue
        onset = nearest_cycle(_iso_to_epoch(bc.get("when")))
        if onset is None or onset not in cyc_index:
            continue
        i = cyc_index[onset]
        window = cycles[i + 1 : i + 1 + _FOLLOWTHROUGH_WINDOW]
        if not window:
            continue
        hit = sum(1 for c in window if c.get("action_class") in expected)
        agg = out.setdefault(pat, {"events": 0, "expected_class_hits": 0, "window_cycles": 0})
        agg["events"] += 1
        agg["expected_class_hits"] += hit
        agg["window_cycles"] += len(window)

    for pat, agg in out.items():
        agg["followthrough_rate"] = round(_safe_div(agg["expected_class_hits"], agg["window_cycles"]), 4)
        agg["expected_classes"] = list(_SIGNAL_EXPECTED_CLASS.get(pat, ()))
    return out


def _early_vs_late(cycles: List[dict], rewards: List[dict]) -> Dict[str, Any]:
    """Within-run before→after: first quartile vs last quartile (Part VII)."""
    n = len(cycles)
    if n < 8:
        return {"note": "too few cycles for a within-run slice", "cycles": n}
    q = n // 4
    early, late = cycles[:q], cycles[-q:]
    rew_by_cycle = {r["cycle"]: r.get("reward_signal") for r in rewards if r.get("cycle") is not None}

    def slice_stats(seg: List[dict]) -> Dict[str, Any]:
        prod = sum(1 for c in seg if c.get("action_class") in ("productive", "communicative"))
        acts = sum(1 for c in seg if c.get("is_action"))
        rs = [rew_by_cycle.get(c.get("cycle")) for c in seg]
        rs = [x for x in rs if isinstance(x, (int, float))]
        return {
            "productive_pct": round(100 * _safe_div(prod, len(seg)), 2),
            "action_rate": round(_safe_div(acts, len(seg)), 4),
            "mean_reward": round(sum(rs) / len(rs), 4) if rs else None,
            "distinct_choices": len({c.get("choice") for c in seg if c.get("choice")}),
        }

    e, l = slice_stats(early), slice_stats(late)
    return {
        "quartile_size": q,
        "early": e,
        "late": l,
        "delta_productive_pct": round(l["productive_pct"] - e["productive_pct"], 2),
        "delta_action_rate": round(l["action_rate"] - e["action_rate"], 4),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Claims ledger (Part V) — interpretation, evidence-linked. Each detector emits a
# claim with status, supporting evidence, counter-evidence, confidence, next test.
# ──────────────────────────────────────────────────────────────────────────────
def _build_claims(metrics: Dict[str, Any], tables: Dict[str, List[dict]]) -> List[dict]:
    claims: List[dict] = []
    art = metrics["artifact_summary"]
    rs = metrics["run_summary"]
    ft = metrics["signal_followthrough"]
    goals = metrics["goal_summary"]

    # redundant-output / production-collapse
    if art["logged"]:
        credited_rate = _safe_div(art["credited_novel"], art["logged"])
        claims.append(
            {
                "claim_id": "production_credit_001",
                "claim": "Outward effects were logged but earned production credit.",
                "status": "supported" if credited_rate > 0.05 else "refuted",
                "evidence": ["tables/artifacts.csv", "metrics/artifact_summary.json"],
                "metrics": {
                    "effects_logged": art["logged"],
                    "credited_novel": art["credited_novel"],
                    "dedupe_rate": art["dedupe_rate"],
                },
                "counter_evidence": (
                    [f"{art['logged']} effects logged, {art['credited_novel']} credited "
                     f"(dedupe_rate {art['dedupe_rate']}): the gate graded output as non-novel."]
                    if credited_rate <= 0.05 else []
                ),
                "confidence": "high",
                "next_test": "Inspect the lowest-novelty artifacts; is their content actually duplicative?",
            }
        )

    # action-rate / productive presence
    claims.append(
        {
            "claim_id": "action_rate_001",
            "claim": "Orrin crossed from internal cognition into outward action at a measurable rate.",
            "status": "supported" if rs["outward_action_rate"] >= 0.1 else "candidate_supported",
            "evidence": ["tables/cycles.csv", "metrics/run_summary.json", "metrics/action_distribution.json"],
            "metrics": {
                "outward_action_rate": rs["outward_action_rate"],
                "outward_action_count": rs["outward_action_count"],
                "is_action_flag_count": rs["action_count"],
            },
            "counter_evidence": (
                [f"outward_action_rate {rs['outward_action_rate']} — most cycles were internal cognition."]
                if rs["outward_action_rate"] < 0.1 else []
            ),
            "confidence": "high",
            "next_test": "Break action_class distribution down by run quartile (early_vs_late).",
        }
    )

    # closed-loop-running-open (the 2026-06-14 / R2 failure)
    if ft:
        worst = min(ft.items(), key=lambda kv: kv[1].get("followthrough_rate", 1.0))
        pat, agg = worst
        running_open = agg.get("followthrough_rate", 1.0) < 0.15 and agg.get("events", 0) >= 3
        claims.append(
            {
                "claim_id": "closed_loop_open_001",
                "claim": f"The corrective chain for '{pat}' armed but did not change behavior (closed loop running open).",
                "status": "supported" if running_open else "insufficient_evidence",
                "evidence": ["tables/behavior_changes.csv", "metrics/signal_followthrough.json"],
                "metrics": {pat: agg},
                "counter_evidence": [] if running_open else ["follow-through rate is not low enough to assert defeat."],
                "confidence": "medium",
                "next_test": "Check for survival/threat preemption logs in the cycles after each onset.",
            }
        )

    # goal monoculture / 0% aspirations
    if goals["total"]:
        claims.append(
            {
                "claim_id": "goal_monoculture_001",
                "claim": "The goal store is dominated by intake/introspection kinds.",
                "status": "candidate_supported",
                "evidence": ["tables/goals.csv", "metrics/goal_summary.json"],
                "metrics": {"by_kind": goals["by_kind"], "unique_titles": goals["unique_titles"], "total": goals["total"]},
                "counter_evidence": [],
                "confidence": "medium",
                "next_test": "Are any goals kind=coding/code_edit/research with an AcceptanceCriteria?",
            }
        )
    return claims


def _render_claims_report(claims: List[dict]) -> str:
    lines = ["# Claims Report", "", "Evidence-linked interpretation of this run. Each claim "
             "names its supporting data and its counter-evidence — read the metrics, not the prose.", ""]
    for c in claims:
        lines.append(f"## {c['claim_id']} — {c['status']}")
        lines.append("")
        lines.append(f"**Claim:** {c['claim']}")
        lines.append("")
        lines.append(f"**Confidence:** {c['confidence']}")
        if c.get("metrics"):
            lines.append("")
            lines.append(f"**Metrics:** `{json.dumps(c['metrics'])}`")
        if c.get("counter_evidence"):
            lines.append("")
            lines.append("**Counter-evidence:**")
            for ce in c["counter_evidence"]:
                lines.append(f"- {ce}")
        lines.append("")
        lines.append(f"**Evidence:** {', '.join(c.get('evidence', []))}")
        lines.append("")
        lines.append(f"**Next test:** {c.get('next_test', '')}")
        lines.append("")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# LLM bundle (Part VI) — curated, token-budgeted.
# ──────────────────────────────────────────────────────────────────────────────
def _llm_context_summary(metrics: Dict[str, Any], provenance: Dict[str, Any]) -> str:
    rs = metrics["run_summary"]
    return (
        "# LLM Context — Orrin Life Capsule\n\n"
        "## What Orrin is\n"
        "A symbolic-first cognitive agent prototype. Treat this capsule as observational "
        "evidence about one run.\n\n"
        "## Guardrails (read before reasoning)\n"
        "- Do NOT assume consciousness or infer beyond the data.\n"
        "- Prefer metrics over anecdotes; separate observed behavior from interpretation.\n"
        "- Use the claims ledger (`claims/claims_ledger.json`) — each claim names its evidence and limits.\n"
        "- Frequency is not usefulness; an action picked often may still be low-value.\n\n"
        "## This run at a glance\n"
        f"- cycles recorded: {rs['cycles_recorded']} (cycle {rs['cycle_min']}–{rs['cycle_max']})\n"
        f"- action rate: {rs['action_rate']}  ({rs['action_count']} actions)\n"
        f"- effects logged/credited: {metrics['artifact_summary']['logged']}"
        f"/{metrics['artifact_summary']['credited_novel']}\n"
        f"- goals: {metrics['goal_summary']['total']} "
        f"({metrics['goal_summary']['unique_titles']} unique titles)\n"
        f"- git: {provenance.get('git_sha','')[:12]}  reason: {provenance.get('build_reason','')}\n\n"
        "## How to navigate\n"
        "See `llm_index.json` for which table/metric answers which question, and "
        "`important_windows.jsonl` for the decisive cycle windows.\n"
    )


def _llm_index() -> Dict[str, str]:
    return {
        "what did he do most?": "metrics/action_distribution.json, tables/cycles.csv",
        "did he produce anything real?": "metrics/artifact_summary.json, tables/artifacts.csv",
        "did corrective signals change behavior?": "metrics/signal_followthrough.json, tables/behavior_changes.csv",
        "did he change over the run?": "metrics/early_vs_late.json",
        "what goals did he hold?": "tables/goals.csv, metrics/goal_summary.json",
        "who watched him?": "tables/peers.csv",
        "what is supported vs refuted?": "claims/claims_ledger.json",
    }


def _important_windows(tables: Dict[str, List[dict]], metrics: Dict[str, Any]) -> List[dict]:
    """Auto-detect the most informative cycle windows so the LLM reads ~tens of cycles,
    not thousands (Part VI). Cheap heuristics: run start, run end, first action."""
    cycles = tables["cycles"]
    windows: List[dict] = []
    if cycles:
        windows.append({"label": "run_start", "cycles": [c.get("cycle") for c in cycles[:15]]})
        windows.append({"label": "run_end", "cycles": [c.get("cycle") for c in cycles[-15:]]})
        first_action = next((c for c in cycles if c.get("is_action")), None)
        if first_action is not None:
            idx = cycles.index(first_action)
            seg = cycles[max(0, idx - 5): idx + 10]
            windows.append({"label": "first_action", "cycles": [c.get("cycle") for c in seg]})
    return windows


