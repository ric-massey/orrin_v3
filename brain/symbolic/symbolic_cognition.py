# brain/symbolic/symbolic_cognition.py
# The symbolic cognitive engine.
#
# Performs the actual cognitive work that reflection modules need —
# belief assessment, outcome analysis, rule revision, self-model updates,
# goal generation, contradiction detection, schedule rebalancing —
# entirely without calling the LLM.
#
# Public API (used by reflection modules):
#   assess_beliefs(self_model)            → dict
#   analyze_outcomes(recent_outcomes)     → dict
#   update_self_model_fields(self_model)  → dict   (apply directly, no LLM)
#   propose_rule_changes(outcomes)        → dict   (add/revise/remove)
#   generate_goals(self_model, context)   → list
#   detect_rule_contradictions(self_model) → list
#   rebalance_schedule(schedule, history) → dict
#   analyze_conversation(history)         → str
#   derive_core_value()                   → dict
#   evaluate_cognition(wm, lm)           → dict
from __future__ import annotations
from brain.core.runtime_log import get_logger

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from brain.utils.log import log_activity
from brain.paths import DATA_DIR
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

_FIRINGS_WAL = DATA_DIR / "rule_firings.jsonl"
_WAL_READ_LIMIT = 200   # entries to consider from WAL history


# ─── Private helpers ──────────────────────────────────────────────────────────

def _tok(text: str) -> set:
    stop = frozenset("the and for are was with this that have from its not".split())
    return {w for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in stop}


def _ssm() -> Dict:
    try:
        from brain.symbolic.symbolic_self_model import build_symbolic_self_model
        return build_symbolic_self_model()
    except Exception:
        return {}


def _rules() -> List[Dict]:
    try:
        from brain.symbolic.rule_engine import get_all_rules
        return [r for r in get_all_rules() if not r.get("tombstone")]
    except Exception:
        return []


def _read_wal(limit: int = _WAL_READ_LIMIT) -> List[Dict]:
    """Read the most recent rule-firing WAL entries from disk."""
    entries: List[Dict] = []
    try:
        if not _FIRINGS_WAL.exists():
            return entries
        lines = _FIRINGS_WAL.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in reversed(lines[-limit * 2:]):
            try:
                entries.append(json.loads(line))
                if len(entries) >= limit:
                    break
            except Exception as _e:
                record_failure("symbolic_cognition._read_wal", _e)
    except Exception as _e:
        record_failure("symbolic_cognition._read_wal.2", _e)
    return entries


# ─── 1. Belief assessment ─────────────────────────────────────────────────────

def assess_beliefs(self_model: Dict) -> Dict:
    """
    Compare core_beliefs against rule evidence.
    Returns narrative + structured assessment — no LLM.
    """
    beliefs = self_model.get("core_beliefs", []) or []
    if isinstance(beliefs, str):
        beliefs = [beliefs]

    ssm  = _ssm()
    rls  = _rules()
    health = ssm.get("rule_health", {})
    mean_conf = health.get("mean_confidence", 0.0)
    weak  = ssm.get("weak_areas", [])
    strong = ssm.get("strong_areas", [])

    supported, unsupported, contradictions = [], [], []

    for belief in beliefs[:8]:
        b_str = str(belief)
        b_tok = _tok(b_str)
        if not b_tok:
            continue

        matches = [r for r in rls if len(b_tok & _tok(r.get("conclusion", ""))) >= 2]
        if matches:
            avg_conf = sum(r.get("confidence", 0.5) for r in matches) / len(matches)
            if avg_conf >= 0.55:
                supported.append(b_str)
            else:
                unsupported.append(b_str)
                opposing = [r for r in matches if r.get("confidence", 0.5) < 0.35]
                if opposing:
                    contradictions.append({"belief": b_str[:80], "conflicting_rules": len(opposing)})
        else:
            unsupported.append(b_str)

    parts = []
    if strong:
        parts.append(f"Strong symbolic domains: {', '.join(strong[:3])}.")
    if weak:
        parts.append(f"Weak domains that may challenge beliefs: {', '.join(weak[:3])}.")
    if supported:
        parts.append(f"{len(supported)} belief(s) are rule-grounded.")
    if unsupported:
        parts.append(f"{len(unsupported)} belief(s) lack strong rule support.")
    if contradictions:
        parts.append(f"Potential contradictions detected in {len(contradictions)} belief(s).")
    parts.append(f"Mean rule confidence: {mean_conf:.2f}.")

    return {
        "narrative": " ".join(parts) or "Belief assessment: insufficient symbolic data.",
        "contradiction_detected": bool(contradictions),
        "supported_beliefs": supported,
        "unsupported_beliefs": unsupported,
        "contradiction_details": contradictions,
        "rule_confidence": mean_conf,
        "strong_domains": strong,
        "weak_domains": weak,
    }


