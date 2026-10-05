# goals/handlers/characterize.py
#
# Run 13 gate-passer 3 (DEMO_RUN_2026-08-19 §5 item 3): characterization goals —
# questions about Orrin's OWN behaviour whose answer is a prediction checked
# against his telemetry, out of sample. This is the grounded close-out the Run 12
# plan specified (Slice 1C.2: "answered iff a prediction resolved against ground
# truth") but nothing ever minted: all 12 Run-12 claims files had prediction=null.
#
#   hypothesize: from the resource telemetry so far, find the function whose runs
#                are followed by the largest mean rise in a metric (frequent ones
#                only — a 6-occurrence "driver" never recurs, Run 12 data), and
#                write it to claims.json as a pending prediction.
#   check:       wait for FRESH samples (rows after the hypothesis), then test the
#                same claim on them alone. Correct iff the driver's mean rise on the
#                new rows beats the new rows' baseline. The claim can fail — on the
#                Run 12 telemetry the top driver held in 5 of 6 splits, failed once.
#
# Symbolic only; reads brain/paths' telemetry file (path constant only — no brain
# cognition import, per the daemon membrane). The brain side scores the resolved
# prediction at close-out (epistemic_closeout.score_answer_structured).
from __future__ import annotations

import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from brain.core.runtime_log import get_logger

from ..model import Goal, Step, Status
from .base import BaseGoalHandler, HandlerContext, default_artifacts_dir, new_step

_log = get_logger(__name__)

METRIC_LABELS = {"rss_mb": "memory use (RSS)", "cpu_util": "CPU load"}

MIN_TRAIN_ROWS = 300      # telemetry needed before a hypothesis is worth forming
MIN_TRAIN_OCC = 30        # a driver must have run this often in the training rows
MIN_TEST_OCC = 10         # ...and this often in the fresh rows to be testable
MAX_GAP_S = 120.0         # consecutive samples further apart than this are not a delta
MAX_WAIT_S = 6 * 3600.0   # after this, an untestable prediction resolves inconclusive
_CHECK_EVERY_S = 60.0

_last_check: Dict[str, float] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _telemetry_path(ctx: HandlerContext) -> Path:
    explicit = ctx.get("resource_history_path")
    if explicit:
        return Path(explicit)
    from brain.paths import RESOURCE_HISTORY_FILE
    return Path(RESOURCE_HISTORY_FILE)


