# Orrin UI — Reliability, Usability & Failure-Visibility Audit

> **Historical audit:** the findings in this report have been remediated. Use
> `UI_SECURITY_DESKTOP_MASTER_PLAN_2026-06-16.md` for verified current status.

**Date:** 2026-06-14
**Scope:** The "Face & Brain" UI — `frontend/` (React/Vite) + `backend/` (FastAPI telemetry bridge) + the producer client `backend/telemetry_bridge.py` and its wiring in `main.py` / `brain/`.
**Goal of this review:** Is the UI *reliable*, *dependable*, *easy to use*, and *honest about failure* (easy to see when something is going wrong)?

---

## 1. Executive summary

The UI is, on the whole, **thoughtfully built and unusually honest**. It already does many things that most dashboards get wrong:

- A single shared WebSocket (`useTelemetry`) with exponential-backoff reconnect, StrictMode-safe double-connect protection, and bounded client-side rings.
- Demo fallback is **off by default**, so a dead backend reads as "Connecting", not fake activity (`App.tsx:19-25`). This is the right call and rare.
- Per-panel `StaleBadge` that reads a real per-URL "last success" clock and goes amber when data is old (`StaleBadge.tsx`, `fetchJSON.ts`).
- Server-side aggregation (`/api/vitals`) so the vital-signs row polls **one** endpoint on one timer instead of eleven.
- Defensive rendering throughout the panels: empty states, `not_run`/`FAIL` shown first-class, `isFinite` guards, sanitized localStorage.
- Bounded buffers on **both** ends (`telemetry_bridge.py` deques, `hub.py` caps) with explicit backpressure surfacing.

So this report is mostly about **edges**, ranked by severity. The headline issues are:

1. **Security (HIGH):** several telemetry/control endpoints are unauthenticated or loopback-trusting in a way that, combined with `CORS: *`, lets *any web page open in the user's browser* read secrets (`.env`) and shut Orrin down. This bites even on pure-localhost installs.
2. **Reliability (HIGH):** there is **no top-level React error boundary**. A single malformed `brain/data/*.json` payload that throws inside any of the 20 Brain panels white-screens the entire dashboard — the opposite of "easy to see what's wrong".
3. **Honesty inconsistency (MEDIUM):** the shared Header reports "Live" using a different, weaker definition of liveness than the Brain page's own KPI, so the header can say "Live" while the stream has been frozen for minutes.

Details and concrete fixes below.

---

## 2. Architecture (as built)

```
 producers (cognitive loop)                         consumers (browser)
 brain/ORRIN_loop.py ── TelemetryBridge ──POST /ingest──►┌──────────┐──WS /ws/telemetry──► useTelemetry()
 brain/behavior/face_bridge.py ◄─ /api/agent/* ──────────│   Hub    │                      (snapshot then deltas)
                                                          │ (state)  │
 React panels ──GET /api/{vitals,benchmarks,...}─────────►└──────────┘  (read JSON from brain/data/*.json)
```

- **Streaming path** (live affect/narrative/logs/memory ops): WebSocket, single connection, reducer in `lib/telemetry.ts`.
- **REST path** (deep panels): independent pollers funneled through `lib/fetchJSON.ts` (in-flight dedup + TTL cache), each panel paired with a `StaleBadge`.
- **Conversation loop**: Face → `POST /api/agent/input` → `hub.inputs` → `face_bridge.drain_face_inputs()` writes `user_input.txt` → brain replies → `tb.respond()` → `hub.responses` → Face polls `GET /api/agent/response/{id}`.

The layering is clean and the contract is even test-enforced (`tests/observability_tests/telemetry_contract_test.py` asserts every producer keyword ⊆ `schema.LATEST_WINS_KEYS`). Good.

---

## 3. Findings (severity-ranked)

### 🔴 HIGH

#### H1 — Secret exfiltration via `/api/source` + `CORS: *` + loopback trust
`backend/server/app.py:278-292`. `/api/source?file=…` serves any file inside the repo root (path-jailed correctly with `relative_to`). **But `.env` lives at the repo root** (`/.env`, confirmed present) and is therefore inside the jail. So:

```
GET http://127.0.0.1:8800/api/source?file=.env  →  { "source": "OPENAI_API_KEY=…", … }
```

The app sets `CORSMiddleware(allow_origins=["*"], allow_methods=["*"])` (`app.py:50-56`), and the read-token guard (`_authorize_read`, `app.py:816-824`) **returns early for loopback clients**. A browser request to `127.0.0.1` *is* a loopback client. Net effect: **any website the user has open in a tab can `fetch()` `/api/source?file=.env` and read it cross-origin** — even with `ORRIN_READ_TOKEN` set. This leaks the OpenAI key and anything else in `.env`/the repo.

