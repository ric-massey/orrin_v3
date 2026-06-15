"""G1 — the state schema version + migration spine (§10.7). Runs under conftest's
ORRIN_DATA_DIR isolation, so it stamps/migrates a throwaway mind, never the live one."""
import json

import pytest

from utils import schema_migration as sm
from paths import DATA_DIR

_STAMP = DATA_DIR / "schema_version.json"


@pytest.fixture(autouse=True)
def _clean_stamp():
    # Start AND end each test from an UNSTAMPED mind (reads as baseline == current for
    # the real build). Removing the stamp — rather than re-writing CURRENT, which a test
    # may have monkeypatched ahead — keeps the shared session DATA_DIR coherent for the
    # other suites that export/import the same mind.
    if _STAMP.exists():
        _STAMP.unlink()
    yield
    if _STAMP.exists():
        _STAMP.unlink()


def test_unstamped_mind_reads_as_baseline():
    assert sm.read_version() == sm._BASELINE_VERSION


def test_equal_version_is_noop_but_stamps():
    out = sm.check_and_migrate()
    assert out["action"] == "none"
    assert json.loads(_STAMP.read_text())["state_schema_version"] == sm.CURRENT_SCHEMA_VERSION


def test_newer_on_disk_refuses_to_load():
    sm.stamp_version(sm.CURRENT_SCHEMA_VERSION + 5)
    with pytest.raises(sm.SchemaTooNewError):
        sm.check_and_migrate()


def test_older_mind_migrates_forward_and_backs_up(monkeypatch):
    # Pretend this build is one schema ahead, with a registered 1→2 migration.
    ran = {"hit": False}

    def _mig_1_to_2():
        ran["hit"] = True
        (DATA_DIR / "migrated_marker.json").write_text("{}")

    monkeypatch.setattr(sm, "CURRENT_SCHEMA_VERSION", sm._BASELINE_VERSION + 1)
    monkeypatch.setitem(sm._MIGRATIONS, sm._BASELINE_VERSION, _mig_1_to_2)
    sm.stamp_version(sm._BASELINE_VERSION)

    out = sm.check_and_migrate()

    assert out["action"] == "migrated"
    assert out["from"] == sm._BASELINE_VERSION and out["to"] == sm._BASELINE_VERSION + 1
    assert ran["hit"] is True
    assert (DATA_DIR / "migrated_marker.json").exists()
    # The mind was auto-exported BEFORE the migration ran (§10.7 safety net).
    assert out["backup"] and any((DATA_DIR / "_backups").glob("pre-migrate-*.orrindmind"))
    assert json.loads(_STAMP.read_text())["state_schema_version"] == sm._BASELINE_VERSION + 1
