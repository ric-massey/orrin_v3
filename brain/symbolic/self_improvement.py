# brain/symbolic/self_improvement.py
# Symbolic Self-Improvement Loop — the system reasons about and revises its
# own symbolic knowledge using only its symbolic engine (no LLM).
#
# Three improvement passes:
#
#   1. Rule rehabilitation — rules with low confidence but ≥5 hits are valuable
#      but degraded. Re-score them using grounding and try to strengthen them.
#      Rules with high confidence but 0 hits are dead weight — flag for forgetting.
#
#   2. Router calibration — inspect per-domain quality from the self-model.
#      If symbolic hit rate < 40% in a domain, tighten the self-assessment
#      threshold for that domain so the router defers to LLM earlier.
#      If hit rate > 80%, loosen it to trust symbolic more.
#
#   3. Meta-rule pruning & promotion — meta-rules with 0 applications after
#      N cycles are likely misfired. Demote their priority by 1 step.
#      Meta-rules with the highest application counts get promoted.
#
# All changes are logged to data/self_improvement_log.json for transparency.
# Entry point: run_self_improvement(context) → {changes_made, proposals}
from __future__ import annotations
from brain.core.runtime_log import get_logger

import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_activity
from brain.paths import DATA_DIR
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

IMPROVEMENT_LOG  = DATA_DIR / "self_improvement_log.json"
_COOLDOWN        = 3600 * 4        # 4h between improvement passes
_last_run: float = 0.0

_MIN_HITS_REHAB       = 5          # rules fired this often deserve a second chance
_DEAD_CONF_THRESH     = 0.72       # high conf + 0 hits = probably never matches
_DEAD_HITS_THRESH     = 0          # zero hits means never fired
_META_PRUNE_CUTOFF    = 10         # prune meta-rules with 0 apps after this many total apps
_DOMAIN_LOW_THRESH    = 0.40       # below this: tighten symbolic trust
_DOMAIN_HIGH_THRESH   = 0.80       # above this: loosen symbolic trust
_PRIORITY_MIN         = 1
_PRIORITY_MAX         = 40


# ─── Entry point ──────────────────────────────────────────────────────────────

def run_self_improvement(context: Optional[Dict] = None) -> Dict:
    global _last_run
    now = time.time()
    if now - _last_run < _COOLDOWN:
        return {"skipped": True, "reason": "cooldown"}
    _last_run = now

    changes:   List[Dict] = []
    proposals: List[Dict] = []

    rehabilitated = _rule_rehabilitation(changes)
    calibrated    = _router_calibration(changes, proposals)
    pruned        = _meta_rule_pruning(changes)

    total = rehabilitated + calibrated + pruned
    _flush_improvement_log(changes, proposals)

    if total:
        log_activity(
            f"[self_improve] {rehabilitated} rules rehabilitated, "
            f"{calibrated} domain calibrations, {pruned} meta-rule adjustments"
        )

    return {
        "changes_made":   total,
        "rehabilitated":  rehabilitated,
        "calibrated":     calibrated,
        "meta_adjusted":  pruned,
        "proposals":      proposals,
    }


# ─── Pass 1: Rule rehabilitation ──────────────────────────────────────────────

def _rule_rehabilitation(changes: List[Dict]) -> int:
    try:
        from brain.symbolic.rule_engine import get_all_rules, SYMBOLIC_RULES_FILE
        from brain.symbolic.ground_truth import grounding_score as _gs
    except ImportError:  # intentional: rule/grounding engine optional — no rehab
        return 0

    rules = get_all_rules()
    count = 0

    for rule in rules:
        if rule.get("source") == "tombstoned":
            continue

        conf = float(rule.get("confidence", 0.75))
        hits = int(rule.get("hits", 0))
        rid  = rule.get("id", "")

        # Rehabilitate: high-hit, low-confidence rules are valuable but degraded.
        # Give them a grounding-weighted confidence boost.
        if hits >= _MIN_HITS_REHAB and conf < 0.55:
            try:
                gs = _gs(rid)
            except Exception:
                gs = 0.5
            boost = round(0.02 + 0.03 * gs, 4)
            new_conf = round(min(conf + boost, 0.85), 4)
            rule["confidence"] = new_conf
            count += 1
            changes.append({
                "type":    "rehabilitate",
                "rule_id": rid,
                "old_conf": conf,
                "new_conf": new_conf,
                "reason":  f"{hits} hits but conf={conf:.2f}; grounding={gs:.2f}",
            })
            log_activity(f"[self_improve] Rehabilitated '{rid}': {conf:.3f}→{new_conf:.3f}")

        # Flag dead weight: high confidence but never fired — likely too specific.
        elif conf >= _DEAD_CONF_THRESH and hits == _DEAD_HITS_THRESH:
            # Slight decay to encourage eventual tombstoning via idle forgetting
            new_conf = round(conf - 0.01, 4)
            rule["confidence"] = new_conf
            count += 1
            changes.append({
                "type":    "decay_unfired",
                "rule_id": rid,
                "old_conf": conf,
                "new_conf": new_conf,
                "reason":  "high confidence but 0 hits — likely never matches",
            })

    if count:
        save_json(SYMBOLIC_RULES_FILE, rules)
        try:
            from brain.symbolic import rule_engine as _re
            _re._rules_cache = []
        except Exception as _e:
            record_failure("self_improvement._rule_rehabilitation", _e)

    return count


