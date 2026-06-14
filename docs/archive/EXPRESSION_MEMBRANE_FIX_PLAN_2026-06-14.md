# Expression Membrane — Fix Plan

**Date:** 2026-06-14
**Author context:** Follows the live debugging session that fixed the attention
hijack (`memory/attention-hijack-felt-intensity-2026-06-14`). Same shape of bug,
one layer out: the architecture has the *vocabulary* of intention but the
*mechanics* of reflex.

**Guiding principle:** Every artifact a person sees must be **authored by Orrin
through one intentional surface** — composed from his meaning and felt state, not
populated by scraping internal representation. The internal machinery (raw
working memory, symbolic/causal tags, telemetry) is **backend**; it must be
unreachable by the acts that face a person. One door, and the door composes —
it does not copy.

> "When writing a note it needs to be *him* writing the note, not just population
> of backend stuff. He shouldn't be able to get access to that stuff — that's
> backend stuff." — Ric, 2026-06-14

---

## The issues being fixed

| # | Issue | Verdict | Primary evidence |
|---|-------|---------|------------------|
| E1 | `leave_note` scrapes the last 15 working-memory entries and emits the first that passes a weak prefix filter; the note is not *about* any intention | True | `brain/cognition/leave_note.py:78` (`_compose_note`), `:68` (`_SKIP_PREFIXES`) |
| E2 | `write_desktop_note` joins the **last 3 WM lines raw, with no telemetry filter at all** | Worse than the others | `brain/ORRIN_loop.py:763-766` |
| E3 | `announce_to_dashboard` ships the **single last WM entry** `.content` to the user-facing dashboard | True | `brain/ORRIN_loop.py:769-773`; `brain/embodiment/system_presence.py:559` |
| E4 | Notes are **write-only**: nothing in brain, backend, or UI ever reads `outbox/notes.json` | True | only consumers of `NOTES_FILE` are `paths.py:257` (def) and `leave_note.py:24` (its own re-load); header comment admits it: `leave_note.py:25` |
| E5 | Self-initiated speech (`express_state`, no user present) bypasses the speech organ and pipes raw `raw_action` inner text out | True | `brain/think/think_utils/talk_policy.py:167` (`if user_input:` gate), `:184-206` (raw text → `should_speak`) |
| E6 | The intention that *does* exist (at the goal level) is severed at execution: a step is word-matched to a function name, the reason dropped | True | `brain/cognition/planning/step_execution.py:46` (`_INTENT_RULES`), `:59-60` (`note`→`leave_note`), `:148` (`_semantic_step_match`, fired live at sim=0.39) |
| E7 | Each emitter reimplements its own (drifting) filter; there is no single speakability chokepoint off the user-reply path | True | `leave_note.py:68` vs `speech_pipeline.py:309` (`_INTERNAL`) vs `speech_gate` suppression — three different lists |

**The one good thing already in place:** `brain/behavior/expression.py:209` (`express`)
composes language from **affect + a learned vocabulary** with congruence
enforcement (Rogers 1959) and **never reads working memory or symbolic state**.
This is the authoring organ. The fix reuses it; it does not rebuild it.

---

## Audit — every action that emits to a person

| Action | Current behavior | Delivered? | Intentional? | Target state |
|---|---|---|---|---|
| `leave_note` | scrape WM[-15:] → `outbox/notes.json` | ❌ dead file | ❌ | compose via door → delivered channel |
| `write_desktop_note` | join WM[-3:] raw → desktop file | ✅ desktop | ❌ | compose via door |
| `announce_to_dashboard` | last WM entry → `announcements.json` | ✅ dashboard | ❌ | compose via door |
| `express_state` (self-talk) | raw `raw_action` text → output | ✅ UI/SSE | ❌ | compose via door (self-initiated mode) |
| `notify_user` (skill) | emits string handed to it | ✅ OS notify | pass-through | becomes a channel adapter |
| `save_note` (skill) | emits string handed to it | ✅ file | pass-through | becomes a channel adapter |
| `express()` | compose from affect + vocabulary | n/a | ✅ | **the composer the door calls** |
| `build_response` (reply) | full organ (comprehension, ToM, register, `_INTERNAL`) | ✅ | ✅ | **reference implementation** |

---

## Architecture — the membrane

Two sides, one door.

```
   INTENT (motive)                         BACKEND  (off-limits to expression)
   ───────────────                         ─────────────────────────────────
   goal purpose, recipient,        ╳       working_memory entries
   what he means to say                    symbolic_dictionary / causal_graph
        │                                   [symbolic]/[rule]/[causal] strings
        ▼                                   telemetry, reward ticks
   ┌──────────────────────────┐
   │   express_to_user(...)   │  ◄── THE ONE DOOR (composes, never copies)
   │   • take a Motive         │
   │   • compose via express() / speech organ
   │   • run speakability invariant (one place)
   │   • stamp motive on the artifact
   │   • route to channel
   └──────────────────────────┘
        │            │            │            │
        ▼            ▼            ▼            ▼
   live reply     note        desktop      dashboard / OS notify
   (UI/SSE)    (delivered)    (file)       (announcements.json / notify)
```