**Fix:** (a) Add an explicit denylist for dotfiles/secret files in `source()`, or restrict it to known source extensions/subtrees. (b) Don't keep `.env` inside the served root, or move the repo-jail base below it. (c) Tighten CORS to the known UI origin instead of `*`. (d) Apply the read-token to loopback too, or add an `Origin`/`Sec-Fetch-Site` check to reject cross-site reads.

#### H2 — CSRF shutdown: any open browser tab can stop Orrin
`backend/server/app.py:840-883`. `/api/control/shutdown` is correctly guarded *against remote network callers* — but the default (no `ORRIN_CONTROL_TOKEN`) **allows any loopback client**. A cross-origin `fetch('http://127.0.0.1:8800/api/control/shutdown', {method:'POST'})` is a CORS "simple request" (no preflight, no custom headers, no body), arrives with `client.host == 127.0.0.1`, passes `_authorize_control`, and fires `SIGINT` — full shutdown. So **a malicious or compromised page in the user's browser can kill the cognitive loop** without the user touching the Stop button.

**Fix:** require an `Origin`/`Sec-Fetch-Site: same-origin` check (or a token / double-submit cookie) on `/api/control/*` *in addition to* the loopback check. The loopback check alone does not distinguish "the UI" from "evil.com talking to 127.0.0.1".

#### H3 — `/ingest` and `/api/agent/*` are completely unauthenticated
`backend/server/app.py:887-945`. These are registered directly on `app` (not the `api` router), so they carry **neither** `_authorize_read` **nor** `_authorize_control` — *regardless* of `ORRIN_READ_TOKEN`/`ORRIN_CONTROL_TOKEN`. Consequences when the backend is reachable (the code explicitly supports binding `0.0.0.0` / tunnels — `main.py:225-241`, `launcher.py:40-42`), or cross-origin via the CORS hole:
- `POST /ingest` lets any caller **spoof the brain's displayed state** — fake affect, fake narrative, injected log/memory lines. The dashboard can no longer be trusted as ground truth.
- `POST /api/agent/input` lets any caller **inject messages into Orrin's cognition** (they get written to `user_input.txt` and ingested as real user input via `face_bridge.py:59`).
- `POST /api/agent/respond` lets any caller **forge Orrin's replies** to the Face.

**Fix:** move these onto the guarded router (or add the dependency), and gate producer ingest behind a shared secret that `TelemetryBridge` sends. At minimum, document that exposing the backend beyond localhost without these guards is unsafe.

#### H4 — WebSocket stream is never authenticated
`app.py:964` (`/ws/telemetry`) has no auth, while the REST reads can require `ORRIN_READ_TOKEN`. The WS carries the *same* sensitive data the token is meant to protect (his memory ops, logs, narrative, affect). So the read-token control is half-applied: closing the REST door but leaving the streaming door open.

**Fix:** authenticate the WS handshake (token query param or subprotocol) with the same `_authorize_read` policy.

#### H5 — No top-level error boundary → one bad panel blanks the whole Brain
`frontend/src/main.tsx` mounts `<RouterProvider>` with **no** `ErrorBoundary`; `App.tsx` has none; `Brain.tsx:249-253` renders all 20 panels and **only `CognitiveSphere` wraps itself** (`CognitiveSphere.tsx:981`). The panels render live data shapes straight from `brain/data/*.json`. If any one panel throws during render — a `.map` on something that isn't an array, an unexpected nested shape after a data migration, a corrupt file — React unmounts the **entire tree** and the user gets a white screen with nothing in the UI to explain it. This directly defeats the stated goal ("easy to see when things are going wrong"): the failure mode is the *least* visible one possible.

**Fix:** wrap each grid item in `Brain.tsx` with the existing `<ErrorBoundary>` (fallback = a small "this panel failed" card with the panel id), and add one boundary at the router root. The component already exists — it's just not used widely enough.

---

### 🟠 MEDIUM

#### M1 — Two different definitions of "Live"; the Header can lie
The shared `Header` (`Header.tsx:18-23`) shows **"Live"** whenever `source === "live" && connected`. But a WebSocket can stay `connected` while frames stop arriving (backend wedged, producer thread dead). The Brain page knows this — it computes `streamStale = source==="live" && now - updatedAt > 15s` and shows **"Stalled"** in its KPI (`Brain.tsx:139,187`). The Header does **not** use that signal, so on both pages the header pill can read a confident green "Live" while the data is minutes stale. Two verdicts for one fact.

**Fix:** lift the staleness check into the shared telemetry state (or Header) so there is one liveness source of truth. The Face especially has no other stalled indicator.

