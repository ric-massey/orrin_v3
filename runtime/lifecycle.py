"""Process lifecycle stages (Phase 4B, extracted from main.py).

The heartbeat, the stop/shutdown sequence, and the re-exec/reset/restart
lifecycle — everything that operates on the boot-produced runtime state. They
used to be closures over main.py's module globals; now each takes the explicit
`RuntimeContext` main builds after boot, which is what let them move out of the
entrypoint.

`runtime.desktop.run()` drives these; the Stop/Reset/Restart UI buttons are
wired (in main.py) to `stop_cognition`/`reset_to_newborn`/`restart_process`.
"""
from __future__ import annotations

import os
import sys
import shutil
import threading
import time

from brain.core.runtime_log import get_logger
from observability import metrics  # Gauge: cycle_gauge, lifespan_cycles
from brain.utils.get_cycle_count import get_cycle_count
from memory.wal import flush as wal_flush

from runtime import newborn as _newborn
from runtime import single_instance as _single_instance
from runtime.context import RuntimeContext

_log = get_logger(__name__)


def pulse_loop(ctx: RuntimeContext, stop: threading.Event) -> None:
    """The ~10 Hz heartbeat: tick the Pulse, publish cycle gauges, and sample
    fast metrics. Runs on the main thread in dev mode and in a daemon thread when
    the native window owns the main thread."""
    pulse = ctx.pulse
    last_log = 0
    last_active_rec = 0.0
    while not stop.is_set():
        pulse.tick()

        # Stamp 'last alive at' periodically so 'sleep' mode can later credit the
        # closed interval accurately even after a crash (§10.3).
        _now_wall = time.time()
        if _now_wall - last_active_rec > 30.0:
            try:
                from brain.cognition.mortality import record_active_now as _rec_active
                _rec_active()
            except Exception as _e:
                _log.warning("silent except: %s", _e)
            last_active_rec = _now_wall

        n = pulse.read()
        try:
            metrics.cycle_gauge.set(float(n))
        except Exception as _e:
            _log.warning("silent except: %s", _e)

        if (n % 5) == 0:  # ~10Hz loop → fire ~2Hz
            ctx.sample_metrics_fast()
            try:
                cog_n = get_cycle_count()
                metrics.lifespan_cycles.set(float(cog_n))
            except Exception as _e:
                _log.warning("silent except: %s", _e)

        time.sleep(0.02)

        last_log += 1
        if last_log >= 100:
            try:
                print(f"[main] pulse={n} cog_cycles={get_cycle_count()}")
            except Exception:
                print(f"[main] pulse={n}")
            last_log = 0


def stop_cognition(ctx: RuntimeContext) -> None:
    """Turn OFF Orrin's *thinking* — the cognitive loop and its daemons — while
    leaving the UI/window, telemetry hub, and memory store running so you can keep
    viewing his now-frozen mind. This is what the Stop button does; quitting the
    app (full shutdown) is a separate action (close the window / Ctrl+C).

    Memory daemon is deliberately KEPT alive so the Memory panels still read his
    state after he stops. Idempotent."""
    if ctx.cognition_stopped:
        return
    ctx.cognition_stopped = True
    print("[main] stopping cognition (UI stays up)…")
    try:
        ctx.stop_evt.set()
    except Exception as _e:
        _log.warning("silent except: %s", _e)
    # The loop is a daemon thread; setting stop_evt winds it down. Join briefly so
    # a healthy loop is fully quiesced before we report stopped, but never block
    # the UI on a wedged thread.
    if ctx.cog_thread is not None and ctx.cog_thread.is_alive():
        ctx.cog_thread.join(timeout=float(os.environ.get("ORRIN_STOP_JOIN_S", "8")))
    try:
        if ctx.alive: ctx.alive.stop()
    except Exception as _e:
        _log.warning("silent except: %s", _e)
    try:
        if ctx.goals_daemon: ctx.goals_daemon.stop()
    except Exception as _e:
        _log.warning("silent except: %s", _e)
    try:
        if ctx.fs_obs:
            ctx.fs_obs.stop()
            ctx.fs_obs.join(timeout=3)
    except Exception as _e:
        _log.warning("silent except: %s", _e)
    # Surface the stop on the live stream so the UI flips to "Stopped".
    try:
        from backend.telemetry_bridge import get_bridge as _get_tb
        _get_tb().log("warn", "control", "Orrin stopped — cognition halted; the view stays up")
    except Exception as _e:
        _log.warning("silent except: %s", _e)
    print("[main] cognition stopped; UI still running.")


