# tests/test_main_boot.py
# Boot/shutdown characterization tests for the main.py entrypoint
# (CODEBASE_CLEANUP_PLAN Phase 4A/4B — "add import/startup characterization
# tests before extracting lifecycle stages").
#
# main.py runs its ENTIRE boot at import: it acquires the single-instance lock,
# seeds a newborn, starts MemoryDaemon + goals/alive/fs daemons, then run()
# spins the cognitive loop and blocks on the heartbeat/window until a stop
# Event. The 22 lifecycle functions still in main.py (watchdog callbacks, the
# stop/shutdown sequence, the re-exec/reset lifecycle) read module-level state
# built during that import, so they can't be unit-tested in isolation yet — the
# upcoming RuntimeContext restructure is what makes them testable.
#
# Until then, these tests pin the OBSERVABLE boot→shutdown contract of the real
# entrypoint, run as a subprocess against a redirected (tmp) state dir so they
# never touch the live mind. They are the safety net the restructure leans on:
# if a refactor reorders boot, drops a subsystem, breaks the single-instance
# lock, or skips graceful shutdown, one of these fails.
#
# Mirrors tests/test_import_safety.py for the redirected-env + subprocess shape.

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_MAIN = _REPO_ROOT / "main.py"

# First boot loads ML weights + starts every daemon; be generous.
_BOOT_TIMEOUT_S = 90.0


def _boot_env(state_root: Path) -> dict[str, str]:
    """A hermetic, headless child environment: all persisted state redirected to
    a tmp dir, no UI/metrics ports, no OS keychain, unbuffered stdout so the log
    can be polled live."""
    env = dict(os.environ)
    env["ORRIN_DATA_DIR"] = str(state_root / "data")
    env["ORRIN_LOGS_DIR"] = str(state_root / "logs")
    env["ORRIN_THINK_DIR"] = str(state_root / "think")
    env["ORRIN_STATE_DIR"] = str(state_root / "state")
    env["ORRIN_KEYRING"] = "0"
    env["ORRIN_UI"] = "0"            # no window / no open port
    env["ORRIN_METRICS"] = "0"       # no Prometheus listener
    env["ORRIN_EXECUTIVE_DAEMON"] = "0"
    env.setdefault("PYSTRAY_BACKEND", "dummy")
    env["PYTHONUNBUFFERED"] = "1"    # see boot markers in real time
    # Phase 3 put first-party code on the brain.* namespace; only the repo root
    # is needed on the path (matches main.py's own bootstrap).
    env["PYTHONPATH"] = str(_REPO_ROOT)
    return env


