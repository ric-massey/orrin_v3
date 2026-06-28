# Function-Name Rename — Completing the Analogue Removal

Date: 2026-06-27
Status: **Tier A DONE 2026-06-27** (P1+P2+P4 implemented, `make verify` 1105 passed,
frontend typecheck+build green). Tier B **FROZEN**.
**Tier C DONE 2026-06-28** — `affect_stability → signal_stability` migrated: added the
read-old/write-new shim to `data_schema.MIGRATIONS` (control_signals_state.json `top`),
renamed all 84 code refs + `arbiter._SCALAR_TARGETS` + the runtime_coupling wire field +
4 test files, ran the one-time backfill (on-disk key flipped, value 0.8646 preserved →
restart continuity verified). Full suite **1160 passed, 1 skipped**; headless single-cycle
boot clean. The only biological residue remaining is the 5 **deliberately-frozen Tier-B
action names** (see below). The rename is otherwise complete.
Parent: `ANALOGUE_REMOVAL_PLAN_2026-06-26.md` (Phases 1–4 DONE). This plan finishes
the one tier that plan **deliberately left undone**: the biological **function /
method / symbol names** inside the already-renamed modules.

## Implementation notes (2026-06-27, deviations from the proposal)

Three judgment calls made during execution, all in the conservative direction:

1. **Frozen set widened from 5 to 7.** The proposal listed `read_vitals` and
   `reflect_on_emotion_sensitivity` under Tier A, but both are demonstrably
   *dispatched cognition actions carrying learned weights* — they key
   `decision_stats.json`, `bandit_state.json`, `action_reward_ema.json`, and
   `action_associability.json`. That is exactly the silent-reset risk class the
   plan froze Tier B to avoid, so they were **frozen** (def + dispatch strings +
   learned keys untouched) rather than migrated. Residue is therefore 7
   biological-flavored names, not 5. (The other Tier-A names that appeared in
   `context.json`/`cognitive_functions.json` are regenerated snapshots, not
   learned weights — safe, and renamed.)
2. **`affect_utils.py` → `signal_lexicon_utils.py`, not `signal_utils.py`.** The
   proposed target `signal_utils.py` was already taken by an unrelated module
   (`create_signal`/`gather_signals`). `signal_keyword_utils.py` was taken by the
   other renamed util (`affect_signal_utils.py`, different `detect_signal_keyword`
   return type). So the keyword→label lexicon module got a distinct name and its
   6 `detect_signal_keyword` importers were redirected accordingly.
3. **Tier C (`affect_stability`) deferred, not executed** — it remains a persisted
   scalar and follows the parent plan's `KEY_RENAMES` procedure when/if done; it
   is internal hygiene only and untouched here.

Out-of-scope residue kept by the proposal's own scoping: path consts other than
the two named (`AFFECT_MODEL_FILE`, `CUSTOM_EMOTION`, `EMOTIONAL_SENSITIVITY_FILE`),
the `consolidation_emotional_logic.py` *filename*, and wire/persisted keys
(`affect_state`, `affect_quadrant`, `_pending_affect`) — all unchanged by design.

## What this is

