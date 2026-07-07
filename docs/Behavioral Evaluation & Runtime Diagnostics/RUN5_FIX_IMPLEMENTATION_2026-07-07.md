# Run 5 Fix Implementation (2026-07-07)

Implements the fix list in `demo_runs/2026-07-05-run/2026-07-05_findings.md`
(F1–F9), the plan produced by the Run 4 staging life. Every fix names its
mechanism, the files changed, and the Run 5 observable it must move.
Gate at build time: ruff clean, mypy clean, **1393 tests green** (18 new in
`tests/brain/test_run5_findings_fixes.py`, plus rewritten
`test_compose_section_loop.py` / `test_native_composition.py` /
`test_forced_production.py`).

---

## F1 🔴 compose_section: grounded-or-failed, counted retries, lane learning

**(a) Grounded or failed.** `brain/agency/compose_section.py` rewritten; the
fixed 4-paragraph template (the 197 KB / 664-paragraphs-4-unique stamper) is
deleted. Material comes from real stores via the new
`brain/cognition/section_material.py` — credited ledger artifacts (bodies via
the effect_artifacts sidecar), long-memory findings, causal edges on the
topic. Fewer than 2 usable sources → `"nothing to synthesize"` step FAILURE.
LLM and native-organ drafts are both seeded from the material; no capable
writer → `"could not draft"` failure. The ledger's dedupe verdict is read
BEFORE the manuscript is touched — a non-novel draft appends nothing. Sections
that draw on ledger artifacts credit `mark_reused` on those hashes (tier-3).
(`section_material` lives in cognition, not agency, because `symbolic →
agency` already exists — an agency → symbolic import would close a package
cycle.)

**(b) Durable attempt cap + escalation.** New
`brain/cognition/planning/step_attempts.py`: per-(goal, step) attempt counts
in `step_attempts.json` — the old in-dict `_step_attempts` reset every tick
because the executive queue re-pulls goal dicts from the v2 store (why one
step retried 146× with the map empty). Retry pacing + the give-up policy moved
next to the counters (`handle_unexecuted_step`); a goal that abandons
`GOAL_GIVE_UP_MAX=3` steps at the cap is marked FAILED
(`steps_unreachable: …`) instead of cycling retry→advance→replan forever.
`goal_execution.py` now delegates to it.

**(c) Lane-blind learning closed.** `effect_ledger.record_effect` stashes
`context["_last_effect_outcome"]` (credited / novelty / significance) on every
record, both credited and dedupe. `executive.py::_outcome_reward` consumes it:
a deduped effect posts **0.05** (near-failure), a credited one posts
`0.3 + 0.45·novelty·min(1.5, sig)` — into the same `action_reward_ema` the
conscious lane learns from. `awaiting_deliberate` no longer pays the flat 0.6.
Also fixed: `step_execution._result_is_real` now honors an explicit boolean
`success` field — compose_section's dict had none of the text keys, so the
step-runner was blind to its verdict in both directions.

**Run 5 shows:** manuscript sections cite sources or the goal fails honestly;
`compose_section` EMA visibly moves; no step retried >5× without a status
change (`step_attempts.json` is inspectable).

## F2 🔴 Aspirations can be edited, never failed

- Shared `is_aspiration()` in `goal_criteria.py` (kind/tier/_aspiration/id
  markers).
- `mark_goal_failed` REFUSES aspirations (logged).
- `fail_overdue_artifact_goals` walker skips them (aspiration-output_producing
  is artifact-gated by its driven_by tag — it was being deadline-failed).
- `executive._build_queue` excludes them (they sat in_progress/HIGH and were
  planned like tasks; the milestone gate then failed them round-robin).
- Criteria rendering fixed: the failure reason now reads
  `text|label|desc|criterion|description` instead of `m.get("text", "?")` —
  no more `['?', '?']`.
- Boot invariant in `brain/loop/boot.py`: `_ensure_aspirations()` runs before
  the first cycle (the lazy re-seed masked the loss all run; death unmasked it).

**Run 5 shows:** 0 failure rows with `goal_id` starting `aspiration-`; all
four aspirations present at death.

## F3 🔴 Note bodies are artifacts, not memories

- `record_effect` captures every CREDITED row's body into the
  content-addressed `effect_artifacts/` sidecar at the single record
  chokepoint (covers satiety learned notes, produce_and_check, memos, notes).
- Sidecar cap raised 600 → 4000 files (a few MB) so a whole life's bodies stay
  resolvable.
- Signal-to-markup intake gate: `text_sanity.strip_markup_noise` /
  `prose_ratio`; applied in `fetch_and_read` (reject pages <50% prose after
  stripping) and centrally in `update_long_memory` for `world_perception`
  entries (<40% prose or <40 chars after stripping → not stored). No more
  Twitter CSS memories.

