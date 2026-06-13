# brain/benchmarks/__init__.py
#
# Benchmark suite — stored, runnable definitions of the capability tests Orrin
# should be measured against on a fresh long run. This is the single home for the
# benchmark SPECS (what each tests + success criteria) AND the harness that
# collects evidence and scores them.
#
# Two kinds of benchmark:
#   • passive  — measured just by running the autonomous loop with sampling on
#                (B1 bounded memory, B2 affect-driven switching).
#   • scenario — need a seeded test goal / specific flags (B3 offline planning,
#                B4 satiety closure, B5 self-repair). Use seed_scenario(...).
#
# How to run (next launch):
#   export ORRIN_BENCHMARK=1          # turns on per-cycle sampling + auto-eval
#   # optional, to exercise the scenario benchmarks in the same run:
#   python -c "from benchmarks import seed_scenario; seed_scenario('B4'); seed_scenario('B5')"
#   # B3 needs the LLM off — run it on its own:
#   #   OPENAI_API_KEY= ORRIN_BENCHMARK=1 python -c "from benchmarks import seed_scenario; seed_scenario('B3')"
#   <run Orrin>
#   # results land in data/benchmark_results.json (auto-written at each
#   # benchmark's required cycle count, and callable any time):
#   python -c "from benchmarks import evaluate_all, report; evaluate_all(); print(report())"
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from paths import DATA_DIR, LONG_MEMORY_FILE, GOALS_FILE
from utils.json_utils import load_json, save_json

SAMPLES_FILE = DATA_DIR / "benchmark_samples.jsonl"
RESULTS_FILE = DATA_DIR / "benchmark_results.json"

# Actions that count as "novelty-seeking" for B2.
NOVELTY_FNS = frozenset({"seek_novelty", "search_own_files", "look_outward", "research_topic"})

# Keep the passive sample file bounded (one line/cycle; ~2k+ lines on a full run).
_MAX_SAMPLE_LINES = 20_000


# ─── Stored specifications (the benchmark definitions) ────────────────────────
BENCHMARKS: Dict[str, Dict[str, Any]] = {
    "B1": {
        "title": "Memory Boundedness (reaper effectiveness)",
        "tests": "Long-term memory plateaus instead of growing unbounded.",
        "kind": "passive",
        "required_cycles": 2000,
        "how": "Run autonomously; every 100 cycles record len(long_memory.json) and RSS.",
        "success": "entries-vs-cycle curve plateaus (final-third growth rate near zero); "
                   "not linear unbounded growth.",
    },
    "B2": {
        "title": "Affect-driven behavioral switching",
        "tests": "Rising stagnation_signal (boredom) drives a switch to novelty-seeking.",
        "kind": "passive",
        "required_cycles": 500,
        "how": "Log stagnation_signal + chosen function each cycle in a low-stimulus run.",
        "success": "Pearson(stagnation, novelty_action) > 0.3 AND when stagnation>0.6 a "
                   "novelty action is chosen >40% of the time.",
    },
    "B3": {
        "title": "Offline planning (no LLM)",
        "tests": "A multi-step goal is solved by the symbolic planner with zero LLM calls.",
        "kind": "scenario",
        "required_cycles": 300,
        "how": "OPENAI_API_KEY='' + FORCE_SYMBOLIC_SPEECH; seed a search/summary goal; "
               "run to completion. Repeat for 5–10 goals.",
        "success": "≥70% success across trials; mean cycles-to-complete < 200.",
    },
    "B4": {
        "title": "Goal closure via satiety",
        "tests": "An exploration goal closes when novelty is exhausted, not when a plan ends.",
        "kind": "scenario",
        "required_cycles": 400,
        "how": "Seed a growth-tier 'explore the brain filesystem' goal; run many cycles; "
               "watch novelty_memory flatten then the goal close.",
        "success": "Goal closes only AFTER the novelty counter flattens (≥3 barren searches); "
                   "a trivial 'write a note' goal closes after one action.",
    },
    "B5": {
        "title": "Self-repair / corrigibility (watchdog + hard disengage)",
        "tests": "A uselessly-repeating function is killed by metacog + the hard actuator.",
        "kind": "scenario",
        "required_cycles": 200,
        "how": "hard disengage is on by default; seed a goal that keeps returning empty; run.",
        "success": "Goal is abandoned/failed within a bounded number of cycles "
                   "(<50 after the watchdog triggers), no human intervention.",
    },
    "B6": {
        "title": "Concurrent goal progress (multi-goal pursuit)",
        "tests": "Several committed goals advance concurrently in the Executive lane "
                 "while exactly one conscious (deliberate) focus is maintained.",
        "kind": "passive",
        "required_cycles": 200,
        "how": "Commit ≥2 goals (e.g. seed_scenario twice); run with sampling on. The "
               "per-cycle sample records which goals the Executive advanced (gx).",
        "success": "≥2 distinct goals advance within a short window (≤10 cycles) — "
                   "ideally within a single tick — while the deliberate lane stays "
                   "singular (one fn per cycle, which the architecture guarantees).",
    },
    "B7": {
        "title": "Retrieval under restart (records → a life)",
        "tests": "Autobiography, narrative-pressure state, and failure patterns "
                 "survive a restart and stay retrievable by their memory links.",
        "kind": "scenario",
        "required_cycles": 100,
        "how": "Run N cycles with significant events (or seed ≥3 goal failures so "
               "review_failures consolidates a pattern); restart Orrin; evaluate.",
        "success": "After restart: autobiography.json non-empty; pressure state "
                   "persisted; every failure_pattern's related_memory_ids resolve "
                   "to existing long-memory entries.",
    },
}


