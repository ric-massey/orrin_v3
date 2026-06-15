"""I7 — opt-in auto-update wired to the schema spine (§10.7). No real network: the GitHub
call is monkeypatched. Runs under conftest's ORRIN_DATA_DIR isolation."""
import io
import json

import pytest

from utils import updater
from utils import prefs


class _FakeResp:
    def __init__(self, payload: dict):
        self._b = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture(autouse=True)
def _reset_pref():
    prefs.set("auto_update_check", False)
    yield
    prefs.set("auto_update_check", False)


def test_version_compare():
    assert updater.is_newer("0.2.0", "0.1.0") is True
    assert updater.is_newer("0.1.1", "0.1.0") is True
    assert updater.is_newer("1.0.0", "0.9.9") is True
    assert updater.is_newer("0.1.0", "0.1.0") is False
    assert updater.is_newer("0.1.0", "0.2.0") is False
    # A real release outranks a same-core pre-release.
    assert updater.is_newer("0.1.0", "0.1.0-rc1") is True
    assert updater.is_newer("0.1.0-rc1", "0.1.0") is False


def test_current_version_env_override(monkeypatch):
    monkeypatch.setenv("ORRIN_VERSION", "9.9.9")
    from version import current_version
    assert current_version() == "9.9.9"


def test_check_is_opt_in_no_network_when_off(monkeypatch):
    # auto_update_check is off → must NOT touch the network.
    called = {"n": 0}
    monkeypatch.setattr(updater, "urlopen", lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    out = updater.check_for_update()
    assert out["checked"] is False and out["available"] is False
    assert called["n"] == 0


def test_force_check_detects_newer(monkeypatch):
    monkeypatch.setenv("ORRIN_VERSION", "0.1.0")
    monkeypatch.setattr(
        updater, "urlopen",
        lambda *a, **k: _FakeResp({"tag_name": "v0.2.0", "html_url": "http://x/rel", "body": "notes"}),
    )
    out = updater.check_for_update(force=True)
    assert out["checked"] is True and out["available"] is True
    assert out["latest"] == "0.2.0" and out["url"] == "http://x/rel"


def test_force_check_up_to_date(monkeypatch):
    monkeypatch.setenv("ORRIN_VERSION", "0.2.0")
    monkeypatch.setattr(updater, "urlopen", lambda *a, **k: _FakeResp({"tag_name": "v0.2.0"}))
    out = updater.check_for_update(force=True)
    assert out["available"] is False


def test_check_network_error_is_reported_not_raised(monkeypatch):
    def _boom(*a, **k):
        raise OSError("no route to host")
    monkeypatch.setattr(updater, "urlopen", _boom)
    out = updater.check_for_update(force=True)
    assert out["checked"] is True and out["available"] is False and "error" in out


def test_prepare_update_exports_mind_and_reports_schema():
    out = updater.prepare_update()
    assert out["ok"] is True
    from pathlib import Path
    assert Path(out["backup"]).exists() and out["backup"].endswith(".orrindmind")
    # The backup carries the state schema version the new build must understand (G1).
    from utils import schema_migration as sm
    assert out["state_schema_version"] == sm.read_version()
