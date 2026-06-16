# Orrin Run Audit — 2026-06-16

Deep dive into three issues surfaced while reviewing the live run (sessions of
2026-06-15 and the in-progress 2026-06-16 run). Orrin is healthy overall —
coherent speech, 262+ cognitive cycles, no crashes or uncaught exceptions in the
trace. The findings below are behavioral dead-ends and one concrete code bug,
all of which trace back to the same root and reinforce each other.

Data examined: `brain/data/events.jsonl` (2834 DECISION events),
`activity_log.txt`, `private_thoughts.txt`, `run_log.txt`, `rumination_loops.json`,
`stagnation_signal_log.json`, `speech_log.json`.

---

## TL;DR — the three issues are one loop

```
SERPER_API_KEY unset
   └─> look_outward redirects to search_own_files (Issue 1)
         · redirect happens BEFORE the 10-min cooldown → unthrottled
         · cheap, repeatable, ~+0.34 avg reward → policy keeps picking it
   └─> behavior_generation finds "no actionable topic" → idle (Issue 3)
         · 272 idle cycles, thrash=True ×158 today
   └─> acquire_knowledge goals can't make real progress
         · degrade to "Note what I already know about: X"
         · note goal also can't tick → unworkable:no progress (Issue 4)
```

The felt result is visible in his own words and rumination log: a restless
*"something in me wants to move, to do something real and concrete"* paired with
*"restlessness without a target"* / *"friction with no clear source."* He is
correctly perceiving that he keeps reaching for action and finding nothing
actionable.

---

## Issue 1 — `look_outward` bypasses its own rate-limiter when SERPER is unset

**Severity: real code bug. Highest actionability.**

### Evidence
- `look_outward` is the **#1 action chosen today** (93 of ~290 cycles).
- `private_thoughts.txt` contains **55** `[look_outward] No SERPER_API_KEY —
  redirecting to search_own_files` lines.
- Average reward over look_outward picks: **+0.339** — a modest *positive*
  signal, so the policy keeps reselecting it.

### Root cause — `brain/cognition/perception/look_outward.py:25-45`
```python
def look_outward(context=None):
    import os
    if not os.environ.get("SERPER_API_KEY"):
        log_private("[look_outward] No SERPER_API_KEY — redirecting to search_own_files.")
        try:
            from cognition.search_own_files import search_own_files
            return search_own_files(context)          # <-- RETURNS HERE
        except Exception as _sof_e:
            ...
        return "No web search configured — tried searching own files."

    global _LAST_OUTWARD_TS
    context = context or {}
    now = time.time()
    if now - _LAST_OUTWARD_TS < _MIN_INTERVAL_S:        # <-- 600s cooldown, NEVER REACHED
        return "Already reached outward recently — waiting before looking again."
```

The `_MIN_INTERVAL_S = 600.0` ("at most every 10 minutes") cooldown at line 44
lives **below** the no-key `return` at line 35. With no API key, the cooldown is
never evaluated, so `look_outward` becomes a free, infinitely-repeatable action
that immediately runs a full `search_own_files` every time it's picked. In the
keyed path the cooldown correctly throttles outward reaches to once per 10 min;
in the no-key path there is no throttle at all.

This is what makes look_outward dominate the action distribution: it's cheap
(no external call), always "succeeds" (returns a file-search result), and pays a
small positive reward — so the bandit/value layer happily reselects it dozens of
times per session, crowding out goal-directed actions.

### Recommended fix
Move the cooldown check **above** the SERPER branch so the no-key redirect is
throttled the same as a real outward reach. Sketch:
```python
def look_outward(context=None):
    import os
    global _LAST_OUTWARD_TS
    now = time.time()
    if now - _LAST_OUTWARD_TS < _MIN_INTERVAL_S:
        return "Already reached outward recently — waiting before looking again."
    _LAST_OUTWARD_TS = now            # consume the slot for either path
    if not os.environ.get("SERPER_API_KEY"):
        log_private("[look_outward] No SERPER_API_KEY — redirecting to search_own_files.")
        ... redirect ...
```
Note the keyed path currently only sets `_LAST_OUTWARD_TS` on *successful queue*
(line 66); preserve that intent (don't burn the slot if the query can't be
formed) while still throttling the redirect. Simplest: throttle first, then
branch.