def load_rows(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if isinstance(r, dict) and isinstance(r.get("ts"), (int, float)):
                    rows.append(r)
    except OSError:
        return []
    return rows


def driver_stats(rows: List[Dict[str, Any]], metric: str,
                 min_occ: int) -> Tuple[Dict[str, Tuple[int, float]], Optional[float]]:
    """{last_fn: (n, mean delta of `metric` on the sample after it ran)} for drivers
    seen >= min_occ times, plus the baseline mean delta over all usable pairs."""
    by: Dict[str, List[float]] = {}
    every: List[float] = []
    for a, b in zip(rows, rows[1:]):
        fn = b.get("last_fn")
        va, vb = a.get(metric), b.get(metric)
        if not fn or not isinstance(va, (int, float)) or not isinstance(vb, (int, float)):
            continue
        if float(b["ts"]) - float(a["ts"]) > MAX_GAP_S:
            continue
        d = float(vb) - float(va)
        by.setdefault(str(fn), []).append(d)
        every.append(d)
    stats = {k: (len(v), statistics.fmean(v)) for k, v in by.items() if len(v) >= min_occ}
    return stats, (statistics.fmean(every) if every else None)


def hypothesize(rows: List[Dict[str, Any]], metric: str) -> Optional[Dict[str, Any]]:
    stats, base = driver_stats(rows, metric, MIN_TRAIN_OCC)
    if not stats or base is None:
        return None
    driver, (n, mean) = max(stats.items(), key=lambda kv: kv[1][1])
    if mean <= base:
        return None
    return {"driver": driver, "n": n, "mean": round(mean, 4), "base": round(base, 4)}


def test_hypothesis(rows: List[Dict[str, Any]], metric: str,
                    driver: str) -> Optional[Dict[str, Any]]:
    """Out-of-sample test on `rows` (fresh only). None when the driver has not
    recurred often enough to judge."""
    stats, base = driver_stats(rows, metric, MIN_TEST_OCC)
    if driver not in stats or base is None:
        return None
    n, mean = stats[driver]
    return {"n": n, "mean": round(mean, 4), "base": round(base, 4), "correct": mean > base}


class CharacterizeHandler(BaseGoalHandler):
    """goal.spec: {"metric": "rss_mb"|"cpu_util", "question": str}."""
    kind: str = "characterize"

    def plan(self, goal: Goal, ctx: HandlerContext) -> List[Step]:
        h = new_step(goal.id, "hypothesize", {"op": "hypothesize"})
        c = new_step(goal.id, "check prediction", {"op": "check"}, deps=[h.id])
        return [h, c]

    def _dir(self, ctx: HandlerContext, goal: Goal) -> Path:
        d = Path(default_artifacts_dir(ctx)).resolve() / goal.id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def tick(self, goal: Goal, step: Step, ctx: HandlerContext) -> Optional[Step]:
        if step.started_at is None:
            step.started_at = _now()
            step.status = Status.RUNNING
        spec = goal.spec or {}
        metric = str(spec.get("metric") or "rss_mb")
        label = METRIC_LABELS.get(metric, metric)
        claims_path = self._dir(ctx, goal) / "claims.json"
        try:
            if step.action.get("op") == "hypothesize":
                return self._hypothesize(goal, step, ctx, metric, label, claims_path)
            return self._check(goal, step, ctx, metric, label, claims_path)
        except Exception as exc:
            step.attempts = min(int(step.max_attempts or 1), int(step.attempts or 0) + 1)
            step.last_error = f"{type(exc).__name__}: {exc}"
            step.status = Status.FAILED if step.attempts >= (step.max_attempts or 1) else Status.READY
            if step.status == Status.FAILED:
                step.finished_at = _now()
            step.started_at = None
            return step

    def _hypothesize(self, goal: Goal, step: Step, ctx: HandlerContext, metric: str,
                     label: str, claims_path: Path) -> Step:
        rows = load_rows(_telemetry_path(ctx))
        if len(rows) < MIN_TRAIN_ROWS:
            raise ValueError(f"only {len(rows)} telemetry rows (< {MIN_TRAIN_ROWS})")
        h = hypothesize(rows, metric)
        if h is None:
            raise ValueError(f"no function's runs are followed by an above-baseline {metric} rise")
        question = str((goal.spec or {}).get("question") or f"What makes my {label} climb?")
        claim = f"My {label} rises after {h['driver']} runs"
        claims = {
            "question": question[:200],
            "subject_terms": [],
            "entities": [label, h["driver"]],
            "relations": [{"subject": label, "predicate": "rises after",
                           "object": f"{h['driver']} runs", "source": "resource_history"}],
            "prediction": {
                "claim": claim,
                "checkable_against": f"resource_history:{metric}:last_fn",
                "confidence": 0.6,
                "resolved": False,
                "correct": None,
                "driver": h["driver"],
                "made_at_ts": float(rows[-1]["ts"]),        # fresh = samples after this
                "hypothesized_at": time.time(),             # the wait clock (wall time)
                "train": h,
            },
            "sources": [{"src": "resource_history.jsonl"}],
            "ts": _now().isoformat(),
        }
        claims_path.write_text(json.dumps(claims, indent=2), encoding="utf-8")
        step.status = Status.DONE
        step.finished_at = _now()
        step.attempts = int(step.attempts or 0) + 1
        step.last_error = None
        step.artifacts.append(str(claims_path))
        return step

    def _check(self, goal: Goal, step: Step, ctx: HandlerContext, metric: str,
               label: str, claims_path: Path) -> Step:
        now = time.time()
        if now - _last_check.get(goal.id, 0.0) < _CHECK_EVERY_S:
            return self._defer(step, "waiting for fresh telemetry")
        _last_check[goal.id] = now
        claims = json.loads(claims_path.read_text(encoding="utf-8"))
        pred = claims["prediction"]
        made_at = float(pred["made_at_ts"])
        fresh = [r for r in load_rows(_telemetry_path(ctx)) if float(r["ts"]) > made_at]
        result = test_hypothesis(fresh, metric, str(pred["driver"]))
        if result is None:
            if now - float(pred.get("hypothesized_at") or now) < MAX_WAIT_S:
                return self._defer(step, f"{len(fresh)} fresh rows; driver not yet recurred enough")
            pred.update({"resolved": True, "correct": False,
                         "outcome": f"inconclusive: {pred['driver']} did not recur "
                                    f">= {MIN_TEST_OCC}x in {len(fresh)} fresh samples"})
        else:
            pred.update({"resolved": True, "correct": bool(result["correct"]), "test": result,
                         "outcome": (f"{'held' if result['correct'] else 'failed'} out of sample: "
                                     f"mean {result['mean']:+} after {pred['driver']} "
                                     f"(n={result['n']}) vs baseline {result['base']:+}")})
        claims_path.write_text(json.dumps(claims, indent=2), encoding="utf-8")
        report = self._dir(ctx, goal) / "characterization.md"
        report.write_text(
            f"# {claims['question']}\n\n"
            f"**Hypothesis** (from {pred['train']['n']} prior runs): {pred['claim']}.\n"
            f"Training: mean {pred['train']['mean']:+} vs baseline {pred['train']['base']:+}.\n\n"
            f"**Test** on telemetry recorded after the hypothesis: {pred['outcome']}.\n",
            encoding="utf-8")
        step.status = Status.DONE
        step.finished_at = _now()
        step.attempts = int(step.attempts or 0) + 1
        step.last_error = None
        step.artifacts.append(str(report))
        return step

    def _defer(self, step: Step, reason: str) -> Step:
        step.status = Status.READY
        step.last_error = f"DEFERRED: {reason}"
        step.started_at = None
        return step


__all__ = ["CharacterizeHandler", "hypothesize", "test_hypothesis", "load_rows"]
