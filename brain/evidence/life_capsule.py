"""
brain/evidence/life_capsule.py — the Orrin Life Capsule (the Autopsy Engine).

One run sealed into a single self-describing `.orrinlife.zip`: raw streams preserved,
plus cleaned tables, a queryable SQLite DB, computed metrics, a claims ledger, and a
token-budgeted LLM bundle. Hand someone the file and they understand the run *without*
running Orrin.

Design: `ORRIN_LIFE_CAPSULE_PLAN_2026-06-18.md`. The organizing rule is
**raw → cleaned → derived → interpreted**, each layer downstream-only. The builder is a
pure function of the raw layer (deterministic rebuild), so anyone can reproduce the
derived artifacts and check our work.

This is the third sibling of the exporters Orrin already ships
(`mind_archive` → the mind; `diagnostics` → ops logs). The Life Capsule is the
**evidence** export. It is additive and fail-safe: if the builder never runs, the loop
is unaffected; if it partially fails, it writes what it has and records the failure.

Public entry point:

    build_life_capsule(reason: str, *, share=False, out_dir=None) -> Path

`reason` ∈ {normal_shutdown, crash_recovery, mortality_end_of_life, checkpoint, manual}.
"""
from __future__ import annotations

import csv
import json
import os
import platform
import shutil
import sqlite3
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import brain.paths as paths
# The raw->cleaned ingest layer (constants, classify_action, IO/hash/time helpers,
# per-stream parsers) was extracted to life_capsule_ingest.py (Phase 4.5C);
# re-imported so the builder below + external callers keep their references.
from brain.evidence.life_capsule_ingest import (  # noqa: F401
    CAPSULE_SCHEMA_VERSION, VALID_REASONS, _LLM_BUDGET_BYTES, _MIN_ARTIFACT_CHARS,
    _FOLLOWTHROUGH_WINDOW, classify_action, _ACTION_CLASS, _SIGNAL_EXPECTED_CLASS,
    _now_iso, _read_json, _iter_jsonl, _sha256_text, _sha256_file, _iso_to_epoch,
    _last_run_segment, _git_sha, _redact_home,
    _parse_decisions, _parse_affect, _parse_behavior_changes, _parse_goals,
    _parse_artifacts, _parse_memory_events, _parse_peers, _derive_signals,
)

# ──────────────────────────────────────────────────────────────────────────────
# SQLite assembly — tables are built in memory, written to the DB, and CSVs are
# exported FROM the DB so the two can never disagree (Part IV).
# ──────────────────────────────────────────────────────────────────────────────
def _columns_for(rows: List[dict]) -> List[str]:
    cols: List[str] = []
    seen = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                cols.append(k)
    return cols


def _build_sqlite(db_path: Path, tables: Dict[str, List[dict]]) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        for name, rows in tables.items():
            cols = _columns_for(rows) or ["_empty"]
            col_decl = ", ".join(f'"{c}"' for c in cols)
            cur.execute(f'DROP TABLE IF EXISTS "{name}"')
            cur.execute(f'CREATE TABLE "{name}" ({col_decl})')
            if rows:
                placeholders = ", ".join("?" for _ in cols)
                cur.executemany(
                    f'INSERT INTO "{name}" ({col_decl}) VALUES ({placeholders})',
                    [tuple(r.get(c) for c in cols) for r in rows],
                )
        conn.commit()
    finally:
        conn.close()


