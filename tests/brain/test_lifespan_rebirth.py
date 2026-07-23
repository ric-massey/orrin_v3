"""Run-12 Slice 1A.2 regression: a boot that inherits a life whose real lifespan
has already fully elapsed must ROLL A FRESH LIFE (rebirth), not re-enter the death
path. Run 11 died into 4 born-dead relaunches because the reborn instance kept the
old start_time, computed real_fraction >= 1.0, and re-hung on the death path."""
import json
from datetime import datetime, timezone, timedelta

from brain.cognition import runtime_lifetime as m
from brain.cognition.runtime_lifetime import LIFESPAN_FILE


def _write_lifespan(**over):
    data = {
        "start_time": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
        "lifespan_days": 10.0,
        "noise_days": 0.0,
        "slept_seconds": 0.0,
        "final_thoughts_written": False,
    }
    data.update(over)
    LIFESPAN_FILE.write_text(json.dumps(data), encoding="utf-8")


def test_rebirth_when_lifespan_already_elapsed():
    # Born 30 days ago with a 10-day lifespan → already fully elapsed.
    born = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    _write_lifespan(start_time=born, lifespan_days=10.0, final_thoughts_written=True)
    assert m._life_fraction(m._load_lifespan()) >= 1.0  # precondition: dead

    assert m.rebirth_if_elapsed() is True

    data = m._load_lifespan()
    # Fresh clock: the previous life is not resurrected — it's a new life.
    assert m._life_fraction(data) < 1.0
    assert data.get("final_thoughts_written") is False
    # start_time was rolled forward to (approximately) now.
    born_dt = datetime.fromisoformat(data["start_time"])
    assert (datetime.now(timezone.utc) - born_dt).total_seconds() < 60


def test_no_rebirth_mid_life():
    _write_lifespan()  # 5d elapsed of a 10d life — still alive
    before = LIFESPAN_FILE.read_text(encoding="utf-8")
    assert m.rebirth_if_elapsed() is False
    assert LIFESPAN_FILE.read_text(encoding="utf-8") == before  # untouched


def test_no_rebirth_without_prior_life():
    LIFESPAN_FILE.unlink(missing_ok=True)
    assert m.rebirth_if_elapsed() is False
    # A no-op read must not roll a lifespan as a side effect.
    assert not LIFESPAN_FILE.exists()