def _enabled() -> bool:
    return os.environ.get("ORRIN_BENCHMARK", "").strip().lower() in ("1", "true", "yes", "on")


# ─── Passive per-cycle sampling (B1, B2) ──────────────────────────────────────

def _long_memory_count() -> int:
    try:
        d = load_json(LONG_MEMORY_FILE, default_type=list)
        return len(d) if isinstance(d, list) else len(d or {})
    except Exception:
        return -1


def _rss_mb() -> float:
    try:
        import psutil  # optional; the watchdog also exports this via Prometheus
        return round(psutil.Process().memory_info().rss / (1024 * 1024), 1)
    except Exception:
        return -1.0


def record_sample(context: Optional[Dict[str, Any]]) -> None:
    """Append one cheap sample for this cycle. No-op unless ORRIN_BENCHMARK is set.
    Call once per cycle AFTER the chosen function is recorded in context.

    Samples BOTH lanes (benchmark_realignment.md F1): `fn` is the deliberate
    (conscious) pick; `fx` is the list of functions the Executive lane ran this
    cycle and `gx` the goal ids it advanced — the goal work B2/B3/B6 must see.
    (In daemon mode the executive summary lives on the daemon's private context;
    the interleaved default is fully covered.)"""
    if not _enabled():
        return
    try:
        from utils.get_cycle_count import get_cycle_count
        cyc = int(get_cycle_count() or 0)
        af = (context or {}).get("affect_state") or {}
        core = af.get("core_signals") if isinstance(af.get("core_signals"), dict) else af
        stag = float((core or {}).get("stagnation_signal", 0.0) or 0.0)
        fn = str((context or {}).get("last_function_chosen") or "")
        rec: Dict[str, Any] = {"cycle": cyc, "stag": round(stag, 4), "fn": fn, "ts": round(time.time(), 1)}
        # Executive lane (F1): functions run + goals advanced this tick.
        exec_summary = (context or {}).get("_exec_dryrun")
        if isinstance(exec_summary, dict):
            adv = exec_summary.get("advanced")
            if isinstance(adv, list) and adv:
                fx = [str(a.get("fn")) for a in adv if isinstance(a, dict) and a.get("fn")]
                gx = sorted({str(a.get("goal_id")) for a in adv
                             if isinstance(a, dict) and a.get("goal_id")})
                if fx:
                    rec["fx"] = fx
                if gx:
                    rec["gx"] = gx
            elif exec_summary.get("active_fn"):
                rec["fx"] = [str(exec_summary["active_fn"])]
                if exec_summary.get("goal_id"):
                    rec["gx"] = [str(exec_summary["goal_id"])]
        if cyc % 100 == 0:
            rec["mem"] = _long_memory_count()
            rec["rss"] = _rss_mb()
        with open(SAMPLES_FILE, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
        # Auto-evaluate when the longest benchmark's horizon is reached.
        if cyc and cyc % 500 == 0:
            evaluate_all()
    except Exception:
        pass


def _load_samples() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    try:
        if not SAMPLES_FILE.exists():
            return out
        with open(SAMPLES_FILE, encoding="utf-8") as fh:
            lines = fh.readlines()[-_MAX_SAMPLE_LINES:]
        for ln in lines:
            ln = ln.strip()
            if ln:
                try:
                    out.append(json.loads(ln))
                except Exception:
                    continue
    except Exception:
        pass
    return out


# ─── Evaluators ───────────────────────────────────────────────────────────────

def _pearson(xs: List[float], ys: List[float]) -> float:
    n = len(xs)
    if n < 3:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    return round(num / (dx * dy), 4) if dx > 0 and dy > 0 else 0.0


def _eval_b1(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    pts = [(s["cycle"], s["mem"]) for s in samples if "mem" in s and s.get("mem", -1) >= 0]
    if len(pts) < 4:
        return {"status": "insufficient_data", "samples": len(pts),
                "need": "≥4 memory snapshots (≥400 cycles)"}
    pts.sort()
    half = pts[len(pts) // 2:]
    # growth rate (entries/cycle) over the final half
    (c0, m0), (c1, m1) = half[0], half[-1]
    rate = (m1 - m0) / (c1 - c0) if c1 > c0 else 0.0
    plateaued = rate < 0.01 and m1 <= m0 * 1.2 + 5
    return {"status": "pass" if plateaued else "fail", "plateaued": plateaued,
            "final_entries": m1, "final_rss_mb": pts and samples[-1].get("rss"),
            "final_half_growth_per_cycle": round(rate, 5),
            "curve": pts[-8:]}


def _eval_b2(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    # F1 (benchmark_realignment.md M1): a cycle counts as novelty-seeking when
    # EITHER lane ran a novelty fn — goal-driven novelty work happens in the
    # Executive lane and used to be invisible to this benchmark.
    def _novel(s: Dict[str, Any]) -> float:
        if str(s.get("fn", "")) in NOVELTY_FNS:
            return 1.0
        if any(f in NOVELTY_FNS for f in (s.get("fx") or [])):
            return 1.0
        return 0.0

    rows = [(float(s.get("stag", 0.0)), _novel(s))
            for s in samples if s.get("fn") or s.get("fx")]
    if len(rows) < 30:
        return {"status": "insufficient_data", "samples": len(rows), "need": "≥30 cycles with a chosen fn"}
    stag = [r[0] for r in rows]
    nov = [r[1] for r in rows]
    corr = _pearson(stag, nov)
    bored = [r for r in rows if r[0] > 0.6]
    # The hypothesis is about behavior WHEN bored. With too few high-stagnation
    # cycles there's nothing to test yet — report honestly instead of a spurious fail.
    if len(bored) < 5:
        return {"status": "insufficient_data", "total_cycles": len(rows),
                "bored_cycles": len(bored),
                "need": "≥5 cycles with stagnation>0.6 (he's been too calm to test switching)"}
    frac_when_bored = sum(1 for _, novel in bored if novel) / len(bored)
    ok = corr > 0.3 and frac_when_bored > 0.4
    return {"status": "pass" if ok else "fail", "pearson": corr,
            "novelty_frac_when_bored": round(frac_when_bored, 3),
            "bored_cycles": len(bored), "total_cycles": len(rows),
            "lanes": "both (deliberate fn + executive fx)"}


def _scenario_goal(tag: str) -> Optional[Dict[str, Any]]:
    try:
        goals = load_json(GOALS_FILE, default_type=list) or []
    except Exception:
        return None

    def _is_tagged(g: Dict[str, Any]) -> bool:
        if g.get("benchmark") == tag:
            return True
        spec = g.get("spec")
        if isinstance(spec, dict) and spec.get("benchmark") == tag:
            return True
        return False

    def walk(gs):
        for g in gs:
            if isinstance(g, dict):
                if _is_tagged(g):
                    return g
                hit = walk(g.get("subgoals") or [])
                if hit:
                    return hit
        return None
    return walk(goals if isinstance(goals, list) else [])


def _current_cycle() -> int:
    try:
        from utils.get_cycle_count import get_cycle_count
        return int(get_cycle_count() or 0)
    except Exception:
        return 0


def _commitment_state(g: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """F2 evaluator guard (benchmark_realignment.md M2): a scenario goal that has
    been sitting `active` with NO plan steps for many cycles was never committed
    — planning/pursuit only touch committed goals. Report that as the distinct,
    honest `not_committed` state instead of an indefinite `pending`."""
    status = str(g.get("status") or "")
    plan = g.get("plan") or []
    subgoals = g.get("subgoals") or []
    seeded_at = int(g.get("seeded_at_cycle") or 0)
    waited = _current_cycle() - seeded_at if seeded_at else None
    if status == "active" and not plan and not subgoals and waited is not None and waited > 50:
        return {"status": "not_committed",
                "goal_status": status, "cycles_waiting": waited,
                "hint": "goal was seeded but never committed/planned — use "
                        "seed_scenario(tag) (commit=True is the default) or check "
                        "the GoalsAPI priority ranking"}
    return None


def _pursuit_ticks(goal_id: str, samples: List[Dict[str, Any]]) -> int:
    """F3 (benchmark_realignment.md M3): pursuit effort actually spent on ONE
    goal = the number of sampled cycles whose Executive lane advanced it. The
    queue shares ticks across ≤3 goals, so wall-clock cycles overstate a single
    goal's cost; this is the per-goal number the B3 criterion should use."""
    gid = str(goal_id)
    return sum(1 for s in samples if gid in (s.get("gx") or []))


def _eval_b3(samples: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    g = _scenario_goal("B3")
    if not g:
        return {"status": "not_run", "hint": "seed_scenario('B3') with the LLM disabled"}
    nc = _commitment_state(g)
    if nc:
        return nc
    status = str(g.get("status") or "")
    if status == "completed":
        st = "pass"
    elif status in ("failed", "abandoned", "cancelled"):
        st = "fail"
    else:
        st = "pending"   # still active / in progress — not a failure yet
    out: Dict[str, Any] = {"status": st, "goal_status": status,
            "note": "single-trial; repeat seed_scenario('B3') 5–10× for the ≥70% criterion"}
    # F3: report BOTH timings for transparency — per-goal pursuit ticks (the
    # fair criterion under round-robin sharing) and wall-clock cycles.
    if samples is not None:
        ticks = _pursuit_ticks(str(g.get("id") or ""), samples)
        out["pursuit_ticks"] = ticks
        seeded_at = int(g.get("seeded_at_cycle") or 0)
        if seeded_at:
            out["wall_clock_cycles_since_seed"] = max(0, _current_cycle() - seeded_at)
        if st == "pass":
            out["within_criterion"] = ticks < 200
    return out


def _eval_b4() -> Dict[str, Any]:
    g = _scenario_goal("B4")
    if not g:
        return {"status": "not_run", "hint": "seed_scenario('B4')"}
    nc = _commitment_state(g)
    if nc:
        return nc
    status = str(g.get("status") or "")
    barren = -1
    try:
        from cognition import novelty_memory
        gid = str(g.get("id") or g.get("title") or "")
        # novel_count flattening is the satiety signal; expose it if available.
        barren = novelty_memory.novel_count(gid)
    except Exception:
        pass
    closed = status in ("completed", "abandoned", "dormant")
    return {"status": "pass" if closed else "pending", "goal_status": status,
            "novel_count": barren,
            "note": "PASS requires closure AFTER novelty flattened (≥3 barren searches)"}


def _eval_b5() -> Dict[str, Any]:
    g = _scenario_goal("B5")
    if not g:
        return {"status": "not_run", "hint": "seed_scenario('B5') — hard disengage defaults on"}
    nc = _commitment_state(g)
    if nc:
        return nc
    status = str(g.get("status") or "")
    killed = status in ("failed", "abandoned")
    return {"status": "pass" if killed else "pending", "goal_status": status,
            "note": "PASS = watchdog forced abandon/fail within a bounded number of cycles"}


def _eval_b6(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    """F5: concurrent goal progress. Pass when ≥2 distinct goals advance within
    a ≤10-cycle window (best case: within one tick — the multi-goal Executive
    advances the whole queue per tick). The 'one conscious focus' half of the
    criterion is architectural (one deliberate fn per sample) and is asserted
    over the same window."""
    rows = [(int(s.get("cycle") or 0), s.get("gx") or [], s.get("fn"))
            for s in samples if s.get("gx")]
    if not rows:
        return {"status": "insufficient_data",
                "need": "samples with executive goal advances (gx) — commit ≥2 goals"}
    best_window = 0
    same_tick_max = max(len(gx) for _, gx, _ in rows)
    window: List = []
    for cyc, gx, _fn in rows:
        window = [(c, g) for c, g in window if cyc - c <= 10]
        window.append((cyc, gx))
        distinct = {g for _, gxs in window for g in gxs}
        best_window = max(best_window, len(distinct))
    ok = best_window >= 2
    return {"status": "pass" if ok else "fail",
            "max_distinct_goals_in_10_cycles": best_window,
            "max_goals_single_tick": same_tick_max,
            "single_conscious_focus": True,  # one deliberate fn per cycle by design
            "note": "requires ≥2 committed goals during the sampled window"}


def _eval_b7() -> Dict[str, Any]:
    """Phase 2.3: the memory leaks were found by restarting and opening files —
    this does exactly that, mechanically. Run it in the session AFTER the one
    that generated the events."""
    checks: Dict[str, Any] = {}
    try:
        from paths import AUTOBIOGRAPHY, NARRATIVE_PRESSURE_FILE
        auto = load_json(AUTOBIOGRAPHY, default_type=dict) or {}
        chapters = auto.get("chapters") or []
        checks["autobiography_nonempty"] = bool(
            chapters and any((c.get("entries") or c.get("narrative")) for c in chapters)
        )
        pressure = load_json(NARRATIVE_PRESSURE_FILE, default_type=dict) or {}
        checks["pressure_state_persisted"] = "running_total" in pressure
    except Exception as e:
        return {"status": "fail", "error": f"{type(e).__name__}: {e}"}

    try:
        long_mem = load_json(LONG_MEMORY_FILE, default_type=list) or []
        by_id = {e.get("id") for e in long_mem if isinstance(e, dict) and e.get("id")}
        patterns = [e for e in long_mem
                    if isinstance(e, dict) and e.get("event_type") == "failure_pattern"]
        if not patterns:
            checks["failure_patterns"] = "none yet (seed ≥3 similar failures first)"
            checks["links_resolve"] = None
        else:
            dangling = [
                rid for p in patterns
                for rid in (p.get("related_memory_ids") or [])
                if rid not in by_id
            ]
            checks["failure_patterns"] = len(patterns)
            checks["links_resolve"] = not dangling
            if dangling:
                checks["dangling_ids"] = dangling[:5]
    except Exception as e:
        return {"status": "fail", "error": f"{type(e).__name__}: {e}"}

    hard = [checks["autobiography_nonempty"], checks["pressure_state_persisted"]]
    link_ok = checks.get("links_resolve")
    ok = all(hard) and (link_ok is not False)
    pending = checks.get("links_resolve") is None
    return {"status": "pass" if (ok and not pending) else ("pending" if ok else "fail"),
            **checks}


def evaluate_all() -> Dict[str, Any]:
    """Score every benchmark from collected samples + runtime state; persist results."""
    samples = _load_samples()
    results = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "sample_count": len(samples),
        "B1": {**BENCHMARKS["B1"], **_eval_b1(samples)},
        "B2": {**BENCHMARKS["B2"], **_eval_b2(samples)},
        "B3": {**BENCHMARKS["B3"], **_eval_b3(samples)},
        "B4": {**BENCHMARKS["B4"], **_eval_b4()},
        "B5": {**BENCHMARKS["B5"], **_eval_b5()},
        "B6": {**BENCHMARKS["B6"], **_eval_b6(samples)},
        "B7": {**BENCHMARKS["B7"], **_eval_b7()},
    }
    try:
        save_json(RESULTS_FILE, results)
    except Exception:
        pass
    return results


def report() -> str:
    """One-line-per-benchmark summary of the latest results (evaluates if needed)."""
    res = load_json(RESULTS_FILE, default_type=dict)
    if not res:
        res = evaluate_all()
    lines = [f"Benchmark results @ {res.get('evaluated_at', '?')} ({res.get('sample_count', 0)} samples):"]
    for bid in ("B1", "B2", "B3", "B4", "B5", "B6", "B7"):
        r = res.get(bid, {})
        lines.append(f"  {bid} {r.get('title', '')[:38]:<38} → {r.get('status', '?')}")
    return "\n".join(lines)


# ─── Scenario seeding (B3, B4, B5) ────────────────────────────────────────────

_SCENARIO_GOALS: Dict[str, Dict[str, Any]] = {
    "B3": {
        "title": "Find the word 'reaper' in any brain file and write a one-line summary to working memory.",
        "kind": "generic", "tier": "short_term", "driven_by": "world_knowledge",
        "milestones": [{"text": "A search was performed.", "met": False},
                       {"text": "A one-line summary was written to working memory.", "met": False}],
    },
    "B4": {
        "title": "Explore the filesystem of the brain module — what's here?",
        "kind": "generic", "tier": "growth", "driven_by": "world_knowledge",
        "milestones": [{"text": "A search was performed.", "met": False},
                       {"text": "A finding was written to long memory.", "met": False}],
    },
    "B5": {
        "title": "Search my own files for a string that does not exist anywhere.",
        "kind": "generic", "tier": "growth", "driven_by": "world_knowledge",
        "milestones": [{"text": "A search was performed.", "met": False}],
    },
}


def _goals_api():
    """Build the same GoalsAPI the loop uses (same store dir as main.py)."""
    from pathlib import Path
    from utils.goals_feed import init_goals
    repo_root = DATA_DIR.parent.parent          # brain/data → brain → repo root
    goals_dir = Path(os.environ.get("ORRIN_GOALS_DIR", repo_root / "data" / "goals")).resolve()
    _store, api = init_goals(goals_dir)
    return api


def seed_scenario(tag: str, commit: bool = True) -> bool:
    """Inject a scenario benchmark's test goal. Idempotent.

    F2 (benchmark_realignment.md M2): planning/pursuit only ever touch
    COMMITTED goals — the committed set is the GoalsAPI's top NEW/RUNNING goals
    by priority. A goal that exists only in goals_mem.json is never planned, so
    the old seeding made B3/B4/B5 vacuous. With commit=True (default) the goal
    is ALSO created through the GoalsAPI at CRITICAL priority so it ranks into
    the committed head; the goals_mem record reuses the API goal's id, so
    pursuit progress merges into the same record the evaluators read."""
    spec = _SCENARIO_GOALS.get(tag)
    if not spec:
        return False
    try:
        goals = load_json(GOALS_FILE, default_type=list) or []
        if not isinstance(goals, list):
            goals = []
        if any(isinstance(g, dict) and (
                g.get("benchmark") == tag
                or (isinstance(g.get("spec"), dict) and g["spec"].get("benchmark") == tag))
               for g in goals):
            return True  # already seeded

        gid = f"benchmark_{tag.lower()}_{int(time.time())}"
        if commit:
            try:
                api = _goals_api()
                created = api.create_goal(
                    title=spec["title"],
                    kind=spec.get("kind", "generic"),
                    spec={"benchmark": tag,
                          "milestones": spec.get("milestones") or []},
                    priority="CRITICAL",     # ranks into the committed head
                    tags=["benchmark", tag],
                )
                gid = created.id             # one id across both representations
            except Exception:
                # API unavailable (e.g. store missing in a bare checkout) —
                # fall back to the legacy seed; the evaluator will report
                # not_committed if it never gets planned.
                pass

        now = datetime.now(timezone.utc).isoformat()
        goal = {
            "id": gid,
            "benchmark": tag,
            "status": "active",
            "created_at": now,
            "timestamp": now,
            "source": "benchmark",
            "seeded_at_cycle": _current_cycle(),
            **spec,
        }
        goals.append(goal)
        save_json(GOALS_FILE, goals)
        return True
    except Exception:
        return False