def _export_csvs(db_path: Path, tables_dir: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        for (name,) in cur.fetchall():
            cur.execute(f'SELECT * FROM "{name}"')
            cols = [d[0] for d in cur.description]
            with (tables_dir / f"{name}.csv").open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(cols)
                for row in cur.fetchall():
                    w.writerow(row)
    finally:
        conn.close()


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


# ──────────────────────────────────────────────────────────────────────────────
# Raw layer (selective — Addendum #3 / Part VI privacy)
# ──────────────────────────────────────────────────────────────────────────────
# Streams safe to embed verbatim (evidence value, no model weights). private_thoughts
# and the conscious stream are gated to LOCAL builds only; never in a --share build.
_RAW_STREAMS = (
    "events.jsonl",
    "telemetry_archive.jsonl",
    "behavior_changes.json",
    "effect_ledger.jsonl",
    "outcome_metrics.json",
    "runstate.json",
    "lifespan.json",
    "autobiography.json",
    "relationships.json",
    "conscious_stream.json",
    "action_reward_ema.json",
)
# Files NEVER embedded: model weights (size+no value), private thoughts (most sensitive).
_RAW_NEVER = ("native_lm.pt",)
_RAW_LOCAL_ONLY = ("conscious_stream.json",)  # excluded from --share builds


def _copy_raw(data_dir: Path, raw_dir: Path, *, share: bool) -> Dict[str, Any]:
    redaction = {"omitted_local_only": [], "redacted_paths": [], "never_embedded": list(_RAW_NEVER)}
    sel = raw_dir / "selected_streams"
    sel.mkdir(parents=True, exist_ok=True)
    for name in _RAW_STREAMS:
        src = data_dir / name
        if not src.exists():
            continue
        if share and name in _RAW_LOCAL_ONLY:
            redaction["omitted_local_only"].append(name)
            continue
        try:
            text = src.read_text("utf-8", errors="replace")
            if share:
                redacted = _redact_home(text)
                if redacted != text:
                    redaction["redacted_paths"].append(name)
                text = redacted
            (sel / name).write_text(text, encoding="utf-8")
        except Exception:
            continue
    return redaction


# ──────────────────────────────────────────────────────────────────────────────
# Top-level builder
# ──────────────────────────────────────────────────────────────────────────────
def _provenance(reason: str) -> Dict[str, Any]:
    data_dir = paths.DATA_DIR
    lifespan = _read_json(data_dir / "lifespan.json", {}) or {}
    runstate = _read_json(data_dir / "runstate.json", {}) or {}
    orrin_flags = {k: v for k, v in os.environ.items() if k.startswith("ORRIN_")}
    try:
        from brain.utils import schema_migration as _sm
        schema_v = _sm.read_version()
    except Exception:
        schema_v = None
    return {
        "captured_at": _now_iso(),
        "build_reason": reason,
        "capsule_schema_version": CAPSULE_SCHEMA_VERSION,
        "git_sha": _git_sha(paths.ROOT_DIR.parent),
        "orrin_flags": orrin_flags,
        "state_schema_version": schema_v,
        "lifespan": lifespan,
        "runstate": runstate,
        "host": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
        },
    }


def _run_id(provenance: Dict[str, Any]) -> str:
    born = (provenance.get("lifespan") or {}).get("born_at")
    epoch = _iso_to_epoch(born)
    if epoch:
        return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def _executive_summary(metrics: Dict[str, Any], provenance: Dict[str, Any], run_id: str) -> str:
    rs = metrics["run_summary"]
    art = metrics["artifact_summary"]
    ad = metrics["action_distribution"]
    top = list(ad["by_choice"].items())[:5]
    evl = metrics.get("early_vs_late", {})
    lines = [
        f"# Executive Summary — run {run_id}",
        "",
        f"*Build reason: {provenance.get('build_reason')} · git {provenance.get('git_sha','')[:12]}*",
        "",
        "## What happened, in 2 minutes",
        f"- **{rs['cycles_recorded']} cycles** recorded (cycle {rs['cycle_min']}–{rs['cycle_max']}).",
        f"- **Outward action rate {rs['outward_action_rate']}** — {rs['outward_action_count']} of "
        f"{rs['cycles_recorded']} cycles were productive/communicative acts "
        f"(the raw `is_action` flag caught {rs['action_count']}; the class lens recovers the rest).",
        f"- **{art['logged']} outward effects logged, {art['credited_novel']} earned novelty credit** "
        f"(dedupe rate {art['dedupe_rate']}).",
        f"- **{metrics['goal_summary']['total']} goals**, "
        f"{metrics['goal_summary']['unique_titles']} unique titles.",
        "",
        "## Most-selected actions",
    ]
    for choice, cnt in top:
        lines.append(f"- `{choice}` ×{cnt} ({classify_action(choice)})")
    if isinstance(evl, dict) and "delta_productive_pct" in evl:
        lines += [
            "",
            "## Did he change over the run? (early vs late quartile)",
            f"- productive+communicative %: {evl['early']['productive_pct']} → {evl['late']['productive_pct']} "
            f"(Δ {evl['delta_productive_pct']}pp)",
            f"- action rate: {evl['early']['action_rate']} → {evl['late']['action_rate']} (Δ {evl['delta_action_rate']})",
        ]
    lines += ["", "Read next: `claims/claims_report.md`, then query `database/orrin_life.sqlite`."]
    return "\n".join(lines)