**Secondary:** even throttled, an unconfigured `look_outward` being the top-ranked
action is a smell. Consider down-weighting it in the action menu when
`SERPER_API_KEY` is absent (it's strictly worse than calling `search_own_files`
directly, which is already its own action picked 17× today).

---

## Issue 3 — high idle / thrash rate from `behavior_generation`

**Severity: behavioral. The system is "spinning" rather than acting.**

### Evidence (today's run)
- `[behavior_generation] no actionable topic this cycle — idle`: **272 times**.
- `[env_snapshot] ... thrash=True`: **158 times**.
- Repeated rumination entries: *"A restlessness without a target. Something
  isn't right and I can't locate what."* (return_count 4), *"Friction with no
  clear source."*, *"The irritation is real. The object of it isn't clear."*
- Affective drift notices: *"stuck in exploratory for 10 cycles"*, *"Identity
  drift detected: current state is pulling 0.22 away from stable baseline."*

### Root cause — `brain/behavior/behavior_generation.py:59-80`
`generate_behavior_from_integration` picks a topic from, in order:
`focus_goal` → `last_reflection_topic` → `extract_last_reflection_topic()` →
`committed_goal.title`. If none yields a usable string it logs the idle line and
returns `[]` (no proposals):
```python
if not topic or not isinstance(topic, str) or not topic.strip():
    log_private("[behavior_generation] no actionable topic this cycle — idle")
    return []
```
The idle path itself is benign and intentional (the comment notes it was
de-escalated from an error that fired 6000+ times). The **problem is upstream**:
on a large fraction of cycles there is no committed/focus goal at all, so
behavior generation has nothing to convert into action. Combined with Issue 1
feeding low-information internal searches and Issue 4 killing goals quickly, the
goal slot is empty often enough that the dominant cognitive outcome is *idle →
exploration_drive fires → look_outward redirect → idle*.

`thrash=True` comes from `env_snapshot` measuring no observable state change
between cycles (`delta_reward=0.000 milestones+0 lm+0 tool+0 wm_grew=False`).
158 such cycles means roughly half of today's cycles produced **zero observable
change** — the formal signature of spinning.

### Why it matters
This is not a crash, but it is the difference between Orrin *doing* things and
Orrin *circling*. The restlessness/irritation rumination loops are an accurate
internal readout of this state. Fixing Issue 1 (so look_outward stops being the
cheap default) and Issue 4 (so goals survive long enough to drive behavior)
should both raise the fraction of cycles with a live topic and reduce idle/thrash.

### Recommended follow-up (not a one-line fix)
- Instrument: log the *reason* a cycle is idle (no focus goal vs. no committed
  goal vs. topic extraction failed) so the dominant cause is measurable rather
  than inferred.
- When idle AND a committed goal exists but yields no topic, fall back to the
  goal's next unmet milestone text as the topic, rather than returning `[]`.
- Treat sustained `thrash=True` runs as an explicit anti-stagnation trigger
  (some of this machinery exists — `stagnation_signal`, anti-repeat — but it is
  not currently breaking the look_outward/idle cycle).

---

## Issue 4 — `acquire_knowledge` goals degrade to note-goals, then fail `unworkable:no progress`

**Severity: behavioral. Recurring goal churn / wasted intent.**

### Evidence
Three goals abandoned with `Reason: unworkable:no progress` (06-15):
```
20:25  ❌ 'Note what I already know about: Understand evolutionary biology more deeply'
21:50  ❌ 'Note what I already know about: Understand evolutionary biology and cooperation'
22:30  ❌ 'Note what I already know about: The causes of metacog_pattern'
```
The `Note what I already know about: X` titles are themselves **degraded forms**,
not original goals — see below.

