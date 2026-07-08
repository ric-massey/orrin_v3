# eval/evaluator_daemon.py
# Evaluates pending decisions in the WAL using two delayed fitness signals:
#
#   Signal A (retrieval): Did a memory tagged with this decision_id get retrieved
#                         within N_RETRIEVAL=50 cycles?  reward = 0.5 + 0.5*decay
#   Signal B (goal):      Was the active goal at decision time closed within
#                         M_GOAL=200 cycles?  reward += 0.25
#
# Usage in main loop (end of each cycle):
#
#     from eval.evaluator_daemon import EvaluatorDaemon
#     _evaluator = EvaluatorDaemon()
#     _evaluator.tick(context, cycle)
from __future__ import annotations
from brain.core.runtime_log import get_logger

import time
from typing import Any, Dict, List, Optional

from brain.utils.log import log_activity
from brain.paths import COMPLETED_GOALS_FILE
from brain.eval.evaluator_wal import load_all, rewrite
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

N_RETRIEVAL = 50    # cycles to wait for Signal A
M_GOAL      = 200   # cycles to wait for Signal B
MAX_PENDING = 2000  # prune WAL if it grows beyond this
AGE_TIMEOUT = 500   # hard limit: prune unresolved entries older than this
GOAL_CLOSURE_REWARD = 0.55  # raised from 0.25 — goal completion is a strong signal


