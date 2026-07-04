# Data-file audit, part 2 — 2026-07-03 run (the other ~60 files)

The first audit (`DATA_FILE_AUDIT_2026-07-03.md`) covered the §8-relevant
stores, logs, and caps. This pass opens **every remaining file in both data
trees** — the learning/selection layer, the self-model and symbolic stores, the
social/ToM organs, the language organ, and the infra state — and reads each
against the run. Files are grouped by what they revealed, not alphabetically.

Written 2026-07-04, day after the run. Also records the **social tone-down**
applied that day (see §8).

---

## 1. The selection layer knows better than it chooses (S9 evidence deepens)

- **`signal_function_map.json`** — the learned affect→action couplings. One
  dominates everything: `exploration_drive → look_outward` at **0.706** (next
  highest coupling anywhere: 0.195). This is the missing piece of the S9
  puzzle: `look_outward` holds a 15% pick share with the *lowest* reward EMA
  (0.150) because exploration affect — his most common state — routes straight
  to it through this map. Selection follows *learned affect associations*,
  not learned value.
- **`decision_stats.json`** — lifetime per-action reward accounting:
  `look_outward` avg reward **0.216** over 3,961 scored picks; `leave_note`
  0.585; `assess_goal_progress` 0.34 over 9,097. The system *has* the
  knowledge that its favorite actions pay poorly; the ranker just weights
  other terms higher.
- **`attention_value_weights.json`** — 🔴 **numeric underflow**: `system`,
  `long_memory`, `internal`, and `fs_perception` have decayed to ~1e-25 —
  effectively hard-zero attention channels that can never recover through
  multiplication. `emotion` holds 0.403, `social_presence` 0.095. Needs a
  floor (same class of bug as drives pinning, in the opposite direction).
- **`bandit_state.json`** — per-affect-context buckets are live and sanely
  sized (e.g. the `exploration_drive` bucket: `assess_goal_progress` n=3,707
  q=0.34). **`meta_ctrl_bandit.json`** — the 4 meta-arms sit at 0.401 / 0.404
  / 0.407 / 0.420 after 11,332 pulls: the meta-controller has learned almost
  nothing distinguishes its arms.
- `cost_prediction_model.json` (per-action latency EMAs: `leave_note` 1.2 s,
  `look_around` 0.9 s, `assess` 0.5 s), `action_associability.json` (Pearce-
  Hall associability live, `cycle` 0.5 top), `outward_satiety.json`
  (`look_outward` satiety **1.0** at death — the satiety system was correctly
  screaming about the very action the affect map kept feeding),
  `function_chains.json` (nearly empty — chain-bonus learning barely engaged),
  `monitor_kind_bias.json` (`stuck_step` bias learned down to 0.43),
  `domain_action_credits.json` (only GENERAL/COGNITIVE ever credited).

## 2. Metacognition sees the disease with precision — and can't act on it

- **`metacog_rule_candidates.json`** — the pattern census for the whole life:
  **"Goal avoidance" detected 5,224 times** (promoted), "Affective stagnation"
  269, "Cognitive rut" 209, "Reflection–action imbalance" 21. Nearly half of
  all cycles matched the goal-avoidance signature. His dying advice ("act
  outward before reflecting inward") isn't intuition — his own metacog layer
  measured it five thousand times.
- **`behavior_changes.json`** — 250-entry cap, all recent rows goal_avoidance /
  emotional_stagnation, each carrying an `old_action → new_action` proposal —
  the monitor doesn't just detect, it prescribes. Combined with
  `monitor_verdicts.json` (300 stuck_step, 127 honored, loop unbroken) this is
  the same negative result as 06-17: **interventions applied, behaviour
  unchanged**.
- **`introspection_trust.json`** — COGNITIVE trust **0.31** over 3,730
  samples: he has learned to distrust his own introspective reports. Given the
  template-note pathology, that's arguably *well-calibrated*.
- `second_order_volition.json` — 200 Frankfurt-style stances, exactly 100
  `neutral` / 100 `endorse`, zero `resist` — second-order volition runs but
  has never once pushed back on a first-order desire.
- `rumination_loops.json` — 2 loops; the live one: *"A restlessness without a
  target. Something isn't right and I can't locate what."* (mode: brooding,
  return_count 2). Under a 84% social-presence ignition diet, the restlessness
  had a target; the surface just can't name it.

