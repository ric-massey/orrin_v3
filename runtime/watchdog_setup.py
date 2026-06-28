"""Watchdog input construction (Phase 4B, extracted from main.py).

`build()` assembles everything `watchdogs.start_watchdogs()` needs that is NOT
boot-mutable runtime state: the psutil resource providers (host + inward
vital-floor), the host/vital escalation callbacks, and the vital-floor config
parsed from the environment. It touches only psutil, env, the telemetry bridge,
working memory, and gc — none of the boot globals (the daemon, store, goals) —
so it lives outside main.py's coupled boot core.

main.py calls `build()`, then passes the result's `.kwargs` (plus the
boot-state args: `pulse`, `get_memory_health`, `memory_daemon`, the ns sample
intervals, and `per_key_limits`) to `start_watchdogs`. The two inward getters
are also surfaced on the bundle for the vital-calibration stress path.
"""
from __future__ import annotations

import gc
import os
from dataclasses import dataclass
from typing import Callable, Optional

from brain.core.runtime_log import get_logger

_log = get_logger(__name__)

# A float provider, or None when psutil is absent (the guard degrades to off).
_Provider = Optional[Callable[[], float]]


def env_float(name: str, default: float) -> float:
    """Parse a float from the environment, falling back to `default` on any error.
    Shared by the watchdog vital-floor config and main.py's calibration path."""
    try:
        raw = os.environ.get(name)
        return default if raw is None else float(raw)
    except Exception:
        return default


def _host_flag(state: str, msg: str) -> None:
    """Surface host/vital resource pressure on the live telemetry stream. These are
    NON-fatal: the guards never kill Orrin (that wouldn't reclaim host swap/disk),
    they just flag the pressure and, at the hard line, pause the heavy cycles."""
    try:
        from backend.telemetry_bridge import get_bridge
        tb = get_bridge()
        level = "warn" if state != "ok" else "info"
        tb.log(level, "host", msg)
        tb.update(extra={"host_resource_state": state, "host_resource_detail": msg})
    except Exception as _e:
        _log.warning("silent except: %s", _e)


@dataclass
class WatchdogInputs:
    """The extracted watchdog inputs. `kwargs` splats straight into
    `start_watchdogs`; the two getters are also surfaced for the calibration path."""
    kwargs: dict
    get_own_rss_bytes: _Provider
    get_budget_bytes: _Provider


