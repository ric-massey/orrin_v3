"""Run-12 Slice 1A.1 regression: when the cognitive loop thread ends on its own
(a natural lifespan death), the brain-exit watcher must trip main_stop so run()
falls into graceful_shutdown and the process exits 0 — instead of leaving the main
thread in pulse_loop forever (Run 11 shutdown-hang → cycle-stall kill → born-dead
relaunch). A deliberate Stop (cognition_stopped) must NOT trip it: the UI stays up.
"""
from __future__ import annotations

import threading
import time
import types

from runtime import desktop


def _fake_ctx(cog_thread):
    return types.SimpleNamespace(
        cog_thread=cog_thread,
        cognition_stopped=False,
        shutting_down=False,
        main_stop=threading.Event(),
    )


def _short_thread():
    t = threading.Thread(target=lambda: time.sleep(0.1), daemon=True)
    t.start()
    return t


def test_watcher_trips_main_stop_when_loop_ends():
    ctx = _fake_ctx(_short_thread())
    w = desktop._start_brain_exit_watcher(ctx)
    w.join(timeout=5)
    assert not w.is_alive()
    assert ctx.main_stop.is_set()  # natural death → process winds down


def test_watcher_leaves_deliberate_stop_alone():
    ctx = _fake_ctx(_short_thread())
    ctx.cognition_stopped = True  # Stop button: keep the UI up
    w = desktop._start_brain_exit_watcher(ctx)
    w.join(timeout=5)
    assert not w.is_alive()
    assert not ctx.main_stop.is_set()  # watcher did not steal the teardown


def test_watcher_leaves_inflight_shutdown_alone():
    ctx = _fake_ctx(_short_thread())
    ctx.shutting_down = True
    w = desktop._start_brain_exit_watcher(ctx)
    w.join(timeout=5)
    assert not w.is_alive()
    assert not ctx.main_stop.is_set()
