# R10-1: the vitals SERIES must persist (one row per cycle, attribution fields),
# not just the latest snapshot — the Run-9 memory-guard kill was unattributable
# because only the last RSS value survived the process.
import json

from brain.cognition.resource_self_monitor import update_body_sense
from brain.paths import RESOURCE_HISTORY_FILE


def test_update_body_sense_appends_resource_history_row():
    before = 0
    if RESOURCE_HISTORY_FILE.exists():
        before = len(RESOURCE_HISTORY_FILE.read_text().splitlines())

    ctx = {"last_function_chosen": "reflect"}
    update_body_sense(ctx)

    lines = RESOURCE_HISTORY_FILE.read_text().splitlines()
    assert len(lines) == before + 1
    row = json.loads(lines[-1])
    assert row["last_fn"] == "reflect"
    for key in ("ts", "cycle", "rss_mb", "cpu_util", "fd_pct", "phase", "states"):
        assert key in row
    assert isinstance(row["states"], list) and row["states"]
