# Orrin UI — Improvement Audit

A focused list of where the `orrin-ui` frontend (Vite + React + TypeScript + Tailwind)
**needs to improve**. Orrin is a cognitive architecture modeled on the human mind — it
perceives, reflects, plans, and acts in a continuous loop — and this UI is the window into
that mind. The two priorities driving this audit are **visibility** (can a person actually
see what the mind is doing?) and **customization** (can they shape the view to their needs?).

This document reads two ways:

- **🟢 Plain-English** — what's wrong and why it matters, no coding knowledge required.
- **🔵 Under the hood** — the exact file, line, and fix for engineers.

A new-features section at the end proposes ways to make the program clearer, more
customizable, and better looking — designed around the fact that this is a *mind*, not a
generic dashboard.

---

## How to read this report

| Tag | Meaning |
|-----|---------|
| 🟢 **In plain English** | A no-jargon explanation of the issue and why it matters. |
| 🔵 **Under the hood** | The technical detail: file, line numbers, and the fix. |
| 🔴 **Severity: High** | Can cause bugs, crashes, security exposure, or user-visible breakage. |
| 🟠 **Severity: Medium** | Hurts maintainability, performance, or polish; not breaking today. |
| 🟡 **Severity: Low** | Cleanup, consistency, nice-to-have. |

---

## Audit accuracy review (independent re-verification, 2026-06-07)

Every finding below was re-checked against the live tree (`frontend/src/`) and the
type checker. **The audit is accurate**: H1–H3, M1–M5, and L1–L5 all reproduce —
dead-code (`CognitiveGraph` 128L + `CognitiveMap` 429L, zero importers, sole
`reactflow` consumers), the missing `VITE_TELEMETRY_DEMO_FALLBACK` type, the
unauthenticated `Header.tsx:74` shutdown `POST` under `host:true/allowedHosts:true`,
the `MetricsStrip.tsx:452` end-label index bug, the duplicate `hover`/`active`
label branches (`CognitiveSphere.tsx:304–305`), and the `apiBase()`/`fmtTime`
duplications all confirmed. `tsc --noEmit` exits 0 as claimed.

Three minor corrections for precision:

| # | Audit text | Correction |
|---|-----------|-----------|
| 1 | "all **24** source files in `src/`" | There are **25** (`.ts`/`.tsx`). |
| 2 | L1 lists `GoalDrawer`/`MemoryDrawer` like sibling files | They are **inline** components inside `GoalsPanel.tsx:198` and `MemoryInspector.tsx:74`. The a11y point still stands. |
| 3 | L2 fix: "make `active` label the live node" | Already half-done — `CognitiveSphere.tsx:303` `if (isActive) return true` always labels the running node; the real defect is only that the **`hover` vs `active` *modes*** are indistinguishable. Fix is to differentiate the two `settings.labels` branches, not to add running-node labeling. |
| 4 | H1: "`reactflow` (~3.8 MB installed) … gets downloaded and bundled for every visitor" | The *installed tree* is ~4.6 MB (`@reactflow` 3.2M + `zustand` 708K + `d3-*` ~524K; the `reactflow` meta-package is 212K) — so the figure is roughly fair, **but installed ≠ bundled**: the shipped (tree-shaken, gzipped) cost is far smaller. H1's deletion is still correct; the stronger reason is **dead code**, not download weight. |

---

## 🔴 High-severity findings

### H1 — Two large components are dead code, and they drag a heavy library with them

🟢 **In plain English**

Two big files — a "Cognitive Graph" and a "Cognitive Map" — are used by nothing. They're
furniture in a room nobody enters. Worse, they're the *only* things using a sizable
charting library called `reactflow`, which still gets downloaded and bundled for every
visitor even though it's never shown. Deleting the two files lets you remove the library
too, making the app smaller and faster to load.

🔵 **Under the hood**

- `src/components/brain/CognitiveGraph.tsx` (128 lines) and `src/components/brain/CognitiveMap.tsx` (429 lines) have **no importers** anywhere in `src` (only `CognitiveSphere` is wired into `Brain.tsx`).
- These two files are the **sole consumers** of `reactflow` (~3.8 MB installed). The dependency, its `.react-flow__*` CSS rules in `index.css` (lines 114–119), and the `reactflow` entry in `package.json` can all go.
- **Fix:** delete both files, remove `reactflow` from `dependencies`, drop the React Flow CSS block, then re-run `npm run build` to confirm nothing else referenced them. *(See feature F9 — this capability is worth repurposing, not just discarding.)*

---

### H2 — A typo-able env var has no type definition, so mistakes fail silently

🟢 **In plain English**

The app has an "off switch" for a demo mode, controlled by a setting named
`VITE_TELEMETRY_DEMO_FALLBACK`. Every other setting like it is written down in a central
list so a misspelling gets flagged by the editor. This one was never added — so a typo
quietly does nothing, and you're left wondering why the feature didn't turn on.

🔵 **Under the hood**

