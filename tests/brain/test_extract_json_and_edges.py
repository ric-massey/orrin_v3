# Regression tests for the 2026-06-12 log-spam and memory-graph-churn fixes:
#   • extract_json must reject prose with stray brackets ("[analogy/GENERAL] …")
#     silently, without churning the heal/salvage chain or logging per attempt.
#   • add_edges must cap edges per new entry so a burst of near-identical memories
#     cannot fan out to every recent similar at once.
import logging

import utils.memory_graph as mg
from utils.json_utils import extract_json, _has_plausible_json_start


# ---------- extract_json prose rejection ----------

SYMBOLIC_PROSE = [
    "[analogy/GENERAL] Similar situation (score=0.305): [aspiration] direction",
    "[metacog/pattern] Goal avoidance: 5900 consecutive cycles without action",
    "[signal] impasse_signal is overwhelming",
    "[Chunk: [metacog/pattern] Affective stagnation]",
    "plain prose, no brackets at all",
]

VALID_JSON = [
    ('{"x": 1, "y": [2, 3]}', {"x": 1, "y": [2, 3]}),
    ('[{"a": 1}, {"b": 2}]', [{"a": 1}, {"b": 2}]),
    ('Here is the result:\n```json\n{"ok": true}\n```', {"ok": True}),
    ('prefix text {"k": "v"} suffix', {"k": "v"}),
    ("[1, 2, 3]", [1, 2, 3]),
]


def test_prose_with_stray_brackets_returns_none():
    for p in SYMBOLIC_PROSE:
        assert _has_plausible_json_start(p) is False, p
        assert extract_json(p) is None, p


def test_valid_json_still_parses():
    for raw, expected in VALID_JSON:
        assert _has_plausible_json_start(raw) is True, raw
        assert extract_json(raw) == expected, raw


def test_prose_emits_no_log_spam(caplog):
    with caplog.at_level(logging.DEBUG, logger="utils.json_utils"):
        for p in SYMBOLIC_PROSE:
            extract_json(p)
    # The old code logged "extract_json attempt failed" several times per call.
    assert not any("attempt failed" in r.getMessage() for r in caplog.records)


# ---------- memory-graph edge cap ----------

def test_add_edges_caps_per_entry(monkeypatch):
    written = []
    monkeypatch.setattr(mg, "append_jsonl", lambda path, obj: written.append(obj))
    monkeypatch.setattr(mg, "embeddings_available", lambda: False)  # force Jaccard
    monkeypatch.setattr(mg, "_maybe_compact", lambda p: None)

    text = "goal avoidance consecutive cycles without taking action writing function"
    recent = [{"id": f"m{i}", "content": text} for i in range(20)]
    new = {"id": "new", "content": text + " tool"}

    mg.add_edges(new, recent)

    assert len(written) == mg._MAX_EDGES_PER_ENTRY
    assert all(e["source"] == "new" for e in written)


def test_add_edges_below_cap_writes_all(monkeypatch):
    written = []
    monkeypatch.setattr(mg, "append_jsonl", lambda path, obj: written.append(obj))
    monkeypatch.setattr(mg, "embeddings_available", lambda: False)
    monkeypatch.setattr(mg, "_maybe_compact", lambda p: None)

    text = "goal avoidance consecutive cycles without taking action writing function"
    recent = [{"id": f"m{i}", "content": text} for i in range(3)]  # fewer than the cap
    mg.add_edges({"id": "new", "content": text + " tool"}, recent)

    assert len(written) == 3
