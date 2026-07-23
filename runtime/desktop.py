"""Desktop run loop (Phase 4B, extracted from main.py).

`run(ctx)` owns the foreground lifetime: it starts the cognitive loop, installs
the signal handlers, and then either drives the native pywebview window (the
default packaged path, which must own the main thread) or runs the heartbeat on
the main thread (dev / headless / fallback-browser). Either way it returns into
`lifecycle.graceful_shutdown` on stop. main.py builds the RuntimeContext and
calls this; everything it needs is on the context.
"""
from __future__ import annotations

import os
import signal
import threading
import time

from brain.core.runtime_log import get_logger
from brain.utils.get_cycle_count import get_cycle_count

from runtime import lifecycle
from runtime.context import RuntimeContext

_log = get_logger(__name__)


def _brain_exit_watch_loop(ctx: RuntimeContext) -> None:
    """Poll the cognitive-loop thread; when it ends for any reason that is NOT a
    deliberate Stop or an already-started shutdown, trip main_stop so run() falls
    into graceful_shutdown and the process exits 0 (Run-12 Slice 1A.1). ORRIN_ONCE
    folds in as a bounded early-exit condition. Module-level (not a closure) so the
    natural-death→exit contract is unit-testable."""
    once = os.getenv("ORRIN_ONCE") == "1"
    if once:
        print("[brain] ORRIN_ONCE: will stop the process after one cognitive cycle")
    start_cycles = get_cycle_count()
    deadline = time.time() + 120.0
    while True:
        if ctx.cog_thread is None or not ctx.cog_thread.is_alive():
            break
        # A deliberate Stop / any already-started shutdown owns the teardown; the
        # watcher must not steal it (Stop keeps the UI up).
        if ctx.cognition_stopped or ctx.shutting_down or ctx.main_stop.is_set():
            return
        if once and (time.time() >= deadline or get_cycle_count() > start_cycles):
            break
        time.sleep(0.2)
    # The loop thread ended (or ORRIN_ONCE fired). If a deliberate Stop or a
    # shutdown already in flight owns it, leave it alone.
    if ctx.cognition_stopped or ctx.shutting_down or ctx.main_stop.is_set():
        return
    # Print on the single exit path, not inside the loop: under ORRIN_ONCE the
    # loop thread can die between polls (its one tick is done), and the
    # thread-ended break must still emit the single-cycle marker the boot
    # characterization test orders on — not the natural-death line.
    if once:
        print("[brain] ORRIN_ONCE: single cycle complete → stopping")
    else:
        print("[brain] cognitive loop ended (natural death / exit) → stopping process")
    ctx.main_stop.set()


def _start_brain_exit_watcher(ctx: RuntimeContext) -> threading.Thread:
    t = threading.Thread(
        target=_brain_exit_watch_loop, args=(ctx,),
        name="orrin-brain-exit-watcher", daemon=True,
    )
    t.start()
    return t


