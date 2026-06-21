# brain/symbolic/benchmark.py
# Symbolic intelligence benchmark — a fixed test suite for tracking reasoning
# performance over time without LLM involvement.
#
# Each test case has:
#   query            — the input question / statement
#   domain           — expected symbolic domain
#   expected_source  — "rule" | "analogy" | "symbolic_search" | "any_symbolic"
#   content_hint     — a keyword that should appear in a correct answer (optional)
#   description      — what this test is checking
#
# Scoring per test:
#   resolved_symbolically → +1.0
#   correct source type   → +0.5 bonus
#   content_hint matched  → +0.5 bonus
#   max per test = 2.0; normalised to 0–1 across all tests
#
# Results written to data/benchmark_history.json (rolling 180 days).
# Entry point: run_benchmark() → {score, passed, total, domain_scores, timestamp}
# Called from dream_cycle every 5th cycle.
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

BENCHMARK_FILE = DATA_DIR / "benchmark_history.json"

# ─── Test suite ───────────────────────────────────────────────────────────────
# Expand this list to add new tests. Keep tests stable across versions so the
# trend is meaningful. Domain research areas from the actual knowledge base.

_TEST_SUITE: List[Dict] = [
    # ── Cognitive / meta ──────────────────────────────────────────────────────
    {
        "id": "bm_cog_01",
        "query": "how does exploration_drive drive exploration in a learning system?",
        "domain": "COGNITIVE",
        "expected_source": "any_symbolic",
        "content_hint": "exploration_drive",
        "description": "Core causal relationship: exploration_drive → exploration",
    },
    {
        "id": "bm_cog_02",
        "query": "what happens when prediction error is high in a domain?",
        "domain": "COGNITIVE",
        "expected_source": "any_symbolic",
        "content_hint": "predict",
        "description": "Prediction-error feedback loop",
    },
    {
        "id": "bm_cog_03",
        "query": "when should the system defer to LLM instead of symbolic reasoning?",
        "domain": "COGNITIVE",
        "expected_source": "any_symbolic",
        "content_hint": None,
        "description": "Meta-routing self-knowledge",
    },
    # ── Planning ──────────────────────────────────────────────────────────────
    {
        "id": "bm_plan_01",
        "query": "how do I break a complex goal into smaller steps?",
        "domain": "PLANNING",
        "expected_source": "any_symbolic",
        "content_hint": "step",
        "description": "Goal decomposition heuristic",
    },
    {
        "id": "bm_plan_02",
        "query": "what should I do when I'm blocked on a milestone?",
        "domain": "PLANNING",
        "expected_source": "any_symbolic",
        "content_hint": None,
        "description": "Obstacle-handling strategy",
    },
    # ── Technical ────────────────────────────────────────────────────────────
    {
        "id": "bm_tech_01",
        "query": "how do I debug an import error in python?",
        "domain": "TECHNICAL",
        "expected_source": "any_symbolic",
        "content_hint": "import",
        "description": "Technical debugging pattern",
    },
    {
        "id": "bm_tech_02",
        "query": "what causes a system process to become unresponsive?",
        "domain": "TECHNICAL",
        "expected_source": "any_symbolic",
        "content_hint": None,
        "description": "Causal technical diagnosis",
    },
    # ── Emotional / Social ────────────────────────────────────────────────────
    {
        "id": "bm_emo_01",
        "query": "why does impasse_signal increase when a goal is blocked repeatedly?",
        "domain": "EMOTIONAL",
        "expected_source": "any_symbolic",
        "content_hint": "impasse_signal",
        "description": "Emotion-goal interaction",
    },
    {
        "id": "bm_social_01",
        "query": "how should I respond when a user seems frustrated?",
        "domain": "SOCIAL",
        "expected_source": "any_symbolic",
        "content_hint": None,
        "description": "Social response heuristic",
    },
    # ── Analogy / transfer ────────────────────────────────────────────────────
    {
        "id": "bm_analogy_01",
        "query": "this problem is similar to optimising a search path",
        "domain": "COGNITIVE",
        "expected_source": "any_symbolic",
        "content_hint": None,
        "description": "Structural analogy recognition",
    },
]


# ─── Run benchmark ────────────────────────────────────────────────────────────