def graceful_shutdown(ctx: RuntimeContext) -> None:
    """Full quit: stop every subsystem in dependency order, flush state, and tear
    down the UI. Runs on window-close / Ctrl+C. A watchdog force-exits if a wedged
    brain thread keeps shutdown from completing, so quitting always terminates."""
    if ctx.shutting_down:
        return  # window-close + signal can both reach here; run teardown once
    ctx.shutting_down = True
    # Runs on the MAIN thread (the signal handler only sets a flag), so I/O here is
    # safe. This is the line whose absence in the run log proved a stop had skipped
    # graceful shutdown entirely.
    print("[main] graceful shutdown — stopping subsystems…", flush=True)
    # Watchdog: if teardown stalls (e.g. a daemon thread won't honor stop), force a
    # clean exit so the window never lingers and run_orrin.sh sees a 0 (no restart).
    _timeout = float(os.environ.get("ORRIN_SHUTDOWN_TIMEOUT_S", "12"))
    _wd = threading.Timer(_timeout, lambda: (print(f"[main] shutdown exceeded {_timeout}s — forcing exit"), os._exit(0)))
    _wd.daemon = True
    _wd.start()

    # Stamp 'last alive at = now' so 'sleep' mode credits the closed interval exactly
    # from here (§10.3). Cheap and important to do before threads wind down.
    try:
        from brain.cognition.mortality import record_active_now as _rec_active
        _rec_active()
    except Exception as _e:
        _log.warning("silent except: %s", _e)

    # This is a graceful quit — mark the run clean so the next launch doesn't read it
    # as a crash/stall (§10.5).
    try:
        from brain.utils import lifecycle as _lifecycle
        _lifecycle.mark_clean_shutdown()
    except Exception as _e:
        _log.warning("silent except: %s", _e)

    try:
        ctx.stop_evt.set()
    except Exception as _e:
        _log.warning("silent except: %s", _e)

    if ctx.cog_thread is not None and ctx.cog_thread.is_alive():
        ctx.cog_thread.join(timeout=15)

    try:
        if ctx.alive: ctx.alive.stop()
    except Exception as _e:
        _log.warning("silent except: %s", _e)
    try:
        if ctx.goals_daemon: ctx.goals_daemon.stop()
    except Exception as _e:
        _log.warning("silent except: %s", _e)

    try:
        if ctx.fs_obs:
            ctx.fs_obs.stop()
            ctx.fs_obs.join()
    except Exception as _e:
        _log.warning("silent except: %s", _e)

    try:
        ctx.memory_daemon.stop(join=True)
    except Exception as _e:
        _log.warning("silent except: %s", _e)
    try:
        wal_flush()
    except Exception as _e:
        _log.warning("silent except: %s", _e)

    # Seal a Life Capsule for this run — the evidence export (third sibling of the
    # mind/diagnostics exporters). Best-effort and disable-able via ORRIN_LIFE_CAPSULE;
    # done after the WAL flush so the daemon trees are consistent at the captured instant.
    try:
        from brain.evidence.life_capsule import maybe_build_capsule as _build_capsule
        _build_capsule("normal_shutdown")
    except Exception as _e:
        _log.warning("silent except: %s", _e)

    if ctx.ui_proc is not None:
        try:
            from backend.server.launcher import stop_ui
            stop_ui(ctx.ui_proc)
        except Exception:
            _log.warning("silent except")

    _wd.cancel()
    print("[main] shutdown complete.")


