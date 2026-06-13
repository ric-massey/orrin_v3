# Fix plan — Orrin only ever uses ~10 of his ~290 functions

**Status:** Proposed (diagnosis verified against the live tree on branch
`convergence-layer` + the persisted `decision_stats.json`/`bandit_state.json`). This is a
*cognition* change (how functions get chosen), not a UI change.
**One-line problem:** he has hundreds of cognitive functions but a fixed handful win every
cycle — not because the others are bad, but because the selection machinery **cannot
surface them**: winning is decided by hardcoded name-lists, the candidate menu is polluted
with plumbing, there is no real exploration, and the executive (goal-doing) lane can only
reach 8 functions.

---

## The symptom (measured, not inferred)

From the live data files:

| Measure | Count |
|---|---|
| Functions in the introspection catalog (`registry/function_catalog.py`) | **476** |
| Functions in `cognitive_functions.json` (the selectable list) | **447** |
| Candidates that survive filtering each cycle (`_load_action_defs`) | **287** |
| Functions **ever chosen** (entries in `decision_stats.json`) | **18** |
| Functions the bandit has any estimate for (`bandit_state.json["counts"]`) | **19** |
| Share of all deliberate picks taken by `assess_goal_progress` alone | **179 / ~260 (≈69%)** |

So out of ~287 things he *could* pick on any given cycle, the working repertoire is ~10,
and one meta-function (`assess_goal_progress`) accounts for the majority. The tail —
`look_outward` 22, `look_around` 9, `search_own_files` 6, `seek_novelty` 4, … — is all
single/low digits. **~270 functions have never run once.**

---

## How the problem was found

1. **Quantified usage** — read `brain/data/decision_stats.json` (18 entries, all the
   "used" set) and counted catalog vs. selectable functions by importing
   `registry.function_catalog.build_catalog()` (476) and loading
   `cognitive_functions.json` (447).
2. **Found the real candidate pool** — traced `select_function`
   (`brain/think/think_utils/select_function.py:686`) to `_load_action_defs()` (`:346`),
   which filters the 447 down to **287** via `_is_dispatchable` (`:266`). Ran it directly
   to confirm the 287.
3. **Read the scoring loop** (`:1078–1200`) line by line and catalogued every additive
   "boost" block and which function names each one references.
4. **Confirmed determinism** — the selection is `scored.sort(...)[0]` (`:1202`), pure
   argmax, with only an anti-repeat guard (`:1275+`), no ε-exploration over the pool.
5. **Checked the learning signal** — `bandit_state.json` only has `counts` for the 19
   already-used functions, so the bandit can give *no* estimate for a dormant function.
6. **Followed goal-doing into the executive lane** — `pursue_committed_goal`
   (`cognition/planning/pursue_goal.py:538`) and the daemon (`executive.py`) map plan-steps
   to functions through `recognise_step_action` (`cognition/planning/step_execution.py:97`).
   Measured its rule tables: `_KNOWN_FN_NAMES` = **8**, `_INTENT_RULES` = **8** → only **8
   distinct functions** are reachable from a goal step; everything else is treated as "a
   thought" (returns `None`, no function runs).

---

## Root causes

### A. The candidate menu is polluted with plumbing **[primary]**
The registry auto-discovers every function and `_is_cognition` **"Defaults to True to keep
things simple/forgiving"** (`registry/cognition_registry.py:25-36`). Unless a function
explicitly declares otherwise, it lands on the menu. The dispatchability gate
(`select_function.py:266`) only asks "can I supply the arguments?" and **fails open**
("unsure → keep it", `:301`/`:386`). So the 287 candidates include internal machinery that
should never be a *decision* — verified examples in the pool: `ensure_tokenizer`,
`build_system_prompt`, `calibrated_reward`, `decay_awaiting`, `compute_drive_strengths`,
`apply_milestone_updates`. They can't sensibly win, but they **dilute the novelty and
bandit signals** for everything else and inflate the "287" into a number that hides how few
real behaviors exist.

