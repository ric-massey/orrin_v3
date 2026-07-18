# watchdogs.py
from brain.core.runtime_log import get_logger
import os
import threading
import time
from typing import Tuple, Callable, Dict, List, Optional, Any  # added Any

from supervisor.supervisor import Supervisor, kill_current_process
from supervisor.heartbeatdetector import HeartbeatDetector
from supervisor.error_checker import ErrorChecker
from supervisor.liveness_cycle import LivenessByCycles, DEFAULT_MAX_MISSED_CYCLES
from supervisor.lifespan import LifespanByCycles
from supervisor.cycle_stall import CycleStallGuard, DEFAULT_MAX_STALL_S, DEFAULT_POLL_INTERVAL_S
from supervisor.no_goals import NoGoalsGuard
from supervisor.memory import MemoryHealthGuard
from supervisor.host_resources import HostResourceGuard
from supervisor.resource_floor import ResourceFloorGuard
from supervisor.repeat import RepeatLoopGuard
from observability.health_telemetry import HealthBus, HealthTelemetrySampler
from observability.metrics import (
    rss_mb_gauge,
    fd_pct_open_gauge,
    sock_pct_open_gauge,
    cpu_util_gauge,
    step_latency_ms_gauge,
)
_log = get_logger(__name__)

_GB = 1024 * 1024 * 1024


def _swap_gb_env(var: str, default_gb: float) -> float:
    """Read a swap threshold (in GB) from an env var, falling back to default_gb.

    Lets the host swap warn/pause lines be tuned per-machine without code edits
    (e.g. ORRIN_SWAP_PAUSE_GB=6). Bad/empty values fall back to the default.
    Returns a byte count for HostResourceGuard."""
    raw = os.getenv(var)
    if raw:
        try:
            return float(raw) * _GB
        except (TypeError, ValueError):
            _log.warning("ignoring bad %s=%r; using %.1fGB", var, raw, default_gb)
    return default_gb * _GB

# Provider type hints (optional, just for clarity)
GetGoals = Callable[[], List[Dict]]
GetRetryRate = Callable[[], float]
GetBreakers = Callable[[], List[Dict]]

# Memory/FD/CPU provider hints
GetRssMb = Callable[[], float]
GetFdOpen = Callable[[], int]
GetFdLimit = Callable[[], int]
GetSockOpen = Callable[[], int]
GetSockLimit = Callable[[], int]
GetCpuUtil = Callable[[], float]
GetStepLatencyMs = Callable[[], float]
GetMemoryHealth = Callable[[], Dict[str, float | int]]  # ← already NEW

# Host-machine resource provider hints (NEW: outward-looking, not Orrin's own)
GetDiskFreeBytes = Callable[[], float]
GetSwapUsedBytes = Callable[[], float]
GetVmemPercent = Callable[[], float]

# Resource-floor provider hints (inward: Orrin's own footprint vs his granted body)
GetOwnRssBytes = Callable[[], float]
GetBudgetBytes = Callable[[], float]

class Pulse:
    """Thread-safe pulse counter that the main loop updates."""
    def __init__(self) -> None:
        self._n = 0
        self._lock = threading.Lock()

    def tick(self) -> None:
        with self._lock:
            self._n += 1

    def read(self) -> int:
        with self._lock:
            return self._n