## 3. The binding→writeback loop is LIVE (undocumented win)

**`workspace_writeback.jsonl` — 6,787 rows, cycle 0 → 11,332**, source
`binding`, kind `situation`, salience mean 0.98, **4,785 rows carrying real
affect deltas**. The broadcast→substrate write-back loop (binding.py +
workspace_writeback.py, built 06-29) ran the *entire life* in its decaying
form and primed tokens each cycle. Neither the 07-02 nor 07-03 doc sets ever
mentioned it because it never misbehaved. Flagged here because (a) it's the
newest structural organ and it works, and (b) 1 MB/run append growth — needs
rotation eventually.

## 4. Theory-of-mind engaged the real person (new organ exercised)

**`relationships.json`** now holds `anon_d29c8a` alongside the four synthetic
peers — with a working ToM record from the 4-minute conversation:
**11 mental-state predictions, 6 hits (0.545), synchrony 0.543**, and a state
history that tracked the person cycle-by-cycle (*curious and seeking →
positive → frustrated → curious*). The "frustrated" read lands exactly on
*"no no. you have to tell me."* The relationship organ works when fed;
it was fed for four minutes in fourteen hours.

## 5. Self-model and symbolic layer: introspectively rich, worldly thin

- `causal_graph.json` — 258 edges: **252 self-domain, 6 world** (the
  introspective skew from `project_causal_frontier_introspection` persists by
  design); 246 of them intervention-sourced L2 — he learns his own causality
  experimentally.
- `knowledge_graph.json` — 224 entities / 110 relations, but 143 entities are
  type `unknown` — the world model ingests names faster than it types them.
- `prediction_domain_stats.json` — one domain ever: COGNITIVE, accuracy 0.764
  over 8,565 predictions. `predictions.json` (150 live) are all
  self-referential (`After 'look_outward': expect 'impasse_signal rises'`).
- `symbolic_progress.json` — the 07-03 row: 11/11 queries answered
  symbolically (ratio 1.0, zero LLM calls — tool-only gate holding), 5 rules
  added, **46 forgotten**, 4 crystallized. 51 rules alive
  (`symbolic_rules.json`) against that churn: the rule ecology is mostly
  turnover, not accumulation.
- `semantic_facts.json` — 82 action-outcome facts; top: `produce_and_check`
  in emo_neutral → neutral, n=228, confidence 0.979 — the stuck loop taught
  him, with high confidence, that produce_and_check does nothing. (True in
  the daemon lane; poisonous if it ever gates the conscious pick.)
- `world_model.json` / `world_model_stats.json` — GENERAL only, 172 rules / 80
  hits; `world_perception.json` 20 snapshots. Thin but not dead.
- The 4 **git-tracked** data files that show modified: self-model regeneration
  honestly picked up the fix round's new code (`_record_interaction`,
  `last_bound_goal_id` docstrings in `cognitive_functions.json`),
  `control_signals_model.json` grew a ~250-line emotion-keyword lexicon,
  `meta_rules.json` bumped an application counter (14,267→14,293),
  `vocab_weights.json` learned one phrase weight. All benign learning
  artifacts — but note they *are* versioned files that every run dirties.

## 6. The language organ: structure ready, diet monotone

`language/` — `native_lm.pt` 39.2 MB (trained to 2 min before stop),
`tokenizer.json`, `narration_pairs.jsonl` **536 thought→narration pairs**,
`replay_corpus.txt` 5,388 lines, `felt_experience.txt` running diary. The
bilingual pair pipeline works — but nearly every pair's affect slot is
*"something present but hard to name"*, so the native LM's self-narration diet
is the same template the notes channel suffers from. `book_reads.json` is
`{}` and `library/` is **empty** — `read_a_book` was picked 73 times against
an empty library (it falls back to other sources, but the organ's own shelf
has never held a book). `vocabulary.json` `{}` vs `symbolic_dictionary.json`
71 words — two vocab stores, one dead.

## 7. Infra and hygiene

