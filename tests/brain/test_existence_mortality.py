# Group F (DESKTOP_APP_PLAN §10.3): the existence model — lifespan band (set the odds,
# never the number), and sleep accounting that pauses the mortality clock.
import json
from datetime import datetime, timezone, timedelta

from cognition import mortality as m
from cognition.mortality import LIFESPAN_FILE


def _write_lifespan(**over):
    data = {
        "born_at": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
        "lifespan_days": 10.0,
        "noise_days": 0.0,
        "slept_seconds": 0.0,
        "final_thoughts_written": False,
    }
    data.update(over)
    LIFESPAN_FILE.write_text(json.dumps(data), encoding="utf-8")


def test_lifespan_band_rolls_within_env_band_and_varies(monkeypatch):
    monkeypatch.setenv("ORRIN_LIFESPAN_MIN_DAYS", "10")
    monkeypatch.setenv("ORRIN_LIFESPAN_MAX_DAYS", "12")
    spans = set()
    for _ in range(6):
        LIFESPAN_FILE.unlink(missing_ok=True)
        d = m._init_lifespan()
        assert 10.0 <= d["lifespan_days"] <= 12.0
        spans.add(d["lifespan_days"])
    # Always randomized inside the band — not pinned to an edge.
    assert len(spans) > 1


def test_sleep_credits_pause_the_clock():
    _write_lifespan()
    before = m.life_status()["felt_days_remaining"]
    m.credit_sleep(2 * 86400)  # two days of sleep
    after = m.life_status()["felt_days_remaining"]
    assert after > before  # sleep gave life back (less elapsed counts)


def test_credit_sleep_since_last_active():
    _write_lifespan(last_active_at=(datetime.now(timezone.utc) - timedelta(hours=6)).isoformat())
    credited = m.credit_sleep_since_last_active()
    assert 5.5 * 3600 < credited < 6.5 * 3600


def test_lifespan_rolled_toggles():
    _write_lifespan()
    assert m.lifespan_rolled() is True
    LIFESPAN_FILE.unlink(missing_ok=True)
    assert m.lifespan_rolled() is False


def test_life_status_never_exposes_true_lifespan():
    _write_lifespan(lifespan_days=12345.0, noise_days=7.0)
    st = m.life_status()
    assert "lifespan_days" not in st and "noise_days" not in st
    assert "felt_days_remaining" in st
