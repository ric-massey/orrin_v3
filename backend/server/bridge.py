"""
backend/server/bridge.py — the in-process pywebview bridge (no open port).

In the packaged/native window the UI talks to the brain through this object
(exposed as `window.pywebview.api`) instead of a socket:

  • REST reads + writes  → `request()` invokes the FastAPI app IN-PROCESS via one
    shared Starlette TestClient. Because that client owns a single portal event
    loop, every endpoint (and therefore every `hub.merge`) runs on one thread —
    so the producer's frames and the UI's requests can't race on hub state.
  • The live telemetry stream → `telemetry_subscribe()` registers this bridge as
    a hub sink and pushes a snapshot; thereafter every broadcast is forwarded to
    the page via `window.evaluate_js(window.__orrinPush(...))`.
  • The producer (cognitive loop) → `ingest()` / `drain_inputs()` / `deliver()`
    are wired into TelemetryBridge.configure_inprocess(), so its frames, the Face
    inputs, and the replies all flow through the same in-process client.

Nothing here binds a port. The FastAPI app is reused whole, so endpoints added
later (egress, life, activity, mind/*) work over the bridge with no extra work.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from starlette.testclient import TestClient

from brain.utils.failure_counter import record_failure

from .app import app, hub


class OrrinBridge:
    """pywebview `js_api`: REST proxy + telemetry push, all in-process."""

    def __init__(self) -> None:
        # One shared client → one portal thread → serialized hub mutations. Present
        # as a loopback client: the bridge IS on the local machine, so control
        # endpoints (localhost-only without a token) must accept it.
        self._client = TestClient(app, client=("127.0.0.1", 0))
        self._window: Any = None
        self._subscribed = False

    # ── window wiring ─────────────────────────────────────────────────────────
    def attach_window(self, window: Any) -> None:
        """Bind — or rebind — the view to the live brain (E6). Safe to call again when
        the window is re-attached after a detach (F1: hidden then re-shown, or a freshly
        created window): the telemetry stream is re-pointed at this window and, if the
        stream is already live, handed a fresh snapshot so it's current immediately
        rather than waiting for the next delta. The hub sink itself never duplicates —
        it's the same bound method, deduped by hub.add_sink."""
        self._window = window
        if window is not None and self._subscribed:
            self._push_snapshot()

    def detach_window(self) -> None:
        """The view went away (window hidden/closed) but the brain keeps thinking
        (Always-thinking). Telemetry pushes become no-ops until a window re-attaches;
        the sink stays registered (a cheap no-op) so reattach needs no re-subscribe."""
        self._window = None

    def _push(self, payload: Dict[str, Any]) -> None:
        """Forward a snapshot/delta to the page. Double-encode through JSON so the
        payload is a single safely-escaped JS string the page parses — avoids any
        literal-injection / U+2028 hazards."""
        win = self._window
        if win is None:
            return
        try:
            win.evaluate_js(f"window.__orrinPush && window.__orrinPush({json.dumps(json.dumps(payload))})")
        except Exception as exc:  # window gone/unwritable — record, drop the push
            record_failure("bridge._push", exc)

    # ── REST proxy (BridgeTransport.fetch → here) ─────────────────────────────
    def request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Invoke an API path in-process. payload = {method, path, body?, headers?}.
        Returns {status, body, contentType} for the page to build a Response."""
        method = str((payload or {}).get("method", "GET")).upper()
        path = str((payload or {}).get("path", "/"))
        body = (payload or {}).get("body")
        headers = (payload or {}).get("headers") or {}

        # Note: the Stop button (/api/control/shutdown) now halts only cognition and
        # leaves this window open, so it's just a normal proxied request. Quitting
        # the app is the window's close button → webview.start() returns → teardown.
        try:
            kwargs: Dict[str, Any] = {"headers": headers}
            if body is not None:
                # body arrives as a JSON string from the page; pass it through verbatim.
                kwargs["content"] = body if isinstance(body, (str, bytes)) else json.dumps(body)
                kwargs["headers"] = {"Content-Type": "application/json", **headers}
            resp = self._client.request(method, path, **kwargs)
            return {
                "status": resp.status_code,
                "body": resp.text,
                "contentType": resp.headers.get("content-type", "application/json"),
            }
        except Exception as e:
            record_failure("bridge.request", e)
            return {"status": 502, "body": json.dumps({"error": str(e)}), "contentType": "application/json"}

    # ── live telemetry stream (BridgeTransport.connectTelemetry → here) ────────
    def _push_snapshot(self) -> None:
        """Push the current full state to the bound window (used on subscribe and on
        reattach so a re-shown/reloaded view is immediately current)."""
        self._push({"type": "snapshot", "state": {**hub.state, "history": list(hub.history)}})

    def telemetry_subscribe(self) -> Dict[str, Any]:
        """Send the current snapshot immediately, then stream deltas via the sink."""
        self._push_snapshot()
        hub.add_sink(self._push)
        self._subscribed = True
        return {"ok": True}

    def telemetry_unsubscribe(self) -> Dict[str, Any]:
        hub.remove_sink(self._push)
        self._subscribed = False
        return {"ok": True}

    # ── producer side (TelemetryBridge.configure_inprocess → here) ────────────
    def ingest(self, frame: Dict[str, Any]) -> None:
        """Merge + broadcast a producer frame through the app (→ hub sink → page)."""
        self._client.post("/ingest", json=frame)

    def drain_inputs(self) -> List[Dict[str, Any]]:
        r = self._client.get("/api/agent/inputs")
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        items = data.get("inputs") if isinstance(data, dict) else None
        return items if isinstance(items, list) else []

    def deliver(self, input_id: str, reply: str) -> None:
        self._client.post("/api/agent/respond", json={"id": input_id, "reply": reply})

    # ── native file dialogs (E7 — Mind export/import over the bridge) ──────────
    # Binary can't ride the text REST proxy, so the whole transfer runs in Python via
    # a native Save/Open dialog. The handlers live in brain.utils.mind_dialogs (so
    # they're testable without importing the app); these are thin delegators.
    def export_mind(self) -> Dict[str, Any]:
        """Native Save dialog → write the full mind archive to the chosen path."""
        from brain.utils.mind_dialogs import export_mind as _export
        return _export(self._window)

    def import_mind(self) -> Dict[str, Any]:
        """Native Open dialog → restore the mind from the chosen archive (routed
        through the same /api/mind/import endpoint as the browser path)."""
        from brain.utils.mind_dialogs import import_mind as _import
        return _import(self._window, self._client.post)


_bridge: Optional[OrrinBridge] = None


def get_orrin_bridge() -> OrrinBridge:
    """Process-wide bridge singleton (created on first call)."""
    global _bridge
    if _bridge is None:
        _bridge = OrrinBridge()
    return _bridge
