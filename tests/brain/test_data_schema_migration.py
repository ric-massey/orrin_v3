"""Tests for the persisted-schema read-old/write-new shim (analogue-removal Phase 4).

The production registry (brain.data_schema.MIGRATIONS) is populated slice by
slice; these tests exercise the *machinery* with an injected registry so they
stay valid regardless of which keys are live, plus an end-to-end check that
load_json applies whatever is registered.
"""
import json

import brain.data_schema as ds
from brain.data_schema import (
    migrate_loaded, resolve_read_path, FILE_RENAMES, SCHEMA_VERSION, SCHEMA_VERSION_KEY,
)
from brain.utils.json_utils import load_json, save_json

_REG = {
    "sample_state.json": {
        "top": {"valence": "reward_signal", "mood": "smoothed_state"},
        "nested": {"core_signals": {"melancholy": "low_affect_signal"}},
    }
}


def test_top_level_rename_and_stamp():
    d = {"valence": 0.12, "energy": 0.9}
    out = migrate_loaded("sample_state.json", dict(d), registry=_REG)
    assert out["reward_signal"] == 0.12
    assert "valence" not in out
    assert out["energy"] == 0.9  # untouched
    assert out[SCHEMA_VERSION_KEY] == SCHEMA_VERSION


def test_nested_rename():
    d = {"core_signals": {"melancholy": 0.3, "confidence": 0.7}}
    out = migrate_loaded("sample_state.json", d, registry=_REG)
    assert out["core_signals"]["low_affect_signal"] == 0.3
    assert "melancholy" not in out["core_signals"]
    assert out["core_signals"]["confidence"] == 0.7  # engineering-neutral, frozen


def test_idempotent():
    d = {"valence": 0.5}
    once = migrate_loaded("sample_state.json", d, registry=_REG)
    twice = migrate_loaded("sample_state.json", dict(once), registry=_REG)
    assert once == twice


def test_existing_new_key_wins_over_stale_old():
    # A half-migrated file: both keys present. The new write is authoritative;
    # the stale old key is dropped, not allowed to clobber it.
    d = {"valence": 0.1, "reward_signal": 0.9}
    out = migrate_loaded("sample_state.json", d, registry=_REG)
    assert out["reward_signal"] == 0.9
    assert "valence" not in out


def test_unregistered_file_is_untouched():
    d = {"valence": 0.4}
    out = migrate_loaded("some_other_file.json", dict(d), registry=_REG)
    assert out == d  # no rename, no version stamp


def test_non_dict_payload_passes_through():
    assert migrate_loaded("sample_state.json", [1, 2, 3], registry=_REG) == [1, 2, 3]


def test_load_json_applies_registry(tmp_path, monkeypatch):
    monkeypatch.setitem(ds.MIGRATIONS, "live_sample.json", {"top": {"valence": "reward_signal"}})
    p = tmp_path / "live_sample.json"
    p.write_text(json.dumps({"valence": 0.33}), encoding="utf-8")
    loaded = load_json(p)
    assert loaded["reward_signal"] == 0.33
    assert "valence" not in loaded
    # round-trips clean: a save then reload stays migrated
    save_json(p, loaded)
    assert load_json(p)["reward_signal"] == 0.33


# ── 4.7: data-file NAME renames + read-old-path fallback ──────────────────────

def test_file_rename_map_is_consistent():
    # No filename is both an old and a new name (no rename chains/cycles).
    assert set(FILE_RENAMES).isdisjoint(set(FILE_RENAMES.values()))
    # Content-migration registry keys use NEW basenames after the file rename.
    assert "control_signals_state.json" in ds.MIGRATIONS
    assert "affect_state.json" not in ds.MIGRATIONS


def test_resolve_read_path_falls_back_to_old_name(tmp_path):
    new = tmp_path / "control_signals_state.json"   # requested (new) name, absent
    old = tmp_path / "affect_state.json"            # legacy file on disk
    old.write_text("{}", encoding="utf-8")
    assert resolve_read_path(new) == old
    # once the new file exists, it wins
    new.write_text("{}", encoding="utf-8")
    assert resolve_read_path(new) == new


def test_resolve_read_path_noop_for_unmapped(tmp_path):
    p = tmp_path / "goals_mem.json"
    assert resolve_read_path(p) == p


def test_load_json_reads_legacy_file_and_migrates_keys(tmp_path):
    # An old-named affect_state.json with old keys, requested under the NEW name:
    # load_json must find it (fallback) AND migrate its keys (new-basename registry).
    (tmp_path / "affect_state.json").write_text(
        json.dumps({"valence": 0.2, "core_signals": {"wonder": 0.5}}), encoding="utf-8")
    loaded = load_json(tmp_path / "control_signals_state.json")
    assert loaded["reward_signal"] == 0.2 and "valence" not in loaded
    assert loaded["core_signals"]["novelty_signal"] == 0.5
