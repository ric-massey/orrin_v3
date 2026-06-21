# Finding 2: brain/utils/failure_counter.py is the target of the mechanical
# conversion of 646 `_log.warning("silent except: %s", _e)` sites in brain/
# into named `record_failure("module.function[.N]", _e)` handlers, but the
# module itself had no test coverage. These pin record_failure's
# counting/rate-limiting/strict-mode contract and guard()'s swallow/reraise
# behavior, which every converted site now depends on.
import json

import pytest

import brain.utils.failure_counter as fc


class _StubBridge:
    def log(self, *args, **kwargs):
        pass


@pytest.fixture(autouse=True)
def _isolated_state(monkeypatch, tmp_path):
    """Clean in-memory counters, an isolated data dir, default (non-strict)
    mode, and a stubbed telemetry bridge for every test in this file."""
    monkeypatch.setattr(fc, "_counters", {})
    monkeypatch.setattr(fc, "_last_logged", {})
    monkeypatch.setattr(fc, "_data_dir_cache", tmp_path)
    monkeypatch.setattr(fc, "_STRICT", "")
    monkeypatch.setattr("backend.telemetry_bridge.get_bridge", lambda *a, **k: _StubBridge())
    yield


def test_record_failure_increments_counter():
    fc.record_failure("mod.fn", ValueError("boom"))
    fc.record_failure("mod.fn", ValueError("boom again"))
    summary = fc.get_summary()
    assert summary["mod.fn"]["count"] == 2
    assert "boom again" in summary["mod.fn"]["last_error"]


def test_record_failure_writes_jsonl_first_time(tmp_path):
    fc.record_failure("mod.fn", RuntimeError("first"))
    path = tmp_path / "failures.jsonl"
    assert path.exists()
    line = json.loads(path.read_text().splitlines()[0])
    assert line["site"] == "mod.fn"
    assert "first" in line["error"]


def test_record_failure_rate_limits_jsonl_writes(tmp_path):
    fc.record_failure("mod.fn", RuntimeError("first"))
    fc.record_failure("mod.fn", RuntimeError("second"))  # within 60s cooldown
    lines = (tmp_path / "failures.jsonl").read_text().splitlines()
    assert len(lines) == 1
    # In-memory counter still ticks for both.
    assert fc.get_summary()["mod.fn"]["count"] == 2


def test_dump_summary_writes_file(tmp_path):
    fc.record_failure("mod.fn", RuntimeError("x"))
    fc.dump_summary()
    data = json.loads((tmp_path / "failure_summary.json").read_text())
    assert data["sites"]["mod.fn"]["count"] == 1


def test_dump_summary_noop_when_empty(tmp_path):
    fc.dump_summary()
    assert not (tmp_path / "failure_summary.json").exists()


def test_strict_off_by_default():
    assert not fc.strict_should_reraise(NameError("x"))
    assert not fc.strict_should_reraise(ValueError("x"))


def test_strict_1_reraises_programmer_errors_only(monkeypatch):
    monkeypatch.setattr(fc, "_STRICT", "1")
    assert fc.strict_should_reraise(NameError("x"))
    assert fc.strict_should_reraise(AttributeError("x"))
    assert fc.strict_should_reraise(TypeError("x"))
    assert not fc.strict_should_reraise(ValueError("x"))
    assert not fc.strict_should_reraise(KeyError("x"))


def test_strict_all_reraises_everything(monkeypatch):
    monkeypatch.setattr(fc, "_STRICT", "all")
    assert fc.strict_should_reraise(ValueError("x"))
    assert fc.strict_should_reraise(KeyError("x"))


def test_record_failure_reraises_programmer_error_under_strict(monkeypatch):
    monkeypatch.setattr(fc, "_STRICT", "1")
    with pytest.raises(NameError):
        fc.record_failure("mod.fn", NameError("typo"))
    # Still counted before re-raising.
    assert fc.get_summary()["mod.fn"]["count"] == 1


def test_record_failure_does_not_reraise_environmental_error_under_strict_1(monkeypatch):
    monkeypatch.setattr(fc, "_STRICT", "1")
    fc.record_failure("mod.fn", ValueError("not a programmer error"))
    assert fc.get_summary()["mod.fn"]["count"] == 1


def test_guard_swallows_exception_and_records():
    with fc.guard("mod.op"):
        raise ValueError("boom")
    assert fc.get_summary()["mod.op"]["count"] == 1


def test_guard_reraises_under_strict_all(monkeypatch):
    monkeypatch.setattr(fc, "_STRICT", "all")
    with pytest.raises(ValueError):
        with fc.guard("mod.op"):
            raise ValueError("boom")
    assert fc.get_summary()["mod.op"]["count"] == 1
