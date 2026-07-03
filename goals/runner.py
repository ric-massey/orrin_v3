# goals/runner.py
from __future__ import annotations
from brain.core.runtime_log import get_logger

import os
import queue
import threading
import time
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, cast

from .model import Goal, Step, Status, artifact_satisfied
from .handlers.base import GoalHandler, HandlerContext
from . import metrics as metrics_mod
_log = get_logger(__name__)

def UTCNOW() -> datetime:
    return datetime.now(timezone.utc)

def _dbg_enabled() -> bool:
    return os.getenv("GOALS_DEBUG", "0") not in ("0", "", "false", "False")

def _dbg(*a: Any) -> None:
    if _dbg_enabled():
        try:
            print("[runner]", *a, flush=True)
        except Exception as _e:
            _log.warning("silent except: %s", _e)

# ---------- minimal duck-typed store helpers ----------

def _iter_goals(store: Any) -> Iterable[Goal]:
    # store is duck-typed; cast the recognized accessor's result to the contract.
    if hasattr(store, "iter_goals"):
        return cast(Iterable[Goal], store.iter_goals())
    if hasattr(store, "list_goals"):
        return cast(Iterable[Goal], store.list_goals())
    if hasattr(store, "all"):
        return cast(Iterable[Goal], store.all())
    return []  # graceful fallback


def _get_goal(store: Any, goal_id: str) -> Optional[Goal]:
    if hasattr(store, "get_goal"):
        return cast(Optional[Goal], store.get_goal(goal_id))
    for g in _iter_goals(store):
        if g.id == goal_id:
            return g
    return None


def _upsert_goal(store: Any, goal: Goal) -> None:
    if hasattr(store, "upsert_goal"):
        store.upsert_goal(goal); return
    if hasattr(store, "save_goal"):
        store.save_goal(goal); return
    if hasattr(store, "update_goal"):
        store.update_goal(goal); return


def _upsert_step(store: Any, step: Step) -> None:
    if hasattr(store, "upsert_step"):
        store.upsert_step(step); return
    if hasattr(store, "save_step"):
        store.save_step(step); return
    if hasattr(store, "update_step"):
        store.update_step(step); return


def _list_steps(store: Any, goal_id: Optional[str] = None) -> List[Step]:
    if hasattr(store, "steps_for"):
        return cast(List[Step], store.steps_for(goal_id))
    if hasattr(store, "iter_steps"):
        out: List[Step] = []
        for s in store.iter_steps():
            if goal_id and s.goal_id != goal_id:
                continue
            out.append(s)
        return out
    if hasattr(store, "list_steps"):
        return cast(List[Step], store.list_steps(goal_id=goal_id))
    return []


# ---------- StepRunner ----------