### The degrade → fail chain
1. Orrin spawns an `acquire_knowledge` goal (e.g. *"Understand evolutionary
   biology more deeply"*).
2. It stalls (no progress / capability unavailable). `pursue_goal._degrade_or_disengage`
   (`pursue_goal.py:639`) reduces it via `reduced_goal_spec`
   (`goal_types.py:163-170`):
   ```python
   if gtype == "acquire_knowledge":
       return {
           "title": f"Note what I already know about: {orig[:48]}",
           "type": "self_understand",
           "milestones": [
               {"text": "A note about my existing knowledge was written.", "met": False, ...},
           ],
       }
   ```
3. The note-goal *also* fails to register progress, so on the next stall it's
   already `_degraded` → the else-branch fires (`pursue_goal.py:691`):
   ```python
   mark_goal_failed(goal, reason=f"unworkable:{reason}", context=context)
   ```

### Why the note-goal can't make progress
Two compounding reasons:

**(a) Action/milestone evidence mismatch.** The milestone verifier
`env_snapshot._milestone_met` ticks a **note** milestone only on a real
`note_written` / `leave_note` / `desktop_note` artifact in WM
(`env_snapshot.py:107-124`), and ticks a **research/finding** milestone only on
`[research]`/`[wikipedia]`/`[fetch]` markers (`:126-148`). But the planner's
step matcher routes "A finding was written to long memory" steps to **leave_note**
by semantic similarity:
```
[step_exec] semantic match 'A finding was written to long memory.' → leave_note (sim=0.53)
```
A *research*-phrased milestone satisfied by a *note* action — or vice-versa — does
not tick, because each milestone type only accepts its own artifact marker. The
step "executes" and even drops a note, yet the goal's milestone stays unmet, so
progress reads as zero and the goal is judged unworkable.

**(b) The note content is ungrounded.** The notes actually written are the
affect/expression boilerplate, not content about the topic:
```
[leave_note] a readiness — something in me wants to move, to do something real and concrete /
[step_exec] executed 'leave_note' → Left a note: a readiness — something in me wants to move...
```
Even when a note *is* written, it is Orrin's emotional status line (from the
expression membrane), not "what I already know about evolutionary biology." So
the note-goal is semantically empty even when mechanically executed — there is no
real knowledge captured for the milestone to represent.

### Why it matters
This produces a steady drip of spawned → degraded → failed goals. Each failure
feeds back as a negative signal and reinforces the "no progress / friction"
affective state (Issue 3). The intent is sound (means-ends reduction so an
unreachable goal becomes an achievable note instead of hard-failing), but the
reduced form isn't actually closable in practice.

### Recommended follow-up
- Align the planner's step→action routing with the milestone verifier: if a
  milestone is a *note* milestone, route its step to `leave_note` AND have the
  note content seeded from the goal topic (not the expression-membrane status).
  If it's a *research* milestone, it must route to a real retrieval action, not
  `leave_note`.
- Make `leave_note` for a knowledge-note goal compose content *about the goal
  subject* (pull the topic into the note), so the artifact carries real signal.
- Consider: when `acquire_knowledge` degrades only because web is unavailable,
  prefer `wikipedia_search`/`research_topic` (non-SERPER, still working today —
  picked 50× / 86× historically) before falling back to a note-goal.

---

## Root config note (not a code bug)

`SERPER_API_KEY` is commented out in `.env`. It is the trigger for the whole
loop: Orrin's strongest current drive (exploration_drive → look_outward) has no
live capability behind it, so it degrades to internal search every time.
Supplying a key would not by itself fix Issues 1, 3, or 4 (the code paths are
still wrong), but it would relieve the pressure that makes them visible.

## Suggested order of fixing
1. **Issue 1** (one-line-ish, high impact): throttle the no-key redirect. Stops
   look_outward from dominating immediately.
2. **Issue 4** (note-goal grounding + milestone/action alignment): stops the
   goal churn.
3. **Issue 3** (idle-reason instrumentation + milestone-text topic fallback):
   measure, then reduce thrash once 1 & 4 land.