#### M2 — `fetchJSON` assumes the response is always JSON
`fetchJSON.ts:68-69` does `await r.json()` unconditionally. When the backend is down behind the Vite dev proxy (or behind a tunnel), the proxy/tunnel returns an **HTML** 502/504 page, so `r.json()` throws. For the pollers this is swallowed by `usePoll`'s `.catch(()=>{})` and `StaleBadge` covers it (fine). But one-shot callers that don't wrap it (drawer `/code`/`/source` opens, etc.) can surface an unhandled rejection. It's also slightly dishonest: a non-JSON error body is treated identically to "no data".

**Fix:** branch on `content-type`/`r.ok`; return a typed `{error}` for non-JSON so callers can render "backend unreachable" instead of silently nothing.

#### M3 — Chat de-duplication can drop legitimate repeated messages
`Face.tsx:65-71` merges server history by the key `\`${role}|${text}\``. If the user genuinely sends the same line twice ("ok", "yes"), the server copy is deduped against the local one and a real turn disappears from the transcript. Keys should be the message id/timestamp, not the content.

#### M4 — Vital-signs row vanishes entirely on backend failure
`VitalSignsRow.tsx:22` returns `null` when `chips.length === 0`. Because `usePoll` keeps `null` on error, a backend outage makes the whole row (and its at-a-glance health summary) silently *disappear* rather than show a "vitals unavailable" state. Disappearing UI is a weaker failure signal than a visibly-degraded one.

---

### 🟡 LOW / polish

- **L1 — Reconnect is opaque.** `telemetry.ts:272` backs off to 8s but the UI only ever says "Connecting"; no attempt count or "retrying in Ns". For a long outage the user can't tell connecting-forever from about-to-give-up.
- **L2 — 30s silent chat timeout.** `Face.tsx:251-258` waits 30s then returns a canned "didn't form a reply" line, but the message stays queued server-side. The user can't tell dropped from slow; consider surfacing "still thinking" vs "gave up".
- **L3 — `metric()`/`metrics` casts everything through `float()`** in both the bridge and `hub.merge` (`hub.py:180`). A non-numeric metric value raises inside `merge` and is caught nowhere obvious in the ingest path — worth a guard so one bad producer value can't drop a whole frame.
- **L4 — `webbrowser.open` fired before Vite is ready.** `main.py:255-262` opens the tab on a 0.6s-staggered thread while `launcher.py` may still be running `npm install`/cold-starting Vite, so first-launch users can hit a connection-refused tab and assume it's broken. A readiness poll on `:5173` before opening would be friendlier.
- **L5 — `react-grid-layout` "Reset layout"** is good, but there's no per-panel "reset just this one"; a panel dragged off-screen on a small window is only recoverable via the global reset.
- **L6 — Health/observability is split across many `/api/*` endpoints** that each read a JSON file on every poll with broad `except Exception: return default`. That's robust, but it also means a *corrupt* data file reads as "empty" indistinguishably from "genuinely nothing yet". A parse-error signal (vs empty) would make "something is wrong with the data" visible rather than looking like a quiet idle.

---

## 4. What's already done well (keep)

- Demo fallback **off by default** — honesty over liveliness (`App.tsx:19-25`).
- StrictMode double-socket guard via per-socket `_intentional` flag (`telemetry.ts:259-275`) — a subtle bug correctly handled.
- Bounded rings + backpressure surfacing on the producer (`telemetry_bridge.py:151-159, 288-295`).
- Persisted, restart-continuous metric history (`hub.py:26-41, 88-90`).
- Single-instance lock + crash/faulthandler nets in `main.py` — the launcher itself is dependable.
- `StaleBadge` everywhere + server-side `/api/vitals` aggregation — genuine failure-visibility design.
- Process-group kill of the Vite child tree on shutdown (`launcher.py:70-105`) — no orphaned node processes.

---

## 5. Recommended priority order

1. **H1 / H2 / H3 / H4** (security) — small, high-value. Tighten CORS to the real origin, add an `Origin`/`Sec-Fetch-Site` check to `/api/control/*` and the producer/agent endpoints, exclude dotfiles from `/api/source`, and authenticate the WS. These are the only findings with real-world blast radius beyond "a panel looks wrong".
2. **H5** (error boundaries) — wrap grid items + router root. ~20 lines, removes the worst-case white-screen.
3. **M1** (unify liveness) so the Header can't claim "Live" on a frozen stream.
4. **M2–M4, then the L-items** as polish.

None of these undermine the architecture — it's sound. They're the difference between "works on my localhost" and "dependable and honest when something breaks or when it's exposed".
