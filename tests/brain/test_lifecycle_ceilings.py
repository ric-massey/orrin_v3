# Follow-ups to Group F: telling stall vs crash apart (§10.5) and the disk ceiling the
# forgetting sweeps respect (§10.3). Both run under conftest's ORRIN_DATA_DIR isolation.
import json

import pytest

from utils import lifecycle as lc
from utils import resource_ceilings as rc
from brain.paths import DATA_DIR


@pytest.fixture(autouse=True)
def _clean_runstate():
    yield
    # Leave the shared lifecycle module in a clean 'alive' state for other tests.
    lc.mark_clean_shutdown()
    lc.mark_running()


def test_reaper_stall_reads_as_stalled():
    lc._write({"clean": False, "reaper": True, "reason": "HARD:lifespan_reached"})
    lc.mark_running()
    st = lc.status()
    assert st["state"] == "stalled"
    assert "lifespan" in st.get("reason", "")


def test_unclean_no_reaper_reads_as_crashed():
    lc._write({"clean": False, "reaper": False})
    lc.mark_running()
    assert lc.status()["state"] == "crashed"


def test_clean_shutdown_reads_as_alive():
    lc.mark_clean_shutdown()
    lc.mark_running()
    assert lc.status()["state"] == "alive"


def test_mark_stall_sets_reaper_marker():
    lc.mark_running()
    lc.mark_stall("HARD:heartbeat")
    cur = json.loads((DATA_DIR / "runstate.json").read_text())
    assert cur["reaper"] is True and cur["clean"] is False


def test_disk_ceiling_trims_growable_stores_when_over(monkeypatch):
    monkeypatch.setenv("ORRIN_DISK_CEILING_GB", "0.0000001")  # ~100 bytes → force over
    (DATA_DIR / "conscious_stream.json").write_text(json.dumps([{"i": i} for i in range(5000)]))
    assert rc.over_disk_ceiling() is True
    report = rc.enforce_disk_ceiling()
    assert report["over"] is True
    assert json.loads((DATA_DIR / "conscious_stream.json").read_text()).__len__() == 2000


def test_disk_ceiling_is_noop_when_under(monkeypatch):
    monkeypatch.setenv("ORRIN_DISK_CEILING_GB", "100")  # huge → never over
    assert rc.over_disk_ceiling() is False
    assert rc.enforce_disk_ceiling() == {"over": False, "trimmed": {}}


def test_memory_ceiling_evicts_caches_when_over(monkeypatch):
    # Force "over": pretend RSS is 8 GB against a 4 GB ceiling. We monkeypatch the RSS
    # reader so the test does not depend on the real process size or on psutil.
    monkeypatch.setenv("ORRIN_MEMORY_CEILING_GB", "4")
    monkeypatch.setattr(rc, "process_rss_bytes", lambda: 8 * rc._GB)
    assert rc.over_memory_ceiling() is True
    report = rc.enforce_memory_ceiling()
    assert report["over"] is True
    assert isinstance(report["evicted"], list)  # whatever caches were importable


def test_memory_ceiling_is_noop_when_under(monkeypatch):
    monkeypatch.setattr(rc, "process_rss_bytes", lambda: 1 * rc._GB)  # under any sane ceiling
    monkeypatch.setenv("ORRIN_MEMORY_CEILING_GB", "4")
    assert rc.over_memory_ceiling() is False
    assert rc.enforce_memory_ceiling() == {"over": False, "evicted": []}


def test_memory_ceiling_noop_when_rss_unavailable(monkeypatch):
    # psutil missing ⇒ process_rss_bytes() returns 0 ⇒ ceiling is a no-op, not a guess.
    monkeypatch.setattr(rc, "process_rss_bytes", lambda: 0)
    monkeypatch.setenv("ORRIN_MEMORY_CEILING_GB", "0.0000001")
    assert rc.over_memory_ceiling() is False