def start_watchdogs(
    pulse: Pulse,
    *,
    # Heartbeat thresholds
    min_period_ms: float = 5.0,
    max_period_ms: float = 10_000.0,  # 10s slow cap
    sustain_checks_fast: int = 100,
    sustain_checks_slow: int = 10,
    window: int = 64,
    # Heartbeat/Liveness polling rate (background thread)
    hb_poll_interval_s: float = 0.010,  # 100 Hz
    # Error checker defaults
    error_window_s: float = 60.0,
    any_rate_limit: Tuple[int, float] | None = (100, 30.0),  # (count, window_s)
    per_key_limits: dict[str, Tuple[int, float]] | None = None,
    # Liveness-by-cycles (section freshness)
    liveness_max_missed_cycles: int = DEFAULT_MAX_MISSED_CYCLES,  # 10_000
    # Cycle-stall tripwire (Run 8 §0 owed item): keyed on production_loop cycle
    # stamps — the pulse-based heartbeat missed a dead brain thread for 6.5 h.
    get_loop_cycle: Optional[Callable[[], int]] = None,
    cycle_stall_max_s: float = DEFAULT_MAX_STALL_S,
    cycle_stall_poll_s: float = DEFAULT_POLL_INTERVAL_S,
    # Lifespan (random hard cutoff) — PER-PROCESS uptime, not agent lifespan.
    # The pulse ticks at ~50 Hz (main loop sleeps 0.02s), so these bounds mean
    # roughly 3–10 days of continuous process uptime before a forced restart.
    # The agent's persistent mortality clock (365–730 days, survives restarts)
    # is owned by brain/cognition/runtime_lifetime.py.
    lifespan_min_cycles: int = 12_960_000,
    lifespan_max_cycles: int = 43_200_000,
    # --------- NO-GOALS / SATURATION GUARD (providers + tunables) ---------
    goals_provider: Optional[GetGoals] = None,
    retry_rate_provider: Optional[GetRetryRate] = None,
    breakers_provider: Optional[GetBreakers] = None,
    # goals idleness (cycles)
    goals_max_idle_cycles: int = 1_800_000,
    # retry saturation (R/sec over T seconds)
    retry_rate_threshold: float = 5.0,
    retry_sustain_s: float = 10.0,
    # circuit breaker saturation
    cb_open_max_s: float = 60.0,
    cb_max_distinct_open: int = 3,
    cb_window_s: float = 30.0,
    # --------- MEMORY / FD / CPU GUARD (providers + tunables) ---------
    get_rss_mb: Optional[GetRssMb] = None,
    get_fd_open: Optional[GetFdOpen] = None,
    get_fd_limit: Optional[GetFdLimit] = None,
    get_sock_open: Optional[GetSockOpen] = None,
    get_sock_limit: Optional[GetSockLimit] = None,
    get_cpu_util: Optional[GetCpuUtil] = None,
    get_step_latency_ms: Optional[GetStepLatencyMs] = None,
    get_memory_health: Optional[GetMemoryHealth] = None,  # already NEW
    # thresholds/windows
    mem_slope_mb_per_s: float = 2.0,
    mem_sustain_s: float = 60.0,
    mem_floor_mb: float = 1500.0,
    mem_min_net_rise_mb: float = 120.0,
    fd_pct_threshold: float = 0.90,
    fd_sustain_s: float = 10.0,
    cpu_util_threshold: float = 0.95,
    cpu_sustain_s: float = 10.0,
    latency_slope_ms_per_s: float = 0.5,
    latency_mean_ms_threshold: float = 50.0,
    # --------- HOST RESOURCE GUARD (outward-looking; providers + tunables) ---------
    get_disk_free_bytes: Optional[GetDiskFreeBytes] = None,
    get_swap_used_bytes: Optional[GetSwapUsedBytes] = None,
    get_vmem_percent: Optional[GetVmemPercent] = None,
    host_on_warn: Optional[Callable[[str], None]] = None,
    host_on_pause: Optional[Callable[[str], None]] = None,
    host_on_resume: Optional[Callable[[str], None]] = None,
    disk_warn_free_bytes: float = 20.0 * 1024 * 1024 * 1024,
    disk_pause_free_bytes: float = 10.0 * 1024 * 1024 * 1024,
    disk_sustain_s: float = 10.0,
    swap_warn_used_bytes: float = _swap_gb_env("ORRIN_SWAP_WARN_GB", 2.0),
    swap_pause_used_bytes: float = _swap_gb_env("ORRIN_SWAP_PAUSE_GB", 4.0),
    swap_growth_warn_bytes_per_s: float = 5.0 * 1024 * 1024,
    swap_sustain_s: float = 20.0,
    vmem_warn_percent: float = 85.0,
    vmem_pause_percent: float = 95.0,
    vmem_sustain_s: float = 15.0,
    # --------- RESOURCE-FLOOR REFLEX (inward; Orrin's own footprint vs granted body) ---------
    get_own_rss_bytes: Optional[GetOwnRssBytes] = None,
    get_budget_bytes: Optional[GetBudgetBytes] = None,
    resource_floor_on_warn: Optional[Callable[[str], None]] = None,
    resource_floor_on_shed: Optional[Callable[[str], None]] = None,
    resource_floor_on_recover: Optional[Callable[[str], None]] = None,
    resource_floor_shed_fn: Optional[Callable[[str], None]] = None,
    resource_floor_warn_frac: float = 0.50,     # calibrated 2026-06-17 (§3.1/§7.2); main.py overrides
    resource_floor_shed_frac: float = 0.55,
    resource_floor_recover_frac: float = 0.22,
    resource_floor_sustain_s: float = 8.0,
    resource_floor_observe_only: bool = True,   # safe default; main.py arms it via ORRIN_VITAL_FLOOR=act
    resource_floor_calibration_file: Optional[str] = None,
    resource_floor_calibration_phase: str = "unspecified",
    resource_floor_calibration_sample_s: float = 1.0,
    # --------- REPEAT-LOOP GUARD (tunables) ---------
    enable_repeat_guard: bool = True,
    action_window_n: int = 50,
    same_call_k: int = 4,
    same_call_t: float = 30.0,
    breaker_cool_s: float = 60.0,
    pingpong_k: int = 6,
    pingpong_t: float = 30.0,
    no_progress_t: float = 60.0,
    no_progress_min_actions: int = 20,
    retry_k: int = 5,
    retry_w: float = 30.0,
    retry_escalate_k: int = 8,
    # --------- NERVOUS SYSTEM ( minimal additions) ---------
    memory_daemon: Optional[Any] = None,
    ns_sample_interval_s: float = 0.2,   # 5 Hz sensing
    ns_summary_interval_s: float = 5.0,  # compact memory summaries
    # --------- NEW: EVENT EMITTER (to wake the brain fast) ---------
    event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
):
    """
    Spin up a daemon thread that continuously checks watchdogs.
    Returns:
      (supervisor, detector, errors, liveness, lifespan, no_goals, mem_guard,
       host_guard, resource_floor_guard, repeat_guard, cycle_stall_guard, stop_evt)
    """
    supervisor = Supervisor(kill=kill_current_process)

    detector = HeartbeatDetector(
        get_pulse=pulse.read,
        on_violation=supervisor.trigger,
        min_period_ms=min_period_ms,
        max_period_ms=max_period_ms,
        sustain_checks_fast=sustain_checks_fast,
        sustain_checks_slow=sustain_checks_slow,
        window=window,
    )

    errors = ErrorChecker(on_violation=supervisor.trigger, window_s=error_window_s)

    if any_rate_limit:
        count, window_s = any_rate_limit
        errors.set_any_rate_limit(count=count, window_s=window_s)

    per_key_limits = per_key_limits or {}
    for key, (count, window_s) in per_key_limits.items():
        errors.set_key_rate_limit(key, count=count, window_s=window_s)

    # Liveness & lifespan
    liveness = LivenessByCycles(get_pulse=pulse.read, on_violation=supervisor.trigger)

    lifespan = LifespanByCycles(
        get_pulse=pulse.read,
        on_violation=supervisor.trigger,
        min_cycles=lifespan_min_cycles,
        max_cycles=lifespan_max_cycles,
    )

    # Cycle-stall tripwire (optional provider; skipped if None)
    cycle_stall_guard: Optional[CycleStallGuard] = None
    if get_loop_cycle is not None:
        cycle_stall_guard = CycleStallGuard(
            get_cycle=get_loop_cycle,
            on_violation=supervisor.trigger,
            max_stall_s=cycle_stall_max_s,
            poll_interval_s=cycle_stall_poll_s,
        )

    # No-goals / saturation guard (optional)
    no_goals = None
    if goals_provider is not None:
        no_goals = NoGoalsGuard(
            get_pulse=pulse.read,
            on_violation=supervisor.trigger,
            get_goals=goals_provider,
            get_retry_rate=retry_rate_provider,
            get_breakers=breakers_provider,
            max_idle_cycles=goals_max_idle_cycles,
            retry_rate_threshold=retry_rate_threshold,
            retry_sustain_s=retry_sustain_s,
            cb_open_max_s=cb_open_max_s,
            cb_max_distinct_open=cb_max_distinct_open,
            cb_window_s=cb_window_s,
        )

    # Memory/FD/CPU guard (optional providers; skipped if None)
    mem_guard = MemoryHealthGuard(
        on_violation=supervisor.trigger,
        get_rss_mb=get_rss_mb,
        get_fd_open=get_fd_open, get_fd_limit=get_fd_limit,
        get_sock_open=get_sock_open, get_sock_limit=get_sock_limit,
        get_cpu_util=get_cpu_util, get_step_latency_ms=get_step_latency_ms,
        get_memory_health=get_memory_health,  # ← already NEW
        mem_slope_mb_per_s=mem_slope_mb_per_s, mem_sustain_s=mem_sustain_s,
        mem_floor_mb=mem_floor_mb, mem_min_net_rise_mb=mem_min_net_rise_mb,
        fd_pct_threshold=fd_pct_threshold, fd_sustain_s=fd_sustain_s,
        cpu_util_threshold=cpu_util_threshold, cpu_sustain_s=cpu_sustain_s,
        latency_slope_ms_per_s=latency_slope_ms_per_s,
        latency_mean_ms_threshold=latency_mean_ms_threshold,
    )

    # Host resource guard (outward-looking; staged, NON-fatal escalation).
    # Unlike every other guard it does NOT route to supervisor.trigger — killing
    # Orrin can't reclaim host swap/disk. It warns, then pauses heavy cycles.
    host_guard = HostResourceGuard(
        on_warn=host_on_warn,
        on_pause=host_on_pause,
        on_resume=host_on_resume,
        get_disk_free_bytes=get_disk_free_bytes,
        get_swap_used_bytes=get_swap_used_bytes,
        get_vmem_percent=get_vmem_percent,
        disk_warn_free_bytes=disk_warn_free_bytes,
        disk_pause_free_bytes=disk_pause_free_bytes,
        disk_sustain_s=disk_sustain_s,
        swap_warn_used_bytes=swap_warn_used_bytes,
        swap_pause_used_bytes=swap_pause_used_bytes,
        swap_growth_warn_bytes_per_s=swap_growth_warn_bytes_per_s,
        swap_sustain_s=swap_sustain_s,
        vmem_warn_percent=vmem_warn_percent,
        vmem_pause_percent=vmem_pause_percent,
        vmem_sustain_s=vmem_sustain_s,
    )

    # Resource-floor reflex (INWARD; the mirror of the host guard). Watches Orrin's
    # OWN RSS against his granted body size and sheds load before the OS OOM-killer
    # does it ungracefully. Like the host guard it does NOT route to supervisor.trigger
    # — it sheds, never suicides. Built only if both providers are present.
    resource_floor_guard: Optional[ResourceFloorGuard] = None
    if get_own_rss_bytes is not None and get_budget_bytes is not None:
        resource_floor_guard = ResourceFloorGuard(
            on_warn=resource_floor_on_warn,
            on_shed=resource_floor_on_shed,
            on_recover=resource_floor_on_recover,
            shed_fn=resource_floor_shed_fn,
            get_own_rss_bytes=get_own_rss_bytes,
            get_budget_bytes=get_budget_bytes,
            warn_frac=resource_floor_warn_frac,
            shed_frac=resource_floor_shed_frac,
            recover_frac=resource_floor_recover_frac,
            sustain_s=resource_floor_sustain_s,
            observe_only=resource_floor_observe_only,
            calibration_file=resource_floor_calibration_file,
            calibration_phase=resource_floor_calibration_phase,
            calibration_sample_s=resource_floor_calibration_sample_s,
        )

    # Repeat-loop guard (optional)
    repeat_guard: Optional[RepeatLoopGuard] = None
    if enable_repeat_guard:
        repeat_guard = RepeatLoopGuard(
            on_violation=supervisor.trigger,
            action_window_n=action_window_n,
            same_call_k=same_call_k,
            same_call_t=same_call_t,
            breaker_cool_s=breaker_cool_s,
            pingpong_k=pingpong_k,
            pingpong_t=pingpong_t,
            no_progress_t=no_progress_t,
            no_progress_min_actions=no_progress_min_actions,
            retry_k=retry_k,
            retry_w=retry_w,
            retry_escalate_k=retry_escalate_k,
        )

    stop_evt = threading.Event()

    # ----------------- EVENT EMISSION HELPERS (NEW) -----------------
    def _emit(evt: Dict[str, Any]) -> None:
        if event_callback is not None:
            try:
                event_callback(evt)
            except Exception as _e:
                _log.warning("silent except: %s", _e)

    # track previous states so we only emit on changes/crossings
    prev: Dict[str, float] = {
        "hb_avg_ms": 0.0,
        "errors_any_rate": 0.0,
        "rss_mb": 0.0,
        "cpu_util": 0.0,
        "fd_pct": 0.0,
        "lat_mean_ms": 0.0,
    }
    last_fd_pct_emit_ts = 0.0
    last_cpu_emit_ts = 0.0
    last_mem_emit_ts = 0.0
    last_err_emit_ts = 0.0

    # ----------------- watchdog background loop ---------------------
    def watchdog_thread():
        nonlocal last_fd_pct_emit_ts, last_cpu_emit_ts, last_mem_emit_ts, last_err_emit_ts
        # background watchdog loop
        while not stop_evt.is_set():
            detector.step()
            liveness.step()
            lifespan.step()
            if cycle_stall_guard is not None:
                cycle_stall_guard.step()
            if no_goals is not None:
                no_goals.step()
            mem_guard.step()
            host_guard.step()
            if resource_floor_guard is not None:
                resource_floor_guard.step()
            if repeat_guard is not None:
                repeat_guard.step()

            # --------- emit change events to wake the brain quickly ---------
            # heartbeat avg period
            try:
                ap = getattr(detector, "avg_period_ms", None)
                hb_avg = float(ap() if callable(ap) else (ap or 0.0))
                if hb_avg > 0 and abs(hb_avg - prev["hb_avg_ms"]) > 5.0:
                    _emit({"type": "hb_change", "avg_ms": hb_avg})
                prev["hb_avg_ms"] = hb_avg
            except Exception as _e:
                _log.warning("silent except: %s", _e)

            # error rate
            try:
                err_rate = float(getattr(errors, "any_rate", 0.0) or 0.0)
                now = time.time()
                if err_rate > 0.2 and (now - last_err_emit_ts) > 1.0:
                    _emit({"type": "error_rate", "rps": err_rate})
                    last_err_emit_ts = now
                prev["errors_any_rate"] = err_rate
            except Exception as _e:
                _log.warning("silent except: %s", _e)

            # memory / cpu / fd / latency — read directly from providers
            try:
                rss_mb = float(get_rss_mb()) if callable(get_rss_mb) else 0.0
                now = time.time()
                if rss_mb > 0 and (rss_mb - prev["rss_mb"] >= 64 or (now - last_mem_emit_ts) > 10.0):
                    _emit({"type": "mem_change", "rss_mb": rss_mb})
                    last_mem_emit_ts = now
                prev["rss_mb"] = rss_mb
                rss_mb_gauge.set(rss_mb)
            except Exception as _e:
                _log.warning("silent except: %s", _e)

            try:
                cpu = float(get_cpu_util()) if callable(get_cpu_util) else 0.0
                now = time.time()
                if cpu >= cpu_util_threshold and (now - last_cpu_emit_ts) > 2.0:
                    _emit({"type": "cpu_hot", "cpu_util": cpu})
                    last_cpu_emit_ts = now
                prev["cpu_util"] = cpu
                cpu_util_gauge.set(cpu)
            except Exception as _e:
                _log.warning("silent except: %s", _e)

            try:
                fd_open = float(get_fd_open()) if callable(get_fd_open) else 0.0
                fd_lim  = float(get_fd_limit()) if callable(get_fd_limit) else 0.0
                fd_pct = (fd_open / fd_lim) if fd_lim > 0 else 0.0
                now = time.time()
                if fd_pct >= fd_pct_threshold and (now - last_fd_pct_emit_ts) > 5.0:
                    _emit({"type": "fd_high", "fd_open": fd_open, "fd_limit": fd_lim})
                    last_fd_pct_emit_ts = now
                prev["fd_pct"] = fd_pct
                fd_pct_open_gauge.set(fd_pct)
            except Exception as _e:
                _log.warning("silent except: %s", _e)

            try:
                sock_open = float(get_sock_open()) if callable(get_sock_open) else 0.0
                sock_lim  = float(get_sock_limit()) if callable(get_sock_limit) else 0.0
                sock_pct = (sock_open / sock_lim) if sock_lim > 0 else 0.0
                sock_pct_open_gauge.set(sock_pct)
            except Exception as _e:
                _log.warning("silent except: %s", _e)

            try:
                lat = float(get_step_latency_ms()) if callable(get_step_latency_ms) else 0.0
                if lat >= latency_mean_ms_threshold and abs(lat - prev["lat_mean_ms"]) > 5.0:
                    _emit({"type": "latency_high", "ms": lat})
                prev["lat_mean_ms"] = lat
                step_latency_ms_gauge.set(lat)
            except Exception as _e:
                _log.warning("silent except: %s", _e)
            # ----------------------------------------------------------------

            time.sleep(hb_poll_interval_s)

    t = threading.Thread(target=watchdog_thread, name="watchdogs", daemon=True)
    t.start()

    # ------------- Nervous System wiring (5 Hz sampler; optional memory summaries) -------------
    # Build a closure that reads current raw values from the live objects above.
    def _get_reaper_raw() -> Dict[str, float]:
        out: Dict[str, float] = {}
        try:
            out["pulse_cycles"] = float(pulse.read())
        except Exception as _e:
            _log.warning("silent except: %s", _e)

        try:
            ap = getattr(detector, "avg_period_ms", None)
            out["hb_avg_period_ms"] = float(ap() if callable(ap) else (ap or 0.0))
        except Exception as _e:
            _log.warning("silent except: %s", _e)

        try:
            out["errors_any_rate"] = float(getattr(errors, "any_rate", 0.0) or 0.0)
        except Exception as _e:
            _log.warning("silent except: %s", _e)

        for name in ["rss_mb", "cpu_util", "index_lag", "working_cache"]:
            try:
                v = getattr(mem_guard, name, None)
                v = v() if callable(v) else v
                if v is not None:
                    out[name] = float(v)
            except Exception as _e:
                _log.warning("silent except: %s", _e)

        return out

    health_bus = HealthBus(maxlen=1200, alpha=0.25)
    # Try to discover a sensible working_cache cap if mem_guard exposes one; else default 512.
    wc_cap = getattr(mem_guard, "working_cap", 512)

    health_sampler = HealthTelemetrySampler(
        get_raw=_get_reaper_raw,
        bus=health_bus,
        daemon=memory_daemon,                 # writes compact summaries to memory if provided
        sample_interval_s=ns_sample_interval_s,   # << every 0.2s by default
        summary_interval_s=ns_summary_interval_s, # memory write cadence
        ranges={
            "cpu_util": (0.05, 0.85),
            "rss_mb": (300, 1500),
            "hb_ms": (5, 50),
            "err_rps": (0.0, 0.5),
            "index_lag": (0.0, 200.0),
            "working_cache": (0.0, float(wc_cap)),
        },
    )
    health_sampler.start()
    # ------------------------------------------------------------------------------------------

    return (
        supervisor,
        detector,
        errors,
        liveness,
        lifespan,
        no_goals,
        mem_guard,
        host_guard,
        resource_floor_guard,
        repeat_guard,
        cycle_stall_guard,
        stop_evt,
    )
