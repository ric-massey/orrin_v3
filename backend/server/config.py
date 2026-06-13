"""
backend/server/config.py — tunables and environment-derived settings.

Single place to find the capacity limits and the host/port/feature-flag wiring,
so they aren't scattered across the hub, routes, and launcher.
"""
from __future__ import annotations

import os

# The four canonical cognitive-loop stages the Brain graph renders.
LOOP_NODES = ("perceive", "reflect", "plan", "act")

# Capacity limits (bounded buffers — keep server memory flat under load).
MEMORY_CAP = 500     # rolling memory-record ring
LOG_CAP = 500        # rolling log-line ring
METRIC_CAP = 240     # rolling chart-series points
HISTORY_CAP = 240    # affect/metric history (persisted across restarts → continuous chart)
INPUT_CAP = 1000     # pending Face inputs awaiting the core loop
RESPONSE_CAP = 300   # agent replies awaiting Face pickup


def _flag(name: str, default: str = "") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes")


def demo_enabled() -> bool:
    """Whether the synthetic demo generator should run (ORRIN_TELEMETRY_DEMO=1)."""
    return _flag("ORRIN_TELEMETRY_DEMO")


def ui_enabled() -> bool:
    """Whether the launcher should spawn the Vite UI (ORRIN_UI defaults to on)."""
    return os.getenv("ORRIN_UI", "1").strip().lower() not in ("0", "false", "no")


def open_browser_enabled() -> bool:
    """Whether the launcher should open a browser tab (ORRIN_UI_OPEN defaults to on)."""
    return os.getenv("ORRIN_UI_OPEN", "1").strip().lower() not in ("0", "false", "no")


def backend_host() -> str:
    return os.getenv("ORRIN_BACKEND_HOST", "127.0.0.1")


def backend_port() -> int:
    return int(os.getenv("ORRIN_BACKEND_PORT", "8800"))


# Convenience for the UI dev server URL the launcher prints / opens.
UI_DEV_URL = "http://localhost:5173"