**The Motive** — a small structured object, captured at selection time, never scraped:

```python
@dataclass
class Motive:
    intent: str          # "report a blocker", "share a finding", "check in"
    why: str             # the goal purpose this serves (from the goal spec)
    recipient: str       # "Ric" | "self" | "dashboard"
    seed: str = ""       # optional content kernel he means to convey (meaning, not a raw WM line)
    goal_id: str = ""    # provenance
```

**The door** — `brain/behavior/express_to_user.py` (new):

```python
def express_to_user(motive: Motive, channel: str, context: dict) -> dict:
    # 1. compose: reuse expression.express()/speech organ from motive + affect.
    #    Never reads context["working_memory"] or any symbolic/telemetry field.
    # 2. enforce the speakability invariant (the single _INTERNAL filter) — a hard
    #    assert here, not a per-emitter reimplementation. Composed text that still
    #    contains a [tag] is a composer bug, raised, not shipped.
    # 3. stamp: attach the motive to the artifact ({text, motive, ts, emotion}).
    # 4. route: dispatch to the channel adapter (reply / note / desktop / dashboard / notify).
    # returns {"success", "channel", "text", "motive"}
```

**Invariant:** the door is the *only* code that turns internal meaning into
person-facing text, and it consumes a `Motive`, never raw representation. Emitters
lose their ability to read `working_memory`.

---

## Phase 1 — Build the door; convert the note/desktop/announce emitters

**Goal:** kill the visible telemetry leak and the dead outbox. No motive
propagation yet (Phase 2); Phase 1 constructs a *local* motive from affect +
committed goal so the composition is real even before E6 is wired.

### 1.1 New file `brain/behavior/express_to_user.py`
- Define `Motive` and `express_to_user(motive, channel, context)`.
- Compose by calling `expression.express(...)` (or a thin `compose_from_motive`
  wrapper around it) — affect-driven, vocabulary-based, congruence-checked.
- Speakability invariant: lift the `_INTERNAL` list from
  `speech_pipeline.py:309` into a shared `brain/behavior/speakability.py`
  (`is_speakable(text) -> bool`, `assert_speakable(text)`). Both the door and
  `build_response` import it — one list, no drift (fixes E7).
- Channel adapters (thin):
  - `reply` → existing `should_speak`/SSE path
  - `note` → **delivered** store (see 1.3)
  - `desktop` → existing `_wdn` file writer (content only, no scrape)
  - `dashboard` → `announce_presence(text)`
  - `notify` → `notify_user(text)`

### 1.2 Convert the three emitters to dumb adapters
- `brain/cognition/leave_note.py`: delete `_compose_note` and `_SKIP_PREFIXES`.
  `leave_note(context)` builds a local `Motive(intent="leave_note",
  why=committed_goal.purpose, recipient="Ric", seed=salience.output_seed)` and
  calls `express_to_user(motive, "note", context)`. **Remove all access to
  `context["working_memory"]`.**
- `brain/ORRIN_loop.py:763` `_write_desktop_note`: stop joining `wm[-3:]`; call
  the door with `channel="desktop"`.
- `brain/ORRIN_loop.py:769` `_announce`: stop reading the last WM entry; call the
  door with `channel="dashboard"`.
- Keep the function names/registrations identical so action selection and the
  procedural set (`step_execution.py:97 _PROCEDURAL_DEFAULT`) are unchanged.

### 1.3 Make notes actually deliver (fixes E4)
- The outbox is a dead drop. Two options:
  - **A (recommended, lowest cost):** route `channel="note"` through the existing
    delivered announcements bridge (`announcements.json`, already polled by the
    dashboard per `system_presence.py:559`) with a `kind:"note"` tag, **and** keep
    a copy in `outbox/notes.json` for durability.
  - **B:** add a backend read endpoint for `outbox/notes.json` + a UI panel.
- Decision needed from Ric: A or B. Plan assumes **A** unless told otherwise.

### 1.4 Reafference unchanged
- Keep the `[note_written]` WM reafference (`leave_note.py:44-52`) so milestone
  verification (`env_snapshot`) still closes note goals. It writes a marker *into*
  WM; it does not read raw WM out — membrane intact.

**Acceptance criteria (Phase 1):**
1. A fresh `leave_note` / `write_desktop_note` / `announce` output contains **no**
   `[symbolic]`/`[rule]`/`[causal]`/`[tag]` substrings and no filesystem paths.
   (`assert_speakable` passes; grep the live artifact.)
2. Each emitted artifact carries a `motive` field with non-empty `intent` + `why`.
3. No emitter module references `context["working_memory"]` (static check:
   `grep -n working_memory leave_note.py ORRIN_loop.py:_write_desktop_note/_announce` → none).
