# Single-writer invariant + thread-safe affect inbox (V3 convergence layer).
#
# These assert the Phase-1 contract from V3_AUDIT.md §1.1 / Deliverable 2 Contract A:
#   - daemons and context-less producers submit affect PROPOSALS, never write
#     AFFECT_STATE_FILE directly;
#   - the thread-safe module inbox is drained by commit_affect on the main loop;
#   - scalar top-level targets (resource_deficit) are applied directly at commit;
#   - concurrent submissions never lose updates (no last-writer-wins race).
import threading

import brain.control_signals.arbiter as arbiter
from brain.control_signals.arbiter import submit_affect, commit_affect


def _ctx(**core):
    return {"affect_state": {"core_signals": dict(core), "resource_deficit": 0.5}}


def setup_function(_):
    # Ensure a clean module inbox between tests.
    with arbiter._inbox_lock:
        arbiter._inbox.clear()


def test_daemon_submission_routes_to_threadsafe_inbox():
    # context=None → goes to the module inbox, NOT to any context dict.
    submit_affect(None, "motivation", +0.10, source="daemon")
    with arbiter._inbox_lock:
        assert len(arbiter._inbox) == 1
        assert arbiter._inbox[0]["target"] == "motivation"


def test_commit_drains_inbox_into_state():
    ctx = _ctx(motivation=0.5)
    submit_affect(None, "motivation", +0.12, source="daemon")
    applied = commit_affect(ctx)
    assert "motivation" in applied
    # inbox emptied after the drain
    with arbiter._inbox_lock:
        assert arbiter._inbox == []


def test_scalar_target_applied_directly():
    ctx = _ctx(motivation=0.5)  # resource_deficit seeded at 0.5
    submit_affect(None, "resource_deficit", -0.35, source="dream_rest", ttl_cycles=2)
    commit_affect(ctx)
    # resource_deficit moves toward setpoint (0.15) immediately, clamped >= 0.
    assert ctx["affect_state"]["resource_deficit"] < 0.5
    assert ctx["affect_state"]["resource_deficit"] >= 0.0


def test_concurrent_submissions_are_not_lost():
    _ctx(motivation=0.0)
    N = 50

    def worker():
        for _ in range(N):
            submit_affect(None, "motivation", +0.001, source="t")

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    with arbiter._inbox_lock:
        assert len(arbiter._inbox) == 8 * N  # every submission survived


def test_drain_consolidations_does_not_write_affect_file(monkeypatch):
    import brain.control_signals.consolidation as consolidation

    entry = {
        "id": "x", "event": "e", "emotion": "reward_positive",
        "intensity": 0.16, "cycles_remaining": 2, "tint_per_cycle": 0.08,
        "importance": 4, "created_ts": "t",
    }
    monkeypatch.setattr(consolidation, "_load_queue", lambda: [dict(entry)])
    monkeypatch.setattr(consolidation, "_save_queue", lambda q: None)

    # save_json must NOT be called with the affect file by drain_consolidations.
    from brain.paths import AFFECT_STATE_FILE
    calls = []
    monkeypatch.setattr(consolidation, "save_json", lambda p, d: calls.append(str(p)))

    ctx = _ctx(reward_positive=0.3)
    consolidation.drain_consolidations(ctx)

    assert str(AFFECT_STATE_FILE) not in calls
    # It submitted a proposal into the context instead.
    props = ctx.get("_affect_proposals") or []
    assert any(p["target"] == "reward_positive" for p in props)