**Run 5 shows:** every `note_novel` ledger row's hash resolves to a readable
body at death; no long_memory entry contains stylesheet text.

## F4 🟠 Research memos exist again (reuse unblocked)

`web_research._write_research_memo`: a `research_topic` / `fetch_and_read`
result ≥400 chars is written as `data/goals/artifacts/<goal>/memo_<topic>.md`
and recorded as a `file_write` effect with `metadata.path` — so the A2
path→hash index resolves it and the builds-on scan / `mark_reused` finally
have a population. Ledger dedupe stops duplicate memo stamping.

**Run 5 shows:** ≥3 memos on disk; ≥1 `mark_reused` row (compose_section's
material credit is a second reuse source).

## F5 🟠 Generator monopoly capped by ATTEMPT rate

- `intrinsic_generators._attempt_rate_quota`: an aspiration whose rolling
  generated count exceeds 3× its attempted count (≥12 generated) keeps ONE
  candidate in the pool until the backlog drains.
- `generate_intrinsic_goals` cooldown stretches up to 3× when total
  generated > 3× attempted (pool-depth backoff).
- `score_actions`: pool-depth term demotes `generate_intrinsic_goals` by up to
  −0.5 when the ratio is deep (cached per cycle).

**Run 5 shows:** generated:attempted < 3:1; no aspiration >50% of generated.

## F6 🟡 Frontier children get a real definition-of-done

- `_maybe_close_on_tier`: a goal with a ≥2-step plan may not satiety-close
  before 2 steps completed (or a milestone genuinely met) — kills the
  research_topic→satiety-note 90-second completion.
- Per-life title completion counts (`intrinsic_helpers.note_title_completion`,
  routed through both completion chokepoints): cooldown doubles per repeat
  completion, hard cap at 5 per life (`title_respawn_blocked`). Enforced in
  the symbolic generator pool AND `long_term_driver.spawn_frontier_subtask`.

**Run 5 shows:** median_seconds_to_complete back over 600 s; no title
completed >5× per life.

## F7 🟡 The user boundary sealed, the mouth habituates

- Inbound: `_open_question_goals` skips entries with user provenance
  (`event_type` starting "user", `[input/…]` records) and never treats the
  live `latest_user_input` as Orrin's own open question.
- Outbound: `talk_policy._self_speech_allowed` — self-initiated speech has a
  90 s minimum-interval floor, and near-identical content (token-Jaccard
  ≥0.75) requires an escalating interval (10 min × 2ⁿ). User replies are never
  gated.

**Run 5 shows:** no goal candidate titled with a verbatim user utterance;
distinct-utterance ratio > 0.3.

## F8 🟡 Silent deaths are first-class data

New `brain/utils/heartbeat.py`: `beat()` stamps `heartbeat.json` ~1/min from
the main loop; `shutdown_loop` marks clean shutdowns; boot runs
`check_silent_death()` — a >5 min gap without a shutdown record writes a
`silent_death` event (gap, last cycle) to `lifecycle_events.jsonl` and the
activity log. (For real runs also prefer `caffeinate -dims`/LaunchAgent — ops,
not code.)

## F9 🟢 Hygiene

- Final thoughts: retrieval-scaffolding memories ("similar situation",
  "similarity", "(GENERAL") excluded from the quote pool, and the final text
  ships through `strip_scaffold` + `strip_internal` (the veil).
- `problem_workaround` / `problem_resolved` added to the EMA's known
  pseudo-action channels (the 07:42Z "unregistered action" warning).

## Untouched (proven in Run 4, per findings §"must NOT be touched")

A1/v2→v1 event bridge; ledger dedupe/novelty gating; production handoff
wiring; final-thoughts write path (C3.2); housekeeping timers.

## Module hygiene forced by the ratchets

- `goal_execution.py` 621→581 (retry policy → `step_attempts.py`),
  `goal_outcomes.py` 618→550 (`fail_overdue_artifact_goals` →
  `goal_deadlines.py`, re-exported).
- No new package edge: material gathering lives in `cognition/`, not
  `agency/`, so `agency → symbolic` was never added (symbolic → agency
  already exists; the reverse edge would be a cycle).

## Run 5 gate (from the findings, unchanged)

Clean newborn via `reset_orrin.py`, baselines captured, then: F1 grounded-or-
failed synthesis + moving daemon EMA; F2 zero aspiration failures, four alive
at death; F3 every note body resolvable; F4 ≥1 `mark_reused`; S2 recovers
(median >600 s) while S5/S6/S8 hold.
