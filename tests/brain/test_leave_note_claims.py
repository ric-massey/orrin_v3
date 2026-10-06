"""Run 13 item 7: notes to Ric are seeded from the daemon's structured findings
(claims.json), using the real Run 12 claims files."""
import json
import os
import shutil
import time
from pathlib import Path

import pytest

from brain.cognition import leave_note as ln
from brain.paths import GOALS_DIR

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "run12_claims"


@pytest.fixture(autouse=True)
def _clean_artifacts():
    # The shared session data dir is later zipped by the mind-export tests; leave
    # nothing behind (and no pre-1980 mtimes, which ZIP cannot store).
    art = GOALS_DIR / "artifacts"
    before = set(art.iterdir()) if art.exists() else set()
    yield
    if art.exists():
        for d in set(art.iterdir()) - before:
            shutil.rmtree(d, ignore_errors=True)


def _place(gid, data, age_s):  # negative age = newer than anything else on disk
    mtime = time.time() - age_s
    d = GOALS_DIR / "artifacts" / gid
    d.mkdir(parents=True, exist_ok=True)
    p = d / "claims.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    os.utime(p, (mtime, mtime))


def test_finding_comes_from_newest_real_claims():
    _place("g_math", json.loads((FIX / "g_24136ed3db.json").read_text()), -200)
    _place("g_evo", json.loads((FIX / "g_40fe7f09e0.json").read_text()), -100)
    topic, finding = ln.recent_claims_finding()
    assert topic == "mathematics"
    assert "mathematics" in finding.lower() and "v t e" not in finding


def test_chrome_only_or_subjectless_claims_give_nothing():
    _place("g_chrome", {"question": "What about ferns do I still not understand?",
                        "relations": [{"subject": "Ferns portal Category v t e Ferns",
                                       "predicate": "is", "object": "a list of plant articles"}]},
           20)
    _place("g_now", json.loads((FIX / "g_dd89aa2324.json").read_text()), 10)
    assert ln.recent_claims_finding(scan=2) is None