# ─── 2. Outcome analysis ─────────────────────────────────────────────────────

def analyze_outcomes(recent_outcomes: List[Dict]) -> Dict:
    """
    Structured outcome quality from WAL + prediction stats.
    Returns narrative + quality_score — no LLM.
    """
    if not recent_outcomes:
        return {"narrative": "No outcomes to analyze.", "quality_score": 0.5,
                "success_rate": 0.5, "failure_patterns": []}

    pos_words = {"success", "completed", "done", "true", "correct", "ok"}
    neg_words = {"failure", "failed", "false", "error", "incorrect", "wrong"}

    successes = sum(1 for o in recent_outcomes if str(o.get("outcome", "")).lower() in pos_words)
    total = len(recent_outcomes)
    success_rate = successes / total if total else 0.5

    # Rule WAL: reward vs penalty count
    wal = _read_wal(50)
    rewarded  = sum(1 for e in wal if isinstance(e, dict) and
                    e.get("outcome") is not None and float(e.get("outcome") or 0) >= 0.65)
    penalized = sum(1 for e in wal if isinstance(e, dict) and
                    e.get("outcome") is not None and float(e.get("outcome")) <= 0.30)

    # Prediction accuracy
    pred_acc = 0.5
    try:
        from brain.symbolic.prediction_engine import get_domain_error_rates
        errs = get_domain_error_rates()
        if errs:
            pred_acc = 1.0 - sum(errs.values()) / len(errs)
    except Exception as _e:
        record_failure("symbolic_cognition.analyze_outcomes", _e)

    quality_score = 0.5 * success_rate + 0.3 * pred_acc + \
                    0.2 * (rewarded / max(rewarded + penalized, 1))

    failure_tasks = [str(o.get("task", ""))[:50]
                     for o in recent_outcomes
                     if str(o.get("outcome", "")).lower() in neg_words][:3]

    parts = [f"Success rate: {success_rate:.0%} ({successes}/{total})."]
    if rewarded:
        parts.append(f"{rewarded} rule firing(s) positively confirmed.")
    if penalized:
        parts.append(f"{penalized} rule firing(s) penalized — revision warranted.")
    parts.append(f"Predictive accuracy: {pred_acc:.0%}.")
    if failure_tasks:
        parts.append(f"Failure patterns in: {'; '.join(failure_tasks)}.")

    return {
        "narrative": " ".join(parts),
        "success_rate": round(success_rate, 3),
        "quality_score": round(quality_score, 3),
        "rule_adjustments": rewarded + penalized,
        "failure_patterns": failure_tasks,
        "prediction_accuracy": round(pred_acc, 3),
    }


# ─── 3. Self-model field update — no LLM ─────────────────────────────────────

def update_self_model_fields(self_model: Dict) -> Dict:
    """
    Directly update self-model fields from symbolic data.
    Returns {updated_fields: dict, changes: list}.
    Apply the updated_fields directly to self_model — no LLM needed.
    """
    ssm = _ssm()
    changes: List[str] = []
    updates: Dict[str, Any] = {}

    weak   = ssm.get("weak_areas",  [])
    strong = ssm.get("strong_areas", [])
    health = ssm.get("rule_health",  {})
    domains = ssm.get("knowledge_domains", {})

    if domains:
        kd_summary = {d: round(s.get("quality", 0), 2) for d, s in domains.items()}
        if self_model.get("knowledge_domains") != kd_summary:
            updates["knowledge_domains"] = kd_summary
            changes.append(f"knowledge_domains updated: {kd_summary}")

    if strong and self_model.get("strengths") != strong:
        updates["strengths"] = strong
        changes.append(f"strengths: {strong}")

    if weak and self_model.get("weaknesses") != weak:
        updates["weaknesses"] = weak
        changes.append(f"weaknesses: {weak}")

    conf = health.get("mean_confidence", 0.0)
    if conf > 0 and abs(self_model.get("symbolic_confidence", 0) - conf) > 0.02:
        updates["symbolic_confidence"] = round(conf, 3)

    if changes:
        now = datetime.now(timezone.utc).isoformat()
        updates["recent_changes"] = [f"[{now[:10]}] Symbolic update: {'; '.join(changes[:3])}"]

    return {"updated_fields": updates, "changes": changes}


