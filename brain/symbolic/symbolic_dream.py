# brain/symbolic/symbolic_dream.py
# Autonomous offline reasoning cycle — zero LLM calls.
#
# Runs before the LLM dream sub-cycles, doing pure symbolic reasoning:
#   Pass A — Rule chaining:
#     Take conclusions from recently fired rules, feed them back as new queries,
#     and run match_all() on those conclusions.  This builds "rule chains" like:
#       exploration_drive → enables exploration → exploration requires uncertainty → ...
#     Chains of depth ≥ 2 that reach a novel conclusion are written to WM.
#
#   Pass B — Analogy chaining:
#     For each recent WM entry with high structural relation overlap against
#     old long-memory, extract the mapped solution and run rule_match on it.
#     This yields "transfer" insights: old solution applied in new context.
#
#   Pass C — Contradiction surfacing:
#     Run match_all on pairs of high-novelty recent queries.  If two matched
#     rules are contradictory (from meta_rules._are_contradictory), surface a
#     "tension" note into WM so the LLM dream can resolve it.
#
# Output is written to data/symbolic_dream_log.json and injected into WM.
# No API calls, no side effects beyond file writes.
from __future__ import annotations
from brain.core.runtime_log import get_logger

from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_activity
from brain.paths import DATA_DIR, WORKING_MEMORY_FILE
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

SYMBOLIC_DREAM_LOG = DATA_DIR / "symbolic_dream_log.json"

_MAX_CHAIN_DEPTH = 4
_MAX_CHAINS      = 12
_MAX_TRANSFERS   = 6
_MIN_CHAIN_SCORE = 0.38


def run_symbolic_dream(context: Optional[Dict] = None) -> Dict:
    """
    Zero-LLM dream pass.  Returns summary of insights generated.
    """
    ts = datetime.now(timezone.utc).isoformat()
    insights: List[Dict] = []

    log_activity("[sym_dream] Starting symbolic dream pass (0 LLM calls).")

    # ── Load recent WM entries as seed queries ──────────────────────────────
    wm = load_json(WORKING_MEMORY_FILE, default_type=list) or []
    recent_wm = wm[-20:]
    seed_texts = [
        str(e.get("content", e) if isinstance(e, dict) else e)
        for e in recent_wm
        if e
    ][:12]

    # ── Pass A: Rule chaining ───────────────────────────────────────────────
    chain_insights, raw_chains = _rule_chain_pass(seed_texts)
    insights.extend(chain_insights)

    # ── Pass B: Analogy transfer ────────────────────────────────────────────
    transfer_insights = _analogy_transfer_pass(seed_texts)
    insights.extend(transfer_insights)

    # ── Pass C: Contradiction surfacing ────────────────────────────────────
    tension_insights = _contradiction_pass(seed_texts)
    insights.extend(tension_insights)

    # ── Pass D: Causal discovery ────────────────────────────────────────────
    causal_insights = _causal_discovery_pass(raw_chains, recent_wm)
    insights.extend(causal_insights)

    # ── Pass E: Counterfactual simulation ───────────────────────────────────
    cf_insights = _counterfactual_pass()
    insights.extend(cf_insights)

    # ── Write insights to WM ────────────────────────────────────────────────
    if insights:
        try:
            from brain.cog_memory.working_memory import update_working_memory as _uwm
            for ins in insights:
                _uwm({
                    "content":    f"[sym_dream:{ins['type']}] {ins['text'][:300]}",
                    "event_type": "symbolic_dream_insight",
                    "importance": ins.get("importance", 2),
                    "priority":   ins.get("priority", 2),
                })
        except Exception as e:
            log_activity(f"[sym_dream] WM write failed: {e}")

    # ── Append to dream log ─────────────────────────────────────────────────
    entry = {"timestamp": ts, "insights": insights}
    try:
        existing = load_json(SYMBOLIC_DREAM_LOG, default_type=list) or []
        existing.append(entry)
        save_json(SYMBOLIC_DREAM_LOG, existing[-50:])
    except Exception as _e:
        record_failure("symbolic_dream.run_symbolic_dream", _e)

    log_activity(
        f"[sym_dream] Complete: {len(chain_insights)} chain(s), "
        f"{len(transfer_insights)} transfer(s), "
        f"{len(tension_insights)} tension(s), "
        f"{len(causal_insights)} causal edge(s), "
        f"{len(cf_insights)} counterfactual(s)."
    )
    return {
        "chains":           len(chain_insights),
        "transfers":        len(transfer_insights),
        "tensions":         len(tension_insights),
        "causal":           len(causal_insights),
        "counterfactuals":  len(cf_insights),
        "total":            len(insights),
    }


