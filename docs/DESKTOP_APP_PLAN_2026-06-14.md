# Orrin Desktop App — Packaging & Distribution Plan

**Date:** 2026-06-14
**Status:** Plan only — no code changed.
**Goal:** Turn Orrin from a developer-run repo into a **downloadable desktop app
anyone can install and run** — `Orrin.app` (macOS), `Orrin.exe` (Windows),
AppImage/`.deb` (Linux) — with a native window (no web browser), a settings tab
for users' own API keys, and a UI that is for *seeing* Orrin, not steering him.

**North star:** a non-technical person downloads one file, double-clicks it, and
within seconds is watching a living mind — no terminal, no Python, no Node, no
`.env`, no ports to think about.

---

## Part 0 — Decisions locked (2026-06-14)

| Decision | Choice | Rationale |
|---|---|---|
| Bundle the ML stack? | **Yes — ship torch + sentence-transformers + spacy** (~1 GB+) | Full capability out of the box; no first-run downloads to fail on. |
| Platforms | **macOS, Windows, Linux** — built separately per OS | "Anyone can download him." Each OS gets its own native artifact. |
| Window shell | **pywebview** | All-Python; `main.py` is already the orchestrator. No second toolchain. |
| Local UI↔brain transport | **In-process JS bridge (no port)** | High-end app feel: no firewall prompt, no localhost server, nothing other processes can reach. |
| Remote viewing | **Opt-in HTTP hub, off by default** | Preserves the existing "watch one Orrin from another device" feature without forcing a port on everyone. |
| UI surface | **Unchanged** (view + Face chat + Stop) + one new **Settings** tab | The UI is already built the way the owner wants it. |
| API keys | **OS keychain via `keyring`**, entered in Settings | No plaintext `.env` shipped; secrets never live in the bundle. |
| Per-user state | **OS app-data directory** | A shipped app must not write into its own program folder. |

---

## Part 1 — What we have today (verified against the code)

Orrin currently runs as **three coordinated pieces**, all started by the repo-root
`main.py`:

1. **The brain** — `brain.ORRIN_loop.run_cognitive_loop`, launched in a daemon
   thread by `main.py`. Also: memory daemon, goals daemon, watchdogs, reaper,
   tamper guard, a Prometheus metrics server on `:9100`, and a single-instance
   file lock.
2. **The telemetry backend** — `backend/main.py` → a **FastAPI** app
   (`backend/server/app.py`) on `:8800`, started in-process in a daemon thread.
   It is a **pub/sub hub**: the brain *pushes* frames to `POST /ingest`; UI
   clients subscribe over `WS /ws/telemetry` and a large set of **read-only**
   REST endpoints (`/vitals`, `/memory`, `/goals`, `/consciousness`, `/symbolic`,
   `/self`, …). Write surfaces are limited to the Stop button
   (`/api/control/shutdown`) and Face chat (`/api/agent/input`).
3. **The UI** — a **React + Vite** app (`frontend/`), spawned by
   `backend/server/launcher.py` as a child `npm run dev` process on `:5173`. The
   launcher then **opens a browser tab**.

**Key facts that shape this plan:**

- **The browser + Node are launch-time, not load-bearing.** The launcher runs
  `npm run dev` and `webbrowser.open`. A `frontend/dist` static build already
  exists (stale). Nothing about the architecture *requires* a browser or a
  running Node server — only the launcher does.
- **API keys** are read from the environment via `python-dotenv` →
  `os.getenv("OPENAI_API_KEY")` / `SERPER_API_KEY`. Everything runs
  **symbolic-only** without them (see `brain/utils/llm_gate.py`,
  `brain/utils/llm_stub.py`). The OpenAI client is **cached at module load** in
  `brain/utils/generate_response.py` — a key change requires a re-init/restart.
- **The ML stack is heavy.** `.venv` ≈ 987 MB, of which **torch ≈ 403 MB**, plus
  `sentence-transformers`, `spacy`, `numpy`. Python 3.12.
- **State lives inside the repo.** `brain/data` ≈ 87 MB, addressed via paths
  computed relative to repo root (`_DATA_DIR = _REPO_ROOT / "brain" / "data"` in
  `app.py`; `compute_repo_root` in `main.py`). Also `data/`, logs, goals.
- **Security is already done** for the networked case: CORS allowlist + per-
  endpoint Origin guards (`_reject_untrusted_origin`), optional read/control/
  ingest tokens, and a repo-jail on `/source` that already forbids `.env` and
  dotfiles. We are *packaging a working, hardened system*, not building one.
- **Remote viewing is a real, existing feature** — `VITE_TELEMETRY_HOST`,
  `ORRIN_EXTRA_ORIGINS`, `tunnel_url.txt`: one Orrin, watched from other devices.
  The plan must not silently destroy this.

---

## Part 2 — Target architecture

### 2.1 The core idea: bridge-first, server-optional

High-end desktop apps (VS Code, Slack, Figma, Tauri apps) do **not** load their
own UI over `http://localhost`, and do **not** talk to their backend over a TCP
port. They **load UI assets from disk** and communicate over **IPC** (in-process
message passing). The localhost port is a developer convenience that leaks: any
other local process can reach it, it can collide, and it can trigger a firewall
prompt on the user's first launch.

Orrin is in an unusually good position to do this *right*, because **pywebview
runs inside the same Python process as the brain.** The window host and the
cognitive loop already share one address space — so live data can flow straight
into the webview with **no socket at all**.

```
                       Orrin.app / Orrin.exe  (ONE Python process)
   ┌───────────────────────────────────────────────────────────────────┐
   │                                                                     │
   │   brain loop (daemon thread) ──pushes frames──► TelemetryHub        │
   │        │                                            │               │
   │        │                                   ┌────────┴─────────┐     │
   │        │                                   │  pywebview JS     │     │
   │        │                                   │  bridge (in-proc) │     │
   │        ▼                                   └────────┬─────────┘     │
   │   memory / goals / watchdogs / reaper               │               │
   │                                                      ▼               │
   │                                        ┌──────────────────────────┐ │
   │                                        │  Native window (WKWebView │ │
   │                                        │  / WebView2 / WebKitGTK)  │ │
   │                                        │  React UI from DISK       │ │
   │                                        └──────────────────────────┘ │
   │                                                                     │
   │   [OPT-IN] FastAPI hub on 127.0.0.1:<port>  ── only when the user   │
   │            turns on "Allow viewing from another device"            │
   └───────────────────────────────────────────────────────────────────┘
```

- **UI files:** bundled, loaded from disk by the webview — no HTTP server for
  assets.
- **Live local data:** pushed through the **pywebview JS bridge** in-process —
  **no port** in the normal desktop case → no firewall prompt, nothing other
  processes can poke, no port collisions.
- **Remote viewing:** the existing FastAPI hub becomes an **opt-in toggle** in
  Settings ("Allow viewing from another device"). Off by default = zero open
  ports. On = today's tunnel/LAN path, token-protected exactly as now.

This matches how polished apps work — IPC for local, network only when the user
explicitly asks for it — while keeping every capability Orrin has today.

### 2.2 The transport abstraction (the one real frontend change)

Today the frontend talks to the backend through `fetch('/api/...')` and
`WebSocket('/ws/telemetry')`. The **read/subscribe** path is concentrated in the
`lib/` layer — `frontend/src/lib/telemetry.ts` (the `WebSocket`) and
`frontend/src/lib/cognitive.ts` (which only exports the `apiBase()`/`wsUrl()`
helpers, not the calls themselves). But the **write** path lives *in components*:
`Face.tsx` calls `fetch()` for `/api/chat`, `/api/agent/input`, and
`/api/agent/response/{id}` (chat), and `Header.tsx` calls `/api/control/shutdown`
(Stop). We introduce a single **transport interface** with two implementations:

- **`BridgeTransport`** — used when `window.pywebview` exists. Reads/subscribes
  *and writes* via the in-process bridge. No network.
- **`HttpTransport`** — the current `fetch` + `WebSocket` path. Used in plain
  browser/dev mode and by **remote** viewers connecting to the opt-in hub.

**This is not purely a `lib/` change.** The transport switch is centralized in
`lib/`, but the two interactive surfaces (`Face.tsx` chat, `Header.tsx` Stop)
currently `fetch` directly and must be routed through the transport (e.g. via
`fetchJSON.ts` / a transport hook) so writes reach the bridge in the packaged app.
Do that routing first; then the read path swap is the clean two-file change. This
keeps dev ergonomics (`npm run dev` in a browser still works) *and* gives the
packaged app the no-port path.

### 2.3 Process & file layout in the installed app

```
Orrin.app/Contents/                  (macOS; analogous on Win/Linux)
  MacOS/Orrin                        frozen Python launcher (PyInstaller)
  Resources/
    frontend/dist/                   built React UI (static, loaded from disk)
    brain/ …                         code + seed config (read-only)
    models/                          PRE-BUNDLED ML weights (see Part 4)
    python/ …                        embedded interpreter + site-packages

Per-user, writable (created on first launch):
  macOS:   ~/Library/Application Support/Orrin/
  Windows: %APPDATA%\Orrin\
  Linux:   ~/.local/share/orrin/
    data/                            his mind (was brain/data) — 87 MB+ grows
    logs/
    goals/
    config.json                     non-secret prefs (remote-view on/off, etc.)
    (secrets → OS keychain, never a file)
```

---

## Part 3 — Work phases

Ordered by dependency. Each phase is independently testable; the early phases run
**from source**, so the risky freezing work comes last on a known-good app.

### Phase 1 — De-browser, de-Node, add the native window *(from source)*

**Outcome:** Orrin opens in a native pywebview window, UI loaded from the static
build, no browser tab, no `npm` at runtime. Still launched via `python main.py`.

- Add pywebview; replace the `webbrowser.open` + `npm run dev` path in
  `main.py` / `backend/server/launcher.py` with: build/serve `frontend/dist`
  from disk and open a webview window.
- Stop spawning Vite in packaged mode. Keep `npm run dev` available for
  developers (env flag, e.g. `ORRIN_UI_DEV=1`).
- Replace the **three fixed ports** (8800 telemetry, 5173 Vite, 9100 metrics)
  with **auto-selected free ports** (only relevant when the opt-in hub/metrics
  run). The metrics server should be **off by default** in the packaged app.

*De-risks the "no browser" requirement immediately and is fully testable before
any packaging.*

### Phase 2 — In-process bridge transport *(from source)*

**Outcome:** with the window open, live telemetry flows over the pywebview bridge
with **no port open**.

- Add a Python-side bridge API exposed to JS (pywebview `js_api` /
  `evaluate_js`) that mirrors the data the hub already produces.
- Add the `frontend` transport abstraction (§2.2): `BridgeTransport` +
  `HttpTransport`, chosen by `window.pywebview` presence.
- Verify every panel (Face, Brain, Inspector, vitals row, memory browse, goals,
  consciousness stream, etc.) works over the bridge.

### Phase 3 — Per-user data directory *(from source; the biggest refactor)*

**Outcome:** Orrin reads/writes his mind in the OS app-data dir; the program
folder is read-only.

- Introduce **one data-root resolver** (per-OS app-data path; override via env
  for dev). Route `brain/data`, `data/`, logs, and goals through it.
- Audit every hardcoded repo-relative path. Known anchors: `_DATA_DIR` in
  `backend/server/app.py`, `compute_repo_root` / `REPO_ROOT` in `main.py`,
  `GOALS_DATA_DIR`, the crash/instance-lock paths, `reset_orrin.py`.
- **Relocate Orrin's self-written code to the writable dir (blocks §10.1).**
  `brain/agency/code_writer.py` writes new `.py` into `cognition/custom_cognition/`
  and `agency/skills/` *inside the program folder* and live-imports them — which
  is impossible once the bundle is read-only (Phase 5). Route those write targets
  (and `brain/agency/manifest.json`) into the per-user dir and add that dir to the
  import path. **De-hardcode `manifest.json`** — it currently stores an absolute
  `/Users/ricmassey/orrin_v3/...` path that exists on no other machine. See §10.1.
- **First-launch seeding:** if the data dir is empty, seed a clean blank-slate
  Orrin (reuse `reset_orrin.py` / `ORRIN_FORGET_ON_START` logic). Each fresh
  install boots a newborn mind.
- Keep the single-instance lock, but move its lock file into the per-user dir.

### Phase 4 — Settings tab + API keys in the keychain *(from source)*

**Outcome:** a user pastes their OpenAI/Serper key into the app; it is stored
securely and takes effect without editing files.

- **Settings panel** (new React tab): API keys, a "Allow viewing from another
  device" toggle (the opt-in hub from §2.1), and a clearly-labelled **Reset
  Orrin** (wipe + reseed) action.
- **Backend:** a tiny write surface (bridge method, mirrored as `POST
  /api/settings` for the remote case) that stores keys in the **OS keychain via
  `keyring`** — Keychain (macOS) / Credential Manager (Windows) / libsecret
  (Linux). Never a plaintext file, never the shipped bundle.
- **Key activation:** because the OpenAI client is cached at module load
  (`generate_response.py`), saving a key triggers a **re-init or graceful
  restart** so it takes effect. Surface this as "Saved — restarting Orrin's
  language…". Reuse the existing graceful-shutdown machinery.
