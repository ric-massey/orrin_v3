"""
backend/main.py — entry point for the Orrin telemetry bridge + UI.

This is a thin launcher. The server itself lives in `backend/server/` (config,
schema, hub, demo, launcher, app). Public surface kept stable:
  - `backend.main:app`            — the ASGI app (uvicorn target)
  - `backend.main.start_ui_stack` — embed the API + UI in a larger launcher
  - `backend.telemetry_bridge`    — the importable producer client

Run:
    python backend/main.py                      # API + Vite UI, opens the browser
    ORRIN_TELEMETRY_DEMO=1 python backend/main.py   # + synthetic data
    uvicorn backend.main:app --reload --port 8800   # API only (dev)
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make `backend.server.*` importable whether this file is run as a script
# (`python backend/main.py`) or imported as a package (`from backend.main import …`).
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from backend.server.app import app  # noqa: E402  (after sys.path bootstrap)
from backend.server.config import UI_DEV_URL, backend_host, backend_port  # noqa: E402
from backend.server.launcher import launch_ui, maybe_open_browser, stop_ui  # noqa: E402

__all__ = ["app", "start_ui_stack", "main"]


def start_ui_stack(host: str = "127.0.0.1", port: int = 8800):
    """
    Start the telemetry API (uvicorn, in a background daemon thread) AND the Vite
    UI (child process). Non-blocking — returns the UI subprocess handle (or None).

    Intended for embedding in a larger launcher (e.g. the repo-root main.py that
    also runs the cognitive loop). Stop the UI later with `proc.terminate()`.
    """
    import threading

    import uvicorn

    threading.Thread(
        target=lambda: uvicorn.run(app, host=host, port=port, log_level="warning"),
        name="orrin-telemetry-api",
        daemon=True,
    ).start()
    return launch_ui(host, port)


def main() -> None:
    import uvicorn

    host, port = backend_host(), backend_port()
    ui = launch_ui(host, port)
    maybe_open_browser(UI_DEV_URL)
    print(f"[orrin] telemetry API → http://{host}:{port}  (ws: /ws/telemetry)")
    try:
        uvicorn.run(app, host=host, port=port, log_level="info")
    finally:
        if ui is not None:
            print("[orrin] stopping UI…")
            stop_ui(ui)


if __name__ == "__main__":
    main()