def _readme(run_id: str) -> str:
    return (
        f"# Orrin Life Capsule — {run_id}\n\n"
        "One run, whole. Raw evidence preserved, plus cleaned tables, a queryable SQLite "
        "DB, computed metrics, an evidence-linked claims ledger, and an LLM-ready bundle.\n\n"
        "## Four entry points\n"
        "1. **Human, 2 min:** `EXECUTIVE_SUMMARY.md`\n"
        "2. **What's supported:** `claims/claims_report.md`\n"
        "3. **Ad-hoc questions:** query `database/orrin_life.sqlite` (CSV mirrors in `tables/`)\n"
        "4. **Hand to an LLM:** `llm/llm_context_summary.md` + `llm/claim_cards.jsonl`\n\n"
        "## Suggested analysis order\n"
        "run integrity (`metrics/run_summary.json`) → action behavior "
        "(`metrics/action_distribution.json`) → reward → goals → memory → "
        "signal→action follow-through (`metrics/signal_followthrough.json`).\n\n"
        "## Layers (downstream-only)\n"
        "`raw/` (never edited) → `tables/` + `database/` (cleaned) → `metrics/` (derived) "
        "→ `claims/` (interpreted). Every derived file traces back to raw via "
        "`file_hashes.csv`.\n\n"
        f"Capsule schema version: {CAPSULE_SCHEMA_VERSION}\n"
    )


