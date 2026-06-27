# Tests for the data-hygiene fixes:
#   • cap_jsonl bounds append-only telemetry logs (events.jsonl / trace.jsonl)
#   • action_reward_ema writes to brain/data (paths.DATA_DIR), not repo-root data/
#   • legacy reward-EMA files are migrated once, then removed
import json

import brain.paths as paths
from brain.utils.json_utils import cap_jsonl
import brain.control_signals.reward_signals.action_reward_ema as aem


def test_cap_jsonl_trims_to_max_lines(tmp_path):
    p = tmp_path / "events.jsonl"
    with p.open("w", encoding="utf-8") as f:
        for i in range(500):
            f.write(json.dumps({"i": i, "pad": "x" * 200}) + "\n")
    assert p.stat().st_size > 50_000
    cap_jsonl(p, max_lines=100, max_bytes=10_000)
    lines = p.read_text().splitlines()
    assert len(lines) == 100
    # newest lines are kept, oldest dropped, and every kept line is valid JSON
    assert json.loads(lines[-1])["i"] == 499
    assert json.loads(lines[0])["i"] == 400


def test_cap_jsonl_noop_when_small(tmp_path):
    p = tmp_path / "small.jsonl"
    p.write_text('{"a":1}\n{"a":2}\n', encoding="utf-8")
    cap_jsonl(p, max_lines=1, max_bytes=10_000_000)   # under byte gate → untouched
    assert len(p.read_text().splitlines()) == 2


def test_cap_jsonl_missing_file_is_safe(tmp_path):
    cap_jsonl(tmp_path / "nope.jsonl")  # must not raise


def test_ema_paths_live_in_brain_data():
    # canonical: under the same DATA_DIR as the rest of cognition
    # (DATA_DIR itself is env-overridable — the suite repoints it at a tmp dir)
    assert aem._EMA_PATH == paths.DATA_DIR / "action_reward_ema.json"
    assert aem._ASSOC_PATH == paths.DATA_DIR / "action_associability.json"


def test_legacy_ema_is_migrated_then_removed(tmp_path, monkeypatch):
    legacy_dir = tmp_path / "legacy_data"
    legacy_dir.mkdir()
    legacy = legacy_dir / "action_reward_ema.json"
    legacy.write_text(json.dumps({"reflect": 0.9}), encoding="utf-8")
    new = tmp_path / "brain_data" / "action_reward_ema.json"
    new.parent.mkdir()

    monkeypatch.setattr(aem, "_LEGACY_DIR", legacy_dir)
    aem._migrate_legacy(new, "action_reward_ema.json")

    assert json.loads(new.read_text()) == {"reflect": 0.9}   # migrated
    assert not legacy.exists()                                # orphan removed


def test_migration_does_not_clobber_existing(tmp_path, monkeypatch):
    legacy_dir = tmp_path / "legacy_data"
    legacy_dir.mkdir()
    (legacy_dir / "action_reward_ema.json").write_text(json.dumps({"old": 0.1}), encoding="utf-8")
    new = tmp_path / "brain_data" / "action_reward_ema.json"
    new.parent.mkdir()
    new.write_text(json.dumps({"current": 0.5}), encoding="utf-8")

    monkeypatch.setattr(aem, "_LEGACY_DIR", legacy_dir)
    aem._migrate_legacy(new, "action_reward_ema.json")

    assert json.loads(new.read_text()) == {"current": 0.5}    # existing data wins
    assert not (legacy_dir / "action_reward_ema.json").exists()