The analogue-removal work renamed *files, modules, data files, API routes, signal
keys, and UI copy*. It stopped at the **function-symbol layer** on purpose (parent
plan §"More implementation cautions" #4: "Function-name renames break learned data
too… Prefer not renaming public function names at all unless they are themselves
biological").

The result is the inconsistency we now have: a module says `signal`, the function
it exports still says `affect`:

```python
from brain.control_signals.update_signal_state   import update_affect_state
from brain.control_signals.apply_signal_feedback import apply_affective_feedback
from brain.control_signals.reflect_on_signals    import reflect_on_affect
from brain.control_signals.signal_drift          import check_affect_drift
```

Those function names **are themselves biological** (`affect`/`emotion`/`mood`/
`wonder`/`vital`/`dream`), so by the parent plan's own rule they are *in scope* —
they were left only because some of them key learned data. This plan renames them,
with the learned-data migration handled explicitly.

The **Term Map in the parent plan is the single source of truth** for old→new.
Every new name here resolves to that table.

## The one fact that controls all the risk

The cognition registry (`brain/registry/cognition_registry.py`) builds its dispatch
table by reflection: `extract_callables(mod, _ALLOWED_PREFIXES)` → `{name: callable}`
where **`name` is the function's `__name__`**. The selector then chooses actions by
that string, and the system *learns* on it:

- `brain/data/signal_function_map.json` is keyed `signal → {function_name: weight}`
  (verified: `motivation → {wikipedia_search: …}`). Function names are **second-level
  learned keys.**
- The hand-authored selection tables hardcode the strings: `selection/scoring.py`,
  `selection/tag_sets.py`, `selection/pick.py` (`"reflect_on_affect"`,
  `"investigate_unexplained_emotions"`, `"check_affect_drift"`,
  `"reflect_on_emotion_model"`, …).
- `meta_rules.json`, `decision_stats.json`, `action_reward_ema`, goal-provenance
  `recent_picks`, and exploration/habituation stores all reference action names.
- The frontend maps them too: `frontend/src/lib/thoughts.ts`
  (`update_affect_state: …`, `reflect_on_affect: …`).

**Therefore renaming a *dispatched cognition function* = renaming a wire/learned
identifier**, and silently resets learning unless migrated in lockstep. Renaming a
*non-dispatched* function (private helper, internal API) is safe and mechanical.
That split defines the tiers below.

---

## The three tiers

### Tier A — Internal symbols (safe, mechanical) — the bulk
Functions **not** used as dispatch strings and **not** persisted: private helpers
and cross-module internal APIs. Rename the `def`, update every import/call site in
the same commit, `make verify`. No data migration, no frozen-surface concern.

Examples (non-exhaustive):
`commit_affect`→`commit_signals`, `submit_affect`→`submit_signal`,
`queue_affect_change`→`queue_signal_change`, `drain_affect_queue`→`drain_signal_queue`,
`update_affect_state`→`update_signal_state`, `apply_affective_feedback`→`apply_signal_feedback`,
`render_affect_state`→`render_signal_state`, `normalize_affect_state`→`normalize_signal_state`,
`describe_dominant_affect`→`describe_dominant_signal`, `_dominant_affect`→`_dominant_signal`,
`detect_affect`→`detect_signal`, `deliver_affect_based_rewards`→`deliver_signal_based_rewards`,
`get_all_affect_names`→`get_all_signal_names`, `process_affective_signals`→`process_signals`,
`_emit_affect`→`_emit_signal`, `_route_affect`→`_route_signal`, `_parse_affect`→`_parse_signal`,
`_harvest_daemon_affect`→`_harvest_daemon_signal`, `_bump_problem_affect`→`_bump_problem_signal`,
`recommend_mode_from_affect_state`→`recommend_mode_from_signal_state`,
`affect_driven_mode_shift`→`signal_driven_mode_shift`, `_affect_enabled`→`_signals_enabled`,
`merge_into_affect_state`→`merge_into_signal_state`, `_describe_affect_state`→`_describe_signal_state`,
`_infer_affective_state`→`_infer_signal_state`, `detect_affectal_inhibition`→`detect_signal_inhibition`,
plus the **emotion** family (`_emotion_name`, `_snapshot_emotion`, `_emotional_salience`,
`get_emotionally_salient_wm`, `_emotion_resonance`, `apply_emotional_contagion`,
`_apply_emotional_uplift`/`_drain`, `_anticipatory_emotions`, `_semantic_emotion_prior`,
`emotional_delta_reward`, `dreams_and_emotional_logic`→`idle_consolidation_logic`,
`_emotional_quality`, `_emotional_valence`, `_emotion_congruence`, `_fix_emotion_dict`,
`_sanitize_emotion_state`, `seed_default_emotion_keywords`→`seed_default_signal_keywords`,
`load_emotion_keywords`→`load_signal_keywords`, `reflect_on_emotion_sensitivity`,
`_find_target_emotion`→`_find_target_signal`),
the **mood** family (`update_mood`→`update_smoothed_state`,
`mood_delta_modifier`→`smoothed_state_delta_modifier`, `_dominant_mood`,
`_derive_*_mood`→`_derive_*_state`),
the **wonder** family in `novelty.py` (`apply_wonder_bias`→`apply_novelty_bias`,
`detect_wonder_trigger`→`detect_novelty_trigger`),
the **dream** family (`crystallize_dream_insights`→`crystallize_idle_insights`,
`run_symbolic_dream`→`run_symbolic_consolidation`, `_dreaming_now`/`_is_dreaming`→
`_consolidating_now`/`_is_consolidating`),
and the **vital** family (`read_host_vitals`→`read_host_resources`,
`read_vitals`→`read_resources`, `_system_vitals`→`_system_resources`,
`vital_on_warn`→`resource_on_warn` …, `maybe_start_vital_calibration_stress`→
`maybe_start_resource_calibration_stress`).

Also rename the two **module files** the parent plan missed:
`brain/utils/affect_utils.py` and `brain/utils/affect_signal_utils.py`
→ `signal_utils.py` / `signal_keyword_utils.py` (`git mv` + fix importers), and the
`paths.py` constant identifiers the parent plan left to bound blast radius:
`AFFECT_STATE_FILE`→`SIGNAL_STATE_FILE`, `EMOTION_FUNCTION_MAP_FILE`→
`SIGNAL_FUNCTION_MAP_FILE` (the filenames they point at already moved).

### Tier B — Dispatched cognition-action names — **FROZEN (decided 2026-06-27)**
Functions whose `__name__` is a selectable action and is therefore **learned/persisted**.
Members in the biological set:

| Frozen action name | (would-be name, NOT applied) |
| --- | --- |
| `reflect_on_affect` | ~~`reflect_on_signals`~~ |
| `reflect_on_emotion_model` | ~~`reflect_on_signal_model`~~ |
| `investigate_unexplained_emotions` | ~~`investigate_unexplained_signals`~~ |
| `check_affect_drift` | ~~`check_signal_drift`~~ |
| `discover_new_emotion` | ~~`discover_new_signal`~~ |

**Decision: FREEZE these as stable wire identifiers** (same treatment as the signal
vocabulary). The registry name (`__name__`), the learned `signal_function_map.json`
keys, the selection tables, and the frontend `thoughts.ts` all already agree on these
strings — so **leaving the functions untouched keeps everything consistent and working.**
Do **not** rename the `def`, the selection-table strings, or the learned-data keys.
No migration is performed; the learned-data risk is avoided by not incurring it.

Rationale: only ~5 names, all cosmetic; renaming them would require a nested learned-key
migration with a *silent* reset failure mode (zeroed weights, no error). Not worth it.
The residue is 5 biological-flavored action names — accepted.

*(If this is ever revisited, the migration recipe is preserved in the next section and
in git history of this file; it is not deleted, just not executed.)*

(`attempt_regulation`, `reflection`, `look_around`, `adapt_subgoals`, etc. are
**not** biological — leave them too, for the ordinary reason.)

### Tier C — Persisted scalar key `affect_stability` (Phase-4-class) — separate, gated
`affect_stability` is **not a function** — it is a persisted scalar (in
`control_signals_state.json`, `context.json`, `motivation_state.json`,
`long_memory.json`, `trace.jsonl`, …; 84 refs) and a member of
`arbiter._SCALAR_TARGETS`. Renaming it in place breaks restart continuity and old
backups, so it follows the **parent plan's persisted-key procedure**, not a code
rename: add `affect_stability → signal_stability` to `data_schema.KEY_RENAMES` with a
read-old/write-new shim + one-time backfill. Do this **last**, as its own gated commit,
or defer it (it is internal hygiene only).

---

## Learned-data migration — NOT EXECUTED (preserved for reference only)

> Under the Tier-B **freeze** decision above, no function-name keys in learned data
> are renamed, so this migration is **not performed**. It is kept here only as the
> recipe to follow *if* Tier B is ever revisited.

`signal_function_map.json` keys function names **one level down** under each signal,
so the existing `_rename_keys` (top-level / single named-nested dict) does **not**
cover it. Add a small helper to `data_schema.py` (or the one-time backfill script):

```python
def _rename_nested_value_keys(d, mapping):   # {parent: {fn: w}} -> rename fn across all parents
    changed = False
    for parent, sub in list(d.items()):
        if isinstance(sub, dict):
            changed |= _rename_keys(sub, mapping)
    return changed
```

Wire a `FUNCTION_RENAMES` map (Tier-B old→new) into:
- `signal_function_map.json` (nested second-level keys),
- `meta_rules.json` (rule action references),
- `decision_stats.json` / `action_reward_ema` (per-action stats keyed by name),
- goal-provenance `recent_picks` (list values, not dict keys — handle as list-rewrite),
- any exploration/habituation store keyed by action name.

Run the backfill against the Phase-0 data snapshot first (idempotent), then live,
exactly as Phase 4.9 did. **Acceptance:** after migration, a restart loads the old
learned weights under the new action names — `signal_function_map.json` shows the new
keys with the *same* weights, not zeros.

---

## Execution order (low blast-radius first)

```
P1  Tier A — pure-internal helpers (emotion/mood/wonder/dream/vital families)
P2  Tier A — cross-module affect/signal API (commit/submit/update/reflect/...) + paths.py consts + the 2 util module files
—   Tier B — FROZEN, no work (see decision above)
P3  Tier C — affect_stability persisted-key migration (gated; or defer)
P4  Tests — rename helper/identifier refs in tests alongside each phase; final test-file name sweep
P5  QA / leak sweep / sign-off
```

Each phase = one (or a few) independently-revertable commits on a dedicated branch
(suggest `function-rename` off the current tree), `make verify` + frontend build
green between phases. Same backup discipline as the parent plan's Phase 0 (safety tag
+ git bundle + data tar) **before P3** (Tier C), since it touches persisted state.
P1–P2 are pure code renames with no data risk.