def build_life_capsule(
    reason: str = "manual",
    *,
    share: bool = False,
    out_dir: Optional[Path] = None,
) -> Path:
    """Build one `.orrinlife.zip` from the current on-disk data. Pure function of the
    raw layer; never mutates Orrin's state. Returns the path to the sealed zip.

    reason ∈ VALID_REASONS. `share=True` redacts home paths and omits local-only
    streams. Atomic: builds under `.building/` then renames into place on success.
    """
    if reason not in VALID_REASONS:
        reason = "manual"

    data_dir = paths.DATA_DIR
    state_dir = paths.STATE_DIR
    out_dir = Path(out_dir) if out_dir else (paths.ROOT_DIR.parent / "exports" / "life_capsules")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Best-effort WAL flush so daemon trees are consistent at the captured instant.
    try:
        from memory.wal import flush as _wal_flush
        _wal_flush()
    except Exception:
        pass

    provenance = _provenance(reason)
    run_id = _run_id(provenance)

    build_root = out_dir / ".building" / run_id
    if build_root.exists():
        shutil.rmtree(build_root, ignore_errors=True)
    cap = build_root / f"orrin_life_capsule_{run_id}"
    for sub in ("raw", "database", "tables", "metrics", "claims", "llm", "privacy"):
        (cap / sub).mkdir(parents=True, exist_ok=True)

    build_errors: List[str] = []

    def _guard(label: str, fn, default):
        try:
            return fn()
        except Exception as e:  # never let one bad stream abort the capsule
            build_errors.append(f"{label}: {e}")
            return default

    # 1. Parse streams → tables.
    cycles, decisions, rewards = _guard("decisions", lambda: _parse_decisions(data_dir), ([], [], []))
    tables: Dict[str, List[dict]] = {
        "cycles": cycles,
        "decisions": decisions,
        "rewards": rewards,
        "affect": _guard("affect", lambda: _parse_affect(data_dir), []),
        "behavior_changes": _guard("behavior_changes", lambda: _parse_behavior_changes(data_dir), []),
        "goals": _guard("goals", lambda: _parse_goals(data_dir, state_dir), []),
        "artifacts": _guard("artifacts", lambda: _parse_artifacts(data_dir), []),
        "memory_events": _guard("memory_events", lambda: _parse_memory_events(state_dir), []),
        "peers": _guard("peers", lambda: _parse_peers(data_dir), []),
    }
    tables["signals"] = _guard("signals", lambda: _derive_signals(tables["behavior_changes"]), [])

    # 2. SQLite + CSV mirrors (CSVs exported FROM the DB so they can't disagree).
    db_path = cap / "database" / "orrin_life.sqlite"
    _guard("sqlite", lambda: _build_sqlite(db_path, tables), None)
    _guard("csv", lambda: _export_csvs(db_path, cap / "tables"), None)

    # 3. Metrics.
    metrics = _guard("metrics", lambda: _compute_metrics(tables), {})
    for name, payload in (metrics or {}).items():
        (cap / "metrics" / f"{name}.json").write_text(json.dumps(payload, indent=2), "utf-8")

    # 4. Claims.
    claims = _guard("claims", lambda: _build_claims(metrics, tables), []) if metrics else []
    (cap / "claims" / "claims_ledger.json").write_text(json.dumps(claims, indent=2), "utf-8")
    (cap / "claims" / "claims_report.md").write_text(_render_claims_report(claims), "utf-8")

    # 5. LLM bundle (token-budgeted).
    if metrics:
        (cap / "llm" / "llm_context_summary.md").write_text(_llm_context_summary(metrics, provenance), "utf-8")
        (cap / "llm" / "llm_index.json").write_text(json.dumps(_llm_index(), indent=2), "utf-8")
        cards = [
            {
                "claim_id": c["claim_id"],
                "question": c["claim"],
                "answer": f"status={c['status']}; {json.dumps(c.get('metrics', {}))}",
                "supporting": c.get("evidence", []),
                "limitations": "; ".join(c.get("counter_evidence", [])) or "see claims ledger",
            }
            for c in claims
        ]
        with (cap / "llm" / "claim_cards.jsonl").open("w", encoding="utf-8") as f:
            for c in cards:
                f.write(json.dumps(c) + "\n")
        with (cap / "llm" / "important_windows.jsonl").open("w", encoding="utf-8") as f:
            for w in _important_windows(tables, metrics):
                f.write(json.dumps(w) + "\n")
        (cap / "llm" / "LLM_README.md").write_text(
            "Start with `llm_context_summary.md`, then `llm_index.json` to navigate, then "
            "`claim_cards.jsonl`. Total bundle is token-budgeted to fit a context window.\n",
            "utf-8",
        )

    # 6. Raw layer (selective).
    redaction = _guard("raw", lambda: _copy_raw(data_dir, cap / "raw", share=share),
                       {"omitted_local_only": [], "redacted_paths": [], "never_embedded": list(_RAW_NEVER)})
    (cap / "privacy" / "redaction_report.json").write_text(json.dumps(redaction, indent=2), "utf-8")

    # 7. Top-level docs + provenance + manifest.
    if metrics:
        (cap / "EXECUTIVE_SUMMARY.md").write_text(_executive_summary(metrics, provenance, run_id), "utf-8")
    (cap / "README.md").write_text(_readme(run_id), "utf-8")
    (cap / "provenance.json").write_text(json.dumps(provenance, indent=2), "utf-8")

    manifest = {
        "run_id": run_id,
        "capsule_schema_version": CAPSULE_SCHEMA_VERSION,
        "build_reason": reason,
        "built_at": _now_iso(),
        "share_build": share,
        "table_row_counts": {k: len(v) for k, v in tables.items()},
        "build_errors": build_errors,
    }
    (cap / "manifest.json").write_text(json.dumps(manifest, indent=2), "utf-8")

    # 8. Tamper-evident hashes of every file (traces derived → raw).
    _write_file_hashes(cap)

    # 9. Seal: zip, then atomic-rename into place.
    final = out_dir / f"orrin_life_capsule_{run_id}.orrinlife.zip"
    tmp_zip = build_root / "capsule.zip.partial"
    with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(cap.rglob("*")):
            if f.is_file():
                zf.write(f, arcname=f.relative_to(cap.parent).as_posix())
    if final.exists():
        final.unlink()
    os.replace(tmp_zip, final)
    shutil.rmtree(build_root, ignore_errors=True)
    return final


def maybe_build_capsule(reason: str) -> Optional[Path]:
    """Fail-safe wrapper for the run-boundary hooks (shutdown / mortality). Never
    raises and never blocks teardown on an error; honors the `ORRIN_LIFE_CAPSULE`
    off-switch (set to 0/false/no to disable). Returns the capsule path or None."""
    flag = os.environ.get("ORRIN_LIFE_CAPSULE", "1").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return None
    try:
        return build_life_capsule(reason)
    except Exception as e:  # a capsule failure must never affect the run
        try:
            print(f"[life_capsule] build skipped ({reason}): {e}", flush=True)
        except Exception:
            pass
        return None