def wipe_to_newborn(ctx: RuntimeContext) -> None:
    """Delete Orrin's accumulated state so the next boot is a clean newborn, while
    PRESERVING the bundled config seeds (a newborn's brain/data == the seeds). Wipes
    the daemon-durability tree, self-written code, logs, and generated think module
    wholesale; in brain/data only the non-seed (accumulated) files are removed. Safe
    in-repo (seeds are kept, never self-destructed) and relocated alike."""
    repo_root = ctx.repo_root
    try:
        from brain.paths import DATA_DIR, STATE_DIR, LOGS_DIR, THINK_DIR, SELF_CODE_DIR
    except Exception:
        DATA_DIR = repo_root / "brain" / "data"
        STATE_DIR = repo_root / "data"
        LOGS_DIR = repo_root / "brain" / "logs"
        THINK_DIR = repo_root / "brain" / "think"
        SELF_CODE_DIR = DATA_DIR / "self_code"

    seeds = set(_newborn.SEED_FILES)
    if DATA_DIR.exists():
        for p in DATA_DIR.iterdir():
            if p.name in seeds:
                continue  # keep the newborn baseline
            try:
                shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
            except Exception as e:
                print(f"[reset] could not remove {p}: {e}")
    # SELF_CODE_DIR lives under DATA_DIR (already covered), but list it explicitly for
    # the relocated case; the rest are separate trees.
    for d in (SELF_CODE_DIR, STATE_DIR, LOGS_DIR, THINK_DIR, repo_root / "tmp"):
        try:
            shutil.rmtree(d, ignore_errors=True)
        except Exception as e:
            print(f"[reset] could not remove {d}: {e}")
    # Recreate the seed baseline where the data dir was relocated (no-op in-repo).
    _newborn.seed_if_newborn()


def reexec() -> None:
    """Replace this process image with a fresh launch — the only reliable way to get
    a true newborn, since the live brain holds his whole mind in RAM and would just
    re-persist it otherwise."""
    print("[reset] re-launching as a newborn…", flush=True)
    try:
        # Frozen (PyInstaller): sys.argv[0] is already the app binary, so re-pass only
        # the extra args. From source: sys.argv[0] is the script and must be handed to
        # the interpreter as its first argument.
        if getattr(sys, "frozen", False):
            argv = [sys.executable, *sys.argv[1:]]
        else:
            argv = [sys.executable, *sys.argv]
        os.execv(sys.executable, argv)
    except Exception as e:
        # If exec fails, exit non-zero so a supervisor (run_orrin.sh) restarts us.
        print(f"[reset] re-exec failed ({e}); exiting for supervisor restart", file=sys.stderr)
        os._exit(42)


def reset_to_newborn(ctx: RuntimeContext) -> None:
    """The Reset Orrin action: stop thinking, flush + wipe his state to a newborn,
    then re-launch. Runs on a backend timer thread (off the HTTP response)."""
    print("[reset] resetting Orrin to a newborn…", flush=True)
    stop_cognition(ctx)  # idempotent: winds down the loop + goals/alive/fs daemons
    try:
        ctx.memory_daemon.stop(join=True)
    except Exception as _e:
        _log.warning("silent except: %s", _e)
    try:
        wal_flush()
    except Exception as _e:
        _log.warning("silent except: %s", _e)
    wipe_to_newborn(ctx)
    _single_instance.release()
    reexec()


def restart_process(ctx: RuntimeContext) -> None:
    """Restart WITHOUT wiping — used after a Mind Restore swaps his state on disk, so
    the new mind loads from a clean process. Same machinery as reset, minus the wipe."""
    print("[restart] restarting Orrin (state preserved)…", flush=True)
    stop_cognition(ctx)
    try:
        ctx.memory_daemon.stop(join=True)
    except Exception as _e:
        _log.warning("silent except: %s", _e)
    try:
        wal_flush()
    except Exception as _e:
        _log.warning("silent except: %s", _e)
    _single_instance.release()
    reexec()


def notify_still_thinking() -> None:
    """Tell the user, via the OS notification path, that Orrin is alive in the
    background after the window closed (Always-thinking mode). Best-effort."""
    try:
        from brain.agency.skills.notify_user import notify_user
        notify_user({"title": "Orrin is still thinking",
                     "message": "His window closed, but he keeps living in the background."})
    except Exception as _e:
        _log.warning("silent except: %s", _e)


def make_on_signal(ctx: RuntimeContext):
    """Build the SIGINT/SIGTERM handler bound to this context.

    The handler MUST be async-signal-safe. It can fire while the main thread holds
    a non-reentrant lock — e.g. mid-`print` holding the stdout buffer lock (the
    pulse loop prints `[main] pulse=…` every 100 ticks). Doing I/O here (print,
    window.destroy, writing the clean-shutdown marker) can therefore deadlock or
    raise a reentrant-call error from inside the handler, which is exactly how a
    stop once died as exit 130 with NO graceful shutdown and got mis-recorded as a
    crash (then needlessly auto-restarted by run_orrin.sh).

    So we do the one safe thing — set the Event (the documented signal-handler
    pattern) — and let the main thread observe the flag and run the I/O-heavy
    teardown on a clean stack:
      • fallback/headless: `pulse_loop`'s `while not main_stop.is_set()` exits →
        `finally: graceful_shutdown()` (prints, marks the run clean, exits 0).
      • bridge mode: a shutdown-watcher thread (started in run()) waits on
        main_stop and destroys the window so webview.start() returns into the
        same graceful path."""
    def _on_signal(signum, _frame) -> None:
        ctx.main_stop.set()
    return _on_signal


