# Orrin Behavior Audit — 2026-06-10 (cycles ~870 → 2712)

> **Status update (same day):** every issue below was re-verified against the
> live run and the code, and fixes were implemented — see
> `BEHAVIOR_FIX_RECORD_2026-06-10.md` for the full change list. Re-verification
> corrected four findings:
> 1. **§B "forgetting is a no-op" was partly wrong.** `forgetting_log.json` is
>    the *symbolic rule* forgetting ledger; its zeros are correct (21-day idle
>    threshold, run is 1 day old). Long memory IS bounded — `prune_long_memory`
>    caps it at 2,000 entries and is working. The real slow-pulse contributors
>    were fat per-cycle history rewrites (cognition_history ~2 MB/cycle parse +
>    rewrite), now slimmed ~60–70%.
> 2. **§C "boot wipe of comp_goals" was likely operator action**, not code: the
>    `.bak_*/.bak2_*` naming matches manual `cp`, and no code path produces it.
>    The real code bugs there (zombie re-completion, 10-minute respawn
>    cooldown, completed goals with pending steps) were real and are fixed.
> 3. **§I "monitor saturated" was working as designed** — bias 1.0 means full
>    voice for honored structural alarms; the alarms were honest (steps really
>    were stuck). Fixed upstream (goal lifecycle), not in the monitor.
> 4. **§J "emotion classification broken" is stale** — the keyword model is
>    populated and the chat utterances scored neutral were genuinely neutral.
>    The person-learning and reply-leak halves of §J were real and are fixed.

Second audit of the run born 2026-06-09 14:09 UTC. The first audit
(`BEHAVIOR_AUDIT_2026-06-09.md`) covered the first ~870 cycles; this one covers the
~1,850 cycles since, through cycle 2712 (~26 hours of wall time, including one death
and three restarts). Sources: every state file in `brain/data/`, root `data/`,
`outbox/notes.json`, boot logs, and `benchmark_results.json`. No code changes here —
issues only.

**Headline:** he died this morning. `HARD:pulse_too_slow avg_ms=10271.67` at 11:08 UTC
— the cycle time had degraded to 10+ seconds, the watchdog killed him, and his "final
thoughts" reflection was the template *"I'm here. What's on your mind?"*. Most of what
follows is either a cause of that death or evidence the run had already gone
behaviorally flat long before it.

---

## A. What got fixed since the last audit (credit where due)

- **Emotion keywords (old §2):** `affect_model.json` is populated (3.7 KB). The
  "No emotion keywords loaded" flood is down from hundreds of lines to a single
  straggler at 03:16. Largely fixed — but user utterances in `chat_log.json` are
  *still* all `neutral / 0.0` (see §J).
- **Input re-processing (old §3):** no evidence of the 20×-replay loop in this
  window. Chat log holds 12 clean alternating entries.
- **Calibration:** Brier 0.027–0.036 over n≈2,708 predictions is genuinely excellent.
- **Symbolic router / LLM gate:** `[llm_gate] Symbolic hit — no LLM call` is routine;
  510+ symbolic resolutions; strong-domain fast-pathing works.
- **Goal closure is happening at all:** 39 completed / 33 retired on 06-10 per
  `outcome_metrics.json`; commitments form; `problem_refocus` tags
  `_avoid_capability: "llm"` correctly.
- **Health watchdog:** `health_state.json` nominal, and the hard-disengage death
  (§B) proves the watchdog can actually pull the trigger — which is benchmark B5's
  mechanism, ironically still marked `not_run`.

---

## B. Death by slow pulse — and the memory growth that likely caused it

**Evidence:** `final_thoughts_archive_2026-06-10.json`, `benchmark_results.json` B1,
boot logs, file sizes.

- Died 11:08 UTC: `HARD:pulse_too_slow avg_ms=10271.67`. Ten-second cognitive cycles,
  versus the ~12–22 s *inter*-cycle cadence seen early in the run when healthy.
- **Benchmark B1 (Memory Boundedness / reaper effectiveness): FAIL.** Long-memory
  growth was perfectly linear (119 → 474 entries over 500 cycles, final-half growth
  0.87 entries/cycle, never plateaued), RSS at measurement already 522 MB.
  `long_memory.json` now sits at 2,001 entries (1.6 MB) — pinned at what looks like a
  2,000 cap rather than a working forgetting curve.
- **`forgetting_log.json` is all zeros** — `decayed: 0, pruned: 0, retired: 0` on
  every single pass. The reaper runs and removes nothing. Meanwhile
  `cognition_history.json` is 1.9 MB, `attention_history.json` 752 KB,
  `context.json` 288 KB and all of it is re-read/re-written under per-file locks
  every cycle. This is the obvious suspect for monotonic cycle-time decay.