4. A note written after the change is visible to the user (announcement bridge),
   not only in the dead outbox.
5. Action selection, reward, and the procedural daemon behave unchanged
   (function names + registrations identical).

---

## Phase 2 — Propagate the goal's motive across the execution boundary (fixes E6)

**Goal:** the note is composed *to serve the reason it was triggered*, and the
reason is recorded — "him writing the note," not "a note happening near him."

### 2.1 Carry intent through `recognise_step_action`
- `brain/cognition/planning/step_execution.py`: when a plan step maps to an
  expressive function (`leave_note`/`write_desktop_note`/`announce`/speech),
  build a `Motive` from the **owning goal's `spec.description` + the step text**
  and thread it into `execute_step_action` → the emitter → `express_to_user`.
- Today the mapping returns only `fn_name` (`recognise_step_action:177`); extend
  the return / context to also carry the motive. Word-match still *selects* the
  act; it no longer *discards* the why.

### 2.2 Self-initiated speech mode (fixes E5)
- `brain/think/think_utils/talk_policy.py:167`: when `not user_input` but there is
  output pressure, stop piping `raw_action` text to `should_speak`. Instead build
  a self-directed `Motive(recipient="self"/"Ric")` and call `express_to_user(...,
  channel="reply")`. Self-talk now goes through the same composer as replies.
- This requires the speech organ to support a self-initiated composition path
  (it is currently keyed to `user_input` at every stage of `build_response`). Add
  a `compose_from_motive` entry that uses affect + memory + motive instead of a
  parsed user utterance.

### 2.3 Record provenance
- Persist `motive` on each artifact and in `speech_log` so "why did he say/write
  this" is answerable and the construction-grammar scorer can learn per-intent.

**Acceptance criteria (Phase 2):**
1. A note triggered by goal *"name the obstacle for Ric"* has `motive.why`
   referencing that goal and content that addresses the obstacle — not unrelated
   WM residue.
2. `express_state` entries in `speech_log` carry a non-empty plan/motive and read
   as composed language, not truncated raw inner text.
3. Removing the goal makes the corresponding expressive act *not fire* (the act is
   now downstream of intent, not of a stray word-match).

---

## Tests

- **Unit:** `express_to_user` with a crafted `Motive` returns speakable text
  (`assert_speakable` holds); composing from a Motive whose seed contains
  `"[symbolic] ... [rule]"` yields output with the tags stripped/reworded, never
  passed through.
- **Unit:** emitters raise/skip if handed `working_memory` (regression guard that
  the scrape path is gone).
- **Static:** grep guard in CI — no expressive emitter imports/reads
  `working_memory` or `symbolic_dictionary`.
- **Integration (live, the way we validated the attention fix):** stop the run,
  restart, force a `leave_note`, confirm (a) speakable, (b) motive present,
  (c) appears on the dashboard, (d) `outbox/notes.json` no longer the only sink.
- **Shadow diff:** log old `_compose_note` output alongside new composed output
  for N cycles to confirm the new path is strictly cleaner before deleting the old.

---

## Risks & non-goals

- **Risk:** `express()` composes shorter/vaguer text than the scraped WM line,
  which sometimes carried real content. Mitigation: `Motive.seed` lets a genuine
  content kernel (e.g. `salience.output_seed`, which is already "raw signal wanting
  expression," not telemetry — `cycle_state.py:35`) flow in and be *reworded*, not
  copied. Tune in the shadow-diff phase.
- **Risk:** milestone verification depends on note text. Mitigation: reafference
  marker (1.4) is unchanged.
- **Risk:** touching `talk_policy`/`build_response` (Phase 2) is higher-blast-radius
  than Phase 1. Mitigation: ship Phase 1 alone first; it is self-contained and
  fixes the visible leak.
- **Non-goal:** rewriting `expression.py` or the vocabulary system. Reuse as-is.
- **Non-goal:** the LLM. Composition stays symbolic (`FORCE_SYMBOLIC_SPEECH=True`).

---

## Rollback

- Phase 1 is additive + three localized edits. Rollback = restore `_compose_note`/
  `_SKIP_PREFIXES`, revert the three emitter bodies, delete `express_to_user.py`
  and `speakability.py`. No data migration (artifacts gain an extra `motive`
  field that old readers ignore).
- Phase 2 rollback = revert the `recognise_step_action` motive thread and the
  `talk_policy` self-initiated branch; word-match selection returns to fn-name-only.

---

## Sequencing

1. **Phase 1** (door + speakability module + 3 emitter conversions + delivery A) —
   self-contained, kills E1/E2/E3/E4/E7, validate live.
2. **Phase 2** (motive propagation E6 + self-speech E5) — after Phase 1 proves out.

**Open decision for Ric:** note delivery **A** (reuse announcements bridge) vs
**B** (new outbox endpoint + UI panel).