def run_benchmark(suite: Optional[List[Dict]] = None) -> Dict:
    """
    Run the test suite through the symbolic reasoning layer (no LLM).
    Returns a result dict and appends to benchmark_history.json.
    """
    tests = suite or _TEST_SUITE
    results: List[Dict] = []
    domain_scores: Dict[str, List[float]] = {}

    for test in tests:
        result = _run_one(test)
        results.append(result)
        d = test.get("domain", "GENERAL")
        domain_scores.setdefault(d, []).append(result["score"])

    total_raw  = sum(r["score"] for r in results)
    max_raw    = len(results) * 2.0
    normalised = round(total_raw / max_raw, 3) if max_raw else 0.0

    per_domain = {
        d: round(sum(ss) / (len(ss) * 2.0), 3)
        for d, ss in domain_scores.items()
    }

    passed = sum(1 for r in results if r["resolved"])

    snapshot = {
        "timestamp":    datetime.now(timezone.utc).isoformat(),
        "score":        normalised,
        "passed":       passed,
        "total":        len(tests),
        "domain_scores": per_domain,
        "results":      results,
    }

    _append_history(snapshot)
    log_activity(
        f"[benchmark] Score={normalised:.2f} ({passed}/{len(tests)} resolved) "
        + " ".join(f"{d}={v:.2f}" for d, v in per_domain.items())
    )
    return snapshot


def _run_one(test: Dict) -> Dict:
    query           = test["query"]
    expected_source = test.get("expected_source", "any_symbolic")
    content_hint    = test.get("content_hint")
    score           = 0.0
    resolved        = False
    actual_source   = "unresolved"
    answer          = ""

    try:
        from brain.symbolic.reasoning_router import route as _route
        ctx = {}
        r = _route(query, context=ctx)
        actual_source = r.get("source", "unresolved")
        answer        = (r.get("answer") or "").lower()
        resolved      = r.get("resolved", False) and actual_source not in ("llm_needed", "suppressed")

        if resolved:
            score += 1.0
            # Source-type bonus
            if expected_source == "any_symbolic" or actual_source == expected_source:
                score += 0.5
            # Content hint bonus
            if content_hint and content_hint.lower() in answer:
                score += 0.5
    except Exception as e:
        actual_source = f"error:{e}"

    return {
        "test_id":       test["id"],
        "domain":        test.get("domain"),
        "resolved":      resolved,
        "actual_source": actual_source,
        "score":         score,
        "answer_head":   answer[:80],
    }


# ─── History & trend ─────────────────────────────────────────────────────────

def _append_history(snapshot: Dict) -> None:
    existing = load_json(BENCHMARK_FILE, default_type=list) or []
    # Keep one entry per day (update today's if it exists)
    today = datetime.now(timezone.utc).isoformat()[:10]
    existing = [e for e in existing if e.get("timestamp", "")[:10] != today]
    existing.append(snapshot)
    save_json(BENCHMARK_FILE, existing[-180:])


def get_benchmark_trend(days: int = 14) -> Dict:
    """Return recent score trend for progress_tracker reporting."""
    history = load_json(BENCHMARK_FILE, default_type=list) or []
    cutoff  = time.time() - days * 86400
    recent  = []
    for e in history:
        try:
            ts = datetime.fromisoformat(e["timestamp"]).timestamp()
            if ts >= cutoff:
                recent.append(e)
        except Exception as _e:
            record_failure("benchmark.get_benchmark_trend", _e)
    if not recent:
        return {"avg_score": 0.0, "trend": "no_data", "entries": 0}

    scores = [e["score"] for e in recent]
    avg    = round(sum(scores) / len(scores), 3)
    trend  = "improving" if len(scores) > 1 and scores[-1] > scores[0] else (
             "declining" if len(scores) > 1 and scores[-1] < scores[0] else "stable")
    return {"avg_score": avg, "trend": trend, "entries": len(recent), "latest": scores[-1]}


def add_test(test: Dict) -> None:
    """Allow runtime addition of new benchmark tests (persisted in a custom file)."""
    custom_file = DATA_DIR / "benchmark_custom.json"
    existing = load_json(custom_file, default_type=list) or []
    if not any(t["id"] == test["id"] for t in existing):
        existing.append(test)
        save_json(custom_file, existing)