def _runstate(state_root: Path) -> dict:
    try:
        return json.loads((state_root / "data" / "runstate.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def _index_of(markers: list[str], needle: str) -> int:
    for i, line in enumerate(markers):
        if needle in line:
            return i
    return -1


def test_headless_single_cycle_boots_and_shuts_down_clean(tmp_path):
    """The end-to-end happy path: a headless single-cycle run boots every
    subsystem, runs one cognitive cycle (ORRIN_ONCE), then shuts down
    gracefully — exiting 0 and flipping the lifecycle marker to clean."""
    env = _boot_env(tmp_path)
    env["ORRIN_ONCE"] = "1"  # break the cognitive loop after one tick → process self-stops

    proc = subprocess.run(
        [sys.executable, str(_MAIN)],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=_BOOT_TIMEOUT_S,
    )
    out = proc.stdout + "\n" + proc.stderr
    assert proc.returncode == 0, f"single-cycle boot exited {proc.returncode}:\n{out}"

    # The boot/shutdown milestones must all appear, in dependency order.
    lines = out.splitlines()
    ordered = [
        "single-instance lock acquired",
        "MemoryDaemon started",
        "cognitive loop thread started",
        "single cycle complete",       # ORRIN_ONCE watcher tripped _main_stop
        "graceful shutdown",           # main thread observed the stop, ran teardown
        "shutdown complete",
    ]
    positions = [_index_of(lines, m) for m in ordered]
    for marker, pos in zip(ordered, positions):
        assert pos >= 0, f"missing boot/shutdown marker {marker!r} in:\n{out}"
    assert positions == sorted(positions), (
        "boot/shutdown markers out of order:\n"
        + "\n".join(f"  {p:>4}  {m}" for m, p in zip(ordered, positions))
    )

    # The lifecycle marker is the cross-restart record the wake/death screens read;
    # a graceful shutdown must leave it clean.
    rs = _runstate(tmp_path)
    assert rs.get("clean") is True, f"graceful shutdown did not mark the run clean: {rs}"


@pytest.mark.skipif(not hasattr(__import__("os"), "fork"), reason="POSIX flock guard")
def test_single_instance_lock_refuses_second_boot(tmp_path):
    """The single-instance guard: with the advisory lock already held against a
    mind's data dir, a second boot must refuse (exit 3) instead of starting a
    second brain over shared state. Pre-acquiring the flock from the test stands
    in for a first running Orrin — deterministic, no race on a live process."""
    fcntl = pytest.importorskip("fcntl")

    env = _boot_env(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    lock_path = data_dir / ".orrin.instance.lock"

    fd = open(lock_path, "w")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # hold it like a running Orrin
        proc = subprocess.run(
            [sys.executable, str(_MAIN)],
            cwd=str(_REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=_BOOT_TIMEOUT_S,
        )
    finally:
        fd.close()

    out = proc.stdout + "\n" + proc.stderr
    assert proc.returncode == 3, (
        f"second boot should refuse with exit 3, got {proc.returncode}:\n{out}"
    )
    assert "already running" in out.lower() or "already thinking" in out.lower(), (
        f"expected an 'already running' refusal message:\n{out}"
    )
    # It must bail BEFORE bringing the heavy subsystems up.
    assert "MemoryDaemon started" not in out, (
        f"second boot started the memory daemon despite the lock:\n{out}"
    )


def test_sigint_drives_graceful_shutdown(tmp_path):
    """The signal path: a long-running headless boot (heartbeat on the main
    thread) must turn SIGINT into a clean graceful shutdown — exit 0, run marked
    clean — via the async-signal-safe _on_signal → _main_stop → _graceful_shutdown
    handoff (the path a past bug skipped, mis-recording a stop as a crash)."""
    env = _boot_env(tmp_path)  # NOT ORRIN_ONCE: it blocks on the heartbeat until signalled

    log_path = tmp_path / "boot.log"
    with open(log_path, "w") as log:
        proc = subprocess.Popen(
            [sys.executable, str(_MAIN)],
            cwd=str(_REPO_ROOT),
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    try:
        # Wait until run() has installed the SIGINT handler — it does so before
        # printing this marker. Signalling earlier would hit Python's default
        # handler and crash boot, which is not what we're characterizing.
        deadline = time.time() + _BOOT_TIMEOUT_S
        ready = False
        while time.time() < deadline:
            if proc.poll() is not None:
                break
            if "cognitive loop thread started" in log_path.read_text(errors="ignore"):
                ready = True
                break
            time.sleep(0.2)
        assert ready, (
            "cognitive loop never reported ready before signalling:\n"
            + log_path.read_text(errors="ignore")
        )

        # Let the heartbeat settle into its main-thread wait, then interrupt.
        time.sleep(1.0)
        proc.send_signal(signal.SIGINT)
        try:
            rc = proc.wait(timeout=_BOOT_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise AssertionError(
                "SIGINT did not drive shutdown in time:\n" + log_path.read_text(errors="ignore")
            )
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)

    out = log_path.read_text(errors="ignore")
    assert rc == 0, f"SIGINT shutdown exited {rc}, expected 0:\n{out}"
    assert "graceful shutdown" in out, f"SIGINT did not reach graceful shutdown:\n{out}"

    rs = _runstate(tmp_path)
    assert rs.get("clean") is True, f"SIGINT shutdown did not mark the run clean: {rs}"