def maybe_start_vital_calibration_stress(ctx: RuntimeContext) -> None:
    mode = os.environ.get("ORRIN_VITAL_CALIBRATION_STRESS", "").strip().lower()
    if not mode:
        return
    from runtime import watchdog_setup as _wd_setup
    delay_s = _wd_setup.env_float("ORRIN_VITAL_CALIBRATION_STRESS_DELAY_S", 20.0)
    read_steps = int(_wd_setup.env_float("ORRIN_VITAL_CALIBRATION_READING_STEPS", 45.0))
    sample_s = _wd_setup.env_float(
        "ORRIN_VITAL_CALIBRATION_STRESS_SAMPLE_S",
        _wd_setup.env_float("ORRIN_VITAL_CALIBRATION_SAMPLE_S", 1.0),
    )
    delay_s = max(0.0, delay_s)
    read_steps = max(1, read_steps)
    sample_s = max(0.2, sample_s)

    def _direct_sample(stop: threading.Event, phase: str) -> None:
        path = os.environ.get("ORRIN_VITAL_CALIBRATION_FILE", "").strip()
        if not path:
            return
        import json
        while not stop.is_set():
            try:
                _rss_fn = ctx.wd_inputs.get_own_rss_bytes
                _budget_fn = ctx.wd_inputs.get_budget_bytes
                rss = float(_rss_fn()) if callable(_rss_fn) else 0.0
                budget = float(_budget_fn()) if callable(_budget_fn) else 0.0
                if rss > 0.0 and budget > 0.0:
                    rec = {
                        "ts": time.time(),
                        "monotonic_s": round(time.monotonic(), 3),
                        "phase": phase,
                        "rss_bytes": int(rss),
                        "budget_bytes": int(budget),
                        "frac": round(rss / budget, 6),
                        "level": "stress_sample",
                        "observe_only": True,
                    }
                    with open(path, "a", encoding="utf-8") as fh:
                        fh.write(json.dumps(rec, sort_keys=True) + "\n")
            except Exception as _e:
                _log.warning("vital calibration direct sample failed: %s", _e)
                return
            stop.wait(sample_s)

    def _run() -> None:
        sampler_stop = threading.Event()
        sampler_thread = None
        try:
            time.sleep(delay_s)
            print(f"[vital-cal] stress={mode} starting", flush=True)
            phase = os.environ.get("ORRIN_VITAL_CALIBRATION_PHASE", mode) or mode
            sampler_thread = threading.Thread(
                target=_direct_sample,
                args=(sampler_stop, phase),
                name="orrin-vital-cal-direct-sampler",
                daemon=True,
            )
            sampler_thread.start()
            cog_ctx = {
                "calibration_phase": phase,
                "latest_user_input": "",
            }
            if mode in ("reading", "dream_reading", "reading_dream"):
                try:
                    from brain.cognition.language.acquisition import read_a_book as _read_a_book
                    line = _read_a_book(cog_ctx, steps=read_steps)
                    if line:
                        print(f"[vital-cal] reading stress: {line[:120]}", flush=True)
                except Exception as _e:
                    _log.warning("vital calibration reading stress failed: %s", _e)
            if mode in ("dream", "dream_reading", "reading_dream"):
                try:
                    from brain.cognition.dreaming.dream_cycle import dream_cycle as _dream_cycle
                    result = _dream_cycle(cog_ctx)
                    print(f"[vital-cal] dream stress complete: {str(result)[:160]}", flush=True)
                except Exception as _e:
                    _log.warning("vital calibration dream stress failed: %s", _e)
            print(f"[vital-cal] stress={mode} complete", flush=True)
        except Exception as _e:
            _log.warning("vital calibration stress thread failed: %s", _e)
        finally:
            sampler_stop.set()
            if sampler_thread is not None:
                sampler_thread.join(timeout=2.0)

    threading.Thread(target=_run, name="orrin-vital-cal-stress", daemon=True).start()
    try:
        ctx.stop_evt.set()
    except Exception:
        # Handler context — never do logging I/O here; the main thread reports.
        pass