# ── Pass E: Counterfactual simulation ────────────────────────────────────────


def _counterfactual_pass(max_edges: int = 8) -> List[Dict]:
    """
    For established causal edges (evidence ≥ 3), run simulate_counterfactual()
    to check whether the effect can be produced WITHOUT the cause.
    When likely counterfactual, the edge strength is weakened automatically
    inside simulate_counterfactual().
    """
    insights: List[Dict] = []
    try:
        from brain.symbolic.causal_graph import get_all_edges, simulate_counterfactual
    except ImportError:  # intentional: causal graph optional — no counterfactual pass
        return insights

    edges = [
        e for e in get_all_edges()
        if e.get("evidence_count", 0) >= 3
        and e.get("causal_score", 0) >= 0.30
    ]
    edges = sorted(edges, key=lambda e: e.get("causal_score", 1.0))

    for edge in edges[:max_edges]:
        try:
            result = simulate_counterfactual(edge["cause"], edge["effect"])
            if result.get("counterfactual_likely"):
                insights.append({
                    "type":      "counterfactual",
                    "text":      (
                        f"Counterfactual: '{edge['cause'][:50]}' → '{edge['effect'][:50]}' "
                        f"may be spurious — {len(result['alternative_rules'])} alternative rule(s) "
                        f"can produce the effect independently."
                    ),
                    "edge_id":   edge["id"],
                    "importance": 3,
                    "priority":   2,
                })
        except Exception as _e:
            record_failure("symbolic_dream._counterfactual_pass", _e)

    return insights


# ── Pass A: Rule chaining ───────────────────────────────────────────────────

def _rule_chain_pass(seeds: List[str]) -> Tuple[List[Dict], List[List[Dict]]]:
    """Returns (insights, raw_chains) — raw_chains fed to causal discovery."""
    insights: List[Dict] = []
    raw_chains: List[List[Dict]] = []
    visited_conclusions: Set[str] = set()

    try:
        from brain.symbolic.rule_engine import match_all, apply as rule_apply
    except ImportError:  # intentional: rule engine optional — no chain pass
        return insights, raw_chains

    for seed in seeds[:8]:
        chain = _follow_chain(seed, visited_conclusions, match_all, rule_apply, depth=0)
        if chain and len(chain) >= 2:
            text = " → ".join(c["conclusion"][:60] for c in chain)
            insights.append({
                "type":      "rule_chain",
                "text":      text,
                "chain":     [c["id"] for c in chain],
                "depth":     len(chain),
                "importance": min(2 + len(chain), 4),
                "priority":   2,
            })
            raw_chains.append(chain)
        if len(insights) >= _MAX_CHAINS:
            break

    return insights, raw_chains


def _follow_chain(
    query: str,
    visited: Set[str],
    match_all_fn,
    apply_fn,
    depth: int,
) -> List[Dict]:
    if depth >= _MAX_CHAIN_DEPTH:
        return []
    matches = match_all_fn(query, threshold=_MIN_CHAIN_SCORE)
    if not matches:
        return []

    rule, score = matches[0]
    rid = rule.get("id", "")
    if rid in visited:
        return []
    visited.add(rid)

    conclusion = rule.get("conclusion", "")
    next_chain = _follow_chain(conclusion, visited, match_all_fn, apply_fn, depth + 1)
    return [rule] + next_chain


# ── Pass B: Analogy transfer ────────────────────────────────────────────────

