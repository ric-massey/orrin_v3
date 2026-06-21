"""Request auth guards for the telemetry/control server.

Split out of app.py (Phase 4C) so domain route modules can guard themselves
without importing app.py (which would be circular). These are stateless functions
over the request plus tokens fixed at import time. The lifecycle-handler registry
(stop/reset/restart) deliberately stays in app.py: main.py rebinds those globals
at runtime, so they can't be imported by value.
"""
from __future__ import annotations

import hmac
import os

from fastapi import HTTPException, Request

from .config import trusted_origins

# ── Optional read-token guard (UI_FIXES new-surfaces security note) ──────────
# Every read endpoint is unauthenticated by default (localhost dev). The new
# surfaces raise the stakes (/memory, /chat, /consciousness are his memory,
# conversations, and stream of awareness) — so when ORRIN_READ_TOKEN is set,
# all reads require the X-Orrin-Read-Token header; loopback stays open so
# localhost dev is zero-config, exactly like authorize_control. When unset,
# behavior is unchanged — the tunnel URL is then the only secret.
_READ_TOKEN = os.environ.get("ORRIN_READ_TOKEN", "").strip()
_CONTROL_TOKEN = os.environ.get("ORRIN_CONTROL_TOKEN", "").strip()
_INGEST_TOKEN = os.environ.get("ORRIN_INGEST_TOKEN", "").strip()
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def authorize_read(request: Request) -> None:
    if not _READ_TOKEN:
        return
    client_host = (request.client.host if request.client else "") or ""
    if client_host in ("127.0.0.1", "::1", "localhost"):
        return
    supplied = (request.headers.get("X-Orrin-Read-Token") or "").strip()
    if not hmac.compare_digest(supplied, _READ_TOKEN):
        raise HTTPException(status_code=403, detail="invalid or missing read token")


def ws_read_authorized(ws) -> bool:
    """Read-token policy for the telemetry WebSocket (UI_AUDIT H4). The WS carries
    the same live data authorize_read protects, but browsers can't set handshake
    headers, so the token rides as a query param; loopback stays open so localhost
    dev is zero-config. Returns True when the connection may proceed."""
    if not _READ_TOKEN:
        return True
    client_host = (ws.client.host if ws.client else "") or ""
    if client_host in ("127.0.0.1", "::1", "localhost"):
        return True
    supplied = (ws.query_params.get("token") or "").strip()
    return hmac.compare_digest(supplied, _READ_TOKEN)


def reject_untrusted_origin(request: Request) -> None:
    """Reject browser requests carrying an Origin we don't trust (UI_AUDIT H2/H3).

    The shutdown / ingest / agent endpoints are side-effecting "simple requests"
    that CORS does NOT stop (no preflight, the side effect fires server-side even
    though the browser can't read the response). So a hostile page on evil.com
    could otherwise POST to 127.0.0.1 and shut Orrin down or inject input. We
    distinguish the real UI from a hostile page by the Origin header: the UI's
    own origin is allowlisted; a foreign Origin is rejected; native clients (the
    in-process producer, curl) send no Origin and pass through.
    """
    origin = (request.headers.get("origin") or "").strip()
    if origin and origin not in set(trusted_origins()):
        raise HTTPException(status_code=403, detail="untrusted origin")


def authorize_control(request: Request) -> None:
    """Guard /api/control/* — destructive, so it must not be triggerable by any
    network caller (UI_AUDIT H3). Layered:
      • reject any untrusted browser Origin (blocks cross-site CSRF even from a
        loopback-reaching page — UI_AUDIT H2);
      • ORRIN_CONTROL_TOKEN set → require matching X-Orrin-Control-Token header;
      • not set → allow loopback clients only (localhost dev), reject the rest
        with guidance to configure a token for remote use.
    """
    reject_untrusted_origin(request)
    if _CONTROL_TOKEN:
        supplied = (request.headers.get("X-Orrin-Control-Token") or "").strip()
        if not hmac.compare_digest(supplied, _CONTROL_TOKEN):
            raise HTTPException(status_code=403, detail="invalid or missing control token")
        return
    client_host = (request.client.host if request.client else "") or ""
    if client_host not in _LOOPBACK_HOSTS:
        raise HTTPException(
            status_code=403,
            detail="control endpoint is localhost-only; set ORRIN_CONTROL_TOKEN to allow remote control",
        )


def authorize_ingest(request: Request) -> None:
    """Guard /ingest — the producer entry point (UI_AUDIT H3). Reject hostile
    browser Origins (a page should never spoof the brain's telemetry), and when
    ORRIN_INGEST_TOKEN is set require the matching header so a remote-exposed
    backend only accepts frames from the real cognitive loop. Unset → loopback
    dev is zero-config; the in-process producer sends no Origin and passes."""
    reject_untrusted_origin(request)
    if _INGEST_TOKEN:
        supplied = (request.headers.get("X-Orrin-Ingest-Token") or "").strip()
        if not hmac.compare_digest(supplied, _INGEST_TOKEN):
            raise HTTPException(status_code=403, detail="invalid or missing ingest token")
