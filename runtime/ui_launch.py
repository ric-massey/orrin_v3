"""UI launch helpers (Phase 4B): resolve the built UI index, wait for a port to
accept connections, and open browser tabs once the server is up.

Pure helpers — importing this module has no boot side effects. main.py keeps the
mode-selection orchestration (bridge / dev / fallback) and just calls these.
"""
from __future__ import annotations

import socket
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlsplit

from brain.utils.paths import resolve_dist as _resolve_dist
from brain.utils.ui_build import ensure_ui_build as _ensure_ui_build

# runtime/ui_launch.py → repo root is two levels up.
_REPO_ROOT = Path(__file__).resolve().parents[1]


def resolve_ui_index():
    """Resolve the built UI's index.html (building the dist if missing). Returns a
    Path, or None if no build is available. Honors ORRIN_UI_DIST."""
    dist = _resolve_dist("ORRIN_UI_DIST", _REPO_ROOT / "frontend" / "dist")
    if _ensure_ui_build("orrin", dist):
        return dist / "index.html"
    return None


def wait_for_port(url: str, timeout_s: float = 30.0) -> bool:
    """Poll the URL's host:port until it accepts a TCP connection, so we don't
    open a browser tab onto a connection-refused page while Vite is still
    cold-starting / installing deps (first-run friction — UI_AUDIT L4)."""
    parts = urlsplit(url)
    host = parts.hostname or "127.0.0.1"
    port = parts.port or (443 if parts.scheme == "https" else 80)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def open_browsers(urls: list) -> None:
    for label, url in urls:
        if not wait_for_port(url):
            print(f"[browser] {label} not ready after wait; opening anyway: {url}")
        try:
            webbrowser.open(url)
            print(f"[browser] opened {label}: {url}")
        except Exception as e:
            print(f"[browser] could not open {label}: {e}")
        time.sleep(0.6)
