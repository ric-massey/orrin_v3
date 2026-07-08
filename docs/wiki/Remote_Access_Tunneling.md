# Remote Access & Tunneling

How to watch (and optionally control) a running Orrin from another device. Treat this as an
advanced configuration: the backend is not security-hardened, so never expose control endpoints
publicly without the tokens below.

## The one-tunnel path

```bash
./expose_orrin.command
```

This opens a **single** public tunnel to the Vite dev server, which proxies both `/ws` (telemetry
WebSocket) and `/api` (REST) through to the backend on `:8800`. The frontend derives both URLs from
the page origin, so one tunnel carries everything. The resulting URL is written to
`tunnel_url.txt`; open `<url>/brain` on the remote device. `tailscale_funnel.command` does the same
over Tailscale Funnel for a stable, authenticated alternative.

For plain LAN/Tailscale viewing without a tunnel, bind the backend beyond loopback
(`ORRIN_BACKEND_HOST=0.0.0.0`, pin `ORRIN_BACKEND_PORT`) and point the UI at it with
`VITE_TELEMETRY_HOST=<ip>:8800`.

## Security model

Three independent tokens (all zero-config on localhost, enforced by `backend/server/auth.py`):

- `ORRIN_READ_TOKEN` / `VITE_READ_TOKEN` — require a token to **read** telemetry (REST and the
  WebSocket handshake) from non-loopback clients.
- `ORRIN_CONTROL_TOKEN` / `VITE_CONTROL_TOKEN` — require a token on `/api/control/*` (the Stop
  button and any steering). **Set this before opening a tunnel**, so a viewer can't stop or steer
  the agent.
- `ORRIN_INGEST_TOKEN` — require a token on `POST /ingest`, so a remote-exposed backend only
  accepts telemetry from the real cognitive loop.

If the UI is served from a tunnel with its own public origin, allowlist it with
`ORRIN_EXTRA_ORIGINS=https://...` (comma-separated); the local Vite origin and the backend host are
trusted automatically.

Remember: the tunnel URL itself is effectively the read secret — anyone who has it can watch.
Stop the tunnel when done.

## Code pointers

- `expose_orrin.command`, `tailscale_funnel.command`, `tunnel_url.txt`
- `backend/server/auth.py` — token enforcement
- `docs/CONFIGURATION.md` — the full remote-access reference
