# Behavior Fix Record — 2026-06-10

Implementation record for every issue in `BEHAVIOR_AUDIT_2026-06-10.md`,
re-verified against the live run before fixing. Governing principle (same as
the 06-09 fix plan, now enforced in code): **the LLM is only a tool.** No
background cognition may call it; it is reachable solely through explicit tool
entry points. All fixes are deterministic/symbolic.

The changes are in the working tree (uncommitted). The running process still
executes the old code — **restart Orrin to pick these up.**

---

## 1. LLM-as-tool-only, enforced (audit §G)

- `utils/generate_response.py`
  - **Tool-only is now the DEFAULT** (`ORRIN_LLM_TOOL_ONLY=0` to disable).
    Only `_LLM_TOOL_CALLERS` = {`ask_llm`, `ask_llm_for_research`,
    `ask_llm_about_conversation`, `user_chat`} may reach the API. Everything
    else is served by the symbolic gate and then gets a clean
    `tool unavailable` — never a stub pretending to be generative output (the
    old tool-only mode returned an llm_stub template; that branch is removed).
  - **Auth circuit breaker**: a 401/invalid-key opens a 1-hour breaker. The
    4-call gpt-4.1 bursts every utterance (model_failures.txt) cannot recur.
- `utils/llm_gate.py` — `llm_available()` now **fails closed**: a torn/
  unreadable `model_config.json` reuses the last good `llm_enabled` value
  (deny before first good read). The fail-open `except: pass` was the hole
  that let a disabled LLM still produce live API calls.
- `symbolic/reasoning_router.py` — weak-domain LLM routing now uses the same
  default-ON tool-only check.
- `behavior/speech_pipeline.py` — the one path that answers a real user
  utterance is tagged `caller="user_chat"` (allowlisted); all self-directed
  speech stays symbolic.
- `think/think_utils/select_function.py` — `filter_llm_dependent(actions) or
  actions` restored the *unfiltered* pool whenever filtering emptied it; that
  is how `requires_llm` functions kept being selected while the tool was down.
  Now falls back to safe defaults instead.
- `cognition/planning/evolution.py` — `simulate_future_selves` returns the
  clean "tool unavailable" shape on an empty LLM response instead of raising
  "Result is not in expected structure".

## 2. Memory boundedness / pulse_too_slow death (§B)

- Verified: long memory is capped (2,000) and rule-forgetting zeros are
  by design (21-day idle threshold). The death-path contributor that IS real:
  multi-MB JSON parsed and rewritten under locks every cycle.
- `think/think_utils/finalize.py` — `reason.component_scores` (~1.8 KB/entry,
  53% of cognition_history.json) plus `candidates`/`neuro_boosts`/
  `energy_boosts`/`helpfulness_boosts` are stripped before persisting, with an
  in-place migration that slims the 500 existing entries immediately.
- `think/signal_router.py` — attention-history records keep only the top-5
  rounded core signals instead of the full ~800 B snapshot ×3/cycle; same
  in-place migration.
- Net: the two fattest per-cycle rewrite files shrink ~60–70%.

## 3. Setpoint override & stability budget (§E)

- `ORRIN_loop.py` — the Tier-1 critical override is now **bounded**: max once
  per 3 cycles per repair fn (cooldown), and if the same alert survives 5
  overrides the repair is declared futile and stands down for 50 cycles.
  Previously it re-fired EVERY cycle, making `update_affect_state` 22.7% of
  all decisions and vetoing every ε-exploration pick. Pacing state resets when
  the alert clears.
- `affect/arbiter.py` — **two-tier stability budgeting**: toward-setpoint
  (regulatory/decay) deltas are funded first; away-from-setpoint deltas split
  the remaining budget. The old single proportional scale throttled decay by
  the same ×0.43 as the noise, which is why `impasse_signal` stayed pinned at
  0.85 for days and `vitality` at 0.

## 4. Reward inversion (§D)

- `ORRIN_loop.py` — **outcome coupling**: introspective functions
  (`assess_goal_progress`, `update_affect_state`, `search_own_files`, all the
  reflect_*/check_* set) are capped at reward 0.35 on cycles where
  env_snapshot measured no observable change (env_r < 0.35). Introspection
  that actually ticks milestones / writes memory / resolves tools still pays
  in full. This breaks the 60%-of-decisions introspection monoculture at its
  source: the standing bonuses can no longer outpay reality.
- `cognition/seek_novelty.py` — root cause of seek_novelty's 0.086 avg
  reward: `vocabulary.json` ships none of the three phrase sections it needs,
  so every mode returned `""` and the no-novelty cap floored it. Added
  deterministic built-in fallback pools (`_DEFAULT_PHRASES`) used when the
  vocab sections are missing or the file is unreadable.

## 5. Goal lifecycle (§C)

- `cognition/planning/goals.py::mark_goal_completed`
  - **Idempotent**: re-marking an already-completed goal is a no-op (was
    re-firing the +1.0 reward and re-archiving — the zombie loop and the
    `median_seconds_to_complete=0.0` instant completions).
  - **Closes pending plan steps** (`skipped`, reason "goal completed") so a
    completed goal never carries live steps for the executive to grind on.