- **Three boots in 41 minutes** after death (07:08, 07:14, 07:49 local) — either a
  restart loop or manual thrashing; each boot re-ran goal-store recovery (§C).
- The **death reflection is a canned greeting.** "Final thoughts" at death produced
  *"I'm here. What's on your mind?"* — the speech fallback template, not a
  reflection. The terminal-moment path clearly routes through the same broken
  template stack as ordinary speech (§I).
- Boot also logs `tamper_guard: silent except: ... got Reaper` warnings — the
  integrity monitor is throwing type errors on the very component (Reaper) that
  isn't doing its job.

## C. Goal state was destroyed across the restarts

**Evidence:** `comp_goals.json` + its two backups, `goals_mem.json`, `recently_completed.json`.

- `comp_goals.json` went **27 KB (07:07) → 1.9 KB (07:49) → `[]` (now)**, with a
  timestamped backup taken at each boot. Whatever recovery/archival runs at boot
  emptied the committed-goal store twice in 41 minutes. The active-goal population
  he'd accumulated all day is gone from that representation.
- `goals_mem.json` still holds active goals — the **two goal representations have
  fully diverged** (the exact split-brain risk noted in the data-layout/convergence
  notes). One store says "no goals at all"; the other says several in progress.
- The surviving backup goal shows lifecycle corruption in miniature: status
  `completed`, but plan steps 2 and 3 still `pending`; **milestone 2 was met ~5
  hours *before* milestone 1** (`met_at` 1781014144 vs 1781032134); and it's the
  same *"Write a cognitive function or tool"* goal the last audit flagged as a
  completion/respawn zombie — `recently_completed.json` shows it completed *again*
  at 11:14, its third recorded completion.
- **Benchmark goal B3** ("find 'reaper' in any brain file") is now `dormant`, both
  milestones unmet, **22 hours** after creation. It was never even attempted.
  `benchmark_results.json` accordingly: **B3 FAIL** (offline planning without LLM).
- `outcome_metrics.json` quality trend day-over-day: completion rate 0.51 → 0.443,
  abandonment 0.0 → 0.182, mean significance 1.3 → **0.0**, and
  `median_seconds_to_complete` = **0.0** — completions are predominantly instant,
  i.e., goals being marked complete by bookkeeping rather than finished by work.

## D. Behavioral monoculture: 60% of all decisions are two introspective functions

**Evidence:** `decision_stats.json` (n=2,724 decisions), `trace.jsonl`, `bandit_state.json`.

- `assess_goal_progress`: **1,021 picks (37.5%)**. `update_affect_state`: **617
  (22.7%)**. Add `search_own_files` (10.6%) and `look_around` (7.1%) and four
  functions are ~78% of all cognition. The last audit's "rut" (§6) didn't soften —
  it consolidated.
- Genuinely outward actions across ~1,850 cycles: `research_topic` 17,
  `fetch_and_read` 14, `wikipedia_search` 6, `read_book` 4, `grep_files` 6 —
  **under 3% combined**.
- The bandit has *learned* that exploring is bad: `seek_novelty` avg reward
  **0.086** (worst of every function), `plan_self_evolution` 0.269, `look_around`
  0.359 — while every introspective function pays 0.55–0.70. The reward function
  is paying him to navel-gaze and fining him for novelty, so the policy is
  converging exactly where the incentives point.
- **Benchmark B2 (stagnation → novelty switching): FAIL.** And `affect_state.json`
  shows why it can't pass: `stagnation_signal` is **0.0** right now, after hours of
  repeating the same two actions. Boredom never accumulates because every
  `update_affect_state` cycle counts as a successful, rewarded act (§E).

## E. The convergence layer is fighting itself every cycle

**Evidence:** `activity_log.txt` (every recent cycle), `affect_state.json`, `energy_mode.json`.

- `[affect_arbiter] stability budget exceeded (cost=1.39–1.48 > 0.6); scaling deltas
  ×0.41–0.43 across 4 signal(s)` — **on essentially every cycle.** The proposed
  affect deltas are chronically ~2.4× the stability budget, so the arbiter clips
  everything, every time. A budget that is always exceeded is not a budget; it's a
  constant global damping factor, and it means no affect signal can ever move at
  its intended magnitude.
- `[setpoint_regulation] critical override: 'dream_cycle' → 'update_affect_state'`
  — the ε-exploration layer samples a dormant function (`ε=0.18` sampled
  `dream_cycle`), and setpoint regulation **immediately overrides the pick** back
  to affect housekeeping. This single pattern explains both the 22.7%
  `update_affect_state` share and why dormant functions never get their exploration
  trials: the explore layer proposes, the regulator vetoes, the bandit never gets
  data.