def build() -> WatchdogInputs:
    # ---- psutil-based resource providers (gracefully absent if psutil isn't) ----
    try:
        import psutil as _psutil
        _proc = _psutil.Process()
        # `resource` is POSIX-only; absent on Windows. Keep psutil monitoring either way.
        try:
            import resource as _resource
        except Exception:
            _resource = None  # type: ignore[assignment]

        def get_rss_mb() -> float:
            return _proc.memory_info().rss / 1024 / 1024

        def get_fd_open() -> int:
            # num_fds() on POSIX, num_handles() on Windows
            if hasattr(_proc, "num_fds"):
                return _proc.num_fds()
            return _proc.num_handles()

        def get_fd_limit() -> int:
            try:
                if _resource is not None:
                    return min(_resource.getrlimit(_resource.RLIMIT_NOFILE)[0], 1024)
            except Exception:
                pass
            return 1024

        def get_sock_open() -> int:
            try:
                return len(_proc.net_connections())
            except Exception:
                return 0

        def get_sock_limit() -> int:
            return 1024

        def get_cpu_util() -> float:
            return _proc.cpu_percent(interval=None) / 100.0

        # Host-machine signals (outward-looking, not Orrin's own process).
        def get_disk_free_bytes() -> float:
            return float(_psutil.disk_usage("/").free)

        def get_swap_used_bytes() -> float:
            return float(_psutil.swap_memory().used)

        def get_vmem_percent() -> float:
            return float(_psutil.virtual_memory().percent)

        # Inward vital-floor signals: Orrin's OWN footprint vs his GRANTED body size.
        def get_own_rss_bytes() -> float:
            return float(_proc.memory_info().rss)

        def get_budget_bytes() -> float:
            # The same grant resource_cadence/interoception read — budget size and safety
            # floor can never disagree. Falls back to a conservative full-RAM ceiling
            # if body_budget is unavailable, so the guard degrades to never-trips.
            try:
                from brain.cognition.host_budget import budget_bytes
                return float(budget_bytes())
            except Exception:
                return float(_psutil.virtual_memory().total)
    except ImportError:
        get_rss_mb = get_fd_open = get_fd_limit = None  # type: ignore[assignment]
        get_sock_open = get_sock_limit = get_cpu_util = None  # type: ignore[assignment]
        get_disk_free_bytes = get_swap_used_bytes = get_vmem_percent = None  # type: ignore[assignment]
        get_own_rss_bytes = get_budget_bytes = None  # type: ignore[assignment]

    # ---- Host-resource escalation → console/dashboard (non-fatal) ----
    def host_on_warn(msg: str) -> None:
        print(f"[host] WARN {msg}")
        _host_flag("warn", msg)

    def host_on_pause(msg: str) -> None:
        print(f"[host] PAUSE heavy cycles — {msg}")
        _host_flag("pause", msg)

    def host_on_resume(msg: str) -> None:
        print(f"[host] resume — {msg}")
        _host_flag("ok", msg)

    # ---- Vital-floor reflex (inward) config ----
    # Orrin nearing the survival line of his OWN granted body → involuntary
    # load-shedding, never a kill. Armed by default after the S2b calm +
    # dream/reading calibration pass (2026-06-17). Set ORRIN_VITAL_FLOOR=observe
    # to return to calibration-only logging.
    vital_mode = os.environ.get("ORRIN_VITAL_FLOOR", "act").strip().lower()
    vital_observe_only = vital_mode not in ("act", "1", "on", "true")

    warn_frac = env_float("ORRIN_VITAL_WARN_FRAC", 0.50)
    shed_frac = env_float("ORRIN_VITAL_SHED_FRAC", 0.55)
    recover_frac = env_float("ORRIN_VITAL_RECOVER_FRAC", 0.22)
    sustain_s = env_float("ORRIN_VITAL_SUSTAIN_S", 8.0)
    calibration_file = os.environ.get("ORRIN_VITAL_CALIBRATION_FILE", "").strip() or None
    calibration_phase = os.environ.get("ORRIN_VITAL_CALIBRATION_PHASE", "unspecified").strip() or "unspecified"
    calibration_sample_s = env_float("ORRIN_VITAL_CALIBRATION_SAMPLE_S", 1.0)

    # Keep the hysteresis shape valid even with env overrides.
    warn_frac = max(0.01, min(0.99, warn_frac))
    shed_frac = max(warn_frac + 0.01, min(1.50, shed_frac))
    recover_frac = max(0.0, min(warn_frac - 0.01, recover_frac))
    sustain_s = max(0.5, sustain_s)
    calibration_sample_s = max(0.2, calibration_sample_s)

    def vital_on_warn(msg: str) -> None:
        print(f"[vital] WARN {msg}")
        _host_flag("warn", msg)

    def vital_on_shed(msg: str) -> None:
        print(f"[vital] SHED — {msg}")
        _host_flag("pause", msg)

    def vital_on_recover(msg: str) -> None:
        print(f"[vital] recover — {msg}")
        _host_flag("ok", msg)

    def vital_shed_action(reason: str) -> None:
        """The autonomic gasp: let go of the heaviest disposable thing, in priority
        order, until Orrin is back above his granted-body floor. Reversible, never
        fatal. Only called when the guard is armed (not observe-only).

        Note: "stop launching new heavy cycles" is handled durably by the guard's own
        vital_floor_shedding() gate (self-clearing with hysteresis), which the loop
        checks before dream/reading — so this action does only the one-shot reclaim
        and must NOT touch the host pause gate (the host guard would never clear it)."""
        # Force-trim rebuildable working memory if the store exposes a trim.
        try:
            from brain.cog_memory import working_memory as _wm
            for _name in ("force_trim", "shed", "trim_to_floor"):
                _fn = getattr(_wm, _name, None)
                if callable(_fn):
                    _fn(); break
        except Exception as _e:
            _log.warning("vital shed: wm-trim failed: %s", _e)
        # Reclaim arena memory the allocator is holding.
        try:
            gc.collect()
        except Exception as _e:
            _log.warning("vital shed: gc failed: %s", _e)

    kwargs = dict(
        get_rss_mb=get_rss_mb,
        get_fd_open=get_fd_open,
        get_fd_limit=get_fd_limit,
        get_sock_open=get_sock_open,
        get_sock_limit=get_sock_limit,
        get_cpu_util=get_cpu_util,
        get_disk_free_bytes=get_disk_free_bytes,
        get_swap_used_bytes=get_swap_used_bytes,
        get_vmem_percent=get_vmem_percent,
        host_on_warn=host_on_warn,
        host_on_pause=host_on_pause,
        host_on_resume=host_on_resume,
        get_own_rss_bytes=get_own_rss_bytes,
        get_budget_bytes=get_budget_bytes,
        vital_on_warn=vital_on_warn,
        vital_on_shed=vital_on_shed,
        vital_on_recover=vital_on_recover,
        vital_shed_fn=vital_shed_action,
        vital_warn_frac=warn_frac,
        vital_shed_frac=shed_frac,
        vital_recover_frac=recover_frac,
        vital_sustain_s=sustain_s,
        vital_observe_only=vital_observe_only,
        vital_calibration_file=calibration_file,
        vital_calibration_phase=calibration_phase,
        vital_calibration_sample_s=calibration_sample_s,
    )
    return WatchdogInputs(
        kwargs=kwargs,
        get_own_rss_bytes=get_own_rss_bytes,
        get_budget_bytes=get_budget_bytes,
    )
