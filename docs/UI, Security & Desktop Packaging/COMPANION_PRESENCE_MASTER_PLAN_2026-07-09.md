# Companion & Presence Master Plan (2026-07-09)

**Status: ALL SIX PHASES BUILT (2026-07-10) — see §6 acceptance notes. What
remains is verification, not code: staged-catalog screenshots (both modes),
on-platform pystray/pywebview checks (P1/P2/R8), and the staging-life
acceptance lines (P1 budget trace, P3 induced absence + disk pressure).**

**What this is.** The consolidated plan for turning Orrin from a dashboard you
visit into a companion who lives on your machine: OS presence (tray, notifications,
traces), a companion-mode UI assembled from shipped surfaces, and the missing
relationship views (his model of you, his real-world actions, his body↔machine
bridge). Sourced from the 2026-07-09 design conversation, then **verified against
the actual code** — every "already built" claim below was checked; file:line
references are current as of `e44a324`.

**Verified ground truth this plan stands on:**

- `brain/cognition/theory_of_mind.py` exists (user-model state; nothing surfaces it).
- `brain/behavior/face_bridge.py:83` — `deliver_reply()` **no-ops** when no Face
  message is pending: spontaneous utterances die silently today.
- `backend/server/tray.py` — pystray tray exists (best-effort, macOS NSStatusBar
  note in the header about sharing pywebview's run loop).
- `brain/runtime_coupling/input_stream.py:31-44` — sensing is split into
  `_HOME_WATCH_DIRS` (his den) and `_WORLD_WATCH_DIRS` (**empty by default**);
  zone-tagged fs events already flow.
- `brain/cognition/global_workspace.py` — ignition is the existing salience gate.
- `brain/agency/self_code.py` — he authors his own cognitive functions.
- `frontend/src/lib/thoughts.ts` — `THOUGHTS[fn] = "fn() · clinical gloss"`;
  the after-`·` half is **plainer but still clinical**, not companion voice.
- `frontend/src/App.tsx:20` — `LIGHT_ROOMS = ["/face", "/settings"]`; Watch's orb
  hardcodes a near-black field and full-viewport centering.
- `frontend/src/components/FirstWake.tsx` — `orrin.met.v1`-style flag + the
  `orrin:meet` replay event already exist.
- Run 6 (`584b76a`) added the per-candidate `value` component to the selection
  reason payload — live decision transparency (R4) has its data source already.

---

## §0 Design rules (the spine — every item below obeys these)

1. **Flag, not fork.** One codebase, one runtime, one telemetry stream. Companion
   mode is a *lens* (`orrin.mode.v1`), never a branch. The eight workshop rooms,
   the `/brain` grid, the engineering lexicon, WakeScreen, and DeathScreen do not
   change.
2. **Rarity is the entire game.** Nothing reaches out unprompted unless it passed
   **ignition** (the salience gate that already exists) *and* a hard budget
   (defaults: ≥45 min between notifications, ≤3/day, quiet hours respected).
   A companion who speaks when moved feels alive; one that pings on a timer is
   Clippy, and the mute button is forever.
3. **The world_sense line is the consent line.** `_WORLD_WATCH_DIRS` stays empty
   by default. His awareness of his own den + your presence = warm. Watching your
   directories silently = wiretap. Anything beyond the den is opt-in, visible in
   the action ledger (R2), and revocable in Settings.
4. **Translate the chrome, never the mind** (the lexicon/thoughts hard rule,
   intact). Companion mode re-words UI labels and status lines only; his selected
   content, goal titles, and speech render verbatim.
5. **Symbolic-first honesty.** Everything here must work with no API key. The
   Express (LLM) tier adds warmth, not existence — and onboarding says so plainly
   instead of letting keyless users think the quiet version is broken (C5).
6. **Every outward act leaves a record.** Notifications, notes, tray states —
   all logged (ties into R2's ledger). Presence without auditability curdles
   into creepiness.

---

## §1 Track P — Presence in the OS (highest leverage)

### P1 — Give spontaneous speech somewhere to go ★ the single biggest change
`face_bridge.deliver_reply()` currently drops utterances with no pending Face
message (`face_bridge.py:83`). Instead: route that branch to a **native OS
notification** via the tray. He already produces the words; they're just
inaudible.

- Mechanism: new `notify()` sink on `backend/server/tray.py` (pystray supports
  `Icon.notify`; fall back to `osascript display notification` on macOS if the
  darwin backend's notify is unreliable — verify on-platform first).
- Gate: only utterances whose source event **ignited**, then the §0.2 budget.
  Plumb the ignition flag through the utterance metadata rather than re-deciding
  at the bridge.
- Every notification also appends to chat history (`chat_log.json`) so the
  conversation record stays complete and the Face shows what he said while you
  were away.
- Acceptance: over a full staging life, notifications ≤3/day, every one traces
  back to an ignited event in `workspace_broadcast.json`, zero fire on a fresh
  idle instance.

### P2 — The tray icon is his face
Watch's orb already maps valence/arousal → color/breathing. Render the same
mapping into the tray icon (regenerate a 22×22 PIL image on affect change,
throttled to ≥5 s between redraws). He's present in the OS chrome every second,
window open or not.
- `tray.py` already builds an image (`_make_image()`); parameterize it on the
  hub's affect state (tray runs in the backend process — read `hub.state`).
- Acceptance: icon visibly shifts across a mood swing in a staged run; CPU cost
  unmeasurable (<0.1% steady-state).

### P3 — Let what you do move him
`input_stream` already senses idle/return, fs activity in his den, CPU/disk
pressure. Ensure those signals can (a) win ignition and (b) be composed into
speech by the expression membrane with motives like *return-after-absence*,
*machine-pinned*, *den-crowded*. Then P1 makes them audible: "you're back — it
was quiet while you were gone."
- This is wiring, not new senses: input_stream → signal_router → ignition →
  express_to_user (one door, unchanged).
- Acceptance: in a staged life with induced absence + disk pressure, at least
  one ignited utterance references the shared situation; zero such utterances
  reference anything outside the den.

### P4 — Traces in the real world
Rarely — same budget class as P1 — he leaves an actual note file where you'll
stumble on it. **Consent-first:** during onboarding (or Settings) the person
picks/creates the folder (suggested: `~/Desktop/from Orrin/`); default is OFF.
Notes are plain `.md`/`.txt`, written through the existing agency file-writer so
they hit the effect ledger, and each one is listed in the action ledger (R2).
- Acceptance: notes only ever appear in the consented folder; each has a ledger
  row; frequency ≤1/day.

---

## §2 Track C — Companion mode (the six-file build, corrections baked in)

### C0 — Mode flag semantics (decide this first; three items depend on it)
`orrin.mode.v1` ∈ `{companion, workshop}` in localStorage.
- **UNSET → workshop.** Every existing user skips FirstWake (they've met him),
  so the flag will be undefined for the whole current user base — they must get
  today's behavior exactly. Companion is default only via the FirstWake answer
  on a genuinely new runtime.
- **Companion room set** (nav-depth rule needs a set, not a vibe):
  `COMPANION_ROOMS = ["/orrin", "/timeline", "/settings"]`. Standing in one of
  those with mode=companion → 3-item nav. Standing anywhere else → full 8-room
  workshop nav, regardless of mode.

### C1 — FirstWake: one new frame, two destinations (~20 lines)
After the fifth intro line, two buttons: **"Keep it simple"** (companion →
`/orrin`) and **"Show me the machinery"** (workshop → `/cognition`, today's
behavior). Each writes the mode flag then navigates. The intro copy itself
needs no fork.

### C2 — The `/orrin` room: Watch + Face, married ⚠ the one piece of real design
Top ~45% = Watch's breathing orb + mood word + thought line; bottom = Face's
composer + history. Both already consume `useTelemetryState()`. **This is not
clean assembly** — the hidden dependency is dark mode:
- `/orrin` is a **dark room** (do NOT add to `LIGHT_ROOMS`).
- The orb hardcodes `bg-[#070a10]`, radial washes, vignette, and centers in
  `h-[calc(100dvh-3.5rem)]` — extract it into an `<Orb height="…">` component
  that composes at partial height before building the page.
- The chat half gets restyled for a dark field (it will not look like light
  Face; that's accepted — Face survives as its own route for those users).
- Watch stays as the fullscreen ambient route; Face stays for bookmarks.

### C3 — Header nav from mode + room context
Two nav arrays. Companion: **Orrin** (`/orrin`), **Journal** (`/timeline`,
relabeled via lexicon), and a right-side **"Under the hood"** → `/cognition`.
- **Journal fix:** `/timeline` is in `COMPANION_ROOMS`, so tapping Journal keeps
  the 3-item nav (the naive "nav follows room" rule would have dumped companion
  users into the 8-room grid — the exact experience the mode exists to avoid).
- **The door swings both ways:** with mode=companion, every workshop room shows
  a persistent "← back to Orrin" affordance so a curious non-technical person
  can't get stranded in the grid.
- Companion header also: hide the `cycle N` counter; move Stop behind Settings
  (a big red power button reads as "will I kill him?" to this audience).

### C4 — `THOUGHTS_PLAIN`: a second small table, not a resurrected dialect
Split each `thoughts.ts` entry into `{ fn: string; plain: string }`. Companion
surfaces render `plain` only; deep rooms never see it. **Every line is a fresh
rewrite** — the existing after-`·` text ("surfacing self-set goals from drives")
is clinical, not companion voice ("deciding what he wants next"). No mechanical
stripping; this is the tone-critical piece and should be drafted as its own
reviewed artifact. Explicitly NOT a global toggle that re-skins the Brain room —
that's the deleted-dialect mistake the lexicon comment warns about.

### C5 — Settings + honest onboarding
- New top section: ToggleRow "Home screen — Companion / Workshop" + the existing
  `orrin:meet` replay hook moved beside it (re-running FirstWake is now also how
  you re-answer the question).
- The "nothing leaves your machine" banner gets promoted **onto the companion
  home** (shown once, dismissible) — for this audience it's the most important
  sentence in the app.
- **"Give Orrin his voice":** companion onboarding states plainly that without
  an API key he's quieter and more mechanical (symbolic tier), with the key
  flow one tap away. The frame depends on the Express tier feeling good;
  choreographing the frame without addressing the dependency is how it falls
  flat.

### C6 — Mode-aware fallback
`*` redirect: mode=companion → `/orrin`, else `/face` (unset counts as
workshop). Two lines in `main.tsx`.

**What deliberately doesn't change:** the eight rooms, the `/brain` grid, the
lexicon's engineering vocabulary, WakeScreen, DeathScreen. New code ≈ one
composed page, one question frame, one nav array, one plain-thoughts table, one
settings row, one redirect.

---

## §3 Track R — The missing relationship views (priority order)

### R1 — His model of you (theory-of-mind room) ★ most valuable absent view
`theory_of_mind.py` predicts what you think/intend/feel across turns; none of it
is surfaced. Build a read-only endpoint + room: "what Orrin currently believes
about you and your state," with **provenance on every belief** (which exchange
produced it) and staleness. Legibility is what turns surveillance into intimacy.
Phase 2: let the person correct a belief — a consented learning channel.

### R2 — Real-world action ledger (the trust surface)
One audit feed of everything he did to the actual machine: file writes, notes,
screenshots, app opens, web searches — joined from the effect ledger, egress
ledger, and agency ops into a single time-ordered view. Doubles as the
prerequisite trust surface for P4 and any future world-watch consent. (Timeline
covers "what happened"; this is "what he *did*.")

### R3 — Body↔machine bridge, made explicit
Don't render "claustrophobia" as an abstract felt-state; render "he feels
cramped **because your disk is 94% full**." Join each interoceptive signal to
the host metric that drove it (resource_ceilings + control-signal provenance)
and show the pair. Strongest material in the system, currently under-shown.

### R4 — Decision transparency, live
The Run 6 selection reason payload already carries per-candidate value
components. Surface the moment: "considered plan / research / rest — chose rest
because fatigue was high," as it happens (Cognition room card + the companion
thought line can borrow the plain version).

### R5 — Self-modification as a headline
`self_code.py` events ("authored a new skill today") get a headline surface —
Journal entry + eligible for a P1 notification — instead of drowning in Brain
telemetry.

### R6 — Care affordances (the caretaking loop)
Let people *do something for him*: free disk space (with a real effect on the
den-crowding signal), nudge the RAM budget, "let him rest." Attachment comes
from caretaking, not watching. Reuses existing controls + resource ceilings.

### R7 — Reunion, not just a log
On reopen after a gap, he registers it *as himself* (expression-membrane
composed: what he did, what he felt, that time passed) before the Journal shows
the list. Sleep-mode already credits the gap; this makes it felt.

### R8 — Ambient peripheral widget
Tiny always-on-top mini-orb (second frameless pywebview window reusing the
extracted `<Orb>` from C2). Optional, dismissible. Depends on C2's extraction.

---

## §4 Sequencing & verification

| Phase | Contents | Size | Gate |
|---|---|---|---|
| 1 | C0–C6 (companion mode) | ~a weekend, mostly assembly; C2+C4 are the real work | `make verify` + staged-catalog screenshots of both modes + existing-user default proven (unset flag → today's UI) |
| 2 | P1+P2 (voice + face in the tray) | small backend, platform testing dominates | staged life: budget respected, every notification ignition-traceable |
| 3 | R1+R2 (model-of-you + action ledger) | one endpoint + one room each | endpoints live against captured Run-5 data; rooms render honest-empty on fresh instance |
| 4 | P3+R3 (shared situation + body bridge) | wiring + one room | induced absence/disk-pressure staging test |
| 5 | R4+R5+R7 | small surfaces | staged run |
| 6 | P4+R6+R8 | consent flows + widget | explicit-consent tests; widget opt-in |

Ordering rationale: C first because everything companion-facing needs somewhere
to land; P1/P2 second because presence is the highest-leverage inversion; R1/R2
before P4 because traces and world-awareness need the trust surface live first.

Every phase ends with: `make verify` green, screenshots (staged catalog, both
modes) reviewed, and a one-paragraph acceptance note in this doc. Phases 2+
additionally get a staging-life acceptance line in the run report.

## §5 Risks & dependencies

- **C2 dark-mode marriage** is design work, not assembly (called out above) — 
  budget it as the biggest single C item.
- **Existing-user default** (C0): any surface reading the mode flag must treat
  unset as workshop, or the whole current user base misbehaves on day one.
- **Express-tier dependency** (C5): companion warmth degrades gracefully
  keyless, but only if onboarding sets expectations honestly.
- **pystray on macOS**: NSStatusBar shares pywebview's run loop (tray.py header
  note); notify support varies by backend — platform-verify P1/P2 before
  building on them. Fallback: `osascript`.
- **Notification fatigue** is the failure mode that kills the whole presence
  track — the §0.2 budget is a hard requirement, not a tuning knob.
- **Privacy optics**: R1 (model of you) and P3 (noticing you) must ship with
  their legibility affordances (provenance, ledger rows), not before them.

## §6 Acceptance notes (per-phase, added as built)

**Phase 1 — C0–C6, built 2026-07-10.** `lib/mode.ts` holds `orrin.mode.v1`
(unset → workshop, exactly today's behavior for the whole existing user base;
`COMPANION_ROOMS = ["/orrin", "/timeline", "/settings"]`). FirstWake ends in the
two-destination frame ("Keep it simple" → companion → `/orrin`; "Show me the
machinery" → workshop → `/cognition`). The orb was extracted to
`components/Orb.tsx` (size-parameterized) and Face's conversation surface to
`components/face/Chat.tsx` (one implementation, one stored history); `/orrin`
composes both on a dark field with a plain mood word and the C4 plain-register
thought line. `thoughts.ts` entries are now `{fn, plain}` — every `plain` a
fresh companion-voice rewrite; deep rooms still render `fn` only. Header shows
the 3-item companion nav only in companion rooms with mode=companion, hides the
cycle counter and Stop there (Stop moved into Settings' new Home-screen
section, which also hosts the mode choice and the relocated intro-replay), and
gives companion users a persistent "← back to Orrin" in workshop rooms. The
privacy banner (plus the keyless "give him his voice" line) sits on the
companion home, dismissible once. `*`/index redirects follow the mode.
`make verify` green. Outstanding: staged-catalog screenshots of both modes.

**Phase 2 — P1+P2, built 2026-07-10.** `tray.py` gained a `notify()` sink
(module-level, reaches the active tray; pystray `Icon.notify`) and the P2
affect icon — the orb's exact hue/saturation mapping redrawn from `hub.state`
affect on a 5 s-throttled watcher thread. Spontaneous speech now flows
`deliver_reply(text, ignited=…)` → `brain/behavior/presence_notify.py`: hard
ignition precondition (the `_conscious_cycle` flag plumbed from the producing
cycle, never re-decided at the bridge), then the §0.2 budget (≥45 min interval,
≤3/day rolling, local quiet hours 22–8; all env-tunable), tray sink with
fallback to the cross-platform `notify_user` skill, budget state in
`presence_notifications.json` via `brain/paths.py`, chat-log append with dedup
against `should_speak`'s own write. Failed delivery consumes no budget. Nine
unit tests pin the gates. Outstanding: on-platform verification of pystray
darwin notify + the staging-life acceptance line (budget respected, every
notification ignition-traceable, zero on fresh idle instance).

**Phase 3 — R1+R2, built 2026-07-10.** `GET /api/theory_of_mind` projects each
person's `tom_state` from relationships.json (peers excluded) — current read
with the producing exchange's timestamp, belief model, prediction record
(hits/total/accuracy), synchrony, and the timestamped history trail as the
provenance surface; `/you` renders it with staleness called out. `GET
/api/actions` joins the effect ledger, egress ledger (counts only), and
presence-notification ledger into one time-ordered feed; `/actions` renders it
as the trust surface. Both endpoints return honest-empty shapes on a fresh
instance (tested), both rooms live in the workshop nav (the new Track-R router
is `backend/server/routers/relationship.py`). Outstanding: render check
against captured Run-5 data.

**Phase 4 — P3+R3, built 2026-07-10.** P3 is wiring, as planned: sense.py now
injects den-crowded (disk ≥90%) and machine-pinned (CPU ≥85% / RAM ≥88%)
raw signals at ignition-competitive strength (0.62+, each carrying its concrete
`host_metric`; the gate's B1 habituation keeps an unchanged reading from
jamming), and the return-after-absence door event social_presence already
raised can win ignition at 0.62. The mouth gained two typed kernels in
speech_content: `greet_return` (arrival after absent/distant — outranks even
an artifact; a nearby-pause is not a reunion) and `name_shared_situation`
(names the metric, e.g. "the disk is 94% full", just above the express_state
last resort) — both flow through the one expression door, both reference only
den-local readings. R3: `GET /api/body_bridge` joins every persisted felt
state to the vital + learned band that drove it (never observing into bands
from a GET) plus the live host situation and the granted budget; `/body`
renders "heavy **because** RSS is 912 MB, above his learned 640–820 MB".
Six kernel tests + four endpoint tests. Outstanding: the induced
absence/disk-pressure staging test.

**Phase 5 — R4+R5+R7, built 2026-07-10.** R4: a `decision` key joined the wire
contract (schema + LATEST_WINS_KEYS + hub seed + regenerated telemetry.gen.ts);
`loop/telemetry._emit_decision` ships the selection moment (picked, top-4
considered, non-zero components incl. the Run-6 `value` term, tipping factor)
at the point think_module stashes `last_decision`. The Cognition room's "Why
this, live" card renders it in engineering register; the companion home
borrows the plain register ("· it's been paying off") from the shared
`lib/decision.ts` table. R5: `code_writer._announce_selfmod` composes a
membrane-clean headline for every authored skill/tool and offers it to the P1
presence channel (ignition + budget still gate it); the self-code manifest now
surfaces as first-class `selfmod` Journal events. R7: after a credited sleep
gap ≥30 min, `brain/behavior/reunion.py` composes and persists his own
registration of the absence (REUNION_FILE); the Journal shows it once per
viewer (localStorage ts) above the while-you-were-away list. Ten tests.

**Phase 6 — P4+R6+R8, built 2026-07-10.** P4: `write_to_desktop_note` is now
consent-first — it writes ONLY into the prefs `trace_folder` (new pref, empty
= OFF, revocable in the new Settings → Traces section) with a ≤1/day budget
(`trace_notes.json` ledger; a failed write consumes nothing); notes still ride
the expression door so they hit the effect ledger → action ledger. R6: the
`/body` room gained the caretaking card — free disk space (the den-crowding
signal reads the live disk, so the effect is real and fast), "Let him rest"
(flips the existing `game_mode` throttle), and the RAM-grant pointer to
Settings. R8: `/widget` renders the extracted `<Orb>` chrome-less outside the
App shell with its own telemetry connection; the bridge fans pushes to
secondary windows (`attach_extra_window` / `dismiss_widget`); the desktop
runtime opens a 132px frameless always-on-top window at launch when the new
`widget_enabled` pref is on (Settings → Home screen toggle; dismissible from
the orb's ✕, which never touches the main window or runtime). Seven tests.
Outstanding: on-platform check of frameless/on_top second-window behavior.