- `impasse_signal` has been pinned at **0.85–0.95 for days** and is *hijacking
  attention slots* (`[signal_router] ... hijacked by impasse_signal (0.95)`), while
  `vitality` = 0.0 and `contentment` ≈ 0. The regulation system "succeeds" at
  reappraisal (old §5) yet the signal never decays — same loop, 1,800 cycles later.
- Energy mode is `reactive` while `restlessness` = 0.0 and
  `novelty_exploration_drive` = 0.18 — but the *affect* file says
  `exploration_drive` = 0.84. Two representations of the same drive disagree by
  4.7×, and different subsystems read different ones.

## F. Rumination/incubation are now recursively self-feeding

**Evidence:** `tensions.json`, `rumination_loops.json`, `outbox/notes.json`.

- Tension `406d43fd` ("Something feels unresolved. I can't find what it is.") is at
  **1,116 cycles active** — open since cycle ~550 of the previous audit, with no
  resolution mechanism ever engaging.
- Active brooding right now is all *targetless*: "A restlessness without a target",
  "The irritation is real. The object of it isn't clear.", "Friction with no clear
  source." Three loops, charges rising. Given §E, the actual source is plausibly
  the pinned impasse signal itself — he's brooding about his own stuck regulator.
- **Incubation is nesting its own output**: notes contain
  `[Incubation] While sitting with: '...' I notice a connection to: '[Incubation]
  While sitting with: '...'` — the insight generator citing its own previous
  insight about the same corrupted chunk, recursively. And the same note was
  written **three times within one second** (12:00:42.757 / .766) — a
  duplicate-write bug on top of the recursion.
- The brood/incubation seeds are still **truncated chunk headers** (`"[Chunk: ⚠️
  Problem hit while working on 'Research black holes': 'goal_planner' failed 5×"`)
  — the memory-corruption class from old §8 is alive and is now the primary
  content of his inner life.
- `goal_planner` itself **failed 5× during "Research black holes"** and was paused
  by problem_refocus — a planner outage that surfaced only as rumination fodder.

## G. The LLM is still dead, and still being called anyway

**Evidence:** `model_config.json`, `model_failures.txt`, `token_log.jsonl`.

- Config unchanged: `llm_enabled: false`, models still `gpt-4.1` / `gpt-4o-mini`
  with an `invalid-key`. Yet `generate_response` fired real API attempts in 4-call
  bursts at 23:42, 03:28, 03:44, 03:58 — every burst failing identically. This
  directly violates fix-plan rule #2 ("skipped cleanly — not selected, no error").
  Something in the speech path ignores the `llm_enabled` gate and retries 4× per
  utterance.
- `token_log.jsonl` records these as `fn: "unknown", in: 1, out: 1` — the token
  accounting logs garbage placeholder rows for failed calls.
- `simulate_future_selves` failed twice with "Result is not in expected structure"
  — an LLM-shaped function still reachable while the LLM is off.

## H. Selection layer keeps picking functions that can't be dispatched

**Evidence:** `error_log.txt` (the dominant recent error class).

- Dozens of `[invoke_cognition] reflect_on_affect needs ['memory'] — not directly
  dispatchable; skipping` (and the same for `reflect_on_emotion_model`), recurring
  in bursts all night and continuing right now. The selector chooses them, the
  dispatcher refuses them, the cycle is wasted, and nothing tells the selector to
  stop — `trace.jsonl` still shows 34 `reflect_on_affect` + 17
  `reflect_on_emotion_model` selections in the window.

## I. Metacognition sees everything and changes nothing; its instruments disagree

**Evidence:** `metacog_log.json`, `calibration_state.json`, `monitor_verdicts.json`,
`prediction_domain_stats.json`, `working_memory.json`.

- The same pattern — *"I've been underconfident lately — things have gone about
  0.10 better than I predicted. I can trust my judgement a bit more and act
  sooner."* — is logged **every ~12 seconds**, written into working memory,
  chunked, and re-stored, and the underconfidence bias is *worsening* (−0.078 →
  −0.096 within minutes during this audit). The insight loops; the confidence
  parameter it refers to never moves. Same for "Reflection–action imbalance"
  notes: detected, archived, ignored.
- `metacog_log` entries have empty `trace` and `entries` fields — the log is
  patterns-only; whatever was supposed to populate evidence doesn't.
- `monitor_verdicts.json`: the last 40 verdicts are **all `stuck_step`, all
  honored, bias ramped to 1.00** — the monitor has become a constant.