## Mechanics per rename
- `git mv` for the two remaining module files; targeted reviewed search-replace for
  identifiers **within the concept's files**, never repo-wide blind.
- Update imports/call sites in the **same commit** (`grep -rn '\bOLDNAME\b'` across
  `brain backend goals tests runtime supervisor reaper`).
- For Tier B, the exact-string grep (`"oldname"` / `'oldname'`) must come back empty
  in code after the rename, except in `data_schema.FUNCTION_RENAMES` and verbatim
  archived logs.

## Inherited cautions (unchanged from parent plan)
- **Scientific citations stay verbatim** — don't strip a citation because it sits by
  the word "affect."
- **LLM-prompt wording is behavior, not chrome** — this plan renames *symbols*, not
  prompt copy. Do not touch "how you feel" prompt strings here.
- **Old log strings are data** — a post-rename grep of historical `*.json`/`*.jsonl`
  will still show old words; that is verbatim history, not a leak.
- **Borderline-keep** — `reflection`, `introspection`, `reward`, `heartbeat`,
  `watchdog`, `world_model`, `setpoint` stay.

## Acceptance (whole plan)
- No biological function/method/symbol name remains in `brain backend goals runtime
  supervisor reaper` except (a) the **5 frozen Tier-B action names**, (b) the frozen
  Tier-C key until P3, (c) `data_schema` rename maps, (d) verbatim archived data/logs.
- `make verify` green (currently 1,099 tests) and `cd frontend && npm run typecheck
  && lint && build` green after every phase.
- A clean runtime restart loads pre-rename `brain/data` with no learning reset — and
  because Tier B is frozen, `signal_function_map.json` is **untouched**, so learned
  weights are preserved trivially (no migration to get wrong).
- Module names and their exported symbols agree everywhere except the 5 frozen
  action names (the inconsistency this plan exists to close, minus the accepted residue).

## Risk register (delta from parent)
| Risk | Mitigation |
| --- | --- |
| Renaming a dispatched fn resets learned weights | **Avoided** — Tier B frozen; those functions/keys are not touched |
| Registry name follows `__name__`, so a def rename would silently change the action string | **Avoided** — the dispatched functions are out of scope (frozen) |
| `affect_stability` rename breaks restart/backups | Tier C = persisted-key procedure (KEY_RENAMES + read-old shim + backfill), gated/deferrable |
| Bulk find-replace hits unrelated code | Concept-by-concept, within-file, `make verify` between |
```