def _write_file_hashes(cap: Path) -> None:
    rows = []
    for f in sorted(cap.rglob("*")):
        if f.is_file() and f.name != "file_hashes.csv":
            rows.append((f.relative_to(cap).as_posix(), f.stat().st_size, _sha256_file(f)))
    with (cap / "file_hashes.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["path", "bytes", "sha256"])
        w.writerows(rows)


# ──────────────────────────────────────────────────────────────────────────────
# Read-side API — list capsules and read one's summary without unzipping it fully.
# Used by the UI surface (Part IX) and the desktop bridge.
# ──────────────────────────────────────────────────────────────────────────────
def capsules_dir() -> Path:
    return paths.ROOT_DIR.parent / "exports" / "life_capsules"


def _inner_root(zf: zipfile.ZipFile) -> str:
    """The single top-level folder inside a capsule zip (orrin_life_capsule_<id>)."""
    for n in zf.namelist():
        if "/" in n:
            return n.split("/", 1)[0]
    return ""


def _read_member(zip_path: Path, suffix: str) -> Optional[bytes]:
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for n in zf.namelist():
                if n.endswith(suffix):
                    return zf.read(n)
    except Exception:
        return None
    return None


def list_capsules() -> List[dict]:
    """Catalog of sealed capsules, newest first. Each entry carries enough to render a
    list row (id, reason, size, built_at, headline counts) read from the manifest."""
    out: List[dict] = []
    d = capsules_dir()
    if not d.exists():
        return out
    for z in d.glob("*.orrinlife.zip"):
        entry = {
            "run_id": z.stem.replace("orrin_life_capsule_", "").replace(".orrinlife", ""),
            "file": z.name,
            "size_bytes": z.stat().st_size,
            "mtime": z.stat().st_mtime,
        }
        man = _read_member(z, "manifest.json")
        if man:
            try:
                m = json.loads(man)
                entry.update(
                    {
                        "run_id": m.get("run_id", entry["run_id"]),
                        "build_reason": m.get("build_reason"),
                        "built_at": m.get("built_at"),
                        "table_row_counts": m.get("table_row_counts", {}),
                        "share_build": m.get("share_build"),
                    }
                )
            except Exception:
                pass
        out.append(entry)
    out.sort(key=lambda e: e.get("mtime", 0), reverse=True)
    return out


def capsule_path(run: str = "latest") -> Optional[Path]:
    """Resolve a capsule zip by run_id, or the most recent one for `latest`."""
    caps = list_capsules()
    if not caps:
        return None
    if run in ("", "latest", None):
        target = caps[0]
    else:
        target = next((c for c in caps if c.get("run_id") == run), None)
        if target is None:
            return None
    return capsules_dir() / target["file"]


def read_capsule_summary(run: str = "latest") -> Optional[dict]:
    """The inline-renderable summary for one capsule: executive summary markdown,
    the manifest, the run-summary + key metrics, and the claims ledger."""
    z = capsule_path(run)
    if z is None:
        return None
    out: Dict[str, Any] = {"run_id": z.stem.replace("orrin_life_capsule_", "").replace(".orrinlife", "")}

    def _j(suffix: str) -> Any:
        b = _read_member(z, suffix)
        try:
            return json.loads(b) if b else None
        except Exception:
            return None

    md = _read_member(z, "EXECUTIVE_SUMMARY.md")
    out["executive_summary_md"] = md.decode("utf-8", "replace") if md else ""
    out["manifest"] = _j("manifest.json")
    out["run_summary"] = _j("metrics/run_summary.json")
    out["action_distribution"] = _j("metrics/action_distribution.json")
    out["artifact_summary"] = _j("metrics/artifact_summary.json")
    out["claims"] = _j("claims/claims_ledger.json") or []
    return out


# ──────────────────────────────────────────────────────────────────────────────
# CLI — build a capsule from current data without running Orrin.
#   python -m brain.evidence.life_capsule [--share] [--reason manual] [--out DIR]
# ──────────────────────────────────────────────────────────────────────────────
def _main(argv: List[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Build an Orrin Life Capsule from current data.")
    ap.add_argument("--reason", default="manual", choices=sorted(VALID_REASONS))
    ap.add_argument("--share", action="store_true", help="redact home paths, omit local-only streams")
    ap.add_argument("--out", default=None, help="output directory (default exports/life_capsules)")
    args = ap.parse_args(argv)

    path = build_life_capsule(args.reason, share=args.share, out_dir=args.out)
    size_kb = path.stat().st_size / 1024
    print(f"capsule sealed: {path} ({size_kb:.1f} KB)")
    return 0


if __name__ == "__main__":
    # Allow running as a standalone script: ensure the repo root is importable so
    # `import brain.paths` resolves whether invoked as a module or a file.
    if "brain.paths" not in sys.modules:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        import brain.paths as paths  # noqa: F811
    raise SystemExit(_main(sys.argv[1:]))