> Note: each candidate *does* carry a real definition (signature + docstring), so the
> keyword-overlap terms below *can* fire — the problem isn't missing text, it's that
> overlap is a weak, noisy match (code docstrings vs. goal prose).

### B. Winning is decided by ~15 hardcoded name-lists, not by the repertoire **[primary]**
The score for each candidate (`select_function.py:1138`) is:
```
total = w_dir·dir + w_goal·goal + w_emo·emo + w_novel·nov + w_band·band + w_drive·drv
        + s_attn + s_energy + s_help + s_emo_route + s_chain + s_neuro + s_emo_mode
        + s_outward + s_explore + s_curio + s_evc
```
The `w_*` weighted terms are small (each weight 0.10–0.26). The `s_*` **additive boosts are
large (+0.13 to +0.90)** and every one of them is keyed to a *hand-curated list of the same
~25 names*:
- attention-mode boosts (`:750-794`): `pursue_committed_goal`, `assess_goal_progress`,
  `plan_next_step`, `look_outward`, `seek_novelty`, `search_own_files`,
  `generate_intrinsic_goals`, `look_around`, …
- monitor-route map (`:805-814`), tension boost (`:828`), deadline boost (`:839-844`),
  emotion-mode map (`:899-907`), neuromodulator boosts (`:937-962`), helpfulness
  (`:990`), outward-presence (`:1016-1036`), behavioral-adaptation (`:1154-1166`).

`assess_goal_progress` appears in the **most** of these lists, so it wins almost every
cycle — that's the 69%. A function named in *no* list is structurally invisible.

### C. A dormant function cannot mathematically compete, and is never tried **[primary]**
For a candidate not in any boost list, `total` collapses to the weighted base terms. But:
- **bandit** (`s_band`) has no data for never-used functions → 0.
- **emotion prior** (`s_emo`) is only defined for the curated set.
- **keyword overlap** (`dir`/`goal`) is weak and the novelty weight was *deliberately*
  cut to **0.10** ("was driving look_outward to 33% of cycles", `:733`).

So a dormant function scores ≈0 while a boosted one scores 0.3–1.0+, and the final step is
**deterministic argmax** with no ε-random exploration. The anti-repeat guard only rotates
among the *top (already-boosted) few*. The system therefore can never *discover* that
function #200 would have paid off — it never selects it, so the bandit never learns, so it
stays at 0 forever. A self-reinforcing dead zone.

### D. The one mechanism meant to fix this is ~10× too weak **[contributing]**
The "curiosity nudge" for dormant functions (`s_curio`, `:1132`) is capped at ≈**0.09**,
gated on `exploration_drive > 0.5` and `count < 8`. That is an order of magnitude below the
hardcoded boosts. The code already *admits* this elsewhere — the tension-boost comment
(`:1186-1188`): *"contributing only ~0.04 to total — far too weak to win among 300+
candidates."* The "fix" applied there was to hardcode a +0.60 for `propose_value_revision`
(`:1192`) — i.e. adding *another* name to the curated set, which deepens root cause B.

### E. The executive (goal-doing) lane can only reach 8 functions **[primary, second lane]**
Goal pursuit was moved out of the deliberate lane (`pursue_committed_goal` removed from
candidates, `:1140-1142`) into the Executive daemon. There, a goal's plan-step is mapped to
a function by `recognise_step_action` (`step_execution.py:97`), which matches against
`_KNOWN_FN_NAMES` (**8**) and `_INTENT_RULES` (**8 trigger→fn rules**). Measured: only **8
distinct functions** are reachable from any goal step — `fetch_and_read`, `leave_note`,
`look_around`, `look_outward`, `research_topic`, `search_own_files`, `seek_novelty`,
`wikipedia_search`. Any step that doesn't keyword-match returns `None` and is logged as "a
thought" — no function runs. **So even when a goal decomposes into steps, those steps can
only ever recruit ~8 of the ~290 functions.** Both lanes funnel to the same tiny set.

