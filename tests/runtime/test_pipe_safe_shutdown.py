"""Regression: the 07-18 aborted run died from a BrokenPipeError raised by the
first print() in graceful_shutdown (run_orrin.sh's tee pipe was already gone),
which skipped the whole teardown. Shutdown-path output must never raise."""
from __future__ import annotations

import threading
import types

import pytest

from runtime import lifecycle


class _DeadPipe:
    """A stdout whose every write raises, like a pipe whose reader exited."""

    def write(self, _s: str) -> int:
        raise BrokenPipeError(32, "Broken pipe")

    def flush(self) -> None:
        raise BrokenPipeError(32, "Broken pipe")


def test_say_survives_dead_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lifecycle.sys, "stdout", _DeadPipe())
    monkeypatch.setattr(lifecycle.sys, "stderr", _DeadPipe())
    lifecycle.say("[main] graceful shutdown — stopping subsystems…")
    lifecycle.say("to stderr too", err=True)


def test_graceful_shutdown_completes_with_dead_stdout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lifecycle.sys, "stdout", _DeadPipe())
    monkeypatch.setattr(lifecycle.sys, "stderr", _DeadPipe())

    stopped: list[str] = []

    class _Stoppable:
        def __init__(self, name: str) -> None:
            self._name = name

        def stop(self, join: bool = False) -> None:
            stopped.append(self._name)

    ctx = types.SimpleNamespace(
        shutting_down=False,
        stop_evt=threading.Event(),
        cog_thread=None,
        alive=_Stoppable("alive"),
        goals_daemon=_Stoppable("goals"),
        fs_obs=None,
        memory_daemon=_Stoppable("memory"),
        ui_proc=None,
    )

    lifecycle.graceful_shutdown(ctx)  # must not raise

    # The teardown ran to the end — every subsystem past the first print was
    # still stopped (the bug aborted before any of these).
    assert stopped == ["alive", "goals", "memory"]
    assert ctx.stop_evt.is_set()