- `App.tsx:24` reads `import.meta.env.VITE_TELEMETRY_DEMO_FALLBACK`, but `src/vite-env.d.ts` (lines 3–9) declares only `VITE_TELEMETRY_WS`, `VITE_TELEMETRY_HOST`, `VITE_TELEMETRY_DEMO`, `VITE_CHAT_URL`, and `VITE_API_URL`.
- Access goes through an `as string | undefined` cast, so TypeScript can't catch a misspelling here or at any future call site.
- **Fix:** add `readonly VITE_TELEMETRY_DEMO_FALLBACK?: string;` to the `ImportMetaEnv` interface, and document it in `.env.example` (it's mentioned only in an `App.tsx` comment).

---

### H3 — The "Stop Orrin" button can be triggered by anyone who can open the page

🟢 **In plain English**

There's a red **Stop** button that shuts down the entire system — the brain loop,
background services, and server. It asks "are you sure?" first, but the request it sends
carries no proof of *who* clicked it. If this UI is ever reachable beyond your own laptop
(a shared network, a tunnel, a demo link), anyone who loads the page could shut everything
down. The config already enables network exposure (`host: true`, `allowedHosts: true`),
so this is worth locking down.

🔵 **Under the hood**

- `Header.tsx:74` fires `POST ${apiBase()}/api/control/shutdown` with no auth token, no CSRF protection, and no origin check.
- `vite.config.ts` sets `server.host: true` and `server.allowedHosts: true`, exposing the dev server to LAN/tunnel traffic.
- A destructive, unauthenticated control endpoint reachable over the network is the classic CSRF / unprotected-admin-action pattern.
- **Fix (frontend side):** gate the control surface behind a shared secret/header the backend validates, and confirm the backend rejects cross-origin requests. At minimum, document that this UI must not be exposed publicly while the shutdown route is unauthenticated.

---

## 🟠 Medium-severity findings

### M1 — The metrics chart's end-of-line labels can disappear after filtering

🟢 **In plain English**

On the Brain dashboard, each line in the metrics graph should have its name floating at the
right-hand tip. The code finds that tip using the *unfiltered* data length, but the chart
can drop empty points along the way. When that happens the label condition never matches the
real last point, so the label vanishes — confusing when several lines share the screen. This
directly hurts **visibility**: you can't tell which line is which.

🔵 **Under the hood**

- `MetricsStrip.tsx:452` returns `null` unless `p.index === data.length - 1`. With `connectNulls` and sparse series (some metrics missing in early history points), the rendered index of the last *defined* point for a series may not equal `data.length - 1`.
- **Fix:** compute a `lastDefinedIndex` per `dataKey` from `data` and compare against that, not the global array length.

---

### M2 — Each Brain panel polls the backend on its own timer (thundering herd)

🟢 **In plain English**

Several panels each independently ask the server for fresh data every few seconds — goals
every 3s, function history every 3s, the function catalogue retries every 2s, plus on-demand
metric/code/source fetches. They don't coordinate. On a slow backend this is a lot of
overlapping chatter, and it duplicates work the single live connection already does.

🔵 **Under the hood**

- Independent `setInterval` pollers: `GoalsPanel.tsx:65` (3s), `CognitiveSphere.tsx` history loader `:524` (3s) and catalog retry `:734` (2s, up to 30 tries), plus per-open fetches in `MetricsStrip` (`/source`), `MemoryInspector` (`/source`), and `FnDetailDrawer` (`/code`).
- No shared fetch layer, cache, or in-flight de-duplication; remounting a panel re-issues its requests.
- **Fix:** add a small shared query/cache layer (even a hand-rolled `fetchJSON` with a TTL cache keyed by URL) or push more of this data over the existing telemetry WebSocket so the polling can retire.

---

### M3 — Two UI primitives are built but never used

🟢 **In plain English**

Two reusable building blocks — an `Input` box and a `Separator` line — exist in the toolkit
but aren't used anywhere (the app uses raw `<input>`/`<textarea>` directly). Dead weight, and
a small inconsistency: some inputs go through the toolkit, others don't.

🔵 **Under the hood**

- `src/components/ui/input.tsx` and `src/components/ui/separator.tsx` have no importers outside their own files. `Face.tsx`, `MemoryInspector.tsx`, and `CognitiveSphere.tsx` use bare `<input>`/`<textarea>` with ad-hoc class strings.
- **Fix:** adopt `Input` consistently (gains the shared focus-ring styling) or remove the unused primitives. Pick one direction.

---

### M4 — `localStorage` logic is scattered and runs during render

🟢 **In plain English**

The app remembers your preferences (selected metrics, chat history, sphere settings) in the
browser's local storage. The reading is duplicated across many places, each with its own
error handling, and one reader runs as the component first draws — which can briefly flicker
and makes private/incognito modes a recurring thing to handle by hand. Because customization
*depends* on this storage working reliably, it deserves one solid implementation.

🔵 **Under the hood**

- Storage logic is duplicated across `Face.tsx` (`loadStoredMessages`), `MetricsStrip.tsx` (`loadSelected`, `VAL_KEY`), and `CognitiveSphere.tsx` (`loadSettings`), each with its own try/catch and key constant.
- `MetricsStrip.tsx:254` reads `localStorage.getItem(VAL_KEY)` in a `useState` initializer (render phase).
- **Fix:** extract one typed `useLocalStorage<T>(key, default)` hook in `lib/` and route all three through it.

---

### M5 — Customization doesn't survive a device change, and there's no reset

🟢 **In plain English**

All the personalization — which metrics you chart, which subsystems you hide on the sphere,
your sort order — lives only in *this* browser. Switch laptops and it's all gone. There's
also no single "reset to defaults" button, so a user who buries themselves in toggles has no
clean way out. For a tool built around customization, the customization itself is fragile.

🔵 **Under the hood**

- Settings persist via `localStorage` keys (`orrin.sphere.v2`, `orrin.metrics.selected`, `orrin.metrics.showValues`, `orrin.chat.history.v1`) — device-local only, no sync, no export.
- `CognitiveSphere` has `DEFAULTS` but no UI affordance to restore them; `MetricsStrip` has no reset.
- **Fix:** add a per-panel "Reset to defaults" action, and consider a settings export/import (JSON) or backend-persisted profile so preferences follow the user.

---

## 🟡 Low-severity findings (visibility & consistency)

### L1 — Accessibility: icon-only buttons and custom popovers are invisible to assistive tech

🟢 **In plain English**

Many small buttons show only an icon (a gear, a chevron, an "i"). Sighted users get it, but a
screen reader may just say "button." The custom dropdown menus and slide-out drawers also
don't announce themselves as menus/dialogs or trap keyboard focus, so keyboard-only users can
tab "behind" an open panel. This is **visibility for the people who need it most.**

🔵 **Under the hood**

- Gaps: the Customize/Metrics/zoom/legend buttons in `CognitiveSphere.tsx` and the section-collapse buttons in `GoalsPanel.tsx` rely on `title` only (not a reliable accessible name). Drawers (`FnDetailDrawer`, `GoalDrawer`, `MemoryDrawer`) lack `role="dialog"`/`aria-modal` and focus trapping.
- **Fix:** add `aria-label` to every icon-only control; add `role="dialog" aria-modal="true"` + focus management to drawers; mark custom dropdowns with `role="menu"`/`aria-expanded`.

### L2 — The "Labels" setting has two options that do the same thing

🟢 **In plain English**

In the 3D sphere's customize panel, the label mode offers "Hover" and "Active" as separate
choices — but they behave identically. A user who picks "Active" expecting different behavior
gets the same result, which feels broken. A customization control that lies about its options
undermines trust in the rest of them.

🔵 **Under the hood**

- `CognitiveSphere.tsx:304–305`: the `"hover"` and `"active"` branches of `showLabel` return the identical expression (`name === hovered || name === focusNode`). The intended distinction (`"active"` = always label the running node) isn't implemented.
- **Fix:** make `"active"` label the live `activeFn` regardless of hover, or remove the redundant option from the `Seg` at line 440.

### L3 — `App.tsx` toggles the global `dark` class but never cleans it up

🔵 **Under the hood** — `App.tsx:28–31` does `root.classList.toggle("dark", isBrain)` in an
effect with no cleanup. Harmless today (App is the root), but it's a global side effect worth
a one-line comment, and a landmine if the layout is ever embedded or reused.

### L4 — Duplicated helpers (`apiBase()`, `fmtTime()`) will drift apart

🔵 **Under the hood** — `apiBase()` is defined identically in `Header.tsx:14` and `Face.tsx:17`,
while `lib/cognitive.ts` separately exports `API` (three spellings of one idea). A second,
*different* `fmtTime` lives in `GoalsPanel.tsx:9` alongside the one in `lib/utils.ts` — a
confusing name collision. **Fix:** export one `apiBase()`/`API` from `lib/cognitive.ts`;
rename the GoalsPanel formatter to `fmtDateTime`.

### L5 — No error UI when the 3D canvas fails

🟢 **In plain English** — If the 3D sphere can't start (older GPU, WebGL disabled), the panel
could just go blank with no explanation. A "couldn't render 3D view" notice keeps the
dashboard feeling intentional rather than broken.

🔵 **Under the hood** — `CognitiveSphere.tsx` renders `<Canvas>` with no error boundary; a
thrown WebGL/three error bubbles up. There's a "waiting for catalog" state (`:838`) but no
"WebGL unavailable" path. **Fix:** wrap `<Canvas>` in an error boundary with a 2D fallback.

---

## Suggested order of work

| # | Finding | Effort | Why now |
|---|---------|--------|---------|
| 1 | **H1** delete dead components + drop `reactflow` | 30 min | Smaller bundle, faster load, less to maintain |
| 2 | **H2** add missing env-var type + doc | 5 min | Prevents silent config typos |
| 3 | **H3** harden / document the shutdown endpoint | varies | Closes a real security gap |
| 4 | **M1** fix chart end-label index logic | 20 min | Restores chart legibility (visibility) |
| 5 | **L2** fix duplicate label-mode behavior | 10 min | Removes a "looks broken" papercut |
| 6 | **M5** reset-to-defaults + settings export | half-day | Makes customization durable |
| 7 | **M3 / L4** remove unused primitives, unify helpers | 30 min | Consistency |
| 8 | **L1** accessibility pass on buttons + drawers | half-day | Visibility for keyboard/screen-reader users |
| 9 | **M2 / M4** shared fetch + `useLocalStorage` | half-day | Cleaner data + storage foundation |

---

# Proposed new features

Forward-looking additions aimed squarely at **visibility**, **customization**, and
**look-and-feel** — leaning into the premise that Orrin is a *mind*, similar to the human
brain. Grouped by theme; each notes the rough lift and which existing panel it builds on.

## A. See the mind think (visibility)

### F1 — "Train of thought" timeline / replay scrubber
🟢 A horizontal timeline along the bottom of the Brain view that records each cognitive cycle
(perceive → reflect → plan → act) as a bead. Drag the scrubber backward and the whole
dashboard — sphere, affect rings, metrics, active goal — rewinds to that moment. It turns a
live-only stream into something you can *study*: "what was he feeling right before he changed
plans?" This is the single biggest visibility upgrade.
🔵 Buffer recent snapshots client-side (extend the `metricSeries` capping logic in
`telemetry.ts`) or pull from the backend `/history` already used in `CognitiveSphere`. New
`TimelineScrubber` component feeds a "frozen snapshot" into the existing telemetry context.

### F2 — Affect "weather" — an at-a-glance emotional state
🟢 The mind has a mood. Surface it as a single ambient indicator: a soft color field or
animated gradient in the header that shifts with valence/arousal (calm blue ↔ agitated red,
low-energy dim ↔ high-arousal bright). A glance tells you his state before you read a single
number — the way a human face broadcasts mood.
🔵 Derive from `telemetry.affect` (already in context). Map valence→hue, arousal→saturation/
motion. Pure CSS/SVG; reuse the `moodWord` logic in `NarrativeStatusCard.tsx`.

### F3 — Attention spotlight on the sphere
🟢 When a function fires, briefly trace the *path* of attention across the sphere — like
watching a thought travel between brain regions. Extend the existing traveling-light into a
fading trail of the last several hops so you can see the *shape* of a thought, not just the
current dot.
🔵 Extend `TravelingLight` in `CognitiveSphere.tsx` to render a decaying poly-line over the
last N `fnRecent` events with per-segment opacity falloff.

### F4 — "Why did he do that?" causal inspector
🟢 Click any action in the log or any fired function and get a plain-language chain: *this goal
→ raised this drive → selected this function → produced this memory write.* The data already
flows through telemetry; the feature is the connective tissue that makes the mind's reasoning
legible.
🔵 Correlate `fnRecent`, active `goals`, `memory` writes, and `metric_point` by `cycle`/`ts`.
New `CausalTrace` drawer; backend may need a per-cycle "decision record" endpoint.

## B. Shape the view (customization)

### F5 — Draggable, resizable dashboard layout
🟢 Let users rearrange and resize panels — make the sphere huge, tuck goals into a corner,
hide the console. Different people watch different things; the layout should bend to them. Save
named layouts ("debugging view," "calm overview").
🔵 Replace the fixed grid in `Brain.tsx` with a layout engine (a lightweight grid-layout lib,
or CSS grid + persisted track sizes). Store layouts via the `useLocalStorage` hook from **M4**,
with the export/import from **M5**.

### F6 — Custom metric dashboards & derived signals
🟢 The metrics picker already lets you choose which signals to chart. Go further: let users
build *their own* composite signals (e.g. "stress = distress × (1 − stability)") and save
custom chart groupings. A researcher studying one behavior shouldn't wade through ten unrelated
lines.
🔵 Extend `METRICS` in `MetricsStrip.tsx` to support user-defined entries with a small safe
expression evaluator over the per-point fields. Persist alongside `orrin.metrics.selected`.

### F7 — Theme & density controls
🟢 Beyond the automatic Face-light / Brain-dark split, offer accent-color themes and a
compact/comfortable density toggle. The design system is already token-based, so this is mostly
exposing what's there. Small touch, big sense of ownership.
🔵 The CSS variables in `index.css` (`--signal-*`, `--radius`) are the seam. Add a theme picker
that overrides the `:root`/`.dark` token values at runtime; persist via `useLocalStorage`.

## C. Make it feel like a mind (look & usability)

### F8 — Narrative "stream of consciousness" view on the Face
🟢 The Face currently shows one calm status line. Offer an optional flowing log of Orrin's
inner narration — short, human sentences as thoughts arrive — so a non-technical visitor *feels*
a mind at work rather than reading a dashboard. The calm summary stays the default; this is an
expandable "let me see him think" affordance.
🔵 Append `narrative` deltas (already in `telemetry`) to a capped client list; render as a
soft, auto-scrolling feed below `NarrativeStatusCard.tsx`, reusing the throttle pattern from
`LiveConsole.tsx`.

### F9 — Memory graph view (episodic ↔ semantic links)
🟢 The Memory Inspector is a table. Add an optional graph view that shows memories as nodes and
their associations as links — the way human memory is a web, not a list. Recent/salient memories
glow; old ones fade. Reinforces the "this is a mind" feeling and makes recall patterns visible.
🔵 This is the *right* home for the soon-to-be-deleted `reactflow` (**H1**) — repurpose that
capability here instead of discarding it, if a force-directed memory graph is on the roadmap.
Drive from `telemetry.memory` plus a backend associations endpoint.

### F10 — Onboarding "guided tour" of the mind
🟢 First-time visitors face a dense console with no map. A dismissible guided tour ("this sphere
is his functions; this ring is his mood; click any node to see the real code") makes the deep
end approachable without dumbing it down — exactly the "understand it whether or not you know
code" goal.
🔵 A lightweight step-driven overlay keyed to element refs; gate on a `localStorage` "seen" flag
via the **M4** hook.

### F11 — Live alerting / anomaly highlights
🟢 Let the mind get your attention: when distress spikes, a goal fails, or an error hits the
console, surface a gentle, dismissible alert (and optionally flash the relevant panel). Right
now important moments scroll by unnoticed. Like a body's pain signal — it should be *felt*, not
buried in a log.
🔵 Thresholds over `telemetry.metrics`/`logs`; a small toast system + per-panel highlight state.
User-configurable thresholds tie back into the customization theme (**F6**).

### Feature priority snapshot

| Feature | Theme | Lift | Impact |
|---------|-------|------|--------|
| **F1** Timeline / replay | Visibility | High | ★★★★★ |
| **F2** Affect "weather" | Visibility / look | Low | ★★★★ |
| **F5** Draggable layout | Customization | Med | ★★★★ |
| **F8** Stream of consciousness | Look / usability | Low | ★★★★ |
| **F4** Causal inspector | Visibility | High | ★★★★ |
| **F9** Memory graph | Visibility / look | Med | ★★★ |
| **F10** Guided tour | Usability | Low | ★★★ |
| **F3** Attention trail | Look | Low | ★★★ |
| **F6** Custom signals | Customization | Med | ★★★ |
| **F11** Alerts | Visibility / usability | Med | ★★★ |
| **F7** Theme/density | Customization / look | Low | ★★ |

---

# Feature Implementation Plans

> The section above describes *what* to build. This section is the engineering
> plan for *how* — written to be buildable by any competent engineer without
> further discovery. It is deliberately opinionated: it resequences the work
> around a dependency graph the feature summaries don't expose, names the shared
> substrate the headline features secretly share, and pins down every data
> contract, performance budget, and failure mode. No code is written here.

## 0. North Star — "an instrument for a mind, not a dashboard"

Orrin is a continuous perceive → reflect → plan → act loop. The interface should
read like the cockpit of that loop: **calm at rest, expressive under load, always
legible.** Three principles govern every feature below:

1. **The view is a pure function of a frame.** A "frame" is one immutable snapshot
   of the mind at a cycle. Live mode renders the latest frame; replay renders a
   past one. Once the UI obeys this, timeline, alerts, and causal tracing stop
   being special cases.
2. **Motion is meaning, never decoration.** Every animation encodes a real signal
   (a thought moving, a mood shifting). All of it degrades to a static, equally
   legible state under `prefers-reduced-motion`.
3. **Customization is durable and reversible.** Anything a user can change, they
   can reset, export, and carry to another device.

### Design language (the "science-fiction, but honest" look)

| Token | Source of truth | Use |
|-------|-----------------|-----|
| Signal palette | `index.css` `--signal-ok/warn/error` (HSL triples) | Every status color derives from these — never hard-coded hex |
| Affect hue field | `telemetry.affect.valence → hue`, `arousal → saturation/motion` | Mood-driven ambient color (F2), reused by alerts (F11) |
| Radius / density | `--radius` + a new `--density` scale | One knob drives compact/comfortable (F7) |
| Motion tier | new `--motion: full | reduced` resolved from media query | Single global switch every animated feature reads |

Visual identity: deep-space charcoal (`#0a0d14`, already the sphere `fog`),
signal-colored accents, thin luminous strokes, generous negative space, type that
stays AA-contrast on every mood background. **Pretty is a constraint, not a
trade-off: no effect ships if it lowers text contrast below WCAG AA.**

---

## 1. Foundation layer (Phase 0) — the substrate the headline features share

The single most important engineering insight in this plan: **F1, F4, F5, F6,
F7, F10, and F11 are not independent.** They share four primitives that don't
exist yet. Building these first turns most "High" features into "Medium," and
skipping them means re-implementing the same plumbing four times.

### F0.1 — Unified telemetry store + snapshot ring (`MindFrame`)
- **What:** Normalize the WebSocket stream into one immutable `MindFrame`
  `{ cycle, ts, affect, goals, fnRecent, metricsTail, memoryTail, narrative, activeFn, activeNode }`
  — every field is verified to exist on `TelemetryState` today; `activeNode` is the
  perceive→reflect→plan→act stage (`LOOP_NODES` in `lib/types.ts`), and `ts` falls
  back to the existing `updatedAt` when the backend sends no per-cycle timestamp.
- **Key constraint:** only `metricSeries` is *currently* historical (capped at
  `SERIES_CAP = 240`, `telemetry.ts:9/52`); `affect`/`goals`/`activeFn`/`narrative`
  are **overwritten on each delta**. So the ring must be built by **sampling** the
  live state into frames here — it cannot be reconstructed from existing state.
- **Capacity:** a fixed-size ring (e.g. 512 frames). Its wall-clock window depends
  on the telemetry **push cadence** (not assumed here); size it in frames, surface
  the covered time range in the UI rather than hard-coding minutes.
- **Why first:** It is the literal definition of "the view is a function of a
  frame." F1 (replay), F4 (causal), F11 (alerts), F3 (trail) all read from it.
- **Anchors:** `lib/telemetry.ts` (`metricSeries`, `LOG_CAP`, `SERIES_CAP`, `applyDelta`).
- **Effort:** Med. **Risk:** memory growth → fixed-capacity ring + structural
  sharing, never deep-clone on the hot path.

### F0.2 — `useLocalStorage<T>` + versioned settings envelope
- **What:** One typed hook (resolves **M4**). All preferences move under a single
  versioned envelope `orrin.settings.v3 = { version, sphere, metrics, chat, layout, theme }`
  with a migration map, plus `exportSettings()/importSettings()/resetSettings()`
  (resolves **M5**).
- **Why first:** F5/F6/F7/F10 all persist user state; without a versioned schema
  the first settings change strands users on stale shapes.
- **Anchors:** the scattered keys in `Face.tsx`, `MetricsStrip.tsx` (`VAL_KEY`),
  `CognitiveSphere.tsx` (`orrin.sphere.v2`).
- **Effort:** Med. **Risk:** migration bugs → keep migrations pure + unit-tested,
  fail safe to defaults.

### F0.3 — Shared `fetchJSON` (TTL cache + in-flight de-dup)
- **What:** A tiny request layer keyed by URL with a short TTL and request
  coalescing (resolves **M2**). Retire the independent timers: the `setInterval`
  pollers (`GoalsPanel.tsx:65` 3s; `CognitiveSphere.tsx:524` 3s, history tab) and
  the bounded `setTimeout` catalog retry (`CognitiveSphere.tsx:~734`, 2s × ≤30).
- **Why:** removes the thundering-herd; gives F4/F9 a clean backend read path.
- **Effort:** Low–Med. **Risk:** stale reads → TTL tuned per route; prefer pushing
  data over the existing WS where possible.

### F0.4 — Theme token + motion-policy layer
- **What:** Runtime overrides of `:root`/`.dark` CSS variables (the F7 seam) plus a
  single `--motion` resolved from `prefers-reduced-motion` that every animated
  feature reads.
- **Effort:** Low. **Risk:** none material; it's CSS-variable plumbing.

> **Dependency DAG**
> ```
> F0.1 (frame store) ─┬─► F1 replay ─┬─► F11 alerts
>                     ├─► F4 causal*  └─► F3 trail
>                     └─► F11 alerts
> F0.2 (settings)   ──┬─► F5 layout ──► F6 custom signals
>                     ├─► F7 theme/density
>                     └─► F10 guided tour
> F0.3 (fetch)      ──┬─► F4 causal*   └─► F9 memory graph*
> backend endpoints ──┴─► F4*, F9*     (*) blocked on backend work
> ```

---

## 2. Per-feature plans

Each card uses the same fields. "Anchors" are verified to exist in the tree today.

### F1 — Train-of-thought timeline / replay scrubber  ·  ★★★★★  ·  High
- **Intent:** Turn a live-only stream into something studyable: scrub back and the
  whole board rewinds to that cycle.
- **Data:** `F0.1` frame ring is the source of truth for full-board rewind. The
  backend `/history?n=120` consumed in `CognitiveSphere.tsx:519` returns only
  **function-activation records** (`d.events` of `{fn, reward, agentic, ts}`) — it
  can seed the timeline's *beads*, but **not** affect/goals/metrics, so it cannot
  drive a whole-board rewind on its own. Durable/long replay beyond the in-memory
  ring would need a new backend snapshot endpoint (see C3).
- **Architecture:** New `TimelineScrubber` writes a `cursor` (null = live) into the
  telemetry context. Panels switch from `useFrame()` to `useFrameAt(cursor)`. A
  "LIVE / REPLAY" mode chip; auto-return to live on new frame unless pinned.
- **Visual/motion:** A luminous bead per cycle along the base of the Brain view;
  stage-colored (perceive/reflect/plan/act); density-aware; reduced-motion = instant
  jumps, no easing.
- **Effort:** High (see critique C1 — the real cost is *panel purity*).
- **Dependencies:** **F0.1** hard; benefits from **F0.2** (pin/bookmark cycles).
- **Risks:** panels with local fetch/state won't rewind. **Mitigation:** ship an
  MVP that freezes the *store* (single source) before refactoring every panel.
- **Acceptance:** scrub to cycle N → sphere/affect/metrics/goal all show cycle N's
  values; releasing returns to live within one frame.

### F2 — Affect "weather" ambient state  ·  ★★★★  ·  Low
- **Intent:** Broadcast mood at a glance, the way a face does.
- **Data:** `telemetry.affect` (live today); `moodWord()` exists at
  `NarrativeStatusCard.tsx:73`.
- **Architecture:** A header-wide CSS field; `valence→--mood-hue`,
  `arousal→--mood-sat`/animation speed. Pure CSS variables driven from one effect.
- **Visual/motion:** slow gradient drift; reduced-motion = solid tint. **AA guard:**
  clamp saturation/lightness so header text stays ≥ 4.5:1.
- **Effort:** Low. **Dependencies:** **F0.4** (motion policy). **Risk:** contrast —
  mitigated by the clamp. **Acceptance:** mood visibly tracks affect; contrast holds.

### F3 — Attention trail on the sphere  ·  ★★★  ·  Low
- **Intent:** See the *shape* of a thought, not just the current dot.
- **Data:** `fnRecent` events (already in context; `TravelingLight` at
  `CognitiveSphere.tsx:163`).
- **Architecture:** Extend `TravelingLight` to a decaying poly-line over the last
  N=8 hops, one `BufferGeometry`, per-vertex opacity falloff.
- **Effort:** Low. **Dependencies:** none (F0.1 optional). **Risk:** GPU/alloc
  churn → preallocate buffers, update in place, cap N. Reduced-motion = current dot
  only. **Acceptance:** 60fps maintained (measure with a frame meter).

### F4 — "Why did he do that?" causal inspector  ·  ★★★★  ·  High · backend-blocked
- **Intent:** Plain-language chain: goal → drive → function → memory write.
- **Data:** correlate `fnRecent`, `goals`, `memory`, `metric_point` by `cycle`/`ts`
  (frame store **F0.1**). **Authoritative version needs a backend decision record.**
- **Backend contract (to request):**
  `GET /api/cycles/:id/decision → { cycle, ts, goal, drives[], selected_fn, reward, memory_writes[] }`.
- **Architecture:** `CausalTrace` drawer; MVP = client-side correlation from the
  frame; v2 = backend record for ground truth.
- **Effort:** High. **Dependencies:** **F0.1**, **F0.3**, backend. **Risk:**
  client correlation can mis-attribute across cycles → label MVP as "inferred,"
  gate "authoritative" on the endpoint. **Acceptance:** clicking a fired function
  shows its cycle's chain; inferred vs authoritative is explicit.

### F5 — Draggable, resizable, named layouts  ·  ★★★★  ·  Med
- **Intent:** Bend the board to each watcher; save "debugging" vs "calm overview."
- **Architecture:** Replace the fixed grid in `Brain.tsx` with a layout engine
  (CSS-grid track sizes persisted, or a small grid-layout lib). Named presets via
  **F0.2**; export/import via the same envelope.
- **Effort:** Med. **Dependencies:** **F0.2** hard. **Risk:** layout lib weight
  (don't reintroduce a heavy dep right after deleting `reactflow`) → prefer CSS
  grid + persisted sizes first. **Acceptance:** rearrange/resize persists; named
  layouts switch instantly; reset restores defaults.

### F6 — Custom metric dashboards & derived signals  ·  ★★★  ·  Med
- **Intent:** User-defined composites, e.g. `stress = distress × (1 − stability)`.
- **Data:** the `METRICS` table at `MetricsStrip.tsx:31`; per-point fields.
- **Architecture:** extend `METRICS` with user entries evaluated by a **safe
  expression parser** over whitelisted fields — **never `eval`/`Function`** (see
  critique C9). Persist beside `orrin.metrics.selected` via **F0.2**.
- **Effort:** Med. **Dependencies:** **F0.2**. **Risk:** injection/foot-gun →
  tiny AST-validated arithmetic grammar only (`+ - * / ( ) fields numbers`).
  **Acceptance:** a saved formula charts correctly and survives reload; malformed
  formulas fail gracefully with an inline message.

### F7 — Theme & density controls  ·  ★★  ·  Low
- **Intent:** Accent themes + compact/comfortable density; a sense of ownership.
- **Architecture:** **F0.4** token layer; a picker overrides `:root`/`.dark`
  values and a new `--density` scale at runtime; persisted via **F0.2**.
- **Effort:** Low. **Dependencies:** **F0.4**, **F0.2**. **Risk:** theme combos
  breaking contrast → ship a curated set, validate each for AA. **Acceptance:**
  theme/density switch instantly and persist; all presets pass AA.

### F8 — Stream-of-consciousness view on the Face  ·  ★★★★  ·  Low
- **Intent:** Let a non-technical visitor *feel* a mind at work.
- **Data:** `narrative` deltas (in telemetry); throttle pattern at `LiveConsole.tsx:38`.
- **Architecture:** capped, auto-scrolling feed below `NarrativeStatusCard.tsx`,
  opt-in ("let me see him think"); calm summary stays default.
- **Effort:** Low. **Dependencies:** none (F0.1 optional). **Risk:** scroll/flush
  cost → upgrade the throttle to a rAF-batched flush, cap the list, pause when the
  tab is hidden. **Acceptance:** thoughts stream smoothly; toggling back to calm
  is one click; no jank.

### F9 — Memory graph view (episodic ↔ semantic)  ·  ★★★  ·  Med · backend-blocked
- **Intent:** Show memory as a web, not a list; salient nodes glow, old fade.
- **Data:** `telemetry.memory` + a backend associations endpoint.
- **Backend contract (to request):**
  `GET /api/memory/associations → { nodes:[{id,kind,salience,ts}], edges:[{a,b,weight,type}] }`.
- **Architecture:** force-directed view as an optional mode in `MemoryInspector`.
  **Do not resurrect `reactflow`** (see C2) — pick a lightweight force-graph or a
  2D-canvas/three layout sized to the read-only use case.
- **Effort:** Med. **Dependencies:** **F0.3**, backend. **Risk:** graph perf at
  scale → cap visible nodes, cluster/decay old ones. **Acceptance:** associations
  render; salience maps to glow; pan/zoom stays smooth at the node cap.

### F10 — Onboarding guided tour  ·  ★★★  ·  Low
- **Intent:** Make the deep end approachable without dumbing it down.
- **Architecture:** step-driven overlay keyed to element refs; "seen" flag via
  **F0.2**. Steps: sphere = functions, ring = mood, node click = real code.
- **Effort:** Low. **Dependencies:** **F0.2**; best built *after* F2/F5 exist so it
  can point at them. **Risk:** ref drift if layout changes → key steps to stable
  `data-tour` attributes. **Acceptance:** first visit shows the tour once;
  dismissible; re-openable from help.

### F11 — Live alerting / anomaly highlights  ·  ★★★  ·  Med
- **Intent:** Let the mind get your attention — distress spike, goal failure, error.
- **Data:** thresholds over the frame store (**F0.1**) metrics/logs.
- **Architecture:** small toast system + per-panel highlight state; thresholds are
  user-configurable and tie into **F6**/**F0.2**.
- **Accessibility:** toasts use `role="status"` + `aria-live="polite"` (never
  `assertive` — avoid screen-reader spam). Reduced-motion = no flash, just the toast.
- **Effort:** Med. **Dependencies:** **F0.1**; thresholds via **F0.2**. **Risk:**
  alert fatigue → debounce, hysteresis on thresholds, max concurrent toasts.
  **Acceptance:** a synthetic distress spike raises exactly one dismissible alert
  and highlights the right panel.

---

## 3. Phased roadmap

| Phase | Goal | Items | Exit criteria |
|------:|------|-------|---------------|
| **0** | Substrate + audit hygiene | F0.1–F0.4, H1, H2, H3, M1, L2 | Frame store live; one settings envelope; pollers retired; shutdown gated |
| **1** | Visibility quick wins | F2, F3, F8 | Mood, trail, and thought-stream shipped; 60fps held; reduced-motion verified |
| **2** | Customization spine | F5, F7, F6 | Layouts/themes/custom signals persist, export, reset |
| **3** | Deep visibility | F1, F11 | Replay rewinds the board; alerts fire without fatigue |
| **4** | Backend-blocked + polish | F4, F9, F10 | Endpoints delivered; causal + memory graph authoritative; tour live |

---

## 4. Cross-cutting budgets (non-negotiable)

- **Performance:** sphere holds **60fps** with F3 active (measure, don't assume);
  F2 is GPU-composited CSS only (no JS per-frame); feeds (F8/console) flush on rAF
  and pause when `document.hidden`; the frame ring is fixed-capacity (~600).
- **Accessibility & motion:** every animated feature has a `prefers-reduced-motion`
  fallback that is *equally legible*; the timeline scrubber is a keyboard ARIA
  slider (←/→/Home/End); alerts are `aria-live="polite"`; this also closes **L1**.
- **State & persistence:** one versioned `orrin.settings.v3` envelope with pure,
  tested migrations; export/import/reset everywhere (closes **M5**).
- **Security:** **H3 must land in Phase 0.** No feature that widens the surface
  (notably F11, and any future write action) ships while the control endpoint is
  unauthenticated.
- **Bundle discipline:** net dependency weight should *fall* across this plan
  (delete `reactflow`); any new lib (F5 layout, F9 graph) must justify its KB and
  beat a hand-rolled CSS/canvas option.

---

## 5. Plan critique & risk register

A plan is only "engineering-perfect" if it states where it can go wrong.

- **C1 — F1 is under-scoped as a feature; it's an architecture change.** "Rewind
  the whole board" only works if every panel is a pure function of a frame. Today
  panels poll and hold local state. *Resolution:* F0.1 first; ship F1 as a
  store-freeze MVP (one source frozen) before refactoring each panel to
  `useFrameAt`. Do not promise full per-panel replay in v1.
- **C2 — H1 (delete `reactflow`) and F9 (repurpose `reactflow`) contradict.**
  *Resolution:* delete now, but for the **right reason**. Measured footprint is
  ~4.6 MB **installed** across the tree (`@reactflow` 3.2M + `zustand` 708K +
  `d3-zoom/drag/selection` ~524K; the `reactflow` meta-package itself is only
  212K) — so the audit's "3.8 MB installed" is approximately fair, *but installed
  size ≠ bundle size*: tree-shaking + gzip make the shipped cost far smaller than
  4.6 MB. The dominant rationale is therefore **dead code**, not bundle weight.
  And `reactflow` is a node-*editor* (drag/connect), the wrong tool for a
  read-only memory graph; when F9 lands, pick a lightweight force-graph or a
  canvas/three layout rather than re-adding it on spec for a Phase-4 maybe.
- **C3 — F4, F9, and *durable* F1 are backend-blocked.** They cannot be fully
  delivered from the frontend. *Resolution:* the contracts in §2 are the asks
  (decision record for F4, associations for F9, and — for replay beyond the
  in-memory ring — a per-cycle snapshot/`since=` history endpoint, since today's
  `/history` is fn-activation beads only). F4 ships an explicitly-labeled
  "inferred" MVP from the frame store; F1 ships live-ring replay first; F9 waits on
  associations.
- **C4 — Motion overload.** Weather + trail + streaming feed + toasts on a 3D page
  can become noise and a vestibular hazard. *Resolution:* the single `--motion`
  policy (F0.4), reduced-motion fallbacks, and a per-feature "calm by default,
  expressive on demand" stance.
- **C5 — Settings sprawl.** F5/F6/F7 multiply persisted state; without F0.2's
  versioned envelope the first schema change strands users. *Resolution:* F0.2 is a
  hard prerequisite for all three; migrations are tested.
- **C6 — F6's expression evaluator is a foot-gun.** A naive `eval`/`new Function`
  is an injection and stability risk even in a single-user tool. *Resolution:* a
  tiny AST-validated arithmetic grammar over whitelisted fields only.
- **C7 — "Pretty" can fight "legible."** Mood backgrounds and accent themes can
  push text below AA. *Resolution:* the contrast clamp (F2) and curated,
  AA-validated theme presets (F7) are acceptance criteria, not afterthoughts.
- **C8 — Performance regressions are invisible until measured.** F3 in WebGL and
  F8's feed are the likely culprits. *Resolution:* a frame meter during dev; the
  60fps budget is an acceptance gate, not a hope.
- **C9 — Single-viewer assumption.** Replay, layouts, and alerts assume one human
  watching one browser. Fine today; flagged for any future multi-viewer/shared
  session, which would need server-authoritative cursors and per-user settings.
- **C10 — The audit's "suggested order" optimizes findings, not features.** It
  front-loads cheap fixes but ignores the F0 dependency graph. *Resolution:* the
  Phase plan in §3 supersedes it for feature work; the audit's order still governs
  the standalone bug fixes (H/M/L).

> **Bottom line:** the headline experience (a mind you can *watch, rewind, and
> question*) is reachable, but only if the four foundations land first. Build the
> substrate, keep motion honest, gate on security and contrast, and the result is
> the rare thing that is both genuinely beautiful and genuinely correct.

---

## Methodology & scope

🔵 **Under the hood**

- **Reviewed:** all 25 source files in `src/`, plus `package.json`, `vite.config.ts`,
  `tsconfig.json`, `tailwind.config.js`, `index.css`, `index.html`, `.env.example`.
- **Verified mechanically:** ran `tsc --noEmit` (exit 0); grep-traced every component import
  to find dead code; mapped each dependency to its consumers; checked `aria-*`/`role` coverage.
- **Not in scope:** the backend (`server/schema.py`, the `/api/*` and `/ws` endpoints) — it's
  referenced but wasn't included. Runtime/visual browser testing was not performed; findings
  are from static review and the type checker.
- **Line numbers** refer to the files as audited and may shift after edits.