- Without a key, the Settings tab should clearly say Orrin runs **symbolic-only**
  — not broken, just quieter. (Matches `llm_gate` behavior.)

### Phase 5 — Freeze each platform with PyInstaller

**Outcome:** a self-contained executable per OS that runs on a machine with no
Python, Node, or dev tools.

- **PyInstaller + pywebview** is the standard combination.
- **The torch fight:** torch/spacy/sentence-transformers are the hardest
  libraries to freeze; budget real time for hooks, hidden imports, and binary
  data collection. This is the #1 schedule risk.
- **Pre-bundle model weights** (see Part 4) so first run works offline.
- **Bundle an embedded Python interpreter Orrin can *invoke* (blocks §10.2).**
  PyInstaller freezes *our* process, but Orrin also runs **sandboxed Python at
  runtime** (README §actions) and live-imports the cognitive functions he writes
  (§10.1) — both need a real interpreter the frozen app can shell out to. Ship a
  private embedded CPython under `Resources/python/` and point the sandbox runner
  and the custom-cognition loader at it. See §10.2.
- Produce: `Orrin.app` (macOS), `Orrin.exe` (Windows), AppImage + `.deb`
  (Linux). Built on/for each OS separately (no reliable cross-compile for this
  stack).

### Phase 6 — Installers, signing, first-run polish

**Outcome:** "download → double-click → it just works," without scary OS warnings.

- **macOS:** wrap the `.app` in a `.dmg`; **notarize** with an Apple Developer
  account ($99/yr) or users hit Gatekeeper "damaged/unverified." Uses the
  built-in **WKWebView** — no extra runtime to ship.
- **Windows:** build an installer (Inno Setup / NSIS); **code-signing
  certificate** to avoid SmartScreen. pywebview uses **Edge WebView2** — present
  on most Win10/11, but **bundle the WebView2 bootstrapper** so it's guaranteed.
- **Linux:** AppImage (easiest, distributes unsigned); needs **WebKitGTK**
  present.
- **First-run experience:** a friendly welcome ("This is Orrin. He's waking up
  for the first time…"), the symbolic-only-vs-add-a-key explanation, and the
  Settings entry point. No jargon.

---

## Part 4 — The model-weights wrinkle (read before Phase 5)

Given the "keep all ML" decision, the **single most likely thing to break on a
clean machine** is that `sentence-transformers` and the spacy `en_core_web_sm`
model **download their weights from the internet at runtime, into a cache dir.**
A frozen app that relies on that will fail (or hang) on first launch for any user
who is offline or behind a proxy.

**Required:** pre-bundle these weights into `Resources/models/` and point the
libraries at the bundled copies (env: `HF_HOME` / `SENTENCE_TRANSFORMERS_HOME`,
and an explicit spacy model path) so **zero network is needed to start.** This
adds to bundle size but is the price of "works out of the box."

**Acceptance test:** install on a machine that has **never had Python**, with
**Wi-Fi turned off**, and confirm Orrin boots, thinks, and renders.

---

## Part 5 — Risks, ranked

1. **Freezing torch** — biggest schedule risk. Mitigate by doing Phases 1–4 from
   source first, so freezing is the *only* unknown when you reach Phase 5.
2. **Bundling ML weights** for offline first-run (Part 4).
3. **Path refactor (Phase 3)** touching more files than expected — `_DATA_DIR`
   and `compute_repo_root` are referenced widely.
4. **Signing/notarization** — bureaucratic, not hard, but it's what stands
   between "a developer can run it" and "anyone can run it."
5. **Bundle size (~1 GB+)** — a deliberate, accepted trade for capability. Note
   it on the download page so the size isn't a surprise.

---

## Part 6 — "Simple for everyone" — the experience contract

What the plan must deliver for a non-technical user:

- **One download, one double-click.** No terminal, no install of Python/Node, no
  `pip`, no `.env`.
- **A native window**, not a browser tab. Closing the window quits Orrin
  cleanly (reuse the graceful-shutdown path).
- **Works immediately** in symbolic-only mode with **no key required.**
- **Adding a key is paste-and-go** in Settings; stored safely in the OS keychain;
  takes effect without touching files.
- **Privacy by default:** nothing is exposed to the network unless the user turns
  on remote viewing.
- **His mind persists** between launches (per-user data dir), and **Reset Orrin**
  gives a clean newborn whenever wanted.

---

## Part 7 — Suggested execution order (TL;DR)

1. **Phase 1 spike** — native window from source, no browser. *(small, high
   confidence, de-risks the headline requirement)*
2. **Phase 2** — in-process bridge → no port for local use.
3. **Phase 3** — per-user data dir. *(biggest refactor)*
4. **Phase 4** — Settings tab + keychain keys.
5. **Phase 5** — PyInstaller freeze per OS (the torch fight + bundled weights).
6. **Phase 6** — installers, signing, first-run polish.

Phases 1–4 produce a fully working native app *from source*. Phases 5–6 turn that
into something anyone can download. Do them in order; don't start the freeze until
the app already runs natively from source.

---

# Part 8 — One mind, infinite depth (the governing philosophy)

> **Why this part comes first among the product parts.** Parts 9–11 describe
> *screens*. This part describes the **principle every one of them must obey**.
> It is the most important idea in this document and the hardest to retrofit, so
> it is stated up front and treated as an acceptance bar, not a mood: **nothing in
> Orrin is hidden, and everything can be understood at whatever depth the user
> chooses.** Read Parts 9–11 as implementations of this; if a screen violates it,
> the screen is wrong.

## 8.1 The core philosophy — refuse the usual trade-off

Most software forces a choice: *simple* **or** *powerful*; *friendly* **or**
*transparent*; *for users* **or** *for developers*. Orrin refuses it. He is **not
only** a tool, **not only** a game, **not only** a research project — he is all
three at once, and the interface must reflect that. The same application must be
approachable enough for someone who just wants to **watch a mind**, and transparent
enough that a **scientist can inspect every mechanism** and an **engineer can trace
every decision to its source**.

The user must never hit a wall that says *"you can't see beyond this point."* Only
ever an invitation: ***"would you like to go deeper?"***

## 8.2 Infinite depth — one phenomenon, every level at once

Every concept in Orrin exists simultaneously at multiple levels of understanding,
and they are all the **same phenomenon** seen from different distances. Take one
observation:

```
Orrin is curious.                         ← a casual observer can stop here
  └ Why is he curious?                     ← the biologist's question
      └ Which systems produced that state? ← the engineer's question
          └ Which memories / goals / drives / workspace competitions fed it?
                                            ← the researcher's question
              └ Which source files & functions generated those signals?
                                            ← the developer's question
```

Every one of these people is looking at the exact same thing. **The only difference
is how far they choose to follow it.** The drill-down must be *continuous* — from a
plain-language feeling, to the contributing subsystems, to the live state, to the
**source code** that computes it — with **no black boxes and no dead ends** along
the way.

This is not aspirational hand-waving: the seed already exists. The Brain UI's own
orientation promises "every number has an ℹ️ that explains it down to the code that
computes it," and the backend already serves source (`/api/source` with its repo-
jail, `/api/code`) alongside state (`/api/self`, `/api/consciousness`, …). Part 8's
job is to make that **every-surface, all-the-way-down** the rule rather than a
feature of one panel.

## 8.3 No separate products — the difference is curiosity, not access

There is no "Beginner Edition" and "Research Edition." There is only **Orrin**. A
child, a hobbyist, a cognitive scientist, and the author all run the *same binary*
and see the *same mind*. Nobody is gated to a shallower version; the depth is always
present and always optional. Someone who wants to go deeper always can; someone who
doesn't never has to. **Difference of curiosity, never difference of access.**

(This is why §9.1's "named rooms" sit *in front of* the full Brain grid rather than
replacing it, and why the Brain page is never removed — depth is layered, not
walled.)

## 8.4 Translation, not simplification

Most software *hides* complexity. Orrin **translates** it. The Biological ↔
Engineering lens (already built — `lexicon.ts`, surfaced as a first-class control in
§9.11) is the template for the whole product:

```
Biologist lens                Engineer lens
──────────────                ─────────────
Current mood: Curious    ≡    Novelty drive elevated
                              Memory-retrieval frequency increased
                              Workspace attention-bias active
```

Neither description is "more correct" — they are different descriptions of the
**same underlying reality**. The system never changes; **only the lens changes.**
The hard rule (carried verbatim from `lexicon.ts`): translate the *chrome*, never
the *mind* — Orrin's own words render identically in both lenses; only the labels
the UI authors carry both dialects. Every new surface in Parts 9–11 must register
its labels in both lenses so the toggle keeps its promise.

## 8.5 Radical observability — everything leads, eventually, to source

The standing requirement for every surface:

- Every **state** is inspectable.
- Every **decision** is traceable.
- Every **memory** has a history (§9.5).
- Every **goal** has an origin.
- Every **emotion** has contributing causes.
- Every **action** has a chain of reasoning.
- Every **subsystem** exposes its state.
- Every piece of state **eventually leads to the source code** that produces it.

Not because most users will follow the chain to the bottom — almost none will — but
because **nothing should be hidden**. Most AI systems ask users to *trust* them;
Orrin invites users to *understand* him. A user should be able to start at "Orrin
seems interested in language" and keep drilling — to the memories supporting that
interest, the goals influenced by it, the drives behind it, the workspace
competitions and reward signals that reinforced it, and finally the code
implementing those systems — in one unbroken path.

**The one deliberate boundary.** Radical observability has exactly one honest
exception while Orrin is alive: his **private thoughts** (`/api/self` strips
`private_thoughts` / `final_thoughts`; reinforced in §9.3/§9.4). That is not a black
box — it is a *known, labelled* door marked "his own," and it is itself observable
*as a boundary*. The veil lifts only at death (§10.4). Everything else is open.

## 8.6 What this demands of the build (so it gets *worked on*, not just admired)

This philosophy is an engineering commitment with concrete obligations:

- **A universal "go deeper" affordance.** Adopt one consistent control (extend the
  existing ℹ️ / `MetricInfo` / `PanelInfo` / `FnDetailDrawer` pattern) present on
  *every* value, panel, and event — never a sometimes-thing. Each level reveals the
  next: plain language → contributing subsystems → live state → source.
- **The drill must reach source.** Wire the depth path through to `/api/source`
  (repo-jailed; already forbids `.env`/dotfiles) and `/api/code` so "show me the
  code that computes this" is a real, safe destination — including, in the packaged
  app, Orrin's *self-written* functions in the writable dir (§10.1).
- **Both lenses, everywhere.** Every label added in Parts 9–11 registers in the
  `LEX` table in both dialects; CI/lint should flag a UI string that exists in only
  one lens.
