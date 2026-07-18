# Run 9 fixes R9-F3/R9-F5 (RUN9_DEEP_ANALYSIS_2026-07-15 Findings 1.3 and 3):
# research steps loaded "the newest JSON in the dir" instead of their expected
# stage artifact — after a successful fetch wrote *_docs.json, a re-tick of
# fetch loaded the docs manifest (no `urls` key) and turned an already-
# successful step into "no URLs to fetch". And _find_prior_memo's topic overlap
# was satisfied by the goal-title scaffold ("more" + "deeply"), so the quantum
# synthesis cited the history memo.

from __future__ import annotations

import json
import os
import time

from goals.model import Goal, Step, Status
from goals.handlers.research import ResearchHandler, _find_prior_memo, _topic_tokens


def _goal(gid: str, title: str) -> Goal:
    return Goal(id=gid, title=title, kind="research", spec={})


# ── R9-F3: stage-scoped artifact loading ──────────────────────────────────────

def test_fetch_retick_loads_search_artifact_not_newest_json(tmp_path):
    g = _goal("g1", "Understand quantum computing more deeply")
    art = tmp_path / "artifacts" / g.id
    art.mkdir(parents=True)

    # A prior successful search wrote its artifact...
    (art / "s_search_search.json").write_text(
        json.dumps({"urls": ["http://example.org/a"], "results": []}), encoding="utf-8")
    # ...and a prior successful fetch wrote the docs manifest LATER (newest file).
    time.sleep(0.02)
    docs = art / "s_fetch_docs.json"
    docs.write_text(json.dumps({"docs": [{"url": "http://example.org/a",
                                          "path": "x", "chars": 3}]}), encoding="utf-8")
    now = time.time()
    os.utime(docs, (now + 5, now + 5))  # guarantee docs is the newest JSON

    fetched = []

    def web_fetch(url, timeout=None):
        fetched.append(url)
        return "body text"

    step = Step(id="s_fetch2", goal_id=g.id, name="fetch sources",
                action={"op": "fetch"}, status=Status.READY)
    out = ResearchHandler().tick(g, step, {"artifacts_dir": str(tmp_path / "artifacts"),
                                           "web_fetch": web_fetch})
    # Pre-fix: loaded s_fetch_docs.json (no "urls") → ValueError("no URLs to fetch").
    assert out.status == Status.DONE, out.last_error
    assert fetched == ["http://example.org/a"]


def test_synthesize_loads_docs_artifact_even_when_search_is_newer(tmp_path):
    g = _goal("g1", "Understand quantum computing more deeply")
    art = tmp_path / "artifacts" / g.id
    art.mkdir(parents=True)
    doc = art / "doc_01.txt"
    doc.write_text("Qubits exploit superposition and entanglement for computation.",
                   encoding="utf-8")
    (art / "s_fetch_docs.json").write_text(
        json.dumps({"docs": [{"url": "http://example.org/a", "path": str(doc),
                              "chars": 60}]}), encoding="utf-8")
    newer = art / "s_search2_search.json"
    newer.write_text(json.dumps({"urls": ["http://example.org/a"]}), encoding="utf-8")
    now = time.time()
    os.utime(newer, (now + 5, now + 5))

    step = Step(id="s_synth", goal_id=g.id, name="synthesize findings",
                action={"op": "synthesize"}, status=Status.READY)
    out = ResearchHandler().tick(g, step, {"artifacts_dir": str(tmp_path / "artifacts")})
    assert out.status == Status.DONE, out.last_error


# ── R9-F5: title scaffold can no longer satisfy the topic-overlap test ────────

def test_boilerplate_titles_share_no_topic_tokens():
    a = _topic_tokens("Understand quantum computing more deeply")
    b = _topic_tokens("Understand world history more deeply")
    assert not (a & b)  # pre-fix: {"more", "deeply"} matched ANY two goals


def test_find_prior_memo_rejects_cross_topic_boilerplate(tmp_path):
    art_base = tmp_path / "artifacts"
    history_dir = art_base / "g_history"
    history_dir.mkdir(parents=True)
    (history_dir / "research_memo.md").write_text(
        "# Understand world history more deeply\n\n"
        "Empires rose and fell; trade routes shaped medieval civilizations.",
        encoding="utf-8")

    quantum = _goal("g_quantum", "Understand quantum computing more deeply")
    exclude = art_base / quantum.id
    exclude.mkdir(parents=True)
    assert _find_prior_memo(art_base, quantum, exclude) is None


def test_find_prior_memo_still_matches_same_subject(tmp_path):
    art_base = tmp_path / "artifacts"
    prior_dir = art_base / "g_quantum_1"
    prior_dir.mkdir(parents=True)
    memo = prior_dir / "research_memo.md"
    memo.write_text(
        "# Understand quantum computing more deeply\n\n"
        "Quantum computing uses qubits, superposition, and entanglement.",
        encoding="utf-8")

    followup = _goal("g_quantum_2", "Understand quantum computing more deeply")
    exclude = art_base / followup.id
    exclude.mkdir(parents=True)
    assert _find_prior_memo(art_base, followup, exclude) == memo