- `cognition/intrinsic_goals.py` — completed-title respawn cooldown raised
  **10 minutes → 6 hours**.
- The boot "wipe" of comp_goals was operator action (manual `.bak` naming);
  no code fix needed.

## 6. Selector/dispatcher mismatch (§H)

- `ORRIN_loop.py::_build_kwargs_for` — added `"memory"`/`"memories"` to the
  kwargs mapping; `reflect_on_affect(context, self_model, memory)` and
  `reflect_on_emotion_model` are now actually dispatchable.
- `_invoke_cognition` records any still-unsatisfiable function in
  `context["_undispatchable_fns"]`, and `select_function` drops those from
  the candidate pool — an undispatchable function can waste at most one cycle
  per session.

## 7. Speech degeneracy (§I, §J)

- `behavior/behavior_generation.py` — the unconditional `speak` proposal
  ("I'm acting on my goal to grow and accomplish: <step>"; 365+ of the last
  500 utterances, spoken to an empty room) now fires only when a user spoke
  within the last 10 minutes AND the announcement differs from the last one;
  otherwise the intent goes to the private log.
- `cognition/terminal.py` — final reflection is now **composed symbolically**
  from real end-of-life state (death reason, unfinished goals, open tensions,
  last thought, handoff advice). The LLM prompt path fell through to the
  symbolic *chat* gate, which pattern-matched the farewell as a greeting —
  that's why the death reflection was "I'm here. What's on your mind?".
- Speech evaluator's frozen 0.622: downstream artifact of the (already fixed)
  input replay loop; no change needed.

## 8. Metacog/monitor instruments (§I)

- `cognition/metacog.py` — the calibration observation ("I've been
  underconfident…") is rate-limited: only when bias moved >0.03 since the
  last note or after 100 cycles. It was writing the identical line to WM and
  metacog_log every ~12 seconds.
- `symbolic/rule_verifier.py` — confidence ceiling **1.0 → 0.98**. A rule
  pinned at exactly 1.0 made the verifier a permanent no-op for it
  (self-heals on the next touch of already-pinned rules).
- `symbolic/prediction_engine.py` — new `reliability` field per domain =
  min(graded EMA, Laplace-smoothed binary hit rate); `get_domain_error_rates`
  uses it. The graded EMA alone had drifted to 0.97 while the binary record
  said 0.64, and routers trusted the inflated number.
- Monitor kind-bias 1.0: working as designed (honored structural alarms get
  full voice); the stuck_step flood is fixed upstream in §5.

## 9. Rumination/incubation (§F)

- `embodiment/subconscious.py::_incubate`
  - Derived text (`[Chunk:`, `[Incubation`, `[metacog/`) can no longer be a
    seed **or** a match target — no more recursive self-quoting insights.
  - Seeds are tracked in a session-bounded seen-set, so the same candidate
    can't be re-incubated into duplicate notes (was 3 identical writes in one
    second).
- Tension TTL (200 cycles → downgrade to open question) already existed and
  works; the 1,116-cycle tension predates it and is already downgraded.
  Targetless brooding pressure subsides with the impasse decay fix (§3).

## 10. Social layer (§J)

- `cognition/selfhood/person_detector.py` — the anonymous fallback now
  **reuses the most recent unnamed person record** (bumping last_seen/
  session_count) instead of minting a fresh `anon_*` "someone" every session;
  a later introduction folds the whole history into the named record.
- `cognition/opinions.py` + `behavior/speech_pipeline.py` — speakability
  filters: internal bookkeeping (`[Chunk:`, `[metacog`, `[Incubation`,
  reward ticks, emoji-tagged telemetry) can never be quoted in a user-facing
  opinion or retrieved as reply material.
- Emotion classification: verified already fixed (populated keyword model,
  once-per-session warning); neutral scores on neutral questions are correct.

## 11. Silent no-op subsystems (§K)

- `cognition/dreaming/dream_cycle.py` — all-empty dream entries are no longer
  logged as dreams; an empty pass logs an explicit skip with the reason.
- `utils/tamper_guard.py` — `inspect.getsourcefile` is no longer called on
  instances (resolved to their class first) and builtin TypeErrors are
  expected, not warnings: both boot warnings gone.
- `cognition/knowledge_graph.py` — regex-fallback entity validation now
  rejects `+15%`-style tokens, mostly-numeric names, time fragments
  ("5h 5", "around hour"), and generic-opener phrases ("New files") while
  keeping proper nouns ("New York").
- token_log placeholder rows: side effect of the 401 bursts; ends with §1.

## Tests

- `tests/llm/test_no_error_leakage.py` — `_force_api_path` now resets both
  circuit breakers (the new auth breaker, tripped by the 401 tests, would
  otherwise fail-fast the rest of the module).
- Full suite: **511 passed**, 2 pre-existing failures in
  `tests/memory/embedder_test.py` (uncommitted embedder work, unrelated).

## Operational notes

- A `git stash` entry from this session still exists (`stash@{0}`) containing
  a snapshot of the working tree mid-session, including stale `brain/data/*`.
  All code was restored from it; it can be dropped (`git stash drop`) once
  you've confirmed the working tree looks right. Do NOT pop it — the data
  files inside are older than what the live process has since written.
- Restart Orrin to load the fixes; the running process predates all of them.
