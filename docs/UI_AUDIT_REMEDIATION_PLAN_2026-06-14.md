# Orrin UI — Audit Remediation Plan

**Date:** 2026-06-14
**Source:** `docs/UI_AUDIT_REPORT_2026-06-14.md`
**Goal:** Close the findings without destabilizing a sound architecture. Localhost dev must stay **zero-config**; the fixes must not break the real UI.

---

## Key constraint that shapes the security fixes

The legitimate UI runs on the **Vite dev origin `:5173`** and talks to the **backend on `:8800`** — so *every real UI request is already cross-origin*. That is exactly why `CORS: *` exists today. Consequences for the plan:

- We **cannot** "reject cross-origin" — that would block the real app.
- We **can** distinguish the UI from a hostile page by the `Origin` **header**: the UI sends `Origin: http://<host>:5173`; `evil.com` sends `Origin: https://evil.com`; native clients (the in-process producer, curl) send **no** `Origin`.
- Therefore the unifying mechanism is an **Origin allowlist**: reject a request only when it carries an `Origin` header that is *not* trusted. No-Origin requests stay allowed (server-to-server producer, curl).
- `CORS: *` must also shrink to that allowlist so a hostile page can't **read** GET responses (the `.env` leak).

This one mechanism (a trusted-origins allowlist) resolves H1, H2, and H3 together.

---

## Phase 0 — Shared origin policy (foundation for H1–H4)

**File:** `backend/server/config.py`

Add a single source of truth for trusted browser origins, derived from the same host/port wiring the launcher already computes:

```python
def trusted_origins() -> list[str]:
    """Browser origins allowed to read/control. The Vite UI (:5173) on every
    host we might serve from, plus any explicitly configured extra origins."""
    hosts = {"localhost", "127.0.0.1", backend_host()}
    vite = os.getenv("VITE_TELEMETRY_HOST", "")          # e.g. "192.168.1.10:8800"
    if vite:
        hosts.add(vite.split(":")[0])
    origins = set()
    for h in hosts:
        if h and h not in ("0.0.0.0", "::"):
            origins.add(f"http://{h}:5173")
            origins.add(f"http://{h}")                    # served build / same-port
    extra = os.getenv("ORRIN_EXTRA_ORIGINS", "")          # comma-sep, for tunnels
    origins.update(o.strip() for o in extra.split(",") if o.strip())
    return sorted(origins)
```

Tunnel/LAN users set `ORRIN_EXTRA_ORIGINS=https://my-tunnel.example` — documented in `.env.example`.

---

## Phase 1 — Security (HIGH: H1, H2, H3, H4)

### H1 — Stop `.env` / secret exfiltration via `/api/source`
**File:** `backend/server/app.py` (`source()`, ~278-292)

Two layers:

1. **Shrink CORS** (`app.py:50-56`) from `allow_origins=["*"]` to `allow_origins=config.trusted_origins()`. This alone stops a hostile page from *reading* the GET response.
2. **Defense-in-depth in `source()`** — reject dotfiles and non-source files even for trusted callers:

```python
_SOURCE_OK_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".css", ".txt"}

target = (_REPO_ROOT / file).resolve()
target.relative_to(_REPO_ROOT)                       # existing repo-jail
if any(part.startswith(".") for part in target.relative_to(_REPO_ROOT).parts):
    return JSONResponse({"error": "forbidden path"}, status_code=403)
if target.suffix.lower() not in _SOURCE_OK_SUFFIXES:
    return JSONResponse({"error": "unsupported file type"}, status_code=403)
```

This blocks `.env`, `.git/*`, lockfiles, binaries — the metric-info pages only ever request `.py` source.

### H2 — CSRF-proof `/api/control/*`
**File:** `backend/server/app.py` (`_authorize_control`, ~840-857)

Add an Origin-allowlist gate *before* the existing loopback/token logic, so a hostile page's `Origin` is rejected even though it reaches `127.0.0.1` (the shutdown is a no-preflight "simple request", so CORS does not stop the side effect — only an explicit server-side check does):

```python
def _reject_untrusted_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and origin not in set(trusted_origins()):
        raise HTTPException(status_code=403, detail="untrusted origin")

def _authorize_control(request: Request) -> None:
    _reject_untrusted_origin(request)        # NEW — blocks browser CSRF from evil.com
    ...                                      # existing token / loopback logic unchanged
```

The real Stop button (Origin `http://host:5173`) passes; `evil.com` is rejected; curl/native (no Origin) still works on loopback.

### H3 — Authenticate `/ingest` and `/api/agent/*`
**File:** `backend/server/app.py` (~887-945)

These are on `app` directly, so they bypass every guard. Apply `_reject_untrusted_origin` to all of them (a hostile *browser* page is the realistic attacker; the in-process producer sends no Origin and is unaffected):

