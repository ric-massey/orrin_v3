"""
Tests for the Life Capsule builder (brain/evidence/life_capsule.py).

The builder is a pure function of the raw data layer, so we point ORRIN_DATA_DIR /
ORRIN_STATE_DIR at a tiny synthetic mind, build a capsule, and assert the capsule is
well-formed: the zip opens, the SQLite tables are populated from the streams, the
metrics are computed, and the action-class taxonomy (R1) tags choices correctly.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import zipfile
from pathlib import Path

import pytest


def _seed_mind(data_dir: Path, state_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "goals").mkdir(parents=True, exist_ok=True)
    (state_dir / "memory" / "wal").mkdir(parents=True, exist_ok=True)

    # events.jsonl — a handful of DECISIONs across two "runs" (cycle resets) so the
    # last-run segmentation is exercised.
    rows = []
    for cyc, choice, act in [
        (0, "generate_intrinsic_goals", False),  # belongs to an OLD run (reset below)
        (998, "look_outward", False),
        (1, "generate_intrinsic_goals", False),  # cycle reset → new run starts here
        (2, "look_outward", False),
        (3, "leave_note", True),
        (4, "research_topic", False),
        (5, "write_tool", True),
    ]:
        rows.append(
            {
                "ts": f"2026-06-20T00:00:{cyc % 60:02d}+00:00",
                "type": "DECISION",
                "payload": {
                    "tick": cyc,
                    "goal": {"id": "g1", "title": "Understand X"},
                    "decision": {
                        "picked": choice,
                        "is_action": act,
                        "candidate_count": 3,
                        "top_candidates": ["a", "b"],
                        "reason": "test",
                    },
                    "tools_used": [],
                    "reward": {"reward_signal": 0.5, "novelty": 0.2, "acceptance_passed": False},
                },
            }
        )
    (data_dir / "events.jsonl").write_text("\n".join(json.dumps(r) for r in rows), "utf-8")

    # telemetry_archive.jsonl — affect series for the new run.
    tel = [{"t": 1781907463.0 + i, "cycle": i, "valence": 0.5, "arousal": 0.3, "distress": 0.1} for i in range(6)]
    (data_dir / "telemetry_archive.jsonl").write_text("\n".join(json.dumps(r) for r in tel), "utf-8")

    # effect_ledger.jsonl — two notes, one a dup (novelty 0).
    eff = [
        {"ts": "2026-06-20T00:00:03Z", "cycle": 3, "kind": "note_novel", "content_hash": "aaa",
         "novelty": 0.8, "significance": 0.5, "goal_id": "g1", "char_len": 200, "dedupe": False},
        {"ts": "2026-06-20T00:00:05Z", "cycle": 5, "kind": "note_novel", "content_hash": "aaa",
         "novelty": 0.0, "significance": 0.0, "goal_id": "g1", "char_len": 200, "dedupe": True},
    ]
    (data_dir / "effect_ledger.jsonl").write_text("\n".join(json.dumps(r) for r in eff), "utf-8")

    (data_dir / "behavior_changes.json").write_text(json.dumps([
        {"when": "2026-06-20T00:00:02+00:00", "pattern": "goal_avoidance",
         "situation": "thinking not doing", "old_action": "x", "new_action": "y", "reason": "z"},
    ]), "utf-8")
    (data_dir / "outcome_metrics.json").write_text(json.dumps([{"date": "2026-06-20", "goals_failed": 1}]), "utf-8")
    (data_dir / "runstate.json").write_text(json.dumps({"clean": True, "ended_at": 1781957501.0}), "utf-8")
    (data_dir / "runtime_lifetime.json").write_text(json.dumps({"born_at": "2026-06-20T00:00:00+00:00"}), "utf-8")
    (data_dir / "relationships.json").write_text(json.dumps(
        {"peer_observer": {"type": "peer", "trust": 0.6, "influence_score": 0.5, "depth": 0.3,
                           "interaction_history": [], "last_interaction_time": "2026-06-20T00:00:00+00:00"}}), "utf-8")

    (state_dir / "goals" / "state.jsonl").write_text(json.dumps(
        {"goal": {"id": "g_1", "title": "Understand X", "kind": "generic", "spec": {},
                  "status": "READY", "tags": ["worldward"], "progress": {"percent": 0.0}}}), "utf-8")
    (state_dir / "memory" / "wal" / "events.jsonl").write_text(json.dumps(
        {"id": "ev1", "ts": "2026-06-20T00:00:00Z", "kind": "note", "content": "a fact"}), "utf-8")


@pytest.fixture()
def capsule(tmp_path, monkeypatch):
    data_dir = tmp_path / "mind"
    state_dir = tmp_path / "state"
    out_dir = tmp_path / "out"
    _seed_mind(data_dir, state_dir)
    monkeypatch.setenv("ORRIN_DATA_DIR", str(data_dir))
    monkeypatch.setenv("ORRIN_STATE_DIR", str(state_dir))
    # Reload paths + the builder so the env overrides take effect. We must restore
    # both sys.modules AND the parent-package attribute on teardown: reloading a
    # submodule (e.g. brain.paths) rebinds it on its parent package (brain), and
    # restoring only sys.modules would leave later `from brain.paths import X`
    # resolving the stale temporary module.
    import importlib

    reload_targets = ("brain.paths", "brain.evidence.life_capsule", "brain.evidence")

    def _snapshot(name):
        parent, _, leaf = name.rpartition(".")
        parent_mod = sys.modules.get(parent) if parent else None
        had = parent_mod is not None and hasattr(parent_mod, leaf)
        return (sys.modules.get(name), parent_mod, leaf, had,
                getattr(parent_mod, leaf, None) if had else None)

    saved = {name: _snapshot(name) for name in reload_targets}
    for name in reload_targets:
        sys.modules.pop(name, None)
    lc = importlib.import_module("brain.evidence.life_capsule")
    path = lc.build_life_capsule("manual", out_dir=out_dir)
    try:
        yield path
    finally:
        for name in reload_targets:
            mod, parent_mod, leaf, had, attr_val = saved[name]
            if mod is not None:
                sys.modules[name] = mod
            else:
                sys.modules.pop(name, None)
            if parent_mod is not None:
                if had:
                    setattr(parent_mod, leaf, attr_val)
                elif hasattr(parent_mod, leaf):
                    delattr(parent_mod, leaf)


def test_capsule_is_wellformed_zip(capsule):
    assert capsule.exists() and capsule.suffix == ".zip"
    with zipfile.ZipFile(capsule) as zf:
        names = zf.namelist()
        assert any(n.endswith("manifest.json") for n in names)
        assert any(n.endswith("database/orrin_life.sqlite") for n in names)
        assert any(n.endswith("EXECUTIVE_SUMMARY.md") for n in names)
        assert any(n.endswith("claims/claims_ledger.json") for n in names)
        assert any(n.endswith("llm/llm_context_summary.md") for n in names)
        assert any(n.endswith("file_hashes.csv") for n in names)


def _load(capsule, suffix):
    with zipfile.ZipFile(capsule) as zf:
        name = next(n for n in zf.namelist() if n.endswith(suffix))
        return zf.read(name)


def test_last_run_segmentation(capsule):
    """Only the post-reset run (5 cycles) should be in the tables, not the old run."""
    manifest = json.loads(_load(capsule, "manifest.json"))
    assert manifest["table_row_counts"]["cycles"] == 5
    assert manifest["build_errors"] == []


def test_sqlite_queryable(capsule, tmp_path):
    raw = _load(capsule, "database/orrin_life.sqlite")
    db = tmp_path / "q.sqlite"
    db.write_bytes(raw)
    conn = sqlite3.connect(str(db))
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM cycles")
        assert cur.fetchone()[0] == 5
        # action-class taxonomy (R1) tagged the productive/communicative acts
        cur.execute("SELECT action_class FROM cycles WHERE choice='leave_note'")
        assert cur.fetchone()[0] == "communicative"
        cur.execute("SELECT action_class FROM cycles WHERE choice='write_tool'")
        assert cur.fetchone()[0] == "productive"
    finally:
        conn.close()


def test_metrics_and_credit(capsule):
    art = json.loads(_load(capsule, "metrics/artifact_summary.json"))
    assert art["logged"] == 2
    assert art["credited_novel"] == 1  # the dup scores 0
    run = json.loads(_load(capsule, "metrics/run_summary.json"))
    # is_action flag caught 2 (leave_note, write_tool); class lens agrees on >=2 outward
    assert run["outward_action_count"] >= 2


def test_classify_action_fallbacks():
    sys.modules.pop("evidence.life_capsule", None)
    import importlib
    lc = importlib.import_module("brain.evidence.life_capsule")
    assert lc.classify_action("leave_note") == "communicative"
    assert lc.classify_action("write_tool") == "productive"
    assert lc.classify_action("look_outward") == "orienting"
    assert lc.classify_action("some_unknown_writer") == "productive"  # heuristic
    assert lc.classify_action(None) == "unknown"