class StepRunner:
    def __init__(
        self,
        *,
        store: Any,
        registry: Any,
        step_queue: "queue.Queue[Step]",
        workers: int = 3,
        ctx: Optional[HandlerContext] = None,
        reaper_sink: Optional[Any] = None,
    ) -> None:
        self.store = store
        self.registry = registry
        self.q: "queue.Queue[Step]" = step_queue
        self.workers = max(0, int(workers))
        self.ctx: HandlerContext = dict(ctx or {})
        # robust, idempotent shutdown controls
        self._stop_evt = threading.Event()
        self._stopping = False
        self._threads: List[threading.Thread] = []
        self._active_mu = threading.RLock()   # re-entrant to avoid self-deadlock
        self._active_count = 0
        self._reaper_sink = reaper_sink

    # ----- lifecycle -----

    def start(self) -> None:
        _dbg("start workers:", self.workers)
        for i in range(self.workers):
            t = threading.Thread(target=self._worker, name=f"GoalsStepWorker-{i+1}", daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        _dbg("stop called")
        # Idempotent: avoid double shutdowns
        if self._stopping:
            return
        self._stopping = True

        if not isinstance(getattr(self, "_stop_evt", None), threading.Event):
            self._stop_evt = threading.Event()
        self._stop_evt.set()

        # Send one poison pill per worker so each can exit cleanly
        for _ in self._threads:
            try:
                self.q.put(None)  # type: ignore[arg-type]
            except Exception:
                try:
                    self.q.put_nowait(None)  # type: ignore[arg-type]
                except Exception as _e:
                    _log.warning("silent except: %s", _e)

    def join(self, timeout: Optional[float] = None) -> None:
        for t in self._threads:
            t.join(timeout=timeout)

    # Public enqueue for schedulers/daemons
    def submit(self, step: Step) -> None:
        _dbg("submit step:", step.id, "goal:", step.goal_id)
        # If the test configured workers=0, run synchronously so tests don't hang.
        if self.workers <= 0:
            self._execute_step(step)
            return

        # If workers were configured but start() wasn't called, auto-start once.
        if not self._threads and self.workers > 0:
            self.start()

        try:
            self.q.put_nowait(step)
        except Exception:
            self.q.put(step)


    # ----- metrics/introspection -----

    @property
    def active_workers(self) -> int:
        with self._active_mu:
            return self._active_count

    def _inc_active(self) -> None:
        with self._active_mu:
            self._active_count += 1
            active = self._active_count
        self._set_worker_metrics(active)  # emit outside lock

    def _dec_active(self) -> None:
        with self._active_mu:
            self._active_count = max(0, self._active_count - 1)
            active = self._active_count
        self._set_worker_metrics(active)  # emit outside lock

    def capacity_left(self) -> int:
        cap = max(0, self.workers - self.active_workers)
        _dbg("capacity_left:", cap)
        return cap

    def queue_size(self) -> int:
        try:
            return self.q.qsize()
        except NotImplementedError:  # intentional: qsize unsupported on some platforms (macOS) → 0
            return 0

    def _set_worker_metrics(self, active: Optional[int] = None) -> None:
        try:
            metrics_mod.update_queue(self.queue_size(), self.active_workers if active is None else active)
        except Exception as _e:
            _log.warning("silent except: %s", _e)

    # ----- core worker loop -----

    def _worker(self) -> None:
        _dbg("worker started")
        while not self._stop_evt.is_set():
            try:
                item = self.q.get(timeout=0.3)
            except queue.Empty:
                continue
            if item is None:  # poison
                _dbg("worker got poison pill")
                try:
                    self.q.task_done()
                except Exception as _e:
                    _log.warning("silent except: %s", _e)
                break  # exit loop

            step: Step = item
            _dbg("dequeued step:", step.id, "goal:", step.goal_id)
            self._inc_active()
            try:
                self._execute_step(step)
            except Exception as e:
                self._emit({"kind": "StepRunnerError", "error": f"{type(e).__name__}: {e}", "ts": UTCNOW().isoformat()})
                _dbg("execute_step error:", e)
            finally:
                self._dec_active()
                self.q.task_done()
                self._set_worker_metrics()

    # ----- execution -----

    def _execute_step(self, step: Step) -> None:
        goal = _get_goal(self.store, step.goal_id)
        if goal is None:
            _dbg("goal missing for step:", step.id)
            step.status = Status.FAILED
            step.last_error = "goal missing"
            step.finished_at = UTCNOW()
            _upsert_step(self.store, step)
            self._emit_step_event("StepFailed", step, goal_kind="unknown", extra={"reason": "goal_missing"})
            return

        handler = self._get_handler(goal)
        if handler is None:
            _dbg("no handler for goal kind:", goal.kind)
            step.status = Status.FAILED
            step.last_error = f"no handler for kind '{goal.kind}'"
            step.finished_at = UTCNOW()
            _upsert_step(self.store, step)
            self._emit_step_event("StepFailed", step, goal_kind=goal.kind, extra={"reason": "no_handler"})
            ng = replace(goal, status=Status.FAILED, updated_at=UTCNOW(), last_error=step.last_error)
            _upsert_goal(self.store, ng)
            self._emit_goal_event("GoalFailed", ng, extra={"reason": "no_handler"})
            return

        started_emitted = False
        t0 = time.perf_counter()
        # ---- anti-stall guards ----
        stall_s = 10.0     # no-progress window before we defer
        max_run_s = 60.0   # hard cap for a single _execute_step loop
        last_change = t0
        last_state = (getattr(step.status, "name", str(step.status)),
                      int(step.attempts or 0),
                      step.started_at.isoformat() if step.started_at else None)

        # A worker is executing this step NOW — say so before the first tick.
        # When a handler raised on its very first tick, started_at stayed None,
        # StepStarted never emitted, and the goal never flipped to RUNNING —
        # broken goals died looking READY (2026-07-02 §5).
        if step.started_at is None:
            step.started_at = UTCNOW()

        while not self._stop_evt.is_set():
            try:
                new = handler.tick(goal, step, self._handler_ctx(goal))
                if new is not None:
                    step = new
                _dbg("tick ->", step.status.name, "step:", step.id)
            except Exception as e:
                step.last_error = f"{type(e).__name__}: {e}"
                step.attempts = int(step.attempts or 0) + 1
                _dbg("tick raised:", step.last_error, "attempts:", step.attempts, "/", step.max_attempts)
                # Machine-readable failure telemetry: the 2026-07-02 run's nine
                # handler crashes survived only as activity-log prose.
                try:
                    from brain.utils.failure_counter import record_failure
                    record_failure(f"goals.runner.tick.{goal.kind}", e)
                except Exception:  # intentional: telemetry must never mask the step error
                    pass
                if step.attempts >= step.max_attempts:
                    step.status = Status.FAILED
                    if step.finished_at is None:
                        step.finished_at = UTCNOW()
                else:
                    step.status = Status.READY
                    step.started_at = None

            # --- DEFENSIVE NORMALIZATIONS ---
            if step.status == Status.RUNNING and step.started_at is None:
                step.started_at = UTCNOW()

            # progress detection (status/attempts/started_at change)
            cur_state = (getattr(step.status, "name", str(step.status)),
                         int(step.attempts or 0),
                         step.started_at.isoformat() if step.started_at else None)
            if cur_state != last_state:
                last_state = cur_state
                last_change = time.perf_counter()

            # Emit StepStarted exactly once, and flip goal→RUNNING on first start
            if not started_emitted and step.started_at is not None:
                self._emit_step_event("StepStarted", step, goal_kind=goal.kind)
                started_emitted = True
                if goal.status not in {Status.RUNNING, Status.DONE, Status.FAILED, Status.CANCELLED}:
                    ng = replace(goal, status=Status.RUNNING, updated_at=UTCNOW())
                    _upsert_goal(self.store, ng)
                    goal = ng  # carry forward for subsequent emits/finalize

            # Persist latest step state each loop
            _upsert_step(self.store, step)

            # ---- terminal handling ----
            if step.status in {Status.DONE, Status.FAILED, Status.CANCELLED}:
                if step.finished_at is None:
                    step.finished_at = UTCNOW()
                    _upsert_step(self.store, step)

                extra = {"duration_sec": max(0.0, time.perf_counter() - t0)}
                if step.status == Status.DONE:
                    self._emit_step_event("StepFinished", step, goal_kind=goal.kind, extra=extra)
                    self._record_step_effects(goal, step)
                    _dbg("finished step:", step.id)
                elif step.status == Status.FAILED:
                    self._emit_step_event("StepFailed", step, goal_kind=goal.kind, extra=extra)
                    _dbg("failed step:", step.id)
                elif step.status == Status.CANCELLED:
                    self._emit_step_event("StepCancelled", step, goal_kind=goal.kind, extra=extra)
                    _dbg("cancelled step:", step.id)

                # Robust finalization: allow the store a moment to reflect the latest write.
                for _ in range(6):  # up to ~60 ms total
                    if self._maybe_finalize_goal(goal, step):
                        break
                    time.sleep(0.01)
                else:
                    # Finalization didn't fire — still update progress so UI isn't stuck at 0%
                    store_steps = _list_steps(self.store, goal_id=goal.id)
                    by_id = {s.id: s for s in store_steps}
                    by_id[step.id] = step
                    all_steps = list(by_id.values())
                    if all_steps:
                        done = sum(1 for s in all_steps if s.status in {Status.DONE, Status.CANCELLED})
                        pct = round(done / len(all_steps) * 100.0, 1)
                        goal.progress.set(percent=pct)
                        _upsert_goal(self.store, goal)
                return

            # deferrable states return control to scheduler
            if step.status in {Status.READY, Status.WAITING, Status.BLOCKED, Status.PAUSED}:
                _dbg("deferring step:", step.id, "status:", step.status.name)
                return

            # ---- anti-stall checks for long RUNNING loops ----
            now = time.perf_counter()
            if (now - last_change) >= stall_s and step.status == Status.RUNNING:
                _dbg("no-progress defer:", step.id, "after", round(now - last_change, 3), "s")
                self._emit_step_event("StepDeferredNoProgress", step, goal_kind=goal.kind,
                                      extra={"stalled_sec": round(now - last_change, 3)})
                step.status = Status.READY
                step.started_at = None
                _upsert_step(self.store, step)
                return

            if (now - t0) >= max_run_s:
                _dbg("max_run cap hit for step:", step.id)
                if (step.attempts or 0) + 1 >= (step.max_attempts or 1):
                    step.status = Status.FAILED
                    step.last_error = (step.last_error or "") + " | max_run_s exceeded"
                    step.finished_at = UTCNOW()
                else:
                    step.status = Status.READY
                    step.started_at = None
                    step.last_error = (step.last_error or "") + " | max_run_s exceeded"
                    step.attempts = int(step.attempts or 0) + 1
                _upsert_step(self.store, step)
                self._emit_step_event("StepDeferredMaxRun", step, goal_kind=goal.kind,
                                      extra={"max_run_s": max_run_s})
                return

            time.sleep(0.02)

    # ----- helpers -----

    def _record_step_effects(self, goal: Goal, step: Step) -> None:
        """AR1 (audit D7): a DONE step that wrote real artifacts records them on
        the effect ledger, so v2 handler production (research memos, housekeeping
        reports, code files) is visible to the goal/production/reward system.

        Reads Step.artifacts only — handlers put *produced* paths there, never
        fetched source material — and the ledger's own gates (novelty dedup,
        MIN_ARTIFACT_CHARS, structural significance) decide what actually earns
        credit. Never raises: ledger trouble must not fail the step.
        """
        paths = [p for p in (step.artifacts or []) if p]
        if not paths:
            return
        try:
            from pathlib import Path as _Path
            from brain.agency.effect_ledger import record_effect
            for p in paths[:8]:
                fp = _Path(str(p))
                if not fp.is_file():
                    continue
                try:
                    text = fp.read_text(encoding="utf-8", errors="replace")[:65536]
                except OSError:
                    continue
                record_effect(
                    "file_write", text, goal_id=goal.id,
                    metadata={"path": str(fp), "goal_kind": goal.kind,
                              "step": step.name, "source": "goals.runner"},
                )
        except Exception as e:
            _log.warning("step effect recording failed: %s", e)

    def _maybe_finalize_goal(self, goal: Goal, last_step: Step) -> bool:
        """
        Try to finalize a goal based on current step states.
        Returns True if we transitioned the goal to a terminal state, else False.
        """
        # Read what the store currently sees
        store_steps = _list_steps(self.store, goal_id=goal.id)

        # Build by-id and overlay the freshest in-memory last_step
        by_id: Dict[str, Step] = {s.id: s for s in store_steps}
        by_id[last_step.id] = last_step
        steps = list(by_id.values())

        # Early finalize if no steps are visible yet but we have a terminal last_step.
        if not steps:
            if last_step.status in {Status.DONE, Status.CANCELLED}:
                ng = replace(goal, status=Status.DONE, updated_at=UTCNOW())
                _upsert_goal(self.store, ng)
                self._emit_goal_event("GoalFinished", ng, extra={"steps_total": 1, "reason": "no_steps_visible"})
                _dbg("finalized goal DONE (no steps visible):", goal.id)
                return True
            if last_step.status == Status.FAILED and (last_step.attempts or 0) >= (last_step.max_attempts or 0):
                ng = replace(goal, status=Status.FAILED, updated_at=UTCNOW(), last_error=last_step.last_error)
                _upsert_goal(self.store, ng)
                self._emit_goal_event("GoalFailed", ng, extra={"step_id": last_step.id, "reason": "no_steps_visible"})
                _dbg("finalized goal FAILED (no steps visible):", goal.id)
                return True
            return False

        # If anything failed and nothing else is pending → FAIL the goal.
        # A pending step whose dependencies (transitively) include a terminally
        # FAILED step can never run — count it as dead, not pending. Without
        # this, a failed keystone step left its dependents WAITING forever and
        # the goal died looking READY (2026-07-02: three research goals stuck
        # NEW→READY→READY with their search step FAILED at attempt 3).
        any_failed = any(s.status == Status.FAILED for s in steps)
        if any_failed:
            by_step_id = {s.id: s for s in steps}
            dead: set[str] = {s.id for s in steps if s.status == Status.FAILED}
            changed_dead = True
            while changed_dead:
                changed_dead = False
                for s in steps:
                    if s.id in dead:
                        continue
                    if any(d in dead for d in (s.deps or []) if d in by_step_id):
                        dead.add(s.id)
                        changed_dead = True
            any_pending = any(
                s.status not in {Status.DONE, Status.CANCELLED, Status.FAILED}
                and s.id not in dead
                for s in steps
            )
        else:
            any_pending = any(s.status not in {Status.DONE, Status.CANCELLED, Status.FAILED} for s in steps)
        if any_failed and not any_pending:
            ng = replace(goal, status=Status.FAILED, updated_at=UTCNOW(), last_error=last_step.last_error)
            _upsert_goal(self.store, ng)
            self._emit_goal_event("GoalFailed", ng, extra={"step_id": last_step.id})
            try:
                from brain.utils.failure_counter import record_goal_failure
                record_goal_failure(goal.id, goal.title, last_step.last_error or "step_failed")
            except Exception:  # intentional: telemetry must never block goal finalization
                pass
            _dbg("finalized goal FAILED:", goal.id)
            return True

        # Done when all steps are terminal non-failed
        if steps and all(s.status in {Status.DONE, Status.CANCELLED} for s in steps):
            # Artifact gate (no fabricated progress): a goal that requires an artifact
            # must not be flipped to DONE when its plan ran but produced nothing. Fail
            # it honestly instead of faking a 100% completion.
            if not artifact_satisfied(goal, steps):
                ng = replace(goal, status=Status.FAILED, updated_at=UTCNOW(),
                             last_error="objective not met: required artifact not produced")
                _upsert_goal(self.store, ng)
                self._emit_goal_event("GoalFailed", ng, extra={
                    "steps_total": len(steps), "reason": "artifact_required_not_produced"})
                _dbg("finalized goal FAILED (artifact required, none produced):", goal.id)
                return True
            ng = replace(goal, status=Status.DONE, updated_at=UTCNOW())
            ng.progress.set(percent=100.0, note="all steps complete")
            _upsert_goal(self.store, ng)
            self._emit_goal_event("GoalFinished", ng, extra={"steps_total": len(steps)})
            _dbg("finalized goal DONE:", goal.id)
            return True

        # Update progress percentage for in-flight goals
        if steps:
            done = sum(1 for s in steps if s.status in {Status.DONE, Status.CANCELLED})
            pct = round(done / len(steps) * 100.0, 1)
            if abs(pct - goal.progress.percent) >= 1.0:
                goal.progress.set(percent=pct)
                _upsert_goal(self.store, goal)

        return False

    def _get_handler(self, goal: Goal) -> Optional[GoalHandler]:
        reg = self.registry
        if reg is None:
            return None
        for meth in ("get", "get_handler", "handler_for", "resolve", "lookup"):
            fn = getattr(reg, meth, None)
            if callable(fn):
                try:
                    h = fn(goal.kind)
                    if h:
                        return cast("Optional[GoalHandler]", h)
                except Exception as _e:
                    _log.warning("silent except: %s", _e)
        for attr in ("by_kind", "handlers", "registry", "_by_kind", "_handlers"):
            m = getattr(reg, attr, None)
            if isinstance(m, dict):
                h = m.get(goal.kind)
                if h:
                    return cast("Optional[GoalHandler]", h)
        if isinstance(reg, dict):
            return cast("Optional[GoalHandler]", reg.get(goal.kind))
        return None

    def _handler_ctx(self, goal: Goal) -> HandlerContext:
        ctx = dict(self.ctx)
        ctx["goal"] = goal
        return ctx

    # ----- event & metrics emitters -----

    def _emit(self, event: Dict[str, Any]) -> None:
        sink = self._reaper_sink
        if callable(sink):
            try:
                sink(event)
            except Exception as _e:
                _log.warning("silent except: %s", _e)

    def _emit_step_event(self, kind: str, step: Step, *, goal_kind: str, extra: Optional[Dict[str, Any]] = None) -> None:
        evt = {
            "kind": kind,
            "ts": UTCNOW().isoformat(),
            "step_id": step.id,
            "goal_id": step.goal_id,
            "goal_kind": goal_kind,
            "name": step.name,
            "status": getattr(step.status, "name", str(step.status)),
            "attempts": int(step.attempts or 0),
            "max_attempts": int(step.max_attempts or 0),
            "extra": dict(extra or {}),
        }
        self._emit(evt)
        try:
            metrics_mod.observe_step_event(evt)
        except Exception as _e:
            _log.warning("silent except: %s", _e)

    def _emit_goal_event(self, kind: str, goal: Goal, *, extra: Optional[Dict[str, Any]] = None) -> None:
        evt = {
            "kind": kind,
            "ts": UTCNOW().isoformat(),
            "goal_id": goal.id,
            "goal_kind": goal.kind,
            "status": getattr(goal.status, "name", str(goal.status)),
            "priority": getattr(goal.priority, "name", str(goal.priority)),
            "title": goal.title,
            "deadline": goal.deadline.isoformat() if goal.deadline else None,
            "extra": dict(extra or {}),
            "goal": goal,  # included for latency histogram when terminal
        }
        self._emit(evt)
        try:
            metrics_mod.observe_goal_event(evt)
        except Exception as _e:
            _log.warning("silent except: %s", _e)


__all__ = ["StepRunner"]