- Add `_reject_untrusted_origin(request)` to `ingest`, `agent_input`, `agent_respond` (add a `request: Request` param to each).
- For deployments that expose the backend to *other machines* (not just the user's browser), gate the **producer** path with an optional shared secret: `TelemetryBridge` sends `X-Orrin-Ingest-Token` (from `ORRIN_INGEST_TOKEN`), and `/ingest` requires it when set. Zero-config localhost leaves it unset.

**File:** `backend/telemetry_bridge.py` (`_post_json`) — add the header when `ORRIN_INGEST_TOKEN` is set.

### H4 — Authenticate the WebSocket
**File:** `backend/server/app.py` (`ws_telemetry`, ~964)

When `ORRIN_READ_TOKEN` is set, require it on the WS handshake (query param, since browsers can't set WS headers), with the loopback exemption matching `_authorize_read`:

```python
@app.websocket("/ws/telemetry")
async def ws_telemetry(ws: WebSocket) -> None:
    if _READ_TOKEN:
        client = (ws.client.host if ws.client else "") or ""
        if client not in ("127.0.0.1", "::1", "localhost"):
            if not hmac.compare_digest((ws.query_params.get("token") or ""), _READ_TOKEN):
                await ws.close(code=4403); return
    await hub.connect(ws)
    ...
```

**File:** `frontend/src/lib/telemetry.ts` (`wsUrl()`) — append `?token=${VITE_READ_TOKEN}` when configured.

**Security tests to add** (`tests/observability_tests/`):
- `/api/source?file=.env` → 403.
- `POST /api/control/shutdown` with `Origin: https://evil.com` → 403; with the UI origin → allowed.
- `POST /ingest` with hostile Origin → 403; with no Origin → 200.
- WS connect from non-loopback without token (when set) → closed.

---

## Phase 2 — Reliability (HIGH: H5)

### H5 — Error boundaries so one bad panel can't blank the dashboard
**File:** `frontend/src/pages/Brain.tsx` (~249-253)

Wrap each grid item with the existing `<ErrorBoundary>`, fallback naming the failed panel:

```tsx
{PANEL_IDS.map((id) => (
  <div key={id} className="overflow-auto">
    <ErrorBoundary fallback={<PanelError id={id} />}>
      {panels[id]}
    </ErrorBoundary>
  </div>
))}
```

`PanelError` = a small card: "⚠ This panel ({id}) failed to render" + a reload-this-panel affordance. Now a malformed `brain/data/*.json` shape degrades one box instead of white-screening all 20.

**File:** `frontend/src/main.tsx` — add a root `<ErrorBoundary>` around `<RouterProvider>` as the last-resort net (renders a "something went wrong — reload" page instead of a blank document).

**Test:** a render-smoke test (or Storybook story) that feeds each panel a deliberately malformed payload and asserts the fallback renders, not a throw.

---

## Phase 3 — Honesty consistency (MEDIUM: M1)

### M1 — One definition of "Live"
**File:** `frontend/src/lib/telemetry.ts`

Expose staleness from the shared state so every consumer agrees. Add a derived `stale` flag (or a tiny `useStreamStale()` hook) computing `source === "live" && updatedAt > 0 && Date.now() - updatedAt > 15_000`, driven by a 5s tick already present in `Brain.tsx:134-138` (move it into the hook).

**File:** `frontend/src/components/Header.tsx` (~18-23) — when `stale`, show "Stalled" (amber), not "Live". `Brain.tsx` then consumes the same flag instead of recomputing it. The Face now also gets an honest stalled indicator (it currently has none).

---

## Phase 4 — Robustness polish (MEDIUM M2–M4)

- **M2 — `fetchJSON` content-type guard** (`fetchJSON.ts:67-77`): branch on `r.ok` / `content-type`; for non-JSON return a typed `{ error, status }` instead of throwing, so proxy/tunnel HTML 502s render "backend unreachable" rather than an unhandled rejection.
- **M3 — chat dedup by id** (`Face.tsx:65-71`): key the `seen` set on message id/timestamp, not `role|text`, so repeated identical messages aren't dropped.
- **M4 — vitals degrade visibly** (`VitalSignsRow.tsx:22`): when the poll has failed (no data *and* `lastSuccessAt` is stale/absent after first load), render a thin "vital signs unavailable" strip + `StaleBadge` instead of returning `null` and disappearing.

---

## Phase 5 — Low / polish (L1–L6)

Batch these last; each is small and independent:

- **L1** surface reconnect attempts ("retrying in Ns") in the connecting state (`telemetry.ts`).
- **L2** distinguish "still thinking" from "gave up" on the 30s chat timeout (`Face.tsx:251-258`).
- **L3** guard `float()` casts in `hub.merge` / bridge so one non-numeric metric can't drop a frame (`hub.py:180`, `telemetry_bridge.py`).
- **L4** poll `:5173` readiness before `webbrowser.open` so first launch doesn't open a refused tab (`main.py:246-262`).
- **L5** optional per-panel "reset this panel" in addition to global Reset layout (`Brain.tsx`).
- **L6** make corrupt-vs-empty data distinguishable: have the `_read_json` helpers (`app.py:430-451`) flag parse errors so panels can show "data file unreadable" vs "nothing yet".

---

## Sequencing & effort

| Phase | Findings | Effort | Risk | Blocking? |
|------|----------|--------|------|-----------|
| 0 | origin policy | ~30 min | low | enables P1 |
| 1 | H1–H4 | ~half day | low (additive guards) | ship first |
| 2 | H5 | ~1 hr | very low | ship first |
| 3 | M1 | ~1 hr | low | — |
| 4 | M2–M4 | ~2 hr | low | — |
| 5 | L1–L6 | ~half day | low | last |

**Recommended order:** Phase 0 → Phase 1 → Phase 2 (the only findings with real blast radius), then 3 → 4 → 5 as polish.

**Verification per phase:** add the Phase-1 security tests to the suite; run the existing `tests/observability_tests/` + `telemetry_contract_test.py`; `cd frontend && npm run build` (tsc + vite) for the React changes; manual smoke: start Orrin, confirm Stop still works from the real UI, confirm a forced panel error shows the fallback, confirm Header/Brain agree on Live/Stalled.

**No schema/contract changes** are required — all backend changes are additive guards, and the frontend changes are isolated to rendering/connection wiring. The telemetry frame contract (`schema.py` / `LATEST_WINS_KEYS`) is untouched.
```