# ─── Pass 2: Router / domain calibration ──────────────────────────────────────

def _router_calibration(changes: List[Dict], proposals: List[Dict]) -> int:
    """
    Read per-domain symbolic hit rates from the progress tracker and self-model.
    Propose threshold adjustments as human-readable proposals (no code patching).
    Also inject calibration signals into the self-model's weak/strong lists.
    """
    try:
        from brain.symbolic.symbolic_self_model import get_symbolic_self_model
        from brain.symbolic.prediction_engine import get_domain_error_rates
    except ImportError:  # intentional: self-model/prediction engine optional — no calibration
        return 0

    model        = get_symbolic_self_model()
    domain_errors = get_domain_error_rates()
    kd           = model.get("knowledge_domains", {})
    count        = 0

    for domain, stats in kd.items():
        quality      = stats.get("quality", 0.5)
        pred_error   = domain_errors.get(domain, 0.5)
        symbolic_hit_proxy = 1.0 - pred_error  # proxy for how well symbolic covers this domain

        if symbolic_hit_proxy < _DOMAIN_LOW_THRESH and stats.get("rule_count", 0) >= 3:
            proposals.append({
                "type":   "tighten_symbolic_trust",
                "domain": domain,
                "reason": (
                    f"Symbolic coverage proxy={symbolic_hit_proxy:.2f} in {domain} "
                    f"(pred_error={pred_error:.2f}, quality={quality:.2f}). "
                    f"Recommend: add rules for {domain} or lower self-assessment threshold."
                ),
            })
            count += 1

        elif symbolic_hit_proxy > _DOMAIN_HIGH_THRESH:
            proposals.append({
                "type":   "loosen_symbolic_trust",
                "domain": domain,
                "reason": (
                    f"Strong symbolic coverage in {domain} "
                    f"(proxy={symbolic_hit_proxy:.2f}, quality={quality:.2f}). "
                    f"Recommend: prefer symbolic resolution over LLM for {domain} queries."
                ),
            })
            count += 1

    return count


# ─── Pass 3: Meta-rule pruning & promotion ────────────────────────────────────

def _meta_rule_pruning(changes: List[Dict]) -> int:
    try:
        from brain.symbolic.meta_rules import get_meta_rule_stats, _load_meta_rules, _save_meta_rules
    except ImportError:  # intentional: meta-rules engine optional — no pruning
        return 0

    stats = get_meta_rule_stats()
    total_apps = sum(s.get("applications", 0) for s in stats)
    if total_apps < _META_PRUNE_CUTOFF:
        return 0  # not enough data to make pruning decisions

    meta_rules = _load_meta_rules()
    count = 0

    for mr in meta_rules:
        apps = int(mr.get("applications", 0))
        prio = int(mr.get("priority", 20))

        # Underused: lower priority to make it fire less aggressively
        if apps == 0 and total_apps >= 20:
            new_prio = min(prio + 2, _PRIORITY_MAX)
            if new_prio != prio:
                mr["priority"] = new_prio
                count += 1
                changes.append({
                    "type":        "demote_meta_rule",
                    "meta_rule_id": mr.get("id", ""),
                    "old_priority": prio,
                    "new_priority": new_prio,
                    "reason":      f"0 applications in {total_apps} total firings",
                })

        # Heavy hitter: raise priority so it fires earlier
        elif apps >= total_apps * 0.40 and prio > _PRIORITY_MIN + 2:
            new_prio = max(prio - 1, _PRIORITY_MIN)
            if new_prio != prio:
                mr["priority"] = new_prio
                count += 1
                changes.append({
                    "type":        "promote_meta_rule",
                    "meta_rule_id": mr.get("id", ""),
                    "old_priority": prio,
                    "new_priority": new_prio,
                    "reason":      f"{apps} / {total_apps} applications — dominant rule",
                })

    if count:
        _save_meta_rules(meta_rules)

    return count


# ─── Logging ──────────────────────────────────────────────────────────────────

def _flush_improvement_log(changes: List[Dict], proposals: List[Dict]) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "changes":   changes,
        "proposals": proposals,
    }
    existing = load_json(IMPROVEMENT_LOG, default_type=list) or []
    existing.append(entry)
    save_json(IMPROVEMENT_LOG, existing[-60:])


def get_improvement_history(n: int = 5) -> List[Dict]:
    return (load_json(IMPROVEMENT_LOG, default_type=list) or [])[-n:]
