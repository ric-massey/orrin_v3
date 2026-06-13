# Phase 2 Behavioral Deduplication Report

> **Note (2026-06-01):** Term names here were updated to the current computational vocabulary
> (dopamine→reward_signal, fear→threat_level, etc.). The analysis predates a later refactor —
> notably the three `_reward` helpers are **no longer byte-identical** (`fragmentation.py`'s has
> drifted to a different signature), so the "TRUE-DUPLICATE → merge" call no longer holds.

> **Rule**: Only merge functions classified as TRUE-DUPLICATE.
> Do NOT merge DISTINCT-CHANNEL or CANONICAL functions.
> Dead functions require zero-caller proof before removal.

---

## SPEAK GATE — 8 functions / 4 files

| Function | File | What it does | Reads | Writes/Returns | Classification |
|----------|------|--------------|-------|----------------|----------------|
| `pre_speak_check` | `behavior/pre_speak_check.py` | Anticipatory self-consciousness gate: adapt register, choose silence, or pass text as-is before it enters the voice pipeline | Person model (tone, style), relationship arc, urgency, message length | `(text, disposition)` tuple — "as_is" / "revised" / "silent" | **CANONICAL** — unique pre-filter that consults person model before speak |
| `maybe_speak_aloud` | `behavior/speak.py` | Self-talk gate: allows Orrin to speak to himself when exploration_drive is elevated and the user is absent | Affect state (exploration_drive), user-absence flag in context | Speech string via `should_speak`, or `""` | **DISTINCT-CHANNEL** — soliloquy / self-talk path only |
| `should_speak` | `behavior/speak.py` | Main speech emission gate: enforces timing cooldown, repetition suppression, affect inhibition (threat_level/social_penalty), routes through tone derivation and person-model register | User presence, timestamps, opinion/world hooks, threat_level/social_penalty, person model | Speech via `speak_final`, or `""`; updates `context["last_tone"]`, `context["awaiting_response"]` | **CANONICAL** — the live runtime decision point for all user-facing speech |
| `speak_final` | `behavior/speak.py` | Final formatting: prepend autobiographical hook, rephrase with tone/register, truncate, log to chat, emit SSE, update speaker state | Thought text, tone_data, self_model, long_memory, recent_tones, goal/intention | Formatted speech string (≤800 chars); persists SPEAKER_STATE_FILE, chat log, SSE event | **CANONICAL** — final output formatter; not a gate |
| `_is_speakable` | `think/speech_memory.py` | — function not found at this name (may have been renamed/removed). The file contains `retrieve_relevant` instead. | — | — | **INVESTIGATE** before touching |
| `talk_policy_allows` | `think_utils/talk_policy.py` | Hard boolean gate: enforces cycle-based cooldown and stagnation_signal-driven monologue suppression | Action type, cycle_count, last_user_cycle, last_speak_cycle, stagnation_signal emotion | `bool` | **DISTINCT-CHANNEL** — operates at the cycle/action-selection level, upstream of `should_speak` |
| `talk_policy_score_bias` | `think_utils/talk_policy.py` | Soft policy bias for the action selector | Action type, cycle_count, stagnation_signal | `float` bias (−1.0 to +0.1) | **DISTINCT-CHANNEL** — soft complement to the hard gate; different mechanism |
| `speak_text` | `think_utils/talk_policy.py` | Routes raw text through speech_gate (emotion-aware pipeline) then delegates to `should_speak` | Raw text, user_input, affect_state, speech_gate result | Speech via `should_speak`; emits REPLY to stdout, updates last_ai_timestamp, appends to speech_log | **CANONICAL** — entry point from the inner loop; wires speech_gate → should_speak |

### Speak gate runtime path
```
talk_policy_allows          # cycle-level hard gate
  → speak_text              # routes through emotion-aware speech_gate
    → pre_speak_check       # person-model / register anticipation
      → should_speak        # final timing + inhibition gate
        → speak_final       # format + emit
```

**Merge candidates**: None. Each node does distinct work in a pipeline.
**Action**: Confirm `_is_speakable` presence — if absent, remove from the brief's list.

---

## REWARD — 22 functions / 15 files

### Generic `_reward` helpers (3 files)