### Why this isn't human-like
A human doesn't independently score ~290 verbs and take the max; they decompose a goal into
the specific capability it needs and recruit *that*. Here, goals collapse onto "assess
progress / look outward / reflect" in the deliberate lane and onto an 8-function keyword
table in the executive lane. The repertoire exists but there is no path from "this goal
needs capability X" to "select function X".

---

## The fix plan

Ordered cheapest-first; each phase is independently shippable and observable on the Brain
dashboard (function-usage spread is directly visible on the Cognitive Sphere).

### Phase 1 — Clean the menu (separate *behaviors* from *plumbing*) **[Low risk]**
Stop plumbing from being selectable so the candidate pool reflects real choices.
1. Add an explicit `is_cognition` / `selectable` flag to the registry entries — the
   mechanism **already exists** (`cognition_registry.py:30` reads `fn.__manifest__`, and
   entries already carry `{"function": …, "is_cognition": True}` in `ORRIN_loop.py:477+`).
   Flip `_is_cognition`'s default to **False** (opt-in) *or* maintain an explicit
   `_NON_SELECTABLE` denylist seeded from the obvious plumbing.
2. Tag the genuine behavioral/cognitive functions as selectable (most are already named in
   the boost lists — that curated set is, ironically, the closest thing to a real
   "behaviors" manifest that exists).
3. **Acceptance:** the candidate count drops from 287 to the real behavior count (estimate
   ~40–80; *needs the audit in Dig-deeper #1*), with no plumbing names appearing as picks.

### Phase 2 — Make exploration real **[Medium risk]**
Replace deterministic argmax over a stacked-boost score with a policy that can actually try
unfamiliar functions.
1. Convert the final pick (`select_function.py:1202-1209`) from `sort[0]` to **softmax
   sampling** over the top-K scores with a temperature, OR add an explicit ε-greedy branch:
   with probability ε, pick uniformly among *eligible, rarely-used* candidates.
2. Make the bandit cover the whole (cleaned) pool with an **optimistic prior** (UCB-style):
   unused functions get an exploration bonus that *decays with use*, so each gets a real
   trial before being judged. Today `bandit_state` only tracks the 19 used ones.
3. Rebalance: the curiosity nudge (`s_curio`) and novelty weight (`w_novel`) need to be
   comparable to the hardcoded boosts, not 10× smaller — *but only after Phase 1*, so
   exploration spends its budget on real behaviors, not plumbing.
4. **Acceptance:** over a fixed run, the number of distinct functions chosen rises
   materially (e.g. 18 → 40+), and reward-per-function shows the system *learning* which new
   ones pay off (not just thrashing).

### Phase 3 — Goal → capability recruitment (the human-like path) **[Medium/High risk]**
Give goals a real route to the specific function they need, in **both** lanes.
1. **Executive lane:** replace/augment the 8-rule `recognise_step_action`
   (`step_execution.py:97`) with a semantic match from step-text → function (embedding
   similarity over function definitions, with the keyword rules as a fast path / fallback).
   This is the highest-leverage single change for goal-doing breadth.
2. **Deliberate lane:** when a committed goal is active, derive a *goal-specific* boost set
   from the goal's text/tags instead of (or in addition to) the static name-lists — i.e.
   the boost that today is hardcoded becomes *computed from what the goal needs*.
3. **Acceptance:** different goals recruit visibly different function sets (a research goal
   pulls research/read/write tools; a self-model goal pulls reflection/revision tools),
   rather than every goal collapsing onto `assess_goal_progress`.

### Phase 4 — Replace hardcoded name-lists with capability tags **[High risk, last]**
The ~15 boost blocks (B) hardcode names because there's no semantic grouping. Once Phase 1
gives functions a manifest, give each a small set of **capability/affect tags** (e.g.
`outward`, `introspective`, `goal-progress`, `regulation`, `creative`). Rewrite the boost
blocks to key off **tags**, not literal names — so a newly added function that's tagged
`outward` automatically participates in the outward-presence boost instead of being
invisible until someone edits a frozenset. This is the structural cure for B/D; do it last
because it touches every boost block.

---

## Areas that need deeper digging (before/while implementing)

1. **How many of the 287 are real behaviors vs. plumbing?** *(blocks Phase 1 acceptance)*
   I confirmed *examples* of plumbing in the pool but did not classify all 287. Needed: a
   one-time audit (manifest sweep) categorising each as behavior / cognition / plumbing.
   This sets the true denominator — the "uses 10 of 290" headline may really be "uses 10 of
   ~60", which changes how alarming the spread is and how aggressive Phase 2 should be.
2. **Is the concentration partly *correct*?** Some functions *should* be rare (e.g.
   `emergency_self_modification`). Before forcing exploration, separate "dormant because
   unreachable" (the bug) from "dormant because situational" (fine). Pull the reward history
   (`reward_trace.json`, `decision_stats.avg_reward`) for the used set to see whether the
   chosen few are actually *high-reward* or just *high-boost*.
3. **Does `recognise_step_action` returning `None` silently strand goal progress?** The
   ui_fixes notes "thought" steps produce no executive light. Need to measure: across real
   goals, what fraction of plan-steps map to a function vs. fall through to `None`? If most
   steps are `None`, goals may be "progressing" without ever acting — quantify from
   `goals_mem.json` plans + run logs.
4. **The bandit's context buckets** (`bandit_state.json["buckets"]`:
   `exploration_drive`/`impasse_signal`/`social_deficit`/`stable`). Understand how the
   contextual bandit keys functions to emotional buckets before adding the optimistic
   prior — an optimistic prior must be *per-bucket* or it will mis-explore.