# ─── 4. Rule change proposals — no LLM ───────────────────────────────────────

def propose_rule_changes(recent_outcomes: Optional[List[Dict]] = None) -> Dict:
    """
    Propose add/revise/remove for rules entirely from firing history and stats.
    Returns structured dict ready to apply directly — no LLM.
    """
    rls = _rules()
    wal = _read_wal(100)

    # Build firing map: rule_id → list of outcome scores
    firing_map: Dict[str, List[float]] = defaultdict(list)
    for entry in wal:
        if not isinstance(entry, dict):
            continue
        rid = entry.get("rule_id", "")
        out = entry.get("outcome")
        if rid and out is not None:
            try:
                firing_map[rid].append(float(out))
            except (TypeError, ValueError) as _e:
                record_failure("symbolic_cognition.propose_rule_changes", _e)

    revise, remove = [], []

    for rule in rls:
        rid  = rule.get("id", "")
        conf = float(rule.get("confidence", 0.5))
        hits = int(rule.get("hits", 0))
        scores = firing_map.get(rid, [])

        # High firing count + consistently bad outcomes → revise
        if len(scores) >= 3 and conf < 0.50:
            avg = sum(scores) / len(scores)
            if avg < 0.40:
                revise.append({
                    "id": rid,
                    "domain": rule.get("domain", ""),
                    "old": str(rule.get("conditions", []))[:60],
                    "reason": f"conf={conf:.2f}, avg_outcome={avg:.2f} over {len(scores)} firings",
                })

        # Never fired, very low confidence, no hits → prune candidate
        if not scores and hits == 0 and conf < 0.28:
            remove.append({
                "id": rid,
                "domain": rule.get("domain", ""),
                "rule": rule.get("conclusion", "")[:60],
            })

    # Add: synthesize from repeated failure patterns in outcomes
    add = []
    if recent_outcomes:
        fail_tasks = [str(o.get("task", ""))[:50]
                      for o in recent_outcomes
                      if str(o.get("outcome", "")).lower() in {"failure", "failed"}]
        task_counts = Counter(fail_tasks)
        for task, count in task_counts.most_common(2):
            if count < 2:
                break
            tok = _tok(task)
            covered = any(len(tok & _tok(r.get("conclusion", ""))) >= 2 for r in rls)
            if not covered and tok:
                add.append({
                    "domain": "GENERAL",
                    "if": task[:60],
                    "then": f"investigate recurring pattern: {task[:50]}",
                })

    return {"add": add[:2], "revise": revise[:4], "remove": remove[:4]}


# ─── 5. Goal generation — no LLM ─────────────────────────────────────────────

def generate_goals(self_model: Dict, context: Optional[Dict] = None) -> List[Dict]:
    """
    Generate concrete goals from weak areas, experiment gaps, and exploration_drive.
    Returns ready-to-use goal dicts — no LLM.
    """
    ssm   = _ssm()
    goals: List[Dict] = []

    # From weak symbolic domains
    for domain in ssm.get("weak_areas", [])[:2]:
        goals.append({
            "name": f"Strengthen {domain} symbolic reasoning",
            "description": (f"The {domain} domain has low rule confidence. "
                            "Accumulate grounded evidence through experiments and reflection."),
            "tier": "short_term",
        })

    # From experiment gaps
    try:
        from brain.symbolic.autonomous_experiment import get_experiment_stats
        stats = get_experiment_stats(days=7)
        low_domains = [d for d, s in stats.get("by_domain", {}).items()
                       if isinstance(s, dict) and s.get("success_rate", 1.0) < 0.40]
        for d in low_domains[:1]:
            goals.append({
                "name": f"Investigate symbolic gap in {d}",
                "description": f"Experiments found low coverage in {d}. Needs deeper probing.",
                "tier": "short_term",
            })
    except Exception as _e:
        record_failure("symbolic_cognition.generate_goals", _e)

    # From intrinsic motivation (high-exploration_drive topics)
    try:
        from brain.symbolic.intrinsic_motivation import run_intrinsic_motivation
        ctx = context or {}
        result = run_intrinsic_motivation(ctx)
        if isinstance(result, dict) and result.get("label") in ("explore", "investigate"):
            goals.append({
                "name": "Explore high-exploration_drive area",
                "description": f"Intrinsic drive suggests investigating: {result.get('query', 'open question')[:80]}",
                "tier": "mid_term",
            })
    except Exception as _e:
        record_failure("symbolic_cognition.generate_goals.2", _e)

    return goals[:3]