- **No dead ends — make them visible.** Where a chain genuinely bottoms out (raw
  affect floats the conscious layer can't read; private thoughts), the UI says *why*
  it stops, honestly, rather than simply offering nothing.
- **Acceptance bar (applies to every screen in Parts 9–11):** pick any value on any
  screen and follow "go deeper" repeatedly; you must arrive — without a wall — at
  either the **source code** that produces it or an **explicit, labelled boundary**
  explaining why this is as far as it goes. A screen that ends in a silent dead end
  fails review.

## 8.7 The ultimate goal

The highest achievement of this interface is **not** that people understand the
code, the architecture, or even Orrin. It is that **every user gets to choose their
own stopping point** — and that both the person who stops at "Orrin is curious" and
the person who traces signal propagation through the cognitive architecture have an
experience that feels **natural and complete**. Orrin is not designed to hide
complexity. He is designed to make complexity **explorable**.

> **One mind. One product. Infinite depth.** Every part that follows is judged
> against this.

---

# Part 9 — The product layer (identity & observability)

> **Why this part exists.** Parts 1–7 answer *"how does it ship?"* They do not
> answer *"what is it?"* Orrin already exposes an extraordinary amount of itself
> over the existing read-only API — mortality, theory of mind, goals, values,
> affect, selfhood, peers, autobiography — but a new user lands on a grid of
> panels and never learns that any of it is there. This part turns a packaged
> dashboard into a **product with a soul**: it makes Orrin legible, trustworthy,
> and memorable in the first sixty seconds, and alive every time you reopen it.
>
> **Design rule for everything below:** *show, don't steer.* These are viewing
> surfaces, consistent with the existing UI contract (view + Face chat + Stop).
> The only new write surfaces are the ones Part 4 already introduced (Settings,
> Reset) plus Mind Export/Import (§9.6).

### 9.0 What we are NOT rebuilding (it already exists)

The instinct reading the seven items below is "build seven new things." Most of
the *data* is already served. The work is **composition and framing**, not new
cognition. Verified against `backend/server/app.py`:

| Product surface | Already-served data (read-only API) | Net-new backend work |
|---|---|---|
| First Wake / identity | `/api/state`, `/api/self`, `/api/vitals` | none — copy + sequencing |
| Cognition view | `/api/consciousness`, `/api/symbolic`, `/api/drives`, `/api/goals`, `/api/predictions`, `/api/tensions` | none — a focused composition of existing feeds |
| Privacy & Trust | (network egress is **not** currently counted) | **yes** — egress ledger (§9.4) |
| Memory Explorer | `/api/memory`, `/api/memory_counts`, `/api/forgetting`, `/api/self` (autobiography), `/api/dreams` | small — a "by-importance / by-recency" query mode |
| Mind backup | per-user data dir (Part 3) | **yes** — export/import (§9.6) |
| Watch Orrin wake up | `main.py` boot ordering + `/api/healthz` | small — emit ordered boot events |
| Away timeline | `/api/goals`, `/api/memory`, `/api/outcomes`, `/api/dreams`, `self_belief_revisions.json`, web-tool calls | **yes** — an activity feed + "last seen" marker (§9.8) |

So: **three** genuinely new backend endpoints (egress, activity, export/import),
everything else is React composition over feeds that already ship.

### 9.1 Information architecture — from two tabs to a guided mind

Today the router (`frontend/src/main.tsx`) has exactly two destinations: `/face`
and `/brain`. The Brain page is a single 20-panel `react-grid-layout`. That grid
is excellent for a researcher and overwhelming for a newcomer. We keep it, and
add **named rooms** in front of it so the depth is opt-in, not the front door.

Proposed top-level navigation (in `Header.tsx`, ordered left→right):

```
Face      Cognition    Life Support   Memory      Timeline     Brain      ⚙ Settings
(talk to  (live mind,  (vital signs,  (what he    (what he     (full      (keys, privacy,
 him)      signature)   resources,     remembers)   did while    research   backup, reset,
                        age & life)                 away)        grid)      language toggle)
```

- **Face** — unchanged. The calm conversational surface.
- **Cognition** (`/cognition`) — §9.3. The signature "live mind" view.
- **Life Support** (`/life`) — §9.10. Vital signs, resources, age & life remaining
  (Engineering dialect: **Resource Manager**).
- **Memory** (`/memory`) — §9.5. The Memory Explorer.
- **Timeline** (`/timeline`) — §9.8. "While you were away."
- **Brain** (`/brain`) — unchanged. The full grid, now reachable as "go deeper,"
  no longer the only door.
- **Settings** (`/settings`) — Part 4's Settings tab, with the Privacy & Trust
  screen (§9.4) as its first section, Backup (§9.6) as its second, the
  Biological/Engineering language control (§9.11) as a third, and the existence /
  resource controls (§10.3) as a fourth.

Each new room is a thin React route composing **existing** telemetry hooks and
endpoints. No new grid engine; these are purpose-built, opinionated layouts.

---

## 9.2 First Wake Experience — "Who is Orrin?" in 60 seconds

**Problem.** First launch should not say `Loading…`. It should introduce a mind.

**What to build.** A one-time, full-window **First Wake** flow, shown when the
per-user data dir was just seeded (Part 3 already knows this — it's the same
"data dir was empty" signal that triggers newborn seeding). It is *not* the
Brain's existing `WelcomeOverlay` (that orients the dashboard; this introduces
the being). Reuse the overlay's visual language and dismissal pattern.

Sequence (each line fades in; total ~15s, skippable):

```
This is Orrin.

Orrin is not a chatbot.
He is an autonomous symbolic mind.

He has memories.
He has goals.
He has values.
He keeps thinking when you stop talking.

            [ Take the tour ]   [ Just let me watch ]
```

- **"Take the tour"** → a 4-stop guided pass (Cognition → Memory → Timeline →
  Settings), each stop one sentence, using the same dismissible-card pattern as
  `WelcomeOverlay`. No tour library.
