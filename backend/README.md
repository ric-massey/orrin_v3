# Orrin Telemetry Backend

FastAPI WebSocket bridge between the cognitive architecture and the Face/Brain UI,
plus the importable producer client. See the top-level [`UI_README.md`](../UI_README.md)
for the full system overview and protocol.

## Layout

```
backend/
├── main.py              # entry point — exposes `app`, `start_ui_stack`, `main`
├── telemetry_bridge.py  # importable producer client (TelemetryBridge, get_bridge)
├── requirements.txt
└── server/              # telemetry server internals
    ├── app.py           # FastAPI app, routes, lifespan
    ├── hub.py           # Hub: client registry + merged latest state + buffers
    ├── demo.py          # synthetic telemetry generator (ORRIN_TELEMETRY_DEMO=1)
    ├── launcher.py      # spawn the Vite UI child process
    ├── schema.py        # wire-format models (TelemetryFrame, …)
    └── config.py        # capacity limits + env-derived settings
```

**Separation of concerns:** `telemetry_bridge.py` (producer) and `server/`
(consumer hub) share no code — only the JSON wire format in `server/schema.py`.

## Run

```bash
pip install -r requirements.txt

python main.py                              # API + Vite UI (+ opens browser)
ORRIN_TELEMETRY_DEMO=1 python main.py       # + synthetic data, no real codebase
uvicorn backend.main:app --reload --port 8800   # API only (dev)
```

## Environment

| var | default | effect |
|---|---|---|
| `ORRIN_BACKEND_HOST` / `ORRIN_BACKEND_PORT` | `127.0.0.1` / `8800` | bind address |
| `ORRIN_TELEMETRY_DEMO` | off | run the synthetic generator |
| `ORRIN_UI` | on | spawn the Vite UI from `main()` / `start_ui_stack()` |
| `ORRIN_UI_OPEN` | on | open a browser tab |
| `ORRIN_TELEMETRY_URL` | `http://127.0.0.1:8800` | where `TelemetryBridge` posts |
| `ORRIN_TELEMETRY_DISABLED` | off | make `TelemetryBridge` a no-op |