# ─── 6. Contradiction detection — no LLM ─────────────────────────────────────

def detect_rule_contradictions(self_model: Dict) -> List[Dict]:
    """
    Find conflicting beliefs/rules via meta-rules. No LLM.

    One of three distinct contradiction checkers (honest names, F6): this one
    scans symbolic rules; `repair.detect_memory_contradictions` reads long
    memory; `fragmentation.detect_self_model_conflicts` checks the self-model.
    """
    results = []
    rls     = _rules()
    beliefs = self_model.get("core_beliefs", []) or []

    # Meta-rule conflict scan across active rules
    try:
        from brain.symbolic.meta_rules import resolve_conflict
        if len(rls) >= 2:
            # resolve_conflict expects (rule, score) pairs sorted best-first —
            # score each rule by its own confidence (no query context here).
            scored = sorted(
                ((r, float(r.get("confidence", 0.5))) for r in rls[:20]),
                key=lambda pair: pair[1],
                reverse=True,
            )
            res = resolve_conflict(scored)
            if res.get("conflict"):
                results.append({
                    "type": "rule_conflict",
                    "meta_rule": res.get("meta_rule_id", ""),
                    "reason": res.get("reason", "")[:100],
                })
    except Exception as _e:
        record_failure("symbolic_cognition.detect_rule_contradictions", _e)

    # Belief vs rule conclusion conflicts
    for belief in beliefs[:6]:
        b_tok = _tok(str(belief))
        opposing = [r for r in rls
                    if len(b_tok & _tok(r.get("conclusion", ""))) >= 2
                    and r.get("confidence", 0.5) < 0.35]
        if opposing:
            results.append({
                "type": "belief_rule_conflict",
                "belief": str(belief)[:60],
                "opposing_rules": len(opposing),
            })

    return results


# ─── 7. Schedule rebalancing — pure statistics, no LLM ───────────────────────

def rebalance_schedule(schedule: Dict, history: List[Dict]) -> Dict:
    """
    Statistical schedule rebalancing from usage and satisfaction data.
    Returns {changes: {fn: new_weight}, summary: str} — no LLM.
    """
    protected = {"persistent_drive_loop", "choose_next_cognition"}
    usage: Counter = Counter()
    value_acc: Dict[str, float] = {}

    for record in history:
        fn    = record.get("function") or record.get("choice")
        score = float(record.get("satisfaction", 0) or 0)
        if fn:
            usage[fn] += 1
            value_acc[fn] = value_acc.get(fn, 0.0) + score

    changes: Dict[str, float] = {}
    log_parts: List[str] = []

    for fn, count in usage.items():
        if fn in protected:
            continue
        avg     = value_acc.get(fn, 0.0) / count
        current = float(schedule.get(fn, 1.0))

        if avg >= 0.5:
            new_w = min(current + 0.5, 10.0)
        elif avg <= 0.3:
            new_w = max(current - 0.5, 0.1)
        else:
            new_w = current

        if abs(new_w - current) > 0.01:
            changes[fn] = round(new_w, 2)
            direction = "↑" if new_w > current else "↓"
            log_parts.append(f"{direction}{fn}: {current:.1f}→{new_w:.1f} (avg={avg:.2f})")

    return {
        "changes": changes,
        "summary": "; ".join(log_parts) if log_parts else "No schedule changes warranted.",
    }


# ─── 8. Conversation pattern analysis — no LLM ───────────────────────────────