- **`user_input.txt` still contains** `"i wonder why."` — the final message of
  the conversation. This is precisely the stale content that next boot's
  presence poll would have read as *new speech at birth*, re-minting the
  phantom visitor (it did exactly that this run: person minted at 02:04:45Z,
  30 s after boot). Fixed in code 2026-07-04 (§8).
- Root `data/memory/wal/`: `items.jsonl` 9.4 MB **with** gz rotation working
  (2 archives) — but **`events.jsonl` 15.0 MB with no rotation**. Biggest
  unbounded file in either tree; silting candidate #1.
- `resource_self_monitor.json` — rss 1.07 GB, cpu ~1.2 cores, fd usage
  negligible, `phase: wake`, `somatic_infancy: true`, zero stress streaks:
  the body was healthy all life.
- `temporal_state.json` — felt time ran hot: 11,579.8 felt cycles vs 11,333
  real (clock rate 0.817, arc "night", retrospective feel "rich").
- `energy_mode.json` — active EMA 0.436; **never approached the 0.60
  allostatic arming line** (matches allostatic_load 0.000 — standing
  invariant since 06-29).
- `regulation_log.json` — 59 regulation attempts, 49 succeeded (grounding 29 /
  reappraisal 29 / distancing 1) — the regulation organ quietly earns the
  "no terminal collapse" result.
- `runstate.json` `{clean: true}`; `mode.json` "creative";
  `model_config.json` `llm_enabled: false` (tool-only, consistent);
  `making_backlog.json` **[]** — a making-backlog organ exists and has never
  held an item (companion fact to the starved make-goal);
  `tool_requests.json` [] ; `identity_belief_revisions.json` {} (no identity
  revision this life); `long_memory.json` 2,001 entries with **zero tags** —
  the tag field exists and nothing populates it.

## 8. Post-run change applied 2026-07-04: social tone-down

Direct response to the run's headline pathology (84% social-presence ignition
monopoly), four targeted changes, full suite green (1,331 passed, 5 skipped):

1. `social_presence.py` — `_last_input_mtime` now seeded with the file's boot
   mtime: **stale `user_input.txt` content can no longer mint a phantom
   visitor at birth** (removes this run's false `_ever_spoke` unlock).
2. `social_presence.py` — presence signal: threshold 0.40→**0.50**, the ×1.1
   amplifier removed, strength capped at **0.85** — presence competes for
   ignition but can never saturate it at 1.00.
3. `social_presence.py` — pressure for a >1 h-silent user now eases toward a
   **0.60 ceiling** ("distant" is absence, not mounting emergency) instead of
   climbing to 0.95.
4. `demand_engine.py` — the `social` drive gets `leak_per_tick=0.005` (same
   treatment as rest): equilibrium ≈ **0.66**, signal strength ≈ 0.79, still
   signals within ~35 min of silence, can never pin at 1.0.

What Run 4 should show: social_presence ignitions a *minority* share while
alone; `drive_social` cruising ~0.66; no person record until someone actually
speaks; the ignition diet (emotion, prediction_check, drives) staying diverse
past hour 2 — and consequently the consolidation organs writing past 01:00.
Note this is the **tone-down**, not the general fix — the deeper-pass
recommendation (habituation of *unchanged* signals at the ignition layer)
still stands as the structural cure for the jammed-horn pattern.

## Fix list from this pass (new items only, smallest first)

1. Floor `attention_value_weights` decay (underflow to 1e-25 is unrecoverable).
2. Rotate root `data/memory/wal/events.jsonl` (15 MB, only unrotated WAL).
3. Populate or drop: `long_memory` tags, `vocabulary.json`, `book_reads` /
   `library/` (stock the shelf or retire `read_a_book`'s shelf path).
4. Rotation policy for `workspace_writeback.jsonl` (1 MB/run).
5. Feed the narration-pair generator affect words beyond "hard to name" once
   the felt-surface vocabulary work lands (P2 roadmap item, noted here because
   the native LM is training on the monotone).
6. Watch `semantic_facts`' high-confidence "produce_and_check → nothing"
   fact when the lane bridge lands — it was learned from the stuck loop.

*Generated 2026-07-04 from post-run data. Code changed same day: the §8
social tone-down only (social_presence.py, demand_engine.py).*
