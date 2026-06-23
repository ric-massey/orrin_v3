"""
backend/server/config.py — tunables and environment-derived settings.

Single place to find the capacity limits and the host/port/feature-flag wiring,
so they aren't scattered across the hub, routes, and launcher.
"""
from __future__ import annotations

import os
import socket

from brain.utils.env import env_bool

# The four canonical cognitive-loop stages the Brain graph renders.
LOOP_NODES = ("perceive", "reflect", "plan", "act")

# Capacity limits (bounded buffers — keep server memory flat under load).
MEMORY_CAP = 500     # rolling memory-record ring
LOG_CAP = 500        # rolling log-line ring
METRIC_CAP = 240     # rolling chart-series points
HISTORY_CAP = 240    # affect/metric history (persisted across restarts → continuous chart)
INPUT_CAP = 1000     # pending Face inputs awaiting the core loop
RESPONSE_CAP = 300   # agent replies awaiting Face pickup


def demo_enabled() -> bool:
    """Whether the synthetic demo generator should run (ORRIN_TELEMETRY_DEMO=1)."""
    return env_bool("ORRIN_TELEMETRY_DEMO")


def ui_enabled() -> bool:
    """Whether the UI stack should run at all (ORRIN_UI defaults to on)."""
    return env_bool("ORRIN_UI", True)


def ui_dev_enabled() -> bool:
    """Developer path: run the Vite dev server + open a browser tab instead of the
    native window (ORRIN_UI_DEV=1). Off by default — the packaged app opens a
    native pywebview window and never spawns npm at runtime."""
    return env_bool("ORRIN_UI_DEV")


def open_browser_enabled() -> bool:
    """Whether the launcher should open a browser tab (ORRIN_UI_OPEN defaults to on)."""
    return env_bool("ORRIN_UI_OPEN", True)


def metrics_enabled() -> bool:
    """Whether the Prometheus metrics exporter should bind a port (ORRIN_METRICS=1).
    Off by default: a shipped desktop app should open no listening port unless the
    user explicitly opts in to observability/remote tooling."""
    return env_bool("ORRIN_METRICS")


def pick_free_port(host: str = "127.0.0.1") -> int:
    """Ask the OS for an unused TCP port on `host`. Used so the native app never
    relies on a fixed well-known number (no collisions, no firewall prompt over a
    recognizable port). The socket is closed immediately; bind the returned port
    promptly to avoid a (small) TOCTOU race."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def backend_host() -> str:
    return os.getenv("ORRIN_BACKEND_HOST", "127.0.0.1")


def backend_port() -> int:
    return int(os.getenv("ORRIN_BACKEND_PORT", "8800"))


def trusted_origins() -> list[str]:
    """Browser origins allowed to read/control the backend.

    Single source of truth shared by the CORS middleware and the per-endpoint
    Origin guards. The real UI runs on the Vite dev origin (:5173) which is
    already cross-origin to the backend (:8800) — so we cannot "reject
    cross-origin"; instead we allowlist the UI's own origin(s) and reject any
    OTHER browser Origin (e.g. a hostile page on evil.com). Native clients
    (the in-process producer, curl) send no Origin header and are unaffected.

    Hosts covered: localhost, 127.0.0.1, the configured backend host, and the
    browser-facing VITE_TELEMETRY_HOST (LAN/Tailscale IP for tunnel use).
    Tunnels with a distinct public origin add it via ORRIN_EXTRA_ORIGINS
    (comma-separated, e.g. "https://orrin.example").
    """
    hosts = {"localhost", "127.0.0.1", backend_host()}
    vite = os.getenv("VITE_TELEMETRY_HOST", "")
    if vite:
        hosts.add(vite.split(":")[0])
    origins: set[str] = set()
    for h in hosts:
        if h and h not in ("0.0.0.0", "::"):
            origins.add(f"http://{h}:5173")   # Vite dev server
            origins.add(f"http://{h}:8800")   # served build / same-port reads
            origins.add(f"http://{h}")        # default-port origin
    extra = os.getenv("ORRIN_EXTRA_ORIGINS", "")
    origins.update(o.strip() for o in extra.split(",") if o.strip())
    return sorted(origins)


# Convenience for the UI dev server URL the launcher prints / opens.
UI_DEV_URL = "http://localhost:5173"