| Function | File | What it does | Reads | Writes/Returns | Classification |
|----------|------|--------------|-------|----------------|----------------|
| `_reward` | `think_utils/execute_cognitive_actions.py` | Thin wrapper: calls `release_reward_signal` for add_goal / update_belief / revise_self_model / log_thought actions | `context` dict | None; queues signal to `release_reward_signal` | **TRUE-DUPLICATE** (of the pattern — all three call the same sink with same signature) |
| `_reward` | `think_utils/finalize.py` | Same wrapper: called during agentic_action / cognition_only / env_delta / self_question / social_deficit_reconnect | `context` dict | None; queues to `release_reward_signal` | **TRUE-DUPLICATE** |
| `_reward` | `cognition/selfhood/fragmentation.py` | Same wrapper: called on reconciliation outcomes (integrate / revise / commit / defer) | `context` dict | None; queues to `release_reward_signal` | **TRUE-DUPLICATE** |
| `release_reward_signal` | `affect/reward_signals/reward_signals.py` | Canonical sink: computes RPE, applies resource_deficit/motivation modulation, distributes reward_signal/stability_signal/etc. impulses | context, signal_type, actual/expected/effort | Updates `context["reward_trace"]`, `context["affect_state"]["core_signals"]`, persists raw_signals | **CANONICAL** |

**Merge recommendation**: The three `_reward` helpers are byte-for-byte identical wrappers. They CAN be merged into a single module-level helper imported by all three callers. However, because they are tiny (2–3 lines) and local, this is low-impact. Defer until Phase 3 cleanup.

**Do NOT touch** distinct reward channels: `goal_weighted_reward`, `check_and_reward_prediction_accuracy`, `check_and_reward_contradiction_resolution`, `check_and_reward_goal_closure`, `emotional_delta_reward`, `delta_reward`, `reward_meta_rule`, `novelty_penalty`. These are separate learning signals with different variance — merging would destroy the signal separation that drives learning.

---

## NOVELTY — 13 functions / 11 files

Not yet individually enumerated. Preliminary grep shows two clusters:
- Novelty **scoring** (compute a float from memory/embedding distance) — `memory/novelty.py`
- Novelty **reward release** (call `release_reward_signal` with `novelty` type) — scattered callers

**Status**: REVIEW-FIRST. Do not merge without per-function enumeration. Likely finding: scoring functions are DISTINCT-CHANNEL; reward-release callers may share a TRUE-DUPLICATE pattern.

---

## AFFECT UPDATE — 6 functions / 6 files

| Function | File | What it does | Reads | Writes/Returns | Classification |
|----------|------|--------------|-------|----------------|----------------|
| `update_mood` | `cognition/mood.py` | EMA mood (valence / energy / stability) from core_signals; amplifies mood-congruent emotions | affect_state, core_signals, MOOD_FILE | `{"valence","energy","stability","updated_at"}`; persists MOOD_FILE; amplifies core_signals in-place | **CANONICAL** — full EMA mood tracker |
| `update_mood` (valence-only) | `affect/affect_dynamics.py` | Valence-only update for habituation tracking | habituation state | Internal valence float | **DISTINCT-CHANNEL** — computes a single field for a different subsystem |
| `update_affect_state` | `affect/update_affect_state.py` | Per-cycle decay, velocity, hedonic adaptation, habituation, cross-inhibition, calls affect_buffer drain and mode recommendation | context["affect_state"], working_memory, decay_rate | Mutates context["affect_state"], persists AFFECT_STATE_FILE, calls set_current_mode | **CANONICAL** — master per-cycle affect update |
| `apply_affective_feedback` | `affect/apply_affective_feedback.py` | Post-action affective dynamics: domain confidence, emotion memory decay, mood collapse triggers, suppression, dominant emotion blend | affect_state, cognition_log (last 7), emotional_events buffer | Mutates context["dominant_emotions"], context["affect_narrative"]; calls release_reward_signal, update_affect_state, check_affect_drift | **CANONICAL** — post-action emotional processing |

**Action**: The two `update_mood` functions have the same name but different scopes. Rename `affect/affect_dynamics.py`'s `update_mood` to `_update_habituation_valence` to eliminate the name collision. **No merge** — they compute different things.

---

