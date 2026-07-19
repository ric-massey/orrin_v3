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

    # ORRIN_ONCE: the cognitive loop breaks after a single tick, but the process
    # otherwise lives on (pulse heartbeat + daemons), so a "single-cycle" run never
    # returns on its own. Watch the loop and, once that one cycle is done, trip
    # main_stop so both the bridge and headless paths fall into the normal graceful
    # shutdown (whose own watchdog forces exit if teardown stalls). Armed AFTER
    # main_stop.clear() above so the clear can't race the watcher. Only active when
    # ORRIN_ONCE=1, so steady-state is untouched. The watcher stops on whichever
    # comes first — the loop thread ending, the cognitive cycle counter advancing, or
    # a hard deadline — so a slow/blocking loop teardown can't strand the run.
    if os.getenv("ORRIN_ONCE") == "1" and ctx.cog_thread is not None:
        print("[brain] ORRIN_ONCE: will stop the process after one cognitive cycle")
        _once_start_cycles = get_cycle_count()
        _once_deadline = time.time() + 120.0

        def _once_watcher() -> None:
            while time.time() < _once_deadline:
                if not ctx.cog_thread.is_alive():
                    break
                if get_cycle_count() > _once_start_cycles:
                    break
                time.sleep(0.2)
            print("[brain] ORRIN_ONCE: single cycle complete → stopping")
            ctx.main_stop.set()
        threading.Thread(
            target=_once_watcher, name="orrin-once-watcher", daemon=True
        ).start()

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
