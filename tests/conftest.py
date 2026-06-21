# Root test fixtures.
#
# IMPORTANT: the env-override block below must run before anything imports
# brain's `paths` module — it is what keeps the whole suite out of the live
# brain/data state (DATA_FILE_AUDIT 2026-06-11 §1: unisolated tests overwrote
# real learned state, e.g. action_reward_ema.json, and pruned live memories).
#
# Expected test environment (CODEBASE_CLEANUP_PLAN Phase 0 — hermeticity):
# the suite controls every variable that would otherwise leak from a developer
# or CI shell. The state-redirect + isolation vars are SET here for the whole
# session:
#   ORRIN_DATA_DIR / ORRIN_LOGS_DIR / ORRIN_THINK_DIR / ORRIN_STATE_DIR
#       → per-session tmp dirs (never the live brain/data tree)
#   ORRIN_KEYRING=0      → in-memory secrets, never the real OS keychain
#   PYSTRAY_BACKEND=dummy → headless tray backend (no display needed)
# Embedding backend vars (PYTEST_FORCE_HASH_EMBEDDING, MEMORY_IMG_BACKEND,
# MEMORY_TEXT_FORCE_HASH, MEMORY_IMG_HASH_DIM, …) are NOT set globally; the
# embedder tests clear and re-set exactly what they need per case (see
# tests/memory/embedder_test.py::_reload_embedder), so an inherited shell value
# cannot change the backend out from under them. Run the suite via `make test`.
import os
import sys
import tempfile
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_LIVE_DATA = _REPO_ROOT / "brain" / "data"
_LIVE_LOGS = _REPO_ROOT / "brain" / "logs"

# Repoint all of brain's persisted state at a per-session tmp dir.
_SESSION_STATE = Path(tempfile.mkdtemp(prefix="orrin-test-state-"))
os.environ["ORRIN_DATA_DIR"] = str(_SESSION_STATE / "data")
os.environ["ORRIN_LOGS_DIR"] = str(_SESSION_STATE / "logs")
# Also isolate the think dir and the daemon-durability tree (goals/memory/media)
# now that they're env-overridable (Group C) — keeps the suite fully off the live
# trees, not just brain/data + brain/logs.
os.environ["ORRIN_THINK_DIR"] = str(_SESSION_STATE / "think")
os.environ["ORRIN_STATE_DIR"] = str(_SESSION_STATE / "state")
# Never touch the developer's real OS keychain from the test suite — force the
# in-memory secrets backend (utils.secrets) for the whole session.
os.environ["ORRIN_KEYRING"] = "0"
# Force pystray's headless 'dummy' backend so `import pystray` in the tray tests
# (test_tray_fallback) never tries to open a real display. On headless CI the
# auto-selected Xorg backend raises Xlib DisplayNameError at import time; the
# tray tests only assert the best-effort fallback contract, not live GUI.
os.environ.setdefault("PYSTRAY_BACKEND", "dummy")

if "paths" in sys.modules:  # pragma: no cover — defensive
    raise RuntimeError(
        "brain's `paths` module was imported before tests/conftest.py could "
        "set ORRIN_DATA_DIR — test isolation from live brain/data is broken."
    )


def _snapshot_live_state() -> dict[str, tuple[int, int]]:
    """Map every live state file -> (mtime_ns, size)."""
    snap: dict[str, tuple[int, int]] = {}
    roots = [_LIVE_DATA, _LIVE_LOGS]
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if p.is_file():
                st = p.stat()
                snap[str(p)] = (st.st_mtime_ns, st.st_size)
    # brain-root state files some legacy paths constants still point at
    for p in (_REPO_ROOT / "brain").glob("*.json"):
        st = p.stat()
        snap[str(p)] = (st.st_mtime_ns, st.st_size)
    return snap


@pytest.fixture(autouse=True, scope="session")
def _guard_live_brain_data():
    """
    Fail the session if any live brain/data, brain/logs, or brain/*.json file
    is created, modified, or deleted while tests run. This is the tripwire
    behind the ORRIN_DATA_DIR isolation above — if any code path still writes
    to the live tree, we want a loud failure, not silent state corruption.
    """
    before = _snapshot_live_state()
    yield
    after = _snapshot_live_state()
    changed = sorted(
        set(k for k in before if before[k] != after.get(k))
        | set(after) - set(before)
    )
    if changed:
        raise AssertionError(
            "Test run mutated live Orrin state (isolation breach):\n  "
            + "\n  ".join(changed)
        )


@pytest.fixture(autouse=True)
def _isolate_llm_failure_counts(monkeypatch, tmp_path):
    """
    Keep tests out of the live brain/data state (BEHAVIOR_FIX_PLAN Phase 5):
    llm_ok()'s failure counter writes llm_failure_counts.json under
    utils.generate_response.DATA_DIR — point that at a per-test tmp dir so
    test callers ('test_*') never pollute live failure counts (which
    problem_refocus diffs to detect real outages).
    """
    try:
        import brain.utils.generate_response as gr
    except Exception:
        yield
        return
    monkeypatch.setattr(gr, "DATA_DIR", tmp_path)
    yield
