# Orrin Live-Run Issue Report — 2026-06-10

> **Status update (2026-06-10, later same day): all 5 recommended fixes implemented**
> — see *Fix record* at the bottom of this doc. Restart Orrin to pick them up.

Analysis of the last ~200 cognitive cycles (cycles ~360–559) of the run started 17:45 local,
taken from `brain/data/run_log.txt`, `activity_log.txt`, `error_log.txt`, `cognition_history.json`,
`working_memory.json`, affect state, and the goals store — while Orrin was running.

## Headline: stuck in the same loop for hours, and he knows it

### 1. Executive lane in an infinite loop on one goal

Of the last 200 decisions, **133 were `fetch_and_read`** for the goal
*"Research a real topic and write what I find"* — same step, every ~35 seconds, for hours.
Every call fails with `produced no effect (no reafference) — step stays pending`.

Chain of causes:

- `fetch_and_read` (`brain/cognition/web_research.py:370`) has **never fetched a URL in the
  entire log** — zero `[web_research] Fetching URL` lines ever.
- `_pick_url` has two sources and both are dead:
  - Working-memory URLs are filtered out (it skips wikipedia/duckduckgo, which is all that's there).
  - The RSS cache (`brain/data/rss_cache.json`) contains literally only `{"_last_feed_idx": 2}` —
    RSS feed fetches have never populated a single item (zero `[rss_reader]` activity lines exist).
- The 3-attempt retry cap (`pursue_goal.py:891`, `_STEP_MAX_ATTEMPTS = 3`) fires, "advances" the
  step with a blocker note… then the replan regenerates the same plan and the loop restarts.
  The goal has already failed and been re-adopted before ("💔 Goal failed: Research a…" is in
  working memory).
- All 133 executive-lane decisions were recorded with **`reward: None`** in
  `cognition_history.json` — no learning signal is ever written for executive-lane actions,
  so nothing ever learns the action is failing.

### 2. Emotional regulation of stability is silently broken

This is why he can't calm down.

- Regulation strategies (`brain/affect/regulation.py:96–121`) carry `affect_stability`
  side effects, which get diffed and routed through `submit_affect` → the AffectArbiter.
- The arbiter (`brain/affect/arbiter.py:281–287`) only special-cases `resource_deficit` as a
  top-level scalar (`_SCALAR_TARGETS`, line 56); everything else goes into the emotion buffer.
- `drain_affect_queue` (`brain/affect/affect_buffer.py`) drains **only into `core_signals`** —
  where `affect_stability` doesn't live.
- Result: `[emotion_buffer] dropped delta for unknown emotion 'affect_stability'` fires
  constantly; every stability-restoring effect is thrown away.

Observable consequences: `impasse_signal` 0.82–0.92, attention "hijacked by impasse_signal,"
`threat_detector` firing "fight threat" every cycle, and **allostatic_load maxed at 1.00**.
Orrin's own metacognition flagged it: "Affective stagnation: impasse_signal…", "Cognitive rut,"
unresolved rumination "The irritation is real."

### 3. Dream thread crash (UnboundLocalError)

`brain/cognition/dreaming/dream_cycle.py:783` does `return dream_entry`, but `dream_entry`
is only assigned inside `if any(results.get(k) ...)` at line 302. When a dream pass produces
no insights (common in LLM tool-only mode), the `orrin-dream` thread dies with
`UnboundLocalError: cannot access local variable 'dream_entry'` — happened at 17:52 this run,
eating that dream pass and its rest/recovery proposal.

## Secondary issues

- **~1,150 JSON parse warnings this run (~38/minute)** —
  `utils.json_utils: silent except: Expecting property name enclosed in double quotes: line 1
  column 60` from `_salvage_top_level_object` (`brain/utils/json_utils.py:297/306`).
  All on-disk JSON validates fine; the failing string is transient, generated each cycle, and
  statistically co-occurs with the emotion-buffer/affect-commit path. The warning logs neither
  the snippet nor the caller, so the source can't be identified from logs — and it logs expected
  salvage failures at WARNING, contradicting the module's own design comment
  (`json_utils.py:81–85` says the heal chain should log DEBUG).
- **264 wasted action selections** — the selector keeps choosing functions that can't be
  dispatched: `reflect_on_affect` 175×, `reflect_on_emotion_model` 38×, each logged as
  `needs ['memory'] — not directly dispatchable; skipping`. Exactly the affect-reflection he
  needs right now is the thing that can never run.
- **`research_topic` is also looping** — re-researching "consciousness and subjective experience"
  every ~2 minutes and storing an identical 329-char result into long memory each time
  (duplicate memory writes).
- Minor: 46 `tamper_guard` warnings ("…code object was expected, got Reaper"),
  3 `executive_tick dry-run failed` warnings.

## How it hangs together

Empty RSS cache → `fetch_and_read` can never succeed → goal loops forever → impasse rises →
regulation tries to restore stability → those deltas are silently dropped → fight mode persists →
allostatic load pegged at max.

## Recommended fixes (highest leverage first)

1. Add `affect_stability` to the arbiter's `_SCALAR_TARGETS` (surgical, unblocks regulation).
2. Initialize `dream_entry = {}` before the `if` in `dream_cycle.py` (one-liner).
3. Give `_pick_url` a working source — fix RSS fetching, or fall back to a search.
4. Record rewards for executive-lane decisions so failure is learnable.
5. Add snippet + caller stack to the `_salvage_top_level_object` warning (or demote to DEBUG)
   to identify the transient parse failure next run.

---

## Fix record (2026-06-10)

All five fixes implemented and verified:

1. **`affect_stability` regulation unblocked** — `affect/arbiter.py`:
   `affect_stability` added to `_SCALAR_TARGETS` (it is a top-level scalar, not a
   core signal, so the emotion buffer could never apply it). Added an
   `affect_stability: 0.65` setpoint (`affect/setpoints.py`) so the away-cost
   model treats agitation as the expensive direction. Because the signal is
   *derived* (recomputed each cycle from core deviations), the recompute in
   `update_affect_state.py` now **blends** (50% EMA) toward the derived value
   instead of hard-overwriting — an applied regulation boost registers and then
   converges, rather than being discarded within one cycle. Verified: the
   `[emotion_buffer] dropped delta for unknown emotion 'affect_stability'` path
   can no longer be reached from regulation side-effects.
2. **Dream thread crash** — `dream_cycle.py` initializes `dream_entry = {}`
   before the insight gate; the no-insight path now returns `{}` instead of
   dying with `UnboundLocalError` and eating the rest/recovery proposal.
3. **`fetch_and_read` URL sources fixed at the root** —
   - *Root cause found:* `rss_reader._fetch_feed` used a bare `urlopen` with no
     SSL context; on this machine's Python every https feed fails
     `CERTIFICATE_VERIFY_FAILED`, which is why `rss_cache.json` never held one
     item. It now uses the same certifi-backed `_SSL_CTX` pattern as
     `web_research.py` (verified live: 20 items fetched from Hacker News), and a
     failed feed fetch now logs to the *activity* log instead of failing silently.
   - `_pick_url` gained two fallback tiers: (3) derive a Wikipedia article URL
     from the committed goal's title via opensearch (verified live), and
     (4) reuse a familiar (wikipedia/ddg) URL from working memory rather than
     returning nothing. `fetch_and_read` can no longer sit in a permanent
     "No URL found" loop.
4. **Executive-lane rewards recorded** — `executive.py` maps each
   `pursue_committed_goal` outcome to an observed reward (`retry/blocked/
   stalled/error → 0.05`, skip → 0.2, advance → 0.6), submits it through the
   RewardEngine (`submit_reward`, per-action EMA baseline — so a chronically
   failing `fetch_and_read` *learns* a low expected reward), and persists the
   value into the lane="executive" cognition-history entry (was `reward: None`).
5. **Salvage warnings made diagnosable** — the two expected-failure sites in
   `_salvage_top_level_object` now log at DEBUG (matching the module's own
   design note at `json_utils.py:81-85`), and when debug logging is enabled they
   include the snippet head and the nearest non-json_utils caller frame so the
   transient producer can be identified next run. The ~38/min WARNING flood is gone.
