# utils/metrics_sampling.py
# Build a fast metric sampler that emits change events to the Alive bus

from __future__ import annotations
from core.runtime_log import get_logger
from typing import Callable, Optional
from .sys_events import record_event
from utils.failure_counter import record_failure
_log = get_logger(__name__)

def build_fast_sampler(get_memory_health: Callable[[], dict]):
    last_bytes: Optional[int] = None
    last_wal: Optional[float] = None

    def sample():
        nonlocal last_bytes, last_wal
        try:
            m = get_memory_health() or {}
            b = int(m.get("bytes") or 0)
            w = float(m.get("wal_lag_s") or 0.0)
            if last_bytes is None or (b > 0 and abs(b - last_bytes) / max(1, last_bytes) > 0.1):
                record_event({"type":"metric_change","metric":"bytes","value":b})
            if last_wal is None or (w > 300 and (last_wal or 0) <= 300):
                record_event({"type":"metric_change","metric":"wal_lag_s","value":w})
            last_bytes, last_wal = b, w
        except Exception as _e:
            record_failure("metrics_sampling.build_fast_sampler.sample", _e)

    return sample