class EvaluatorDaemon:
    """
    Stateless per-cycle evaluator.  Call tick() once per cycle from the main loop.
    """

    def tick(self, context: Dict[str, Any], cycle: int) -> None:
        try:
            self._resolve(context, cycle)
        except Exception as e:
            try:
                from brain.utils.log import log_model_issue
                log_model_issue(f"[evaluator] tick failed: {e}")
            except Exception as _e:
                record_failure("evaluator_daemon.EvaluatorDaemon.tick", _e)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _resolve(self, context: Dict[str, Any], cycle: int) -> None:
        entries = load_all()
        if not entries:
            return

        # Enforce MAX_PENDING: drop oldest unresolved if WAL is too large.
        unresolved_all = [e for e in entries if not e.get("resolved")]
        if len(unresolved_all) > MAX_PENDING:
            excess = len(unresolved_all) - MAX_PENDING
            oldest = sorted(unresolved_all, key=lambda e: int(e.get("cycle", 0)))[:excess]
            oldest_ids = {e.get("decision_id") for e in oldest}
            for e in entries:
                if e.get("decision_id") in oldest_ids and not e.get("resolved"):
                    e["resolved"] = True
                    e["reward"] = 0.0
                    e["resolved_by"] = "pruned_overflow"
                    e["resolved_ts"] = time.time()
            rewrite(entries)
            log_activity(f"[evaluator] Pruned {excess} overflow WAL entries.")

        changed = False
        resolved_ids: List[str] = []

        for entry in entries:
            if entry.get("resolved"):
                continue

            did = entry.get("decision_id")
            action = entry.get("action", "")
            origin_cycle = int(entry.get("cycle", 0))
            origin_goal = entry.get("committed_goal_id")
            features = entry.get("features") or {}

            age = cycle - origin_cycle

            # Signal A: retrieval
            reward_a = self._check_retrieval(context, did, age)

            # Signal B: goal closure (F15: chronology + grounded-effect gated,
            # significance-scaled — never a flat proximity payout)
            reward_b = self._check_goal_closure(
                context, origin_goal, origin_cycle, age,
                origin_ts=float(entry.get("ts") or 0.0),
            )

            # Prune if too old without signal
            should_prune = age > AGE_TIMEOUT

            if reward_a is not None or reward_b is not None or should_prune:
                reward = 0.0
                resolved_by = "pruned"
                if reward_a is not None:
                    reward += reward_a
                    resolved_by = "retrieval_A"
                if reward_b is not None:
                    # F15: significance-scaled grounded closure (may exceed the
                    # old flat 0.55 for a hard goal; total still capped at 1.0).
                    reward += reward_b
                    _b_tag = "goal_B_grounded"
                    resolved_by = resolved_by + "+" + _b_tag if reward_a is not None else _b_tag
                reward = min(1.0, reward)

                if not should_prune and action:
                    ok = self._apply_delayed(action, features, reward, did)
                    if not ok:
                        attempts = int(entry.get("_apply_attempts", 0)) + 1
                        entry["_apply_attempts"] = attempts
                        if attempts < 3:
                            changed = True
                            continue
                        resolved_by = "apply_failed"
                    else:
                        resolved_ids.append(did or "")
                        try:
                            from brain.think.thought_stream import emit_thought
                            emit_thought(
                                phase="outcome",
                                summary=f"{action} → reward {reward:.2f} ({resolved_by})",
                                cycle=cycle,
                            )
                        except Exception as _e:
                            record_failure("evaluator_daemon.EvaluatorDaemon._resolve", _e)

                entry["resolved"] = True
                entry["reward"] = round(reward, 4)
                entry["resolved_by"] = resolved_by
                entry["resolved_ts"] = time.time()
                changed = True

        if changed:
            # Compact: keep unresolved + recently resolved (last 500 resolved)
            resolved = [e for e in entries if e.get("resolved")]
            unresolved = [e for e in entries if not e.get("resolved")]
            keep_resolved = resolved[-500:]
            rewrite(unresolved + keep_resolved)

            if resolved_ids:
                log_activity(f"[evaluator] resolved {len(resolved_ids)} decisions: {resolved_ids[:3]}")

    def _check_retrieval(
        self, context: Dict[str, Any], decision_id: Optional[str], age: int
    ) -> Optional[float]:
        if not decision_id or age > N_RETRIEVAL:
            return None
        retrieved: List[Any] = context.get("retrieved_memories") or []
        for item in retrieved:
            meta = {}
            if hasattr(item, "meta"):
                meta = item.meta or {}
            elif isinstance(item, dict):
                meta = item.get("meta") or {}
            # Check both meta sub-dict (mem_bridge writes) and top-level key
            # (working_memory entries store decision_id directly)
            item_did = meta.get("decision_id") or (item.get("decision_id") if isinstance(item, dict) else None)
            if item_did == decision_id:
                # Linear decay: 1.0 at age=1 → 0.5 at age=N_RETRIEVAL
                decay = max(0.0, 1.0 - (age - 1) / max(1, N_RETRIEVAL - 1))
                return round(0.5 + 0.5 * decay, 4)
        return None

    def _check_goal_closure(
        self,
        context: Dict[str, Any],
        origin_goal_id: Optional[str],
        origin_cycle: int,
        age: int,
        origin_ts: float = 0.0,
    ) -> Optional[float]:
        """F15 (2026-07-08 addendum): the closure reward pays for CAUSING a real
        completion, not for proximity to any completion. In the 07-05 WAL all
        500 resolved rows were flat-0.55 goal_B — the evaluator bulk-credited
        generate_intrinsic_goals/assess_goal_progress for standing near cheap
        frontier closures, directly reinforcing the F5/F6 generator loop. Now:
          * the completion must be STRICTLY AFTER the decision (timestamp),
          * the closed goal must carry a qualifying credited effect,
          * the reward scales with the closure's significance."""
        if not origin_goal_id or age > M_GOAL:
            return None
        try:
            from datetime import datetime, timezone
            from brain.utils.json_utils import load_json
            completed = load_json(COMPLETED_GOALS_FILE, default_type=list)
            if not isinstance(completed, list):
                return None
            for g in completed:
                if not isinstance(g, dict):
                    continue
                # v1 goals use "name"; v2 goals use "id"/"title" — check all three
                goal_key = str(g.get("id", "") or g.get("title", "") or g.get("name", ""))
                if not goal_key or goal_key != str(origin_goal_id):
                    continue
                # Chronology: completion must postdate the decision. An
                # unparseable/absent completion stamp fails closed (no reward).
                done_at = str(g.get("completed_timestamp") or "")
                try:
                    dt = datetime.fromisoformat(done_at.replace("Z", "+00:00"))
                    done_ts = dt.replace(tzinfo=dt.tzinfo or timezone.utc).timestamp()
                except (ValueError, TypeError):
                    return None
                if origin_ts and done_ts <= origin_ts:
                    return None
                # Grounding: the closed goal must have produced something real.
                try:
                    from brain.agency.effect_ledger import has_qualifying_effect
                    if not has_qualifying_effect(str(g.get("id") or goal_key), g):
                        return None
                except Exception as _ge:
                    record_failure("evaluator_daemon._check_goal_closure.effect", _ge)
                    return None
                # Significance-scaled (achievement_significance ∈ [0.4, 1.3]).
                try:
                    from brain.cognition.planning.goal_outcomes import achievement_significance
                    sig = achievement_significance(g)
                except Exception:
                    sig = 1.0
                return round(GOAL_CLOSURE_REWARD * max(0.4, min(1.3, sig)), 4)
        except Exception as _e:
            record_failure("evaluator_daemon.EvaluatorDaemon._check_goal_closure", _e)
        return None

    def _apply_delayed(
        self,
        action: str,
        features: Dict[str, float],
        reward: float,
        decision_id: Optional[str],
    ) -> bool:
        try:
            from brain.think.bandit.contextual_bandit import update_delayed
            update_delayed(action, features, reward, decision_id=decision_id)
            return True
        except Exception as e:
            try:
                from brain.utils.log import log_model_issue
                log_model_issue(f"[evaluator] update_delayed failed for {action}: {e}")
            except Exception as _e:
                record_failure("evaluator_daemon.EvaluatorDaemon._apply_delayed", _e)
            return False