5. **EVC cost gating** (`s_evc`, `interoception.evc_selection_adjust`, `:1116`). It applies
   a cost penalty to "expensive-but-low-payoff" functions. Confirm it isn't *itself*
   suppressing dormant functions (an unused function may look "expensive" with no payoff
   history) — if so it compounds root cause C and Phase 2 must account for it.
6. **Semantic match feasibility for Phase 3.** Is there already an embedding model
   available in-process (the native LM / tokenizer work) to do step-text → function-def
   similarity cheaply, or does Phase 3.1 need a lightweight TF-IDF fallback? Determines
   whether Phase 3 is days or weeks.
7. **Interaction with the dual-process split.** `pursue_committed_goal` is deliberate-lane
   excluded (`:1140`) and runs in the executive daemon. Confirm that broadening the
   executive lane (Phase 3.1) doesn't double-execute or race the deliberate lane (the I3
   mutual-exclusion the loop already relies on).

---

## Files involved
- `brain/registry/cognition_registry.py` (Phase 1: `_is_cognition` default / manifest; Phase 4: capability tags)
- `brain/registry/behavior_registry.py` (Phase 1: behavior vs. cognition split reference)
- `brain/think/think_utils/select_function.py` (Phase 2: softmax/ε + optimistic bandit; Phase 3.2: goal-derived boosts; Phase 4: tag-keyed boosts)
- `brain/cognition/planning/step_execution.py` (Phase 3.1: semantic `recognise_step_action`)
- `brain/cognition/planning/pursue_goal.py` / `executive.py` (Phase 3 verification; Dig-deeper #3/#7)
- `brain/data/bandit_state.json` (Phase 2: whole-pool coverage with priors)
- `brain/data/cognitive_functions.json` (Phase 1: regenerated after the manifest sweep)
- *(observability)* the Cognitive Sphere already visualises function-usage spread — use it
  as the acceptance dashboard for every phase.