def run(ctx: RuntimeContext) -> None:
    # ---------- Cognitive loop (v1 brain) ----------
    ctx.cog_thread = None
    # Install our own SIGINT/SIGTERM handlers now (main thread, after all the heavy
    # boot imports) so Ctrl+C reliably drives a clean shutdown.
    _on_signal = lifecycle.make_on_signal(ctx)
    for _sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(_sig, _on_signal)
        except Exception as _e:
            _log.warning("could not install %s handler: %s", _sig, _e)
    try:
        from brain.ORRIN_loop import run_cognitive_loop
        ctx.cog_thread = threading.Thread(
            target=run_cognitive_loop,
            kwargs={
                "pulse": ctx.pulse,
                "goals_api": ctx.goals_api,
                "memory_daemon": ctx.memory_daemon,
                "stop_event": ctx.stop_evt,
                "cycle_sleep": float(os.environ.get("ORRIN_CYCLE_SLEEP", "1")),
            },
            name="orrin-brain",
            daemon=True,
        )
        ctx.cog_thread.start()
        print("[brain] cognitive loop thread started")
        lifecycle.maybe_start_resource_calibration_stress(ctx)
        try:
            from brain.utils import boot_events as _boot
            _boot.emit("Starting cognition")
            _boot.mark_ready()  # cognition is live → the wake screen can dissolve
        except Exception as _e:
            _log.warning("silent except: %s", _e)
    except Exception as e:
        print(f"[brain] could not start cognitive loop: {e}")
        try:
            from brain.utils import boot_events as _boot
            _boot.emit("Starting cognition", ok=False, note=str(e))
            _boot.mark_ready()  # don't trap the UI on the wake screen if cognition failed
        except Exception as _e:
            _log.warning("silent except: %s", _e)

    # ---------- Native bridge window (default) vs headless/dev pulse loop ------
    # A native pywebview window must own the MAIN thread, so the heartbeat moves
    # to a daemon thread and closing the window returns control here → graceful
    # shutdown (same path as Ctrl+C). Dev/fallback keep the heartbeat on the main
    # thread (the UI is a browser tab) and wait on Ctrl+C.
    ctx.main_stop.clear()

    # Brain-exit watcher (Run-12 Slice 1A.1): the cognitive loop runs on a daemon
    # thread, so when it ENDS ON ITS OWN — a natural lifespan death breaks the loop
    # on `_runtime_ending` — nothing else winds the process down. Before this, the
    # main thread stayed in pulse_loop forever, the cognitive cycle counter froze,
    # and the supervisor's cycle-stall watchdog eventually kill+relaunched into a
    # born-dead loop (Run 11 shutdown-hang: 4 born-dead relaunches, 0 cycles).
    #
    # So watch the loop thread and, when it ends for any reason that is NOT a
    # deliberate Stop (the Stop button sets cognition_stopped and keeps the UI up)
    # or an already-initiated shutdown, trip main_stop. Both the bridge and the
    # headless paths then fall into the normal graceful_shutdown (whose own watchdog
    # forces exit if teardown stalls) → the process exits 0 → run_orrin.sh sees a
    # clean exit and does not restart. Armed AFTER main_stop.clear() so the clear
    # can't race the watcher. ORRIN_ONCE (single-cycle run) folds in as a bounded
    # early-exit condition on the same watcher.
    if ctx.cog_thread is not None:
        _start_brain_exit_watcher(ctx)

    if ctx.bridge_mode and ctx.bridge_window_file:
        import webview  # available — bridge mode was only chosen if importable
        _pulse_thread = threading.Thread(
            target=lifecycle.pulse_loop, args=(ctx, ctx.main_stop), name="orrin-pulse", daemon=True
        )
        _pulse_thread.start()
        # "Always thinking" (§10.3): when the window closes on its own, keep the
        # process — and therefore the brain's daemon threads — ALIVE in the
        # background instead of shutting down. (Re-opening a window in the same
        # process isn't possible with pywebview; quitting + relaunch reopens it.)
        _always_thinking = False
        try:
            from brain.utils import prefs as _prefs
            _always_thinking = _prefs.get("existence_mode", "sleep") == "always"
        except Exception as _e:
            _log.warning("silent except: %s", _e)
        try:
            window = webview.create_window(
                "Orrin", url=ctx.bridge_window_file, js_api=ctx.bridge, width=1440, height=900
            )
            ctx.bridge.attach_window(window)

            # R8: the peripheral mini-orb — a second frameless, always-on-top
            # window on the same bridge, opt-in via Settings ("widget_enabled",
            # applied at launch). Best-effort: a failed widget must never block
            # the main window.
            try:
                from brain.utils import prefs as _wprefs
                if _wprefs.get("widget_enabled", False):
                    _widget = webview.create_window(
                        "Orrin (orb)",
                        url=f"{ctx.bridge_window_file}#/widget",
                        js_api=ctx.bridge,
                        width=132, height=132,
                        frameless=True, on_top=True, resizable=False,
                    )
                    ctx.bridge.attach_extra_window(_widget)

                    def _widget_closed() -> None:
                        ctx.bridge.detach_extra_window(_widget)
                    _widget.events.closed += _widget_closed
                    print("[widget] peripheral mini-orb window opened")
            except Exception as _we:
                _log.warning("mini-orb widget failed to open: %s", _we)

            # Signal → window teardown, off the handler stack. _on_signal only sets
            # main_stop (it must stay I/O-free); this watcher does the destroy that
            # returns webview.start() into graceful_shutdown. Daemon so it can't keep
            # the process alive on its own.
            def _shutdown_watcher() -> None:
                ctx.main_stop.wait()
                try:
                    window.destroy()  # idempotent enough; webview ignores a re-destroy
                except Exception:
                    pass
            threading.Thread(
                target=_shutdown_watcher, name="orrin-shutdown-watcher", daemon=True
            ).start()

            # Always-thinking: a status-bar tray (F1) lets the user re-show or quit while
            # the window is closed and the brain keeps running. If the tray comes up, the
            # window's close becomes HIDE (he keeps thinking; the view re-attaches via E6)
            # instead of destroy. If it can't start (missing dep / platform), we keep the
            # old behavior — closing → headless + a notification — so a failed tray can
            # never trap the user with a hidden, unreachable window.
            _tray = None
            _tray_up = False
            _quitting = {"v": False}
            if _always_thinking:
                from backend.server.tray import Tray

                def _on_tray_show() -> None:
                    try:
                        window.show()
                        ctx.bridge.attach_window(window)  # re-point telemetry at the view
                    except Exception as _te:
                        _log.warning("tray show failed: %s", _te)

                def _on_tray_quit() -> None:
                    _quitting["v"] = True
                    ctx.main_stop.set()
                    try:
                        window.destroy()  # real teardown → webview.start() returns
                    except Exception as _te:
                        _log.warning("tray quit destroy failed: %s", _te)

                def _on_closing() -> bool:
                    # While the tray is up and this isn't a real quit, cancel the destroy
                    # (return False) and hide instead. If hiding fails, allow the close
                    # rather than strand the user.
                    if _tray_up and not _quitting["v"] and not ctx.main_stop.is_set():
                        try:
                            window.hide()
                            ctx.bridge.detach_window()
                            return False
                        except Exception:
                            return True
                    return True

                window.events.closing += _on_closing
                _tray = Tray()
                _tray_up = _tray.start(on_show=_on_tray_show, on_quit=_on_tray_quit)
                if _tray_up:
                    print("[existence] Always-thinking — tray active; closing the window "
                          "hides it (Orrin keeps thinking). Quit from the tray.", flush=True)

            # Blocks until the window is destroyed (with a live tray, close is
            # cancelled→hidden; destroy then comes from the tray's Quit).
            webview.start()
            if _tray is not None:
                _tray.stop()

            # Without a working tray, preserve headless-on-close: if the window closed by
            # itself (not Stop/Ctrl+C/tray-Quit, which set main_stop) and Always-thinking
            # is on, stay alive headless — the cognitive loop and daemons keep running and
            # notify_user can still reach the user — until a real termination signal.
            if _always_thinking and not _tray_up and not ctx.main_stop.is_set():
                print("[existence] Window closed — Orrin keeps thinking in the background "
                      "(Always thinking). Ctrl+C / quit to stop him.", flush=True)
                lifecycle.notify_still_thinking()
                ctx.main_stop.wait()  # daemon brain threads keep advancing while we block
            else:
                lifecycle.say("\n[main] window closed; shutting down…")
        except KeyboardInterrupt:
            lifecycle.say("\n[main] Ctrl+C received; shutting down…")
        finally:
            ctx.main_stop.set()
            _pulse_thread.join(timeout=5)
            lifecycle.graceful_shutdown(ctx)
        return

    # No native window (ORRIN_UI=0, dev, or fallback browser tab): heartbeat on the
    # main thread until a signal (handled by _on_signal) sets main_stop.
    try:
        lifecycle.pulse_loop(ctx, ctx.main_stop)
    except KeyboardInterrupt:
        lifecycle.say("\n[main] Ctrl+C received; shutting down…")
    finally:
        ctx.main_stop.set()
        lifecycle.graceful_shutdown(ctx)