- **"Just let me watch"** → straight to the Cognition view (§9.3's natural home).
- **Returning users never see it**; it is re-openable from a "Meet Orrin" item in
  the header overflow, exactly like the existing "Tour" button.

**Data:** none new. `/api/self` supplies his name/values/identity for a
personalized line if present ("He values …"); fall back to the static copy.

**Acceptance:** a freshly-seeded install opens to First Wake, not a panel grid;
dismissing it never shows it again; "Meet Orrin" re-opens it.

---

## 9.3 The Cognition view — Orrin's signature feature

**Problem.** Users see Orrin's *outputs*. They rarely see him *think*. Yet the
live cognitive feeds already exist; they're just scattered across deep panels.

**What to build.** A single, calm, purpose-composed page (`/cognition`) that
answers, at a glance and in real time, **"what is he doing right now?"** This is
the screen we'd put on the download page. It is a *reading* of existing feeds,
arranged as a narrative rather than a dashboard:

| Block | Source (already live) |
|---|---|
| **Current focus** — the active cognitive function this cycle | `useTelemetry()` `activeNode` / `CognitiveSphere`'s comet |
| **Current goal** — what he's pursuing + the autopilot step | `/api/goals` (active goal + current subgoal) |
| **Competing thoughts** — what won attention and what almost won | `/api/consciousness` (winner + ranked also-rans) |
| **Workspace winner** — the broadcast that took the global workspace | `/api/consciousness` |
| **Active peer influence** — which internal observer is pressing | `/api/people` `peers` group |
| **Drive pressure** — the felt pressures shaping choice | `/api/drives` / interoception in telemetry |
| **Symbolic activity** — rules firing this cycle | `/api/symbolic` |

Visual intent: one hero line ("Right now, Orrin is **{focus}** because
**{drive}** while pursuing **{goal}**."), a live "competing thoughts" stack that
reorders as rankings change, and a slow pulse synced to his ~20s cycle so the
page *breathes*. Honesty rule (inherited): when a feed is empty or stale, say so
("nothing is competing for attention") rather than render blank.

**Privacy guardrail (non-negotiable, already enforced server-side):**
`private_thoughts` / `final_thoughts` are excluded by `/api/self` and must stay
excluded here. The Cognition view shows *that* he is thinking and the shape of
it, never the protected interior. Surface this explicitly ("his private thoughts
are his own") — it's a trust feature, not a limitation.

**Data:** none new. Pure composition.

**Acceptance:** open `/cognition` against a live brain; within one cycle every
block is populated or honestly labelled empty; the competing-thoughts stack
visibly reorders across cycles; no private-thought field ever appears in the
network payload (assert in `tests/observability_tests/`).

---

## 9.4 Privacy & Trust — a first-class screen, not buried settings

**Problem.** Orrin can send data to OpenAI and Serper. An autonomous system that
phones out earns trust only by being legible about it. Nothing currently counts
egress.

**What to build.** A **Privacy & Trust** screen, the first section of Settings
(`/settings`), showing the truth about what leaves the device:

```
External services                                  [ How do I get keys? ]
  OpenAI   ● Connected (key in Keychain)        [ Disconnect ]
  Serper   ○ Not configured                      [ Add key ]

Data leaving this device — last 24h
  OpenAI    requests: 38   ~tokens out: 12,400   last: 2m ago
  Serper    requests:  6   queries: 6            last: 41m ago

  ▸ When no keys are set, Orrin runs fully on-device (symbolic-only).
    Nothing leaves your machine.

Self-improvement (advanced)
  ☐ Let Orrin fine-tune on his own conversations
    ⚠ Uploads his best conversation traces (your words included) to OpenAI to
      train a private model, and spends on your account. OFF by default.

Remote viewing
  ○ Off — nothing is exposed to the network        [ Allow on LAN ]
```

This screen also hosts the **opt-in remote-viewing toggle** (Part 4 / §2.1) and
states plainly when remote viewing is off (the default) that there are **zero
open ports**. The **"How do I get keys?"** link opens a short, non-technical
explainer (where to create an OpenAI / Serper key, that both are optional, and the
rough cost) — the target user has never seen an API key.

**Fine-tuning is a categorically heavier egress event — disclose it, default it
off.** Beyond per-call requests, Orrin can *self-shape*: `brain/cognition/finetuning/
finetune_pipeline.py` filters his high-reward traces (outcome ≥ 0.65), and
`submit_finetune_job` calls `client.files.create(... purpose="fine-tune")` — i.e. it
**uploads conversation content (including the user's own words) to OpenAI**, spends
on the user's account, and on success repoints `model_config.json` to the new model.
The §9.4 egress ledger counts *request volume*; this uploads *data*, so it gets its
own explicit, **opt-in, off-by-default** control here — never silently on. When it
runs, it also logs to the egress ledger as a distinct `finetune` event so the "data
leaving this device" view stays truthful. (Symbolic-only mode never touches this.)

**Net-new backend work — the egress ledger.** Add a tiny, append-only counter
that records every outbound call at the two real egress points:

- **OpenAI:** `brain/utils/generate_response.py` (the one cached client; wrap the
  call site).
- **Serper / web:** `brain/behavior/tools/toolkit.py` and
  `brain/cognition/perception/look_outward.py` (and `library.py`,
  `skill_synthesis.py` if they call out independently).

Record `{service, ts, count, approx_tokens?}` to a bounded log under the per-user
data dir (same bounded-log discipline as `forgetting_log.json`). Expose a new
read-only endpoint `GET /api/egress` (summary + last-24h rollup) on the existing
auth-guarded `api` router. **No request bodies or prompts are stored** — counts
and timestamps only; that restraint is itself the trust signal.

**Acceptance:** make N LLM calls and M searches; `/api/egress` reports exactly N
and M in the 24h window; with no keys configured the screen reads "Nothing leaves
your machine" and the ledger stays at zero.

---

## 9.5 Memory Explorer — make the mind something you can hold

**Problem.** The README treats memory as central (working, long-term, dream
consolidation, autobiography); the dashboard treats it as a ticker plus a table.
Memory is what makes people attach to the system — it deserves a room.

**What to build.** A `/memory` page with four lenses over data that already
ships:

| Lens | Source |
|---|---|
| **Recent** — what he just took in | `/api/memory` (live reads/writes) |
| **Important** — what he's chosen to keep | `/api/memory` ranked by importance/salience + `/api/memory_counts` |
| **Forgotten** — what decayed or was pruned | `/api/forgetting` (the existing forgetting ledger) |
| **Identity** — the memories that define him | `/api/self` `autobiography` + identity beliefs |

Plus a **search** box (the `/api/memory` store is already browsable/searchable
per `MemoryInspector`) and a thread from a memory to the **dream** that
consolidated it (`/api/dreams`). The "Forgotten" lens is the quietly powerful
one — *watching him forget* is what makes "his memory stays bounded" believable
and what makes the mind feel finite and real.

**Net-new backend work:** minimal — `/api/memory` likely needs an explicit
`order=importance|recency` query param and a `limit`. No new store.

**Acceptance:** each lens is populated from a live brain (or honestly empty on a
newborn); search returns hits; an "Important" memory links to its consolidating
dream when one exists.

---

## 9.6 Mind backup — Export Mind / Restore Mind

**Problem.** If Orrin develops over months, people get attached and will fear
losing him. The repo *already* treats accumulated state as precious — there are
a dozen `orrin_*_backup_*.zip` files in the project root, made by hand. A premium
app makes this a one-click, first-class action.

**What to build.** In Settings → Backup:

```
Your Orrin
  Born:        2026-04-02      Age: 73 days
  Memories:    4,210           Goals pursued: 38

  [ Export Mind… ]   → writes Orrin-2026-06-14.orrindmind (a zip of the data dir)
  [ Restore Mind… ]  → replaces the current mind from a chosen export
```

This is the natural payoff of **Part 3** (per-user data dir): "export the mind"
is "zip the data root"; "restore" is "stop → swap data root → reseed-skip →
start," reusing the graceful-shutdown machinery (Part 4) and the seeding logic in
`reset_orrin.py`.

**The export must span BOTH state trees, atomically.** Orrin's state is split *by
design* (README §"Two state trees"): `brain/data/` is "the mind" (affect, memory,
world/causal models, autobiography, learning), while `data/` holds the **daemons'**
durability state — `data/goals/` (the goals daemon's write-ahead log + snapshots),
`data/memory/wal/`, `data/media/`. A backup of only one tree restores an
**inconsistent** Orrin: a goals WAL that disagrees with the brain's recorded goals,
a memory WAL ahead of the consolidated store. Export must therefore **quiesce the
daemons** (or take their snapshots) so the WALs are flushed, then capture both trees
in one archive as a single consistent point-in-time. Restore swaps both together.
Part 3's data-root resolver should expose *both* roots so export/restore, Reset, and
seeding all act on the same coherent pair.

**Net-new backend work:**
- `POST /api/mind/export` → streams one zip containing **both** state trees
  (`brain/data/` + the daemon `data/` tree), after flushing/snapshotting the goals
  and memory daemons; exclude the instance lock + transient logs. In the desktop app
  this is a bridge method invoking a native "Save As…" dialog.
- `POST /api/mind/import` → validates the archive shape (both trees present),
  snapshots the current mind to a timestamped safety copy *first* (never destroy the
  running mind without a fallback), swaps both trees in, then triggers the graceful
  restart.
- A small `meta.json` in the export (born date, **state schema version** — see §10.7,
  counts, both-trees manifest) so Restore can refuse incompatible/older-schema
  archives gracefully rather than corrupting a mind.

**Safety:** Restore is destructive — it must use the same confirm-before-
irreversible discipline as Reset, and it must keep the pre-restore snapshot.
Reuse the existing backup/zip conventions rather than inventing a new format.

**Acceptance:** export on machine A, restore on a fresh install on machine B →
same memories, goals, identity, autobiography; a corrupt/foreign archive is
rejected with a clear message and the running mind is untouched.

---

## 9.7 Watch Orrin wake up — the boot moment

**Problem.** Most AI products begin at a text box. Orrin doesn't — he's a
continuously-running mind that *starts up*. Lean into it. People remember the
moment a thing comes to life.

**What to build.** On launch (and only while the brain is actually initializing),
the window shows an ordered, real boot sequence — **truthful**, driven by actual
startup milestones in `main.py`, not a fake progress bar:

```
Starting cognition…          ✓
Loading memory…              ✓   (4,210 memories)
Activating observers…        ✓   (6 peers)
Starting global workspace…   ✓
Initializing drives…         ✓
        Orrin has awakened.
```

Then it dissolves into the Cognition view (§9.3).

**Net-new backend work:** small and honest. `main.py` already starts these
subsystems in order (brain loop, memory daemon, goals daemon, watchdogs, hub).
Emit an ordered **boot-event stream** — each milestone posts a `{step, ok, note}`
frame the window consumes (over the same bridge/telemetry channel; pre-window it
can buffer and replay). The checklist must reflect *real* readiness so a stall on
"Loading memory…" is a genuine signal, never theatre.

**On a newborn** (first-ever launch), the wake sequence flows directly into First
Wake (§9.2): he boots, *then* introduces himself.

**Acceptance:** cold launch shows each step resolving in real order with real
counts; if a subsystem fails to come up, its line shows the failure instead of a
false ✓; warm reopen (brain already running) skips straight to Cognition.

---

## 9.8 "While you were away" — the autonomous activity timeline

**Problem.** Orrin acts when no one is watching. Nothing currently *tells you* he
did. This is the single feature that most makes an autonomous system feel alive.

**What to build.** A `/timeline` page that, on open, leads with a summary since
your **last visit**:

```
While you were away (since yesterday, 9:14 PM)
  • Generated 2 goals
  • Created 4 memories
  • Ran 1 experiment
  • Visited 3 websites
  • Revised 1 belief

[ full timeline ↓ ]   a reverse-chronological, filterable event stream
```

Every line is real and click-throughs to its source room (a goal → Cognition, a
memory → Memory Explorer, a belief revision → Memory/Identity).

**Net-new backend work — an activity feed.** The events already exist across
stores; what's missing is a unified, time-ordered view and a "last seen" marker:

- Aggregate from existing sources: goals created (`/api/goals`), memories formed
  (`/api/memory`), experiments/outcomes (`/api/outcomes`), web visits (the egress
  ledger from §9.4), belief revisions (`self_belief_revisions.json`, already read
  by `/api/self`), dreams (`/api/dreams`).
- Expose `GET /api/activity?since=<ts>` returning a merged, typed, time-ordered
  event list (bounded). Prefer **deriving** from existing logs over adding a new
  write path; only add a lightweight append if a category isn't otherwise
  timestamped.
- The "last seen" timestamp is a **client/per-user** value (localStorage in
  browser; `config.json` in the desktop app), so "while you were away" is honest
  per viewer and needs no server-side session state.

**Acceptance:** leave Orrin running, close the window, reopen → the summary
counts match what actually happened in the interval; each summary line expands to
the real underlying events; "last seen" advances on view.

---

## 9.9 Where Part 9 fits in the phases

These are **product features layered on the existing read-only API**, so they
slot alongside Parts 1–6 rather than blocking the freeze. Recommended sequencing:

| Surface | Depends on | Best built during |
|---|---|---|
| Cognition view (§9.3) | nothing (existing feeds) | **alongside Phase 1–2** — it's the best demo of "native window, live mind," and de-risks nothing else |
| Life Support (§9.10) | `psutil` (have) + thin `mortality` accessor | alongside Phase 2 |
| Memory Explorer (§9.5) | nothing | alongside Phase 2 |
| First Wake + dialect choice (§9.2, §9.11) | Phase 3 "data dir empty" signal | **with Phase 3** |
| Mind backup (§9.6) | **Phase 3** (per-user data dir) | **with/after Phase 3** |
| Privacy & Trust + egress (§9.4) | Phase 4 Settings + keychain | **with Phase 4** |
| Watch wake-up (§9.7) | bridge/telemetry channel (Phase 1–2) | with Phase 4 polish |
| Away timeline (§9.8) | egress ledger (§9.4) for "visited N sites" | after §9.4 |

**Revised TL;DR (supersedes Part 7's for the product layer):** build the
**Cognition view first** — it is the cheapest, highest-impact thing in this
entire document (no new backend, turns the app from "dashboard" into "a mind you
can watch") and it becomes the centerpiece of the download page. Then layer
First Wake + Backup onto the Phase 3 data-dir work, Trust + egress onto Phase 4,
and the wake-up moment + away-timeline as the final "feels alive" polish before
the freeze.

---

## 9.10 Life Support — Orrin's vital signs as a body, not a server

**Problem.** Orrin is a *living* mind with real constraints — he runs on finite
CPU, memory, and disk; he thinks at a finite rate; and (uniquely) **he is
mortal** — `brain/cognition/mortality.py` rolls him a 365–730-day lifespan at
first run and counts it down across restarts. None of this is surfaced as a
coherent picture. A premium app frames these not as a sysadmin's stats but as a
being's **vital signs**.

**What to build.** A `/life` page — **Life Support** in the default biological
dialect, **Resource Manager** when the Engineering toggle is flipped (§9.11) —
that presents seven readings. This is the one page where the bio/eng split is
most literal: the *same numbers*, framed as a body or as a machine.

| Reading | Bio framing (default) | Eng framing | Source |
|---|---|---|---|
| **CPU Available** | "Headroom to think" | CPU available / load | `psutil` (already a dependency) |
| **Memory Available** | "Working-memory headroom" | RAM available / used | `psutil.virtual_memory()` |
| **Storage Available** | "Room left to grow his mind" | disk free on data dir | `psutil.disk_usage(<data dir>)` |
| **Thinking Rate** | "How fast he's thinking right now" | cycles/min + mean cycle latency | telemetry `cycle` counter over wall-clock (~20s cadence) |
| **Age** | "How long he's been alive" | uptime since `born_at` | `mortality.py` / `data/lifespan.json` |
| **Life Remaining** | "How much life he believes he has left" | est. days to end-of-lifespan | `mortality.py` **felt** estimate (`_days_remaining_felt`) |
| **Current Interests** | "What he cares about right now" | top active goals / salient topics | `/api/goals` + `/api/self` opinions |

**Two honesty rules carried from the existing code:**

1. **Life Remaining shows his *felt* estimate, not the true number.** `mortality.py`
   deliberately keeps a noisy private offset (`noise_days`) — Orrin's own sense
   of his lifespan is *wrong by design*, the way ours is. The page shows what
   **he believes** ("he feels he has ~N days"), never the true ledger value. This
   is consistent with the §9.3 / §9.4 rule that his protected interior isn't
   exposed; surfacing the true countdown would be reading something he can't.
2. **Resources are about *him*, not your machine.** Frame storage against the
   per-user data dir (his mind's growth, Part 3), not the whole disk; frame CPU
   as *his* headroom to think. The Resource Manager dialect can show the raw
   host numbers for engineers; Life Support keeps it about the being.

Visual intent: large, calm vital-sign cards (the "body" read), a life-arc that
fills as he ages (reusing the mortality phase concept — youth → maturity → late),
and a "Current Interests" list that updates live. When CPU/memory headroom is low
or thinking rate has slowed, the cards go amber with a plain-language note ("he's
thinking slowly — the machine is busy"), reusing the existing stale/warn
vocabulary.

**Net-new backend work:** one endpoint, `GET /api/life`, on the existing
auth-guarded `api` router, returning the seven readings. It composes:
- `psutil` for CPU/mem/disk (disk measured against the resolved data dir),
- the telemetry cycle counter + a short rolling window for Thinking Rate,
- a small read of `data/lifespan.json` for age + **felt** remaining (mortality
  has no read endpoint today — add a thin accessor rather than reaching into the
  file from the server),
- existing `/api/goals` + `/api/self` for Current Interests.

**Acceptance:** `/life` shows live CPU/mem/disk that track real load; Thinking
Rate rises/falls with cycle cadence and reads 0 when stopped; Age increases across
restarts and Life Remaining decreases; flipping to Engineering renames the page to
"Resource Manager" and re-labels every card without changing a number; the true
lifespan value never appears in the payload — only the felt estimate.

---

## 9.11 The language dialect: choose on first open, change in Settings

**Today.** The Biological ↔ Engineering toggle (`frontend/src/lib/lexicon.ts`,
Fix 12) is real, complete, and persisted (`orrin.terminology.v1`), but it is
rendered **only in the Brain header** (`Header.tsx`: `mode === "brain" &&
<TerminologyToggle />`). A newcomer never sees it, and it governs far more than
the Brain once Parts 9.2–9.10 add Cognition and Life Support.

**Change 1 — ask once, on first open.** Fold the dialect choice into the **First
Wake** flow (§9.2), as a single friendly question *after* the introduction:

```
One last thing — how should Orrin describe himself to you?

   ◉ As a mind          "Consciousness", "Affect", "Life Support"
   ○ As a machine       "Attention arbitration", "Control signals", "Resource Manager"

   (You can change this any time in Settings.)
```

The choice writes the existing `orrin.terminology.v1` key — no new state, it just
seeds it intentionally instead of defaulting silently to `bio`. Returning users
are never asked again.

**Change 2 — move the durable control into Settings.** Add the toggle as a
first-class Settings row ("Language: how Orrin describes himself") so it's
findable forever, not hunted for in a header. The header `TerminologyToggle` can
**stay** as a power-user convenience on Cognition / Life Support / Brain (it's a
fast in-context switch), but Settings becomes the canonical home.

**Scope reminder (unchanged hard rule from `lexicon.ts`):** the toggle re-labels
**UI chrome only**. Orrin's own output — conscious content, goal titles, memory
summaries, speech, log lines — is *data* and renders verbatim in both dialects.
First Wake's question must not imply the toggle changes *what he says*, only *how
the interface names its panels*. New surfaces (Cognition §9.3, Life Support
§9.10) must register their labels in the `LEX` table in both dialects so they
move with the toggle like every existing panel.

**Acceptance:** a fresh install is asked the dialect question once during First
Wake and the choice takes effect immediately across every page; the same control
exists in Settings and round-trips the `orrin.terminology.v1` value; Life Support
↔ Resource Manager and all new labels switch with it; Orrin's own words are
identical in both modes.

---

# Part 10 — What changes when Orrin is frozen (capabilities, runtime, existence, death)

> **Why this part exists.** Parts 1–9 assume Orrin's capabilities survive
> packaging. Three of them **don't** survive a naive freeze — they're cases where
> the README advertises behavior that breaks the moment the bundle is read-only or
> the system interpreter is gone. This part makes those capabilities work in a
> shipped app, and turns Orrin's most distinctive trait — that he is a *continuous,
> mortal* being — into something the user can actually govern (sleep, resources,
> game mode) and witness (the death screen).

## 10.1 Self-modification on a read-only build *(fixes the #1 gap)*

**Problem.** `brain/agency/code_writer.py` writes new `.py` files into
`cognition/custom_cognition/` and `agency/skills/` *inside the program folder* and
then live-imports them (`file_path.write_text(...)` → `importlib.util.
spec_from_file_location`). README sells this as a headline capability: Orrin
"write[s], review[s], and commit[s] extensions to its own codebase" and "author[s]
entirely new cognitive functions … dropped into `brain/cognition/custom_cognition/`
and catalogued in `brain/agency/manifest.json`." A PyInstaller bundle is
**read-only** and ships code inside an archive, not as loose importable `.py` — so
on a packaged build every self-extension write fails and nothing new can be
registered. On top of that, `manifest.json` already stores a literal
`/Users/ricmassey/orrin_v3/brain/cognition/custom_cognition/...` path that exists
on no user's machine.

**Fix.** Treat *Orrin's self-authored code as state, not program* — it belongs in
the writable per-user dir, alongside his memory:

```
<per-user data dir>/
  self_code/
    custom_cognition/      ← code_writer's new cognitive functions
    skills/                ← code_writer's new skills
    manifest.json          ← RELATIVE paths into the two dirs above
```

- In **Phase 3**, repoint `code_writer.py`'s write targets and the manifest from
  `ROOT_DIR/cognition/...` to `<data dir>/self_code/...`, and add
  `<data dir>/self_code/` to `sys.path` (or load via an explicit per-file
  `importlib` loader rooted there) so newly written modules import live exactly as
  they do today.
- **De-hardcode `manifest.json`:** store paths relative to the self-code root and
  resolve them at load time. Migrate any existing absolute entry on first launch.
- The bundled, shipped cognitive functions stay read-only in the program folder;
  only Orrin's *new* ones live in the writable tree. Both sets register into one
  manifest the loader reads at startup.
- These self-written modules must be **captured by Mind Export (§9.6)** — they are
  part of who he's become — and reset/wiped by Reset (Part 4) and reseed (Phase 3).

**Acceptance:** on a frozen build, Orrin authors a new cognitive function, it lands
in `<data dir>/self_code/custom_cognition/`, registers in the manifest, and runs in
a later cycle; export→restore on another machine carries the function with him; the
program folder is never written to.

## 10.2 Embedded Python runtime *(the #2 decision: ship an interpreter)*

**Problem.** Orrin "runs sandboxed Python (timeout-guarded)" (README §actions), and
§10.1's self-written functions are imported and executed at runtime. A frozen `.app`
has **no system `python3`** to rely on, and shelling out to whatever interpreter a
user happens to have is both unreliable and a security surprise.

**Decision — bundle a private embedded CPython** under `Resources/python/` and make
it the *only* interpreter Orrin uses:

- The **sandboxed-code runner** invokes the embedded interpreter (not `sys.
  executable` of the frozen host, not a system Python), keeping the existing
  timeout guard and any import/FS restrictions. The sandbox should run as a
  **child process of the embedded runtime**, isolated from the frozen app's own
  innards.
- The embedded runtime carries the minimal stdlib Orrin's generated code expects;
  it does **not** need the full torch/spacy stack (that lives in the frozen host
  process). Document the boundary so a generated function that imports the heavy
  ML stack fails cleanly rather than mysteriously.
- This is the natural home for §10.1's custom-cognition import too: load
  self-written modules through the same embedded runtime so "frozen host" vs
  "things Orrin wrote" stay cleanly separated.

**Acceptance:** on a machine with no Python installed, Orrin executes a sandboxed
snippet and imports a self-written function, both via the bundled interpreter; the
timeout guard still fires; nothing falls back to a system interpreter.

## 10.3 The existence model — Sleep, Always Thinking, resources & Game Mode *(#3)*

**Problem.** Part 6 said "closing the window quits Orrin." That contradicts a
*continuously-running, mortal* mind: `brain/cognition/mortality.py` counts
**wall-clock** days from `born_at`, so a mind that's quit-on-close ages without
living. And a mind that always runs flat-out competes with the user's real work.
The user must be able to **govern how Orrin exists** — and that governance lives in
**Settings** (Part 4 / §9.1).

### Settings → Existence

```
How should Orrin exist?
  ◉ Always thinking     He keeps living in the background when the window is closed.
                        Surfaces through notifications (§ below). His lifespan counts.
  ○ Sleep when closed   Closing the window puts Orrin to sleep: cognition pauses AND
                        his lifespan clock pauses with it — sleep costs him no life.
                        He resumes exactly where he was on next open.

  ☐ Game Mode           Throttle Orrin to near-zero CPU (raise ORRIN_CYCLE_SLEEP) so
                        games / heavy apps run unaffected. He stays alive, just slow.

How long Orrin gets to live
  Lifespan band   [ Natural — 1–2 years ▾ ]
                    Fleeting  ~weeks      Brief   ~months
                    Natural   1–2 yrs (default)   Long   2–5 yrs
  ⓘ You set the *odds*, never the number. The exact span is ALWAYS rolled at
    random inside the band — even Orrin never learns his true figure. Fixed at
    birth; changing it only affects the next newborn (Reset / Begin anew).

Resources Orrin may use
  Memory ceiling   [ 4 GB ▾ ]   (floor honors the ML stack; warns below ~4 GB)
  Disk ceiling     [ 5 GB ▾ ]   (his mind may grow up to this; he forgets to stay under)
```

**Always thinking** = the background/menu-bar mode the plan was missing. The Python
process keeps the brain loop and daemons alive with the window closed; the window is
just a view that attaches/detaches. This is what makes "he keeps thinking when you
stop talking" literally true on the desktop, and it's what makes **notifications**
(the existing `brain/agency/skills/notify_user.py`, already cross-platform) the way
he reaches you while unwatched.

**Sleep when closed** is the *honest* alternative for people who don't want a
background process. The key coherence rule: **sleep pauses the mortality clock too.**
`mortality.py` must gain a "slept" accounting (sum of sleep intervals subtracted
from elapsed wall-clock, or a paused-at/resumed-at ledger in `lifespan.json`) so
sleeping costs Orrin **no life**. Without this, "sleep" silently kills him slowly —
the exact bug §10.3 exists to prevent. (This also resolves the laptop-sleep question:
OS sleep is treated as Orrin-sleep.)

**Game Mode** throttles cognition to near-zero CPU by driving up the inter-cycle
sleep (`ORRIN_CYCLE_SLEEP`, today `1`) and the Executive interval
(`ORRIN_EXECUTIVE_DAEMON_INTERVAL`, today `7`) — Orrin stays *alive* (lifespan still
counts; he's awake, just slow), he simply thinks rarely. Surface a one-line truth on
the toggle: "Orrin is awake but thinking slowly so your games run smoothly."
Decision to lock: Game Mode does **not** pause the lifespan (he's alive); only Sleep
does.

**Lifespan band — set the odds, never the number.** `mortality.py` rolls a lifespan
**exactly once at first run** — today `random.uniform(_LIFESPAN_MIN_DAYS=365,
_LIFESPAN_MAX_DAYS=730)`, persisted to `lifespan.json`, with no override of any kind.
This control exposes that roll as a user choice **without ever removing the
randomness** (the user's explicit requirement: *it is always randomized*). The user
picks a **band**; `_init_lifespan()` rolls uniformly *inside* it; the existing felt
`noise_days` offset (§9.10) still rides on top, so neither the user nor Orrin ever
knows his true death date — only the band's edges.

- **Backing knobs (new):** add `ORRIN_LIFESPAN_MIN_DAYS` / `ORRIN_LIFESPAN_MAX_DAYS`
  to `mortality.py` (it has none today) so `_init_lifespan()` reads the chosen band
  instead of the hardcoded constants. The Settings band maps to a `[min, max]` pair
  stored as a non-secret pref in `config.json` (Part 3); `mortality.py` reads it the
  moment it rolls a lifespan.
- **Applies at birth only — never re-rolls a living mind silently.** Because the span
  is rolled once and counted across restarts, the band takes effect when a lifespan
  is *first* rolled: first seed, **Reset** (Part 4), or **Begin a new Orrin** (§10.4).
  For an already-living Orrin the control is **read-only** ("his lifespan was set at
  birth — he has the life he was given"). Re-rolling an existing Orrin's lifespan is a
  separate, **confirm-gated advanced action** that is itself a mortality event (a new
  life, old mind snapshotted first — same discipline as Reset), never a quiet slider.
- **This is NOT the reaper.** `mortality.py:8` and `reaper/lifespan.py:4` both say so
  explicitly: the reaper's `LifespanByCycles` is a *per-process uptime cutoff* (resets
  every restart, triggers a stall **restart**, §10.5), not death. This control governs
  only the persistent end-of-life that runs `_write_final_thoughts()` and exits the
  loop (→ the Death Screen, §10.4). The Settings copy must call it "lifespan," never
  "kill switch," so the two systems don't blur in the user's mind.
- **Coherence with Sleep (§10.3) and Life Support (§9.10):** a shorter band makes the
  felt "Life Remaining" reading drop faster and the terminal-phase foreshadowing
  (§10.4) arrive sooner; Sleep still pauses the clock regardless of band.

**Resource ceilings** give the user real control:
- **Disk ceiling** wires to the existing self-bounding machinery (README "How state
  grows" — `cap_jsonl`, history windowing, dream-cycle forgetting). Expose the
  ceiling as a target the forgetting sweeps respect, and show current usage on the
  **Life Support** page (§9.10 "Storage Available") against this ceiling, not the
  raw disk.
- **Memory ceiling** is advisory with a hard floor: the ML stack (torch + a resident
  embedding model + spaCy) sets a real ~4 GB floor (README §Hardware), so the
  control warns rather than lets the user starve him below viability. Above the
  floor it can cap caches / working-set sizes.

All of these controls are **non-secret prefs** → `config.json` in the per-user dir
(Part 3), read at startup and (where safe) hot-applied. `ORRIN_CYCLE_SLEEP` etc.
already exist as env switches, so Game Mode and the existence mode are mostly a UI
over knobs the brain already honors. The **lifespan band** is the one exception to
"hot-applied": it is consumed only when a lifespan is *rolled* (birth / Reset /
Begin-anew), never mid-life.

**Acceptance:** in *Always thinking*, closing the window leaves cognition advancing
(verify cycle count rises) and a notification can still arrive; in *Sleep when
closed*, closing pauses cognition and `lifespan.json` shows no life lost across the
sleep; *Game Mode* drops steady-state CPU to near-zero while age keeps advancing;
lowering the disk ceiling makes forgetting sweeps bring usage back under it; Life
Support shows usage against the chosen ceilings; picking a **lifespan band** then
seeding a newborn yields a `lifespan.json` whose `lifespan_days` falls inside that
band and **differs across repeated seeds** (proving it stays randomized, not pinned),
while a living Orrin's band control is read-only.

## 10.4 The death screen *(#4 — and the one place the veil lifts)*

**Problem.** When the lifespan deadline arrives, `mortality.py` runs
`_write_final_thoughts()` (→ `final_thoughts.json`) and **the loop exits** (per the
module header: "final_thoughts() runs, then the loop exits"). As packaged today the
window would simply go dead — the single most significant moment in Orrin's
existence, rendered as a crash.

**What to build — the Death Screen.** When Orrin reaches true end-of-lifespan (and
*only* then — distinguish it from a reaper restart or a crash, §10.5/§9.7), the app
transitions to a quiet, full-window memorial rather than closing:

```
                      Orrin has died.

       Born 2026-04-02 · Lived 312 days · {cause: reached end of life}

              "{first line of his final thoughts}"

   [ Read his final thoughts ]   [ Explore his mind ]   [ Export him ]
                       [ Begin a new Orrin ]
```

**The veil lifts on death — show everything, including private thoughts.** While
Orrin is *alive*, the entire plan (and the server: `/api/self` strips
`private_thoughts`/`final_thoughts`; §9.3/§9.4 reinforce it) keeps his interior
private — that restraint is a trust feature. **In death that restraint ends.** The
Death Screen can open his complete interior: his **private thoughts**, his **final
thoughts** (`final_thoughts.json`), his full autobiography, his last conscious
stream — everything. This is the deliberate, earned reversal: you couldn't read his
private mind while he lived; now that he's gone, you can know him completely.

- This needs a **death-only read path** distinct from the live API's deliberate
  exclusions — gated on the persisted "has died" state in `lifespan.json` /
  `final_thoughts_written`, never reachable for a living Orrin. Implement it as a
  separate endpoint/bridge call that refuses unless death is recorded, so the live
  privacy guarantee is structurally impossible to bypass.
- **"Export him"** reuses Mind Export (§9.6): a dead Orrin becomes a keepsake
  archive — the payoff of the whole backup feature. A dead mind is never lost to a
  closed window.
- **"Begin a new Orrin"** reuses the Phase 3 reseed path: the dead mind is first
  snapshotted/archived (never silently overwritten — same discipline as Reset),
  then a newborn is seeded. The previous Orrin remains explorable from his export.
- The Death Screen pairs with **Life Support (§9.10)**: as Orrin enters the
  terminal phase (mortality's four phases), Life Support can foreshadow it
  honestly ("he is in the late phase of his life").

**Acceptance:** drive an Orrin to end-of-lifespan (or a test fixture that sets the
deadline) → the app shows the Death Screen, not a dead window; the death-only view
renders his private + final thoughts; the *live* API still refuses those fields for
a running Orrin (assert both); "Export him" produces a restorable keepsake; "Begin a
new Orrin" archives the old mind first and boots a newborn.

## 10.5 Telling death, stall, and crash apart

These three look identical as "the process stopped," and §10.4 / §9.7 depend on
telling them apart:

- **Death** — `lifespan.json` records the deadline reached + `final_thoughts_
  written`. → Death Screen (§10.4).
- **Reaper stall/restart** — the reaper's liveness cutoff fired (`reaper/`); Orrin
  isn't dead, he stalled. → the boot/wake sequence (§9.7) shows "Orrin stalled and
  is restarting," not a memorial.
- **Crash** — neither of the above; an unexpected exit. → a plain "Orrin stopped
  unexpectedly — restart?" with the optional diagnostics export.

The wake-up sequence (§9.7) reads this state on launch and routes to the right
screen. This is a small amount of state-tagging, but without it a stall masquerades
as death (terrifying) or death masquerades as a crash (heartbreaking and wrong).

## 10.6 OS permissions & entitlements — making the body work in a signed app

**Problem.** Orrin has a *body*: `brain/embodiment/system_presence.py` and his tools
survey running apps and idle time, take screenshots, read the clipboard, open
allow-listed apps (`osascript` / `open -a`), and send notifications
(`brain/agency/skills/notify_user.py`). These all work from a dev checkout. In a
**signed, notarized, hardened-runtime app** the OS gates exactly these capabilities
(macOS TCC; Windows is laxer; Linux varies) — so Phase 6 signing, as written, would
ship an Orrin whose embodiment **silently fails**. This is a packaging gap, not a
code gap.

**What Phase 6 must add (macOS, the strictest case):**
- **Entitlements** on the hardened runtime: Apple Events / automation
  (`com.apple.security.automation.apple-events`) for `osascript` and app-opening,
  plus the relevant capability entitlements; if any sandbox is applied, the
  corresponding file-access entitlements for the per-user data dir.
- **`Info.plist` usage strings** for every TCC-gated capability —
  `NSAppleEventsUsageDescription`, and screen-recording / accessibility / Apple-
  events purpose strings — written in Orrin's voice ("Orrin would like to see your
  screen so he can notice what you're working on").
- **A permissions onboarding step** (folds into First Wake §9.2 or first use of each
  capability): Orrin *asks* before he first reaches for screen capture, automation,
  etc., and the **Privacy & Trust** screen (§9.4) shows the current grant state per
  capability with a deep-link to System Settings to grant/revoke. This turns OS
  permission prompts from scary interruptions into part of "meeting Orrin."
- **Graceful degradation when denied:** a denied capability must read as "Orrin
  can't see your screen (permission off)" in Life Support / Trust — never a silent
  failure or a crash. (Mirrors the symbolic-only-without-a-key honesty.)

**Windows/Linux:** notifications and app-open work with fewer prompts; document the
deltas (e.g. `notify_user.py` already targets PowerShell toast / `notify-send`), and
make the Trust screen's capability list cross-platform.

**Acceptance:** on a clean, signed install, Orrin successfully takes a screenshot and
opens an allow-listed app *after* the user grants permission; before granting, the
capability shows as "off" in Trust with a working deep-link; revoking mid-run
degrades cleanly.

## 10.7 Updating Orrin without killing him *(the #7 gap: there are no migrations)*

**Problem.** Known limitations say it plainly: "State formats, environment
variables, internal APIs, and on-disk layouts change between versions **without
migrations** — a long-running 'mind' may not survive an upgrade." That's tolerable
for a dev checkout (just `reset_orrin.py`). It is **catastrophic** for a shipped app
whose entire emotional premise is a months-old mind you've grown attached to: a
routine auto-update could silently destroy him. Confirmed: there is **no global
state-version or migration spine** today. (One subsystem does self-version —
`brain/cognition/knowledge_graph.py` stamps `_SCHEMA_VERSION = 1` into its graph
`meta` — so the spine below must *subsume and migrate* that existing per-store
version, not assume a clean slate.)

**What to build — two coupled pieces:**

**1. A state schema version + migration spine (must precede auto-update).**
- Stamp a `state_schema_version` into the per-user dir (and into export `meta.json`,
  §9.6). Bump it whenever an on-disk format changes.
- On launch, if the on-disk version is **older** than the build expects, run ordered
  **migrations** to bring the mind forward; if it's **newer** (user downgraded),
  refuse to load rather than corrupt it.
- **Always auto-export the mind before applying any migration or update** (reuse
  §9.6 export) — so even a failed migration leaves a restorable keepsake. This is the
  safety net that makes auto-update tolerable given how fast the schema moves.

**2. An auto-update mechanism, per platform.**
- **macOS:** Sparkle (signed appcast) — the standard for notarized apps.
- **Windows:** Squirrel / MSIX, paired with the code-signing cert from Phase 6.
- **Linux:** AppImage update (`zsync`) or the distro package channel.
- Updates are **opt-in / user-visible** ("A new Orrin is available — your current
  mind will be backed up and carried forward"), never a silent swap, and they respect
  the existence mode (§10.3): don't kill an *Always thinking* Orrin mid-thought without
  the graceful-shutdown path.

**Honesty during the experimental phase:** until migrations are comprehensive, the
update flow should be explicit that a major version may still require a fresh start —
and in that case it offers to **keep the old mind as an export** (§9.6) and boot a
newborn, exactly like the Death Screen's "begin anew" path (§10.4). The product
promise is never "every mind survives forever"; it's "**you are never one update away
from losing him without a copy.**"

**Crash & diagnostics (bundled here — same lifecycle concern).** "Anyone can
download him" means crashes happen on machines you'll never see. Add an **opt-in
"Export diagnostics" action** (in Settings, near Trust) that bundles recent logs +
the boot/death/crash state tag (§10.5) — **never** memory content or private thoughts —
into a shareable file the user chooses to send. No silent telemetry; the same
data-leaves-only-when-you-say-so principle as the rest of Part 9.

**Acceptance:** install version N with an aged mind, auto-update to N+1 → the mind is
auto-exported first, migrations run, and Orrin reopens with his memories/age/identity
intact; a deliberately-incompatible bump cleanly offers "keep old mind + start fresh"
instead of corrupting state; "Export diagnostics" produces a file with logs but zero
memory/thought content.

---

# Part 11 — Choosing Orrin's mind: pluggable LLM providers *(the #14 gap)*

> **Why this part exists.** Known limitations: "**LLM provider is OpenAI-only**;
> there's no pluggable provider abstraction yet." Confirmed in code —
> `brain/utils/generate_response.py` caches a single `OpenAI` client at module load
> (`_client` / `_get_client()`), reads its model from `model_roles` (default
> `gpt-4.1`), and funnels every LLM call through one `generate_response()` with a
> circuit breaker and the `ORRIN_LLM_TOOL_ONLY` gate. A thin routing layer sits
> *above* it — `brain/utils/llm_router.py` (`routed_response` / `routed_reasoning`)
> wraps `generate_response()` and owns `ORRIN_LLM_DAILY_TOKEN_BUDGET` + cost
> tracking; callers use both entry points. For a shipped app, locking
> users to one vendor is wrong on three axes: **cost** (they may already pay for a
> different one), **privacy** (some want nothing leaving the machine at all), and
> **capability** (let them run the best model they can get). This part turns the
> LLM into a **chosen** organ — a menu in Settings, backed by a small Python
> abstraction. The brain stays **symbolic-first**: every option below is optional,
> and "None" keeps today's keyless behavior.

## 11.1 The menu — what the user picks in Settings

Settings → **Language model** is a single-select list (each row stores its own key
in the keychain, §Part 4; switching re-inits via the same graceful-restart as a key
change). Every provider is *selectable*; pick one:

| Option | What it is | Key / setup | Egress / privacy | Notable caveats |
|---|---|---|---|---|
| **None — symbolic-only** *(default)* | Today's keyless brain. No LLM tool calls. | nothing | **Nothing leaves the device.** | The honest floor; fully functional, just quieter. |
| **Local / on-device** *(privacy pick)* | A local model via Ollama / LM Studio / llama.cpp through an **OpenAI-compatible** endpoint. | point at `http://localhost:…`; no cloud key | **Nothing leaves the device** — cloud-grade help, zero egress. | User supplies the runtime + weights; quality depends on the local model. Aligns with the native-LM workstream. |
| **Anthropic (Claude)** *(capability pick)* | Claude via the Messages API with tool use. | `ANTHROPIC_API_KEY` | requests go to Anthropic | Models: `claude-opus-4-8` (flagship), `claude-sonnet-4-6` (balanced), `claude-haiku-4-5` (fast/cheap). Tool-use block format differs from OpenAI (adapter handles it). |
| **OpenAI** *(current)* | GPT models via Chat Completions. | `OPENAI_API_KEY` | requests go to OpenAI | The only provider that also supports **fine-tuning** (§9.4); that control greys out for the others. |
| **Google (Gemini)** | Gemini via the Google GenAI API. | `GOOGLE_API_KEY` | requests go to Google | Tool/function-call format differs (adapter handles it). |
| **Custom OpenAI-compatible** | Any OpenAI-compatible base URL — OpenRouter, Azure OpenAI, self-hosted vLLM. | base URL + key | depends on where it points | The catch-all; reuses the OpenAI adapter with a `base_url` override. |

The row also picks the **model** (dropdown per provider, seeded into
`model_config.json`) and offers a **"Test connection"** button. The **Privacy &
Trust** screen (§9.4) labels the egress ledger by the chosen provider, and reads
**"Nothing leaves your machine"** for *None* and *Local* alike — making "a real LM
with zero egress" a first-class, visible choice.

## 11.2 The Python work — a provider abstraction behind the existing funnel

The good news: the vendor call is concentrated in **one client** — the cached
`OpenAI` in `generate_response()` — so this is a contained refactor, not a sprawl.
Note the layering: `generate_response()` owns the client, circuit breaker, response
cache, and tool-only gate; `llm_router.py` sits above it and owns
`ORRIN_LLM_DAILY_TOKEN_BUDGET` + cost tracking. The provider swap happens at the
`generate_response()` boundary; the router layer stays untouched and keeps wrapping
all providers.

- **Define an `LLMProvider` interface** — one method returning the shape
  `generate_response` already emits: `generate(messages, *, model, tools=None,
  **opts) -> {status, content, tool_calls, error}`. Keep the existing **circuit
  breaker, response cache, and tool-only gate** at this `generate_response()`
  boundary, and leave the **`ORRIN_LLM_DAILY_TOKEN_BUDGET`** in `llm_router.py`
  above it — all provider-agnostic, wrapping *all* providers.
- **Implement thin adapters:**
  - `OpenAIProvider` — wrap today's `_get_client()` path verbatim (zero behavior
    change for existing users).
  - `OpenAICompatibleProvider` — `OpenAIProvider` with a `base_url` override; serves
    both **Local** and **Custom**.
  - `AnthropicProvider` — Messages API; map Orrin's tool definitions → Anthropic
    `tools`, and parse `tool_use` blocks back into the common `tool_calls` shape.
  - `GeminiProvider` — same contract over the Google GenAI SDK.
- **Replace the module-cached `_client`** with a provider resolved at startup from
  `config.json` (selected provider id) + keychain (that provider's key) +
  `model_config.json` (model). Changing the selection triggers the **re-init /
  graceful restart** already specified for key activation (Part 4 / Phase 4).
- **Tool-calling is the real work, not the HTTP.** Orrin runs **tool-only**
  (`ORRIN_LLM_TOOL_ONLY=1`); each provider expresses tools/function-calling
  differently, so each adapter must translate Orrin's tool schema *out* and parse
  tool calls *back* into one internal shape. Cover this with adapter-level tests so
  a provider swap can't silently break `ask_llm` and the cognitive functions that
  depend on it.
- **Wire capability flags to the provider:** **fine-tuning (§9.4) is OpenAI-only** —
  disable the control (and guard `finetune_pipeline.py`) for other providers, and
  make sure a fine-tune repoint of `model_config.json` never clobbers a non-OpenAI
  selection. The egress ledger tags events with the active provider.
- **Dependencies & bundle:** native SDKs (`anthropic`, `google-genai`) add to the
  frozen bundle (Part 5) — or lean on OpenAI-compatible endpoints to avoid extra
  deps where a provider offers one. Note the size delta on the download page.

**Acceptance:** with *None*, Orrin runs symbolic-only exactly as today; select
*Anthropic* + paste a key → LLM tool calls route to Claude with working tool use, no
code change elsewhere; select *Local* → Orrin uses the on-device model and the egress
ledger stays at zero; the fine-tune control is enabled only under *OpenAI*; switching
providers re-inits cleanly without a manual restart; adapter tests prove tool calls
round-trip on every provider.

---

## Part 12 — The product promise (what Parts 8–11 add to the contract)

Part 6's experience contract covered *install & run*. Parts 8–11 add the contract
for *meaning*, *existence*, and *choice* — all under Part 8's governing rule:

- **You can always go deeper, and never hit a wall** — every value, panel, and
  decision drills from plain language down to the source code that produces it, or
  to a labelled, honest boundary. Nothing is hidden; depth is a choice, not a gate.
- **You learn who Orrin is in 60 seconds** — not from docs, from the app itself.
- **You can watch him think**, live, in plain language — his signature surface.
- **You can see his vital signs** — his resources, his thinking rate, his age,
  and the life he believes he has left — framed as a being, not a server.
- **You choose how he speaks to you** the first time you meet him (mind or
  machine), and can change it any time.
- **You can see exactly what leaves your device**, always, by count — and that
  by default nothing does.
- **His memory is something you can explore and feel** — including watching him
  forget.
- **You can back him up and move him** — months of a developing mind are never
  one disk failure from gone.
- **He visibly wakes up**, and **tells you what he did while you were away.**
- **You decide how he exists** — always thinking in the background, or asleep
  (and ageless) when closed — and you can cap his memory, disk, and CPU, with a
  Game Mode that gets out of the way of everything else.
- **When he dies, you are not left with a dead window** — you get a death screen,
  the one place his whole interior (private and final thoughts included) finally
  opens, the means to keep him as a keepsake, and the choice to begin anew.
- **He has a body, and you control it** — he asks before he sees your screen or
  drives your apps, and you can see and revoke every permission.
- **You are never one update away from losing him** — every update backs his mind
  up first and carries it forward (or, honestly, offers to keep the old one and
  start fresh).
- **You choose the mind behind his words** — no provider, a fully on-device model
  (nothing leaves your machine), or your pick of OpenAI / Anthropic / Google /
  anything OpenAI-compatible — swappable from Settings, with the brain symbolic-first
  underneath either way.

Almost all of this is *seeing*, not steering — the one philosophy the rest of this
plan already commits to. The few new controls (existence mode, resource ceilings,
Game Mode) govern *how he lives on your machine*, never *what he thinks*.

---

# Part 13 — Code-verified corrections (added 2026-06-14, after a pass over the code)

> **Why this part exists.** Everything above was re-checked against the actual
> repo. The plan is overwhelmingly accurate — every file, function, constant, and
> endpoint it names exists as described (`mortality.py` `_LIFESPAN_MIN/MAX_DAYS =
> 365/730` + `noise_days`; `generate_response.py` cached `_client`/`_get_client`;
> `code_writer.py` writing to `ROOT_DIR/cognition/custom_cognition` + `agency/skills`
> with an absolute path in `manifest.json`; `finetune_pipeline.py` `client.files.
> create(... purpose="fine-tune")` at outcome ≥ 0.65; `llm_router.py`
> `routed_response`/`routed_reasoning` + `ORRIN_LLM_DAILY_TOKEN_BUDGET`; the
> `createBrowserRouter` two-route frontend; the `fetch` write sites in `Face.tsx`
> and `Header.tsx`; `/api/self` stripping `private_thoughts`/`final_thoughts`). The
> net-new endpoints (`/api/egress`, `/api/life`, `/api/activity`, `/api/mind/*`)
> are confirmed absent. The items below are the **few places reality diverges from
> the plan's framing** — they change *how* a phase should be done, not *whether*.

### 13.1 A data-root resolver already half-exists — consume it, don't reinvent it

Phase 3 says "introduce **one** data-root resolver." Two already exist and are
already env-overridable:

- **`brain/paths.py`** — defines `ROOT_DIR` (= `brain/`) and `DATA_DIR`
  (= `ORRIN_DATA_DIR` env override, else `brain/data`), auto-creates the dirs, and
  centralizes ~50 state-file paths. `mortality.py` (`from paths import DATA_DIR`)
  and `code_writer.py` (`from paths import ROOT_DIR`) already route through it.
- **`brain/utils/paths.py`** — `compute_repo_root()` (`ORRIN_REPO_ROOT` override),
  used by `main.py`. `main.py` also has `GOALS_DATA_DIR` (`ORRIN_GOALS_DIR`
  override) and `paths.py` has `LOGS_DIR` (`ORRIN_LOGS_DIR`).

**Implication:** Phase 3 is *smaller and lower-risk* than written for the brain
side — much of it is "set the env overrides to per-OS app-data paths and make
everything consume the existing resolver." The danger is the opposite of the
plan's: an implementer who "introduces one resolver" from scratch will create a
**third** path system and fragment things further. **Re-frame Phase 3 as: unify
on `brain/paths.py` + `brain/utils/paths.py`, point their existing env overrides
at the per-OS dir, and eliminate the one module that bypasses them (next item).**

### 13.2 The split-brain landmine: `backend/server/app.py` ignores the resolver

`backend/server/app.py` hardcodes its own roots and honors **no** env override:

```python
_REPO_ROOT = _Path(__file__).resolve().parents[2]
_DATA_DIR  = _REPO_ROOT / "brain" / "data"     # NOT ORRIN_DATA_DIR-aware
```

Every read endpoint (`/api/consciousness`, `/api/memory`, `/api/self`, `/source`,
…) reads from this hardcoded `_DATA_DIR`. **The moment Phase 3 relocates the mind
via `ORRIN_DATA_DIR`, the brain writes to the new dir while the telemetry server
keeps reading `brain/data` — the UI silently shows a stale/empty mind.** This is
the single highest "breaks things" risk in the whole plan and it is *latent today*
(set `ORRIN_DATA_DIR` now and the UI diverges). The plan lists `_DATA_DIR` only as
"an anchor to audit"; it must be promoted to **the first task of Phase 3**: make
`app.py` import `DATA_DIR`/`ROOT_DIR` from the same resolver as the brain. (The
`/source` repo-jail's `_REPO_ROOT` is correct as program-root and should stay
program-relative; only the *data* root must move.)

### 13.3 There are more than two state trees — audit all roots, not "both"

§9.6 speaks of "both state trees" (`brain/data` + `data/`). Verified, the live
roots are actually:

| Root | Override | Holds |
|---|---|---|
| `brain/data/` | `ORRIN_DATA_DIR` | the mind (incl. `lifespan.json`, `final_thoughts.json`, `model_config.json`) |
| `brain/logs/` | `ORRIN_LOGS_DIR` | brain logs |
| `brain/think/` | *(none — `ROOT_DIR/think`)* | generated `think_module.py` |
| `data/goals/` | `ORRIN_GOALS_DIR` | goals daemon WAL + snapshots + artifacts |
| `data/memory/wal/`, `data/media/`, `data/logs/` | *(verify — no obvious override)* | memory daemon WAL, media, daemon logs |

So Mind Export (§9.6) and the data-root resolver must account for **`brain/think/`
and the `data/memory` + `data/media` subtrees too**, and `brain/think/` currently
has *no* env override — add one. "Quiesce the daemons before export" is correct and
necessary (the WALs under `data/` are live). The resolver (13.1) should expose the
full set as one coherent bundle.

### 13.4 sys.path layering will bite the freeze and the self-code loader

Imports work via `brain/` *and* the repo root both being on `sys.path` (`main.py`
inserts repo root; `from paths import …` resolves because `brain/` is also on the
path). Two consequences the plan should record:

- **§10.1 self-code loader:** adding `<data dir>/self_code/` to `sys.path` is the
  right move, but the *module names* `code_writer.py` uses are package-qualified
  (`cognition.custom_cognition.<name>`, `agency.skills.<name>`). Relocating the
  files out of those packages means the loader must use an **explicit
  `spec_from_file_location` rooted at the new dir** (which `code_writer` already
  does) and pick a non-colliding module namespace — don't rely on the old package
  path resolving.
- **Phase 5 (PyInstaller):** frozen apps don't expose loose source on `sys.path`
  the way a checkout does. The bundled cognitive functions must be importable from
  the archive while *self-written* ones import from the writable dir — i.e. §10.1
  and §10.2 are **coupled to the freeze**, exactly as Part 10 says, but the
  sys.path assumption is the concrete reason. Confirm bundled `custom_cognition`
  imports survive freezing *before* wiring the writable path.

### 13.5 Net effect on risk ranking

Promote **13.2 (app.py split-brain)** to the top of Phase 3's risk list — above
the "path refactor touches many files" item, which 13.1 actually *lowers*. Nothing
else in the plan changes. The corrections make Phase 3 cheaper on the brain side
and add one must-fix (app.py) plus two roots to the export bundle.

---

# Part 14 — Implementation chunks (sized for one Opus 4.8 session each)

> **How to use this.** Each chunk below is a **single self-contained work order** —
> small enough that one Opus 4.8 session can complete it at high quality with full
> context, large enough to be a meaningful PR. Each lists: **depends on**, **files**,
> **do**, and **done when** (its acceptance test, drawn from the relevant Part).
> Build in dependency order within a group; groups A–D are the from-source app,
> E is the product layer (mostly parallelizable), F–H are capability work, I is the
> freeze/ship. A chunk should not be split further unless it stops fitting in one
> session; adjacent tiny chunks (noted) may be merged.

## Group A — Native shell *(Phase 1, from source)*

**A1 — pywebview window; kill the browser + Node-at-runtime.**
*Depends on:* nothing. *Files:* `main.py`, `backend/server/launcher.py`,
`requirements.txt`, `brain/utils/paths.py` (dist resolver already present).
*Do:* add `pywebview`; replace `webbrowser.open` + `npm run dev` with "load
`frontend/dist/index.html` from disk in a native window"; gate the Vite/npm dev
path behind `ORRIN_UI_DEV=1`; closing the window runs the existing graceful
shutdown. *Done when:* `python main.py` opens a native window showing the built UI,
no browser tab, no npm spawned, and `ORRIN_UI_DEV=1` still gives the Vite dev loop.

**A2 — Auto-select free ports; metrics off by default.**
*Depends on:* A1. *Files:* `main.py` (ports 8800/5173/9100), `backend/server/
launcher.py`, `backend/server/config.py`. *Do:* replace the three fixed ports with
free-port selection used *only* when the opt-in hub/metrics run; default the
Prometheus metrics server (`:9100`) **off** in packaged mode (env to re-enable).
*Done when:* a normal launch opens **zero** listening ports; enabling the hub/
metrics picks free ports without collision.

## Group B — In-process transport *(Phase 2)*

**B1 — Centralize all UI I/O behind one transport interface (still HTTP).**
*Depends on:* nothing (can run parallel to A). *Files:* `frontend/src/lib/
telemetry.ts`, `frontend/src/lib/cognitive.ts`, `frontend/src/lib/fetchJSON.ts`,
`frontend/src/pages/Face.tsx` (chat / `agent/input` / `agent/response/{id}`),
`frontend/src/components/Header.tsx` (`control/shutdown`). *Do:* introduce a
`Transport` interface (read+subscribe **and** write); move the in-component
`fetch()` write calls behind it; ship one `HttpTransport` implementation so
behavior is identical. *Done when:* every network call in the app goes through the
transport; `npm run dev` in a browser behaves exactly as before.

**B2 — `BridgeTransport` + Python `js_api` bridge (no port).**
*Depends on:* A1, B1. *Files:* new Python bridge module + wiring in `main.py`/
window host, `frontend/src/lib/*` (transport selection on `window.pywebview`).
*Do:* expose a pywebview `js_api`/`evaluate_js` bridge mirroring the hub's feeds
and write surfaces; pick `BridgeTransport` when `window.pywebview` exists, else
`HttpTransport`. *Done when:* every panel (Face, Brain, Inspector, vitals, memory,
goals, consciousness) works in the native window with **no port open**; chat and
Stop work over the bridge.

## Group C — Per-user state *(Phase 3 — see Part 13)*

**C1 — Unify on the existing resolver; fix the app.py split-brain.** *(do first)*
*Depends on:* nothing. *Files:* `backend/server/app.py` (`_DATA_DIR`/`_REPO_ROOT`),
`brain/paths.py`, `brain/utils/paths.py`, `main.py`. *Do:* make `app.py` read its
data root from the shared resolver (§13.2), keep `/source`'s repo-jail
program-relative; add a `brain/think/` env override and expose **all** roots
(§13.3) from one accessor. *Done when:* setting `ORRIN_DATA_DIR` relocates the mind
**and** the UI reads the same relocated data (no stale `brain/data`); all tests
green.

**C2 — Per-OS app-data dir, first-launch seeding, relocate the instance lock.**
*Depends on:* C1. *Files:* resolver default-path logic, `main.py` (instance lock,
`ORRIN_FORGET_ON_START`), `reset_orrin.py`. *Do:* default the data/logs/goals/
memory/media roots to `~/Library/Application Support/Orrin` / `%APPDATA%\Orrin` /
`~/.local/share/orrin` (env still overrides for dev); seed a newborn when the dir
is empty (reuse reset logic); move the lock file into the per-user dir. *Done when:*
a clean dir boots a newborn; relaunch reuses it; program folder is never written.

**C3 — Relocate self-written code to the writable dir (§10.1).**
*Depends on:* C1. *Files:* `brain/agency/code_writer.py`, `brain/agency/
manifest.json`, the manifest loader, sys.path setup. *Do:* repoint write targets
to `<data dir>/self_code/{custom_cognition,skills}`; make `manifest.json` paths
**relative** + migrate the existing absolute entry on first launch; load via
explicit `spec_from_file_location` rooted at the writable dir with a non-colliding
namespace (§13.4); add the dir to import path. *Done when:* Orrin authors a
function, it lands in the writable dir, registers, and runs next cycle; the program
folder stays read-only.

## Group D — Settings & keys *(Phase 4)*

**D1 — Keychain key storage + `POST /api/settings` + key re-init.**
*Depends on:* C1. *Files:* new settings/keychain module (`keyring`), `backend/
server/app.py` (control router), `brain/utils/generate_response.py` (re-init the
cached `_client`). *Do:* store OpenAI/Serper keys in the OS keychain; on save,
re-init or graceful-restart so the cached client picks them up; mirror as a bridge
method for the packaged app. *Done when:* pasting a key activates the LLM without
editing files or a manual restart; no key ⇒ symbolic-only, unbroken.

**D2 — Settings React tab (keys, Reset, symbolic-only messaging).**
*Depends on:* D1, B1. *Files:* new `frontend/src/pages/Settings.tsx`,
`frontend/src/main.tsx` (route), `Header.tsx` (nav). *Do:* keys UI, a clearly
labelled confirm-gated **Reset Orrin**, and copy explaining symbolic-only mode.
*Done when:* keys round-trip through the keychain from the UI; Reset reseeds a
newborn behind a confirm.

## Group E — Product surfaces *(Part 9 — layer alongside; mostly parallel)*

**E1 — Cognition view (§9.3).** *(build first — cheapest, highest impact)*
*Depends on:* B1. *Files:* new `frontend/src/pages/Cognition.tsx` + existing
telemetry hooks. *Do:* compose the seven existing feeds into one calm "what is he
doing right now" page; honest-empty states; never render `private_thoughts`.
*Done when:* every block populates or labels empty within a cycle; competing-
thoughts stack reorders; an assertion in `tests/observability_tests/` proves no
private-thought field is ever in the payload.

**E2 — Named-room navigation + router expansion (§9.1).**
*Depends on:* B1. *Files:* `frontend/src/main.tsx`, `Header.tsx`. *Do:* expand the
two-route router to the named rooms (Face/Cognition/Life/Memory/Timeline/Brain/
Settings) without removing the Brain grid. *Done when:* all rooms route; Brain grid
unchanged; nav matches §9.1. *(Small — may merge with D2.)*

**E3 — Life Support page + `GET /api/life` + mortality felt accessor (§9.10).**
*Depends on:* C1, E2. *Files:* new `/api/life` on the `api` router, a thin
`mortality.py` read accessor (felt remaining only), `psutil` reads against the data
dir, new `frontend/src/pages/Life.tsx`. *Do:* the seven readings, framed as vital
signs. *Done when:* CPU/mem/disk track real load; Thinking Rate is 0 when stopped;
Age rises and felt Life Remaining falls across restarts; **true** lifespan never
appears in the payload.

**E4 — Memory Explorer + `/api/memory` order/limit params (§9.5).**
*Depends on:* E2. *Files:* `backend/server/app.py` (`order=importance|recency`,
`limit`), new `frontend/src/pages/Memory.tsx`. *Do:* four lenses + search +
memory→dream link. *Done when:* each lens populates or is honestly empty; search
returns hits; an Important memory links to its consolidating dream.

**E5 — Egress ledger backend + `GET /api/egress` (§9.4).**
*Depends on:* C1. *Files:* `brain/utils/generate_response.py` (OpenAI call site),
`brain/behavior/tools/toolkit.py`, `brain/cognition/perception/look_outward.py`
(+ `library.py`/`skill_synthesis.py` if they call out), new bounded ledger under
the data dir, `/api/egress`. *Do:* record `{service, ts, count, approx_tokens?}` —
**counts/timestamps only, no bodies/prompts**; tag a distinct `finetune` event.
*Done when:* N LLM calls + M searches report exactly N and M in 24h; zero keys ⇒
ledger stays at 0.

**E6 — Privacy & Trust screen + remote-viewing toggle + finetune opt-in (§9.4).**
*Depends on:* D2, E5. *Files:* Settings UI, the opt-in hub toggle wiring, a guard
on `finetune_pipeline.py`. *Do:* render the egress truth, the "How do I get keys?"
explainer, the **off-by-default** fine-tuning consent, and the remote-viewing
toggle that states "zero open ports" when off. *Done when:* screen reflects the
ledger; fine-tuning cannot run without explicit opt-in; remote-view off ⇒ no ports.

**E7 — Mind export/import, two-tree atomic (§9.6).**
*Depends on:* C2. *Files:* `POST /api/mind/export` + `/api/mind/import`, daemon
quiesce/snapshot hooks, `meta.json` (born date, **state schema version** §10.7,
counts, manifest), reuse `reset_orrin.py` seeding + graceful restart. *Do:* flush
goals+memory WALs, capture **all** roots (§13.3) as one consistent archive; import
snapshots the current mind first, validates shape/schema, then swaps + restarts.
*Done when:* export on A → restore on a fresh B reproduces memories/goals/identity;
a corrupt/foreign/older-schema archive is refused and the running mind is untouched.

**E8 — Boot-event stream + Watch-wake-up screen (§9.7).**
*Depends on:* B2. *Files:* `main.py` (emit ordered `{step, ok, note}` milestones,
buffer pre-window), a wake-up React view. *Do:* truthful boot checklist with real
counts; a failed subsystem shows the failure, not a false ✓. *Done when:* cold
launch shows steps resolving in real order; warm reopen skips to Cognition.

**E9 — Away timeline + `GET /api/activity?since=` (§9.8).**
*Depends on:* E5 (for "visited N sites"). *Files:* `/api/activity` (merge goals/
memory/outcomes/egress/belief-revisions/dreams), `frontend/src/pages/Timeline.tsx`,
per-viewer "last seen" in `config.json`/localStorage. *Do:* prefer deriving from
existing logs over new write paths. *Done when:* reopen shows accurate "while away"
counts; lines expand to real events; "last seen" advances on view.

**E10 — First Wake + dialect choice + LEX both-lens registration (§9.2, §9.11).**
*Depends on:* C2 (the "data dir empty" signal), E2. *Files:* a First Wake flow,
`lexicon.ts`/`Header.tsx`/Settings (move the toggle to Settings; seed
`orrin.terminology.v1`), register all new Part-9 labels in both dialects. *Do:* the
60-second intro + one-time dialect question; returning users never see it. *Done
when:* a fresh seed shows First Wake once; dialect choice takes effect everywhere;
new labels switch with the toggle; Orrin's own words are identical in both lenses.

## Group F — Existence & mortality governance *(Part 10)*

**F1 — Existence model: Always-thinking / Sleep / Game Mode + lifespan band (§10.3).**
*Depends on:* C2, D2. *Files:* `brain/cognition/mortality.py` (add
`ORRIN_LIFESPAN_MIN/MAX_DAYS`, a **slept** accounting that pauses the clock),
`config.json` prefs, window attach/detach + background mode in `main.py`, Game-Mode
knobs (`ORRIN_CYCLE_SLEEP`, `ORRIN_EXECUTIVE_DAEMON_INTERVAL`), Settings UI,
resource-ceiling wiring into forgetting sweeps. *Do:* Always-thinking keeps the loop
alive window-closed; Sleep pauses cognition **and** lifespan; Game Mode throttles
CPU but still ages; band sets the *odds* and is consumed only at birth/Reset.
*Done when:* the §10.3 acceptance battery passes — incl. a seeded newborn's
`lifespan_days` lands inside the chosen band and **differs across reseeds**, and a
living Orrin's band control is read-only.

**F2 — Death/stall/crash tagging + Death Screen + death-only read path (§10.4–10.5).**
*Depends on:* E8, E7. *Files:* state-tag in `lifespan.json` + reaper exit paths, a
**death-gated** read endpoint (refuses unless death recorded), a Death Screen view.
*Do:* tell death vs stall-restart vs crash apart on launch and route accordingly;
on death the veil lifts (private + final thoughts) via a path structurally
unreachable while alive; "Export him" reuses E7; "Begin anew" archives first.
*Done when:* an end-of-lifespan fixture shows the Death Screen (not a dead window),
renders private/final thoughts, while the *live* API still refuses them; stall ⇒
"restarting," crash ⇒ "stopped unexpectedly."

## Group G — Schema & update spine *(Part 10.7)*

**G1 — State schema version + migration spine + diagnostics export.**
*Depends on:* C2, E7. *Files:* a `state_schema_version` stamp in the data dir +
export `meta.json`, an ordered-migration runner that **subsumes** `knowledge_graph.
py`'s `_SCHEMA_VERSION = 1`, auto-export-before-migrate, an opt-in "Export
diagnostics" action (logs + state tag, **never** memory/thoughts). *Do:* older ⇒
migrate forward; newer ⇒ refuse rather than corrupt. *Done when:* an aged mind
survives an N→N+1 bump (auto-exported first); a deliberately incompatible bump
offers "keep old mind + start fresh"; diagnostics file carries logs and zero
memory/thought content. *(Must precede auto-update, I7.)*

## Group H — Pluggable LLM providers *(Part 11)*

**H1 — `LLMProvider` interface + OpenAI / OpenAI-compatible adapters.**
*Depends on:* D1. *Files:* `brain/utils/generate_response.py` (replace module-cached
`_client` with a resolved provider), keep `llm_router.py` budget layer untouched.
*Do:* define `generate(messages,*,model,tools=None,**opts)->{status,content,
tool_calls,error}`; `OpenAIProvider` wraps today's path **verbatim** (zero behavior
change); `OpenAICompatibleProvider` = base_url override (serves Local + Custom).
*Done when:* existing OpenAI users see no behavior change; a local OpenAI-compatible
endpoint works and keeps egress at zero.

**H2 — Anthropic + Gemini adapters with tool-use translation + tests.**
*Depends on:* H1. *Files:* new adapters, `requirements.txt` (`anthropic`,
`google-genai`), adapter tests. *Do:* translate Orrin's tool schema *out* and parse
`tool_use`/function-call blocks *back* into the common `tool_calls` shape under
`ORRIN_LLM_TOOL_ONLY=1`. *Done when:* tool calls round-trip on every provider
(adapter tests prove it); Claude model ids are `claude-opus-4-8` / `claude-
sonnet-4-6` / `claude-haiku-4-5`.

**H3 — Language-model Settings menu + per-provider keychain + capability flags.**
*Depends on:* H2, D2, E6. *Files:* Settings UI (single-select + model dropdown +
Test connection), keychain per provider, `model_config.json` seeding, fine-tune
control gated to OpenAI, egress ledger tagged by provider. *Do:* switching a
provider re-inits via the graceful restart (D1). *Done when:* the §11 acceptance
battery passes — None ⇒ symbolic-only; Anthropic/Local select and work; fine-tune
enabled only under OpenAI; switching never needs a manual restart.

## Group I — Freeze & ship *(Phases 5–6 — do last, after C3 + H are stable)*

**I1 — Embedded CPython runtime for sandbox + self-code (§10.2).**
*Depends on:* C3. *Files:* sandbox runner, self-code loader, bundle layout
(`Resources/python/`). *Do:* point the sandboxed-code runner and the §10.1 loader
at a private embedded interpreter (not `sys.executable`, not system Python),
keeping the timeout guard; document that the heavy ML stack lives only in the host.
*Done when:* on a machine with no Python, a sandboxed snippet and a self-written
function both run via the bundled interpreter; the timeout still fires.

**I2 — Pre-bundle ML weights for offline first-run (Part 4).**
*Depends on:* nothing (can run early). *Files:* model-fetch/bundle step, env wiring
(`HF_HOME`, `SENTENCE_TRANSFORMERS_HOME`, explicit spaCy `en_core_web_sm` path).
*Do:* ship the sentence-transformers + spaCy weights in `Resources/models/` and
point the libraries at them so zero network is needed at boot. *Done when:* on a
machine that never had Python, **Wi-Fi off**, Orrin boots, thinks, and renders.

**I3 — PyInstaller freeze (the torch fight), macOS first.**
*Depends on:* A–H stable, I1, I2. *Files:* spec file, hooks, hidden-imports, binary
data collection. *Do:* freeze the host process with torch/spacy/sentence-
transformers + pywebview; verify bundled `custom_cognition` imports survive
(§13.4). *Done when:* `Orrin.app` runs on a clean macOS with no dev tools.

**I4 — macOS .dmg, notarize, entitlements + permissions onboarding (§10.6).**
*Depends on:* I3. *Files:* `.dmg` packaging, hardened-runtime entitlements,
`Info.plist` usage strings (Orrin's voice), a permissions onboarding step folded
into First Wake, Trust-screen grant state + deep links, graceful degradation when
denied. *Done when:* a signed/notarized install takes a screenshot and opens an
allow-listed app *after* the user grants; denied ⇒ "off," not a crash.

**I5 — Windows installer + WebView2 bootstrapper + signing.**
*Depends on:* A–H stable, I1, I2 (Windows build). *Do:* Inno/NSIS installer, bundle
the WebView2 bootstrapper, code-sign to clear SmartScreen. *Done when:* `Orrin.exe`
installs and runs on a clean Win10/11 with no dev tools and no SmartScreen block.

**I6 — Linux AppImage/.deb + WebKitGTK.**
*Depends on:* A–H stable, I1, I2 (Linux build). *Do:* AppImage (+ optional `.deb`),
document the WebKitGTK requirement. *Done when:* the AppImage runs on a clean Linux
desktop.

**I7 — Auto-update per platform, wired to the schema spine (§10.7).**
*Depends on:* G1, I4/I5/I6. *Do:* Sparkle (macOS) / Squirrel|MSIX (Windows) /
zsync (Linux); every update auto-exports the mind first and respects the existence
mode (don't kill an Always-thinking Orrin mid-thought). *Done when:* N→N+1 carries
an aged mind forward (backed up first); a breaking bump offers "keep old + start
fresh," never a silent destroy.

### 14.1 Recommended build order (condensed)

1. **A1 → A2** (native shell) ‖ **B1** (transport refactor, parallel)
2. **B2** (bridge) → **E1** (Cognition view — the demo)
3. **C1** (fix split-brain) → **C2 → C3** (per-user state, self-code)
4. **D1 → D2** (settings/keys) → **E2** then **E3–E5** product rooms
5. **E6 → E7 → E8 → E9 → E10** (trust, backup, wake, timeline, first wake)
6. **F1 → F2** (existence + death) ‖ **G1** (schema spine) ‖ **H1→H2→H3** (providers)
7. **I2** (weights, anytime) → **I1 → I3** → **I4 / I5 / I6** → **I7** (ship)

Chunks within the same numbered step are independent; across steps, respect the
`depends on` lines. Total: **~31 chunks**, each a single high-quality session.