## SUMMARIZE — 11 functions / 10 files

| Function | File | LLM? | Pattern | Classification |
|----------|------|------|---------|----------------|
| `summarize_chat_to_long_memory` | `cog_memory/chat_log.py` | Yes | Load chat entries → LLM prompt → detect_affect → update_long_memory | **CANONICAL** — chat-specific path |
| `summarize_and_promote_working_memory` | `cog_memory/summarize_w_memory.py` | Yes | Load working_memory → summarize_memories() → LLM (optionally) → update_long_memory | **CANONICAL** — working-memory promotion path |
| `summarize_recent_thoughts` | `utils/summarizers.py` | No | Load LONG_MEMORY_FILE → filter by event_type → format string | **DISTINCT-CHANNEL** — local formatter, no LLM |
| `summarize_self_model` | `utils/summarizers.py` | No | Extract from self_model dict → condensed dict | **DISTINCT-CHANNEL** — local extractor, no LLM |
| `summarize_memories` | `utils/memory_utils.py` | No | Format memory list as string | **DISTINCT-CHANNEL** — local formatter, no LLM |

The two LLM-based summarizers share the **detect_affect → update_long_memory save pattern** but differ in their source data (chat log vs. working memory) and entry format. They are NOT true duplicates — different inputs, different outputs, different callers. No merge needed.

**Note**: If both callers ever need to summarize the same source, extract the shared LLM-prompt structure into a helper. Not justified yet.

---

## SALIENCE — 4 functions / 3 files

Not yet individually enumerated. Status: REVIEW-FIRST. Hold for next sprint.

---

## WORLD MODEL — 4 functions / 3 files (two `update_world_model`)

| Function | File | What it does | Reads | Writes/Returns | Classification |
|----------|------|--------------|-------|----------------|----------------|
| `update_world_model` | `cognition/world_model.py` | **Symbolic** knowledge graph: extract entities, relations, facts, beliefs from long_memory; build causal patterns from decision_stats | LONG_MEMORY_FILE (last 30), DECISION_STATS_FILE, vocabulary.json, self_model | Persists SYMBOLIC_WORLD_MODEL (entities / relations / facts / beliefs / concepts / forces / events / causal_patterns); updates working_memory | **CANONICAL** — knowledge-graph world model |
| `refresh` / `update_world_model` | `embodiment/world_model.py` | **Timeseries sensory**: tracks CPU, file changes, network, circadian rhythms, social silence | sensory_stream, social_presence, drive_engine, file system, time | Persists WORLD_MODEL (time-series vitals); injects context["world_state"]; returns environment narrative string | **DISTINCT-CHANNEL** — machine-state / sensory world model |

**Finding**: Same name, entirely different semantics. One is "what do I know about concepts?" the other is "what is the machine doing right now?". **Do NOT merge.** Rename recommendation: rename `cognition/world_model.update_world_model` → `update_symbolic_world_model` to make the distinction explicit (low-priority, non-breaking change).

---

## SUMMARY — What to act on next

### Confirmed TRUE-DUPLICATEs (safe to merge, low priority)
| Item | Action |
|------|--------|
| `_reward` in execute_cognitive_actions.py, finalize.py, fragmentation.py | Extract to shared 2-line helper in `affect/reward_signals/`; import in all three |

### Name collisions (rename only, no merge)
| Item | Action |
|------|--------|
| `update_mood` in `affect/affect_dynamics.py` shadows `update_mood` in `cognition/mood.py` | Rename the dynamics version to `_update_habituation_valence` |
| `update_world_model` in `cognition/` vs `embodiment/` | Rename cognition version to `update_symbolic_world_model` |

### Confirmed DISTINCT-CHANNEL (do not merge)
- All 8 speak-gate functions — each is a distinct stage in the pipeline
- All named reward channels (goal_weighted_reward, novelty_penalty, etc.)
- Both `update_world_model` implementations
- Both `update_mood` implementations
- All 5 summarize functions (3 local formatters + 2 LLM-save paths with different sources)

### Still to review (not blocking)
- NOVELTY group (13 functions / 11 files)
- SALIENCE group (4 functions / 3 files)
- Confirm `_is_speakable` existence in `think/speech_memory.py` (not found — may be dead or renamed)