def _analogy_transfer_pass(seeds: List[str]) -> List[Dict]:
    insights = []
    try:
        from brain.symbolic.analogy_engine import find_analogues
        from brain.symbolic.rule_engine import match_all
    except ImportError:  # intentional: analogy/rule engine optional — no transfer pass
        return insights

    for seed in seeds[:6]:
        analogues = find_analogues(seed, top_n=2, min_score=0.25)
        for a in analogues:
            solution = a.get("mapped_solution", "")
            if len(solution) < 20:
                continue
            # See if any rule matches the analogue's solution in this new context
            matches = match_all(seed + " " + solution, threshold=0.35)
            rule_note = ""
            if matches:
                rule_note = " → rule: " + matches[0][0].get("conclusion", "")[:80]
            text = (
                f"Transfer from past ({a['intent_type']}, score={a['score']}): "
                f"{solution[:160]}{rule_note}"
            )
            insights.append({
                "type":      "analogy_transfer",
                "text":      text,
                "score":     a["score"],
                "importance": 3,
                "priority":   2,
            })
        if len(insights) >= _MAX_TRANSFERS:
            break

    return insights


# ── Pass C: Contradiction surfacing ────────────────────────────────────────

def _contradiction_pass(seeds: List[str]) -> List[Dict]:
    insights = []
    try:
        from brain.symbolic.rule_engine import match_all
        from brain.symbolic.meta_rules import _are_contradictory
    except ImportError:  # intentional: rule/meta engine optional — no contradiction pass
        return insights

    seen_pairs: Set[str] = set()
    for i, s1 in enumerate(seeds[:6]):
        for s2 in seeds[i+1:7]:
            m1 = match_all(s1, threshold=0.38)
            m2 = match_all(s2, threshold=0.38)
            if not m1 or not m2:
                continue
            r1, r2 = m1[0][0], m2[0][0]
            pair_key = "_".join(sorted([r1["id"], r2["id"]]))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            if _are_contradictory(r1, r2):
                text = (
                    f"Tension between rules '{r1['id']}' and '{r2['id']}': "
                    f"\"{r1['conclusion'][:80]}\" vs \"{r2['conclusion'][:80]}\""
                )
                insights.append({
                    "type":      "contradiction",
                    "text":      text,
                    "rule_ids":  [r1["id"], r2["id"]],
                    "importance": 4,
                    "priority":   3,
                })

    return insights


# ── Pass D: Causal discovery ────────────────────────────────────────────────

def _causal_discovery_pass(
    raw_chains: List[List[Dict]],
    wm_entries: List[Dict],
) -> List[Dict]:
    """
    Propose causal edges from:
      1. Rule chains (R1 conclusion → R2 condition implies causation)
      2. WM temporal co-occurrence (event_type X before Y)
    Returns insight dicts for the dream log.
    """
    insights: List[Dict] = []
    try:
        from brain.symbolic.causal_graph import (
            discover_from_rule_chain,
            discover_from_wm_sequence,
        )
    except ImportError:  # intentional: causal graph optional — no discovery pass
        return insights

    # Rule chains → causal edges
    for chain in raw_chains:
        new_edges = discover_from_rule_chain(chain)
        for edge in new_edges:
            if edge.get("evidence_count", 0) >= 2:
                insights.append({
                    "type":      "causal_edge",
                    "text":      (
                        f"Causal link: '{edge['cause'][:60]}' → '{edge['effect'][:60]}' "
                        f"(score={edge['causal_score']:.2f})"
                    ),
                    "edge_id":   edge["id"],
                    "importance": 3,
                    "priority":   2,
                })

    # WM temporal sequence → causal edges
    dict_entries = [e for e in wm_entries if isinstance(e, dict)]
    seq_edges = discover_from_wm_sequence(dict_entries)
    for edge in seq_edges:
        if edge.get("evidence_count", 0) >= 2:
            insights.append({
                "type":      "causal_temporal",
                "text":      (
                    f"Temporal pattern: '{edge['cause']}' → '{edge['effect']}' "
                    f"(evidence={edge['evidence_count']})"
                ),
                "edge_id":   edge["id"],
                "importance": 2,
                "priority":   2,
            })

    return insights
