"""RuntimeContext — the boot-produced runtime state threaded through the
lifecycle stages (Phase 4B/5).

main.py runs the boot sequence, builds this once, then hands it to the
lifecycle/desktop stages (`runtime.lifecycle`, `runtime.desktop`) instead of
having them reach back into module globals. That's what let those stages move
out of the entrypoint: they no longer close over `main`'s mutable boot state.

A plain mutable dataclass — a few fields (`cog_thread` and the two teardown
guards) are set/flipped after construction (in `run()`), so it isn't frozen.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Event, Thread
from typing import Any, Callable, Optional


@dataclass
class RuntimeContext:
    # --- core heartbeat / stop signalling ---
    pulse: Any
    stop_evt: Event                  # winds down the cognitive loop + its daemons
    main_stop: Event                 # set by Ctrl+C/SIGTERM/window-close to unwind run()
    # --- subsystems brought up during boot ---
    memory_daemon: Any
    goals_api: Any
    goals_daemon: Any
    alive: Any
    fs_obs: Any
    ui_proc: Any
    # --- native UI bridge ---
    bridge: Any
    bridge_mode: bool
    bridge_window_file: Optional[str]
    # --- watchdog providers (surfaced for the vital-calibration stress path) ---
    wd_inputs: Any
    # --- fast metric sampler the heartbeat fires ---
    sample_metrics_fast: Callable[[], Any]
    repo_root: Path
    # --- set/flipped after construction (in run() / teardown) ---
    cog_thread: Optional[Thread] = None   # the cognitive-loop thread
    cognition_stopped: bool = False       # guards stop_cognition against double-invocation
    shutting_down: bool = False           # guards graceful_shutdown against double-invocation