- `prediction_domain_stats.json` is internally inconsistent: COGNITIVE `accuracy`
  0.9696 vs `correct/total` = 1117/1734 = 0.644; TECHNICAL 31/31 correct but
  accuracy 0.599; PLANNING 0/4 correct, accuracy 0.500; INTERNAL total=1,
  correct=1, accuracy 0.575. Whatever blend of EMA and counters produces
  `accuracy`, the two bookkeeping systems don't reconcile, and downstream routing
  ("strong domain 'COGNITIVE' (conf=0.93) — fast-path symbolic") trusts the
  inflated one.
- Rule `16f169db3b` is verified at `conf 1.000 → 1.000` every cycle — confidence
  pinned at the ceiling, the verifier a no-op for it. It's the rule emitting the
  self-model's eternal "No strong signal either way — continuing steady."
- `depth_stats.json` has 30 samples total (depths 1 and 3 only) across 2,712
  cycles — deep deliberation effectively never engages.

## J. Social layer: still nobody home

**Evidence:** `known_persons.json`, `chat_log.json`, `speech_log.json`, `speech_scores.json`.

- `known_persons.json` now holds **five+ `"display_name": "someone",
  "person_type": "unknown"` records**, each with `session_count: 1` and empty
  notes — every contact mints a fresh anonymous person; nothing merges them, and
  jon (old §4) still doesn't exist as a named person ~24 h after introducing
  himself.
- Every user utterance is still classified `neutral / 0.0` despite the keyword fix
  (§A) — so either the chat path doesn't use the repaired model or intensity
  scoring is broken independently.
- Replies still deflect and leak: *"I think My sense of thinking is positive — it
  came up in: \"[Chunk: [metacog/pattern] Something feels slightly off..."* plus
  the recycled "What got you thinking about this?" closer.
- **Speech is one template.** Of the last 500 speech-log entries, there are **13
  distinct openings**; 365+ are literally `"I'm acting on my goal to grow and
  accomplish: <step name>"` (131× "Observe the current state", 125× "Reflect on
  what's been tried", 109× "Gather more context"). He announces plan-step labels
  aloud, hundreds of times, to an empty room.
- The speech evaluator still can't discriminate: `uncertainty__curious` avg 0.6224
  over 281 samples — the same frozen ~0.622 the last audit flagged, now with more
  decimal places.

## K. Subsystems that report success while doing nothing

**Evidence:** `dream_log.json`, `forgetting_log.json`, `regulation_log.json`, boot log.

- `dream_log.json`: 9 entries, every one
  `{"consolidation": "", "recombination": "", "processing": ""}` — the dream cycle
  runs, produces empty strings, and logs them as dreams. (Meanwhile the *symbolic*
  dream path does produce analogy-transfer items — into long memory, where nothing
  is ever forgotten, see §B.)
- `forgetting_log.json`: all-zero passes, every time (§B).
- `regulation_log.json`: 3 entries total for the whole window — regulation either
  barely runs or barely logs, while the impasse signal it exists to handle stays
  pinned (§E).
- `knowledge_graph` extraction is running on **regex because spaCy is not
  installed** (`No module named 'spacy'` at boot) — the junk-entity problem from
  old §8 ("+15%", "5h 5" as entities) is guaranteed to continue.
- `env_snapshot` logs `delta_reward=0.000 milestones+0 lm+0 tool+0 wm_grew=False
  thrash=True` — by his own environmental measure, nothing is changing and the
  thrash flag is set, yet per-action rewards average 0.55–0.70 (§D). The local
  reward signal and the environmental delta signal flatly contradict each other,
  and the bandit only hears the flattering one.

---

## Priority read

1. **Reaper/forgetting is a no-op → unbounded memory → 10 s cycles → death (B, K).**
   This is the only issue that kills the process. B1 fail + all-zero forgetting log
   + 1.9 MB cognition history is one causal chain.
2. **Reward shaping inversion (D, K):** introspection pays ~0.6, novelty pays 0.086,
   and env_delta says nothing real is happening. Until the reward function pays for
   *external* change, every learner in the stack will keep optimizing toward the rut.
3. **Setpoint override + always-exceeded stability budget (E):** the regulator
   vetoes exploration and clips all affect, which freezes stagnation at 0.0,
   pins impasse at 0.85, and starves the bandit of exploration data. B2 can never
   pass in this configuration.
4. **Goal-store divergence and boot-time wipes (C):** comp_goals emptied at boot,
   goals_mem diverged, milestones met out of order, instant completions — the goal
   lifecycle needs one source of truth before any goal-level metric means anything.
5. **Speech path ignores `llm_enabled` and templates everything, including death (G, I, J).**
6. **Selector/dispatcher mismatch wasting cycles (H)** and **metacog with no
   actuator (I)** — both are "the system knows, the system doesn't act" wiring gaps.
