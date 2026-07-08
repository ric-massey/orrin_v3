# Backend & Telemetry

`backend/` is the FastAPI bridge between the cognitive loop and the Face & Brain UI. The loop POSTs
telemetry in; the UI reads it over REST and a WebSocket stream.

## Architecture

- `backend/server/app.py` — the FastAPI app; serves the built UI (`frontend/dist`) in packaged mode.
- `backend/server/hub.py` — the WebSocket hub: buffers state and fans it out to connected clients.
- `backend/server/bridge.py` — the in-process `js_api` bridge used by the native (pywebview) window,
  which needs **no open port** at all.
- `backend/server/state.py` — canonical serialized runtime state.
- `backend/server/schema.py` + `generate_telemetry_ts.py` — the telemetry schema, from which the
  frontend's TypeScript types are generated (one source of truth for both sides).
- `backend/server/lifecycle.py` / `launcher.py` / `tray.py` — startup/shutdown wiring and the
  desktop tray.

## Routers

`backend/server/routers/` splits the API by surface: `telemetry` (read state), `control`
(stop/steer — gate with `ORRIN_CONTROL_TOKEN`), `memory`, `cognition`, `agent`, `settings`
(provider keys → OS keychain), `quality_standard` (ratification UI), `diagnostics`,
`runtime_coupling`, `source`, and `update`.

## Security model

`backend/server/auth.py` enforces three independent tokens, all zero-config on loopback:

- `ORRIN_READ_TOKEN` — required for REST + WebSocket reads from non-loopback clients (frontend
  sends `VITE_READ_TOKEN`).
- `ORRIN_INGEST_TOKEN` — required on `POST /ingest` so a remote-exposed backend only accepts
  telemetry from the real loop.
- `ORRIN_CONTROL_TOKEN` — required on `/api/control/*` (e.g. the Stop button).

`ORRIN_EXTRA_ORIGINS` allowlists additional browser origins (tunnels); the local Vite origin and
the backend host are trusted automatically.

## Ports and modes

- **Native bridge mode (default, packaged):** pywebview window + in-process bridge, no port.
- **Browser/API mode:** backend binds `ORRIN_BACKEND_HOST`/`ORRIN_BACKEND_PORT` (dev default 8800;
  native mode uses an OS-assigned free port unless pinned).
- **Prometheus (opt-in):** `ORRIN_METRICS=1` starts the exporter in `observability/` (Docker pins
  `9100`).

## Code pointers

- `backend/server/` — everything above
- `frontend/src/lib/` — the client that consumes the stream
- `docs/CONFIGURATION.md` — ports, tokens, and remote-access detail