def analyze_conversation(history: List[Any]) -> str:
    """Statistical conversation pattern analysis. No LLM."""
    if not history:
        return "No conversation history to analyze."

    tones: Dict[str, int] = defaultdict(int)
    hesitation_count = 0
    total = 0
    orrin_msgs = 0
    _HPHRASES = ("i'm not sure", "perhaps", "maybe", "i think", "possibly", "uncertain")

    for msg in history:
        if not isinstance(msg, dict):
            continue
        total += 1
        tones[msg.get("tone", "neutral")] += 1
        content = str(msg.get("thought", "") or msg.get("content", "")).lower()
        if any(p in content for p in _HPHRASES):
            hesitation_count += 1
        if msg.get("role", "") in ("assistant", "orrin") or msg.get("agent", "") == "orrin":
            orrin_msgs += 1

    if total == 0:
        return "No analyzable conversation data."

    dominant_tone  = max(tones, key=tones.get) if tones else "neutral"
    hesitation_rate = hesitation_count / total
    speech_ratio    = orrin_msgs / total

    parts = [f"Dominant tone: {dominant_tone}."]
    if hesitation_rate > 0.30:
        parts.append(f"High hesitation rate ({hesitation_rate:.0%}) — consider more direct communication.")
    elif hesitation_rate < 0.08:
        parts.append("Confident communication style — low hesitation.")
    if speech_ratio > 0.60:
        parts.append("Frequent speaker relative to user turns.")
    elif speech_ratio < 0.25:
        parts.append("Low speech ratio — may be under-contributing.")
    parts.append("Suggestion: ground responses in symbolic knowledge first.")

    return " ".join(parts)


# ─── 9. Core value derivation — from causal chains, no LLM ───────────────────

def derive_core_value() -> Dict:
    """
    Derive a core value from the strongest causal chain edges.
    Returns {value: str, justification: str} or {} if insufficient data.
    """
    try:
        from brain.symbolic.causal_graph import get_effects, get_all_edges
        edges = get_all_edges()
        if not edges:
            # Fall back to get_effects on seed concepts
            for seed in ("exploration_drive", "exploration", "learning", "prediction"):
                effects = get_effects(seed)
                if effects and float(effects[0].get("causal_score", 0)) >= 0.50:
                    best = effects[0]
                    cause  = best.get("cause", seed).replace("_", " ")
                    effect = best.get("effect",  "").replace("_", " ")
                    if effect:
                        return {
                            "value": f"{cause}-driven {effect}"[:50],
                            "justification": (
                                f"Strong causal link: '{cause}' → '{effect}' "
                                f"(score={best.get('causal_score', 0):.2f})."
                            ),
                        }
            return {}

        best = max(edges, key=lambda e: float(e.get("causal_score", 0)), default=None)
        if not best or float(best.get("causal_score", 0)) < 0.50:
            return {}
        cause  = best.get("cause",  "").replace("_", " ")
        effect = best.get("effect", "").replace("_", " ")
        if not cause or not effect:
            return {}
        return {
            "value": f"{cause}-driven {effect}"[:50],
            "justification": (
                f"Derived from strongest causal link: '{cause}' → '{effect}' "
                f"(score={float(best.get('causal_score', 0)):.2f}, "
                f"evidence={best.get('evidence', 0)})."
            ),
        }
    except Exception as e:
        log_activity(f"[sym_cog] derive_core_value error: {e}")
        return {}


# ─── 10. Cognition evaluation — no LLM ───────────────────────────────────────

def evaluate_cognition(working_memory: List[Any], long_memory: List[Any]) -> Dict:
    """
    Structured cognition quality from memory + WAL data. No LLM.
    """
    all_mem = list(working_memory or []) + list(long_memory or [])
    insights, missteps = [], []

    _insight_tags = {"reflection", "insight", "discovery", "rule_fired", "symbolic"}
    _misstep_tags = {"error", "failure", "failed", "correction", "mistake"}

    for m in all_mem[-40:]:
        if not isinstance(m, dict):
            continue
        content = str(m.get("content", ""))[:100]
        et   = str(m.get("event_type", "") or m.get("type", "")).lower()
        tags = {str(t).lower() for t in m.get("tags", [])}
        if et in _insight_tags or tags & _insight_tags:
            insights.append(content)
        elif et in _misstep_tags or tags & _misstep_tags:
            missteps.append(content)

    # Alignment score from WAL outcomes
    wal = _read_wal(30)
    outcomes = [float(e.get("outcome"))
                for e in wal if isinstance(e, dict) and e.get("outcome") is not None]
    alignment_score = sum(outcomes) / len(outcomes) if outcomes else 0.5

    ssm = _ssm()
    weak = ssm.get("weak_areas", [])
    adjustments = [f"Deepen {d} symbolic knowledge" for d in weak[:2]] or \
                  ["Continue symbolic learning — foundation is solid."]

    return {
        "insights": insights[:3],
        "missteps": missteps[:3],
        "alignment_score": round(alignment_score, 3),
        "recommended_adjustments": adjustments,
    }
