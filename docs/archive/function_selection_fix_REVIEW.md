# Analyst review of `function_selection_fix.md`

**Reviewer role:** program analyst (cognition + code).
**Method:** every quantitative and code-behavior claim in the plan was re-checked against the
live tree on `convergence-layer` and the persisted data files. I did **not** edit the original
document.
**Bottom line:** the *diagnosis* is unusually accurate — the headline numbers, line citations,
and causal story almost all reproduce. The *fix plan* is directionally right but contains one
**load-bearing technical error in Phase 1** (the proposed mechanism is, as written, a no-op) plus
several ordering/safety gaps in Phases 2–3 that should be corrected before any code is touched.

---

## 1. Diagnosis verification — what reproduces

| Claim in the doc | Verified? | Evidence |
|---|---|---|
| `cognitive_functions.json` = 447 selectable | ✅ exact | `len(json) == 447` |
| Candidate pool after filtering = **287** | ✅ exact | ran `_load_action_defs()` → `287` |
| Named plumbing survives into the pool (`ensure_tokenizer`, `build_system_prompt`, `calibrated_reward`, `decay_awaiting`, `compute_drive_strengths`, `apply_milestone_updates`) | ✅ all 6 present | each tested `in names` → `IN POOL` |
| `assess_goal_progress` ≈ 69% of deliberate picks | ✅ holds | live `216/312 = 69%` (doc's `179/~260` was an earlier snapshot) |
| Selection is pure argmax | ✅ | `scored.sort(...)[0]` at `select_function.py:1202` |
| `_is_dispatchable` "fails open" | ✅ verbatim | `:288` `ok = True  # unsure → keep it` |
| `_is_cognition` defaults to True | ✅ verbatim | `cognition_registry.py:25-36`, *"Defaults to True to keep things simple/forgiving"* |
| `pursue_committed_goal` excluded from deliberate candidates | ✅ (but mis-cited) | it is in `_ALWAYS_EXCLUDE` at `select_function.py:54`, **not** the comment at `:1140-1142` the doc points to |
| `_KNOWN_FN_NAMES` = 8 | ✅ exact | `step_execution.py:37-41` |
| `_INTENT_RULES` = 8 | ✅ exact | `step_execution.py:45-69` |
| 8 reachable goal-step functions, exact set | ✅ exact | matches `fetch_and_read, leave_note, look_around, look_outward, research_topic, search_own_files, seek_novelty, wikipedia_search` |
| `s_curio` capped ≈0.09, gated `expl_drive>0.5 & count<8` | ✅ | `:1132-1136`, `0.18·0.5·1.0 = 0.09` max |
| +0.60 hardcode for `propose_value_revision` | ✅ exact | `:1192`, gated on `active_tensions and name not in recent` |
| Weight band 0.10–0.26; novelty cut to 0.10 | ✅ | `w_dir/w_goal=0.22, w_emo=0.26, base_w_novel=0.10, w_band/w_drive=0.15` (`:735-741`) |
| Bandit context buckets | ✅ | `exploration_drive, impasse_signal, social_deficit, stable` |

**Verdict on the diagnosis:** trustworthy. The core engineering reality — *287 candidates, ~10
ever chosen, one function at 69%, the menu polluted with real plumbing, the winners decided by
hand-curated frozensets, no real exploration, the executive lane funneling to 8 functions* — is
all confirmed against the running system. This is a correct problem statement.

---

## 2. Errors and weaknesses in the **fix plan**

### 🔴 E1 — Phase 1's primary mechanism (flip `_is_cognition` default) is a NO-OP as described **[blocking]**
This is the most important finding. Phase 1.1 says to clean the menu by flipping
`_is_cognition`'s default to `False`, and claims "the mechanism already exists." Tracing the data
flow shows the proposed lever is **not connected to the candidate pool**:

1. `_is_cognition(fn)` is only called at `cognition_registry.py:156,167`, where it sets the
   `is_cognition` *value inside the registry dict*.
2. The persistence step that actually writes `cognitive_functions.json`
   (`cognition_registry.py:185-201`) builds its list from
   `names = sorted(n for n in funcs.keys() ...)` — it **iterates every key and never reads
   `is_cognition`**. The flag is computed and stored, then ignored.
3. `_load_action_defs()` (the 287 pool) reads `cognitive_functions.json` and filters **only** on
   `_ALWAYS_EXCLUDE`, behavioral names, and `_is_dispatchable` — it never consults `is_cognition`.

**Consequence:** flipping the `_is_cognition` default changes a field nobody downstream reads.
The candidate pool would still be 287. To make the manifest path work you must *also* add a
filter (`if meta["is_cognition"]`) at the persist step **and/or** in `_load_action_defs`. The plan
omits that wiring and presents the flip as sufficient.

### 🔴 E2 — The manifest infrastructure is **completely dormant**, so "opt-in" collapses the pool **[blocking]**
Phase 1.1 leans on `fn.__manifest__`. I checked: there are **zero** real `@manifest` decorations
in `brain/` (the only `@manifest` token is inside a *comment* in `behavior_registry.py:15`; the
decorator in `utils/manifest.py` is defined but applied nowhere). Therefore:

- Today `_is_cognition` returns `True` for **every** auto-discovered function (no manifest ⇒
  default).
- If you flip the default to `False` *and* wire up the filter from E1, then with no functions
  carrying a manifest the cognitive pool collapses toward **empty**, not toward "~40–80." The
  opt-in default is only safe **after** dozens-to-hundreds of genuine behaviors are decorated —
  which is Phase 1 step 2, i.e. the expensive part the plan lists second and under-scopes.

### 🟠 E3 — Phase 1 conflates two unrelated `is_cognition` mechanisms
The plan writes: *"the mechanism already exists (`cognition_registry.py:30` reads
`fn.__manifest__`, and entries already carry `{"function":…, "is_cognition":True}` in
`ORRIN_loop.py:477+`)."* These are **two different things**:
- `fn.__manifest__.is_cognition` — an attribute on the *function object* (set by the decorator;
  currently never set).
- the `is_cognition: True` key in the *registry entry dict* in `ORRIN_loop.py` — a hardcoded
  literal on manual registrations, never read by `_is_cognition`.

Presenting them as one existing mechanism is what makes E1/E2 easy to miss.

**Correct framing for Phase 1:** the **denylist** alternative the doc mentions second is actually
the one that already works — `_ALWAYS_EXCLUDE` *is* a `_NON_SELECTABLE` denylist and
`_load_action_defs` already honors it (and already excludes `update_affect_state`, `apply_*`,
`write_tool`, `fade_goals`, `pursue_committed_goal`, …). The cheapest correct Phase 1 is "grow the
denylist from the audit," **not** "flip the manifest default." Recommend swapping which option is
primary.

### 🟠 E4 — Phase 2 forces exploration before knowing what is *dangerous* to explore **[safety gap]**
Phase 2.2 ("optimistic prior over the whole cleaned pool, each function gets a real trial") has no
**reversibility/safety gate**. The pool contains, or will contain, irreversible or
externally-visible acts. The codebase already shows awareness of this risk elsewhere —
`step_execution.py` keeps a `_PROCEDURAL_FNS` allowlist precisely so the background lane can only
run *reversible* gathering/observation steps. Phase 2 has no analogue: "rarely-used" ≠ "safe to
try." An optimistic prior that guarantees every function "gets a trial before being judged" will,
by construction, eventually trial the dangerous tail. **Add an explicit reversibility gate** (reuse
`is_procedural` / a `safe_to_explore` tag) before forcing any trial. This dependency should be
called out as Phase 2 ⟶ depends on the Dig#2 situational-vs-unreachable split, not run in parallel.

### 🟠 E5 — Phase 3.1 relies on the same weak signal the doc itself discredits
Root cause A's own note says keyword/text overlap is *"a weak, noisy match (code docstrings vs.
goal prose)."* Phase 3.1 then proposes step-text→function matching via **embedding similarity over
function definitions** — i.e. the *same docstring text*, just with embeddings instead of token
overlap. Embeddings narrow the gap but do not remove the docstring↔goal-prose mismatch the doc
flagged. This isn't fatal, but the plan should acknowledge that Phase 3.1's quality is bounded by
docstring quality, and likely needs curated capability descriptions (which is really Phase 4's tag
work) to land well. **Phases 3 and 4 are more coupled than the "do 4 last" ordering implies.**

### 🟡 E6 — Dead code the plan should plan to remove (and which can bite Phase 3.2)
Because `pursue_committed_goal` is in `_ALWAYS_EXCLUDE`, the ~10 scoring branches that still
reference it (`:757, :768, :839, :900, :939, :948, :1024, :1063, :1155, :1179`) are now
**unreachable** — `if "pursue_committed_goal" in actions` at `:1063` is always False. Harmless
today, but Phase 3.2 ("derive a goal-specific boost set") will reintroduce goal-pursuit scoring;
if it reuses these stale branches it may silently no-op or double-handle. Phase 1/3 should include
a cleanup pass of these dead references.

### 🟡 E7 — Acceptance criteria measure breadth, not health
Phase 2's acceptance ("18 → 40+ distinct functions") rewards *spread*, which a naive ε-greedy
maximizes by definition — including by thrashing. The doc's own Dig#2 is the right guardrail
(distinguish high-reward from high-boost), but it lives in a separate "dig deeper" list rather than
being wired into the acceptance test. **Promote "reward-per-function is rising, not just count" and
"no increase in irreversible/error-logged calls" into the Phase 2 acceptance itself.**

---

## 3. Minor / cosmetic

- **Numeric staleness (not errors).** The data files are live and have grown since the doc's
  snapshot: `decision_stats` 18→**20**, bandit counts 19→**21**, `assess_goal_progress` 179→**216**.
  The doc says "snapshot," so this is expected; the *ratios* (69%) and the operational number
  (287) are unchanged.
- **Catalog = 476 unverified.** `cognitive_functions.json`=447 and pool=287 reproduce exactly, but
  `build_catalog()` would not import cleanly in isolation here (`ModuleNotFoundError: core`), so the
  476 figure is plausible-but-unconfirmed. It's rhetorical, not load-bearing — the operative number
  is 287.
- **Citation drift.** A few line cites point at a nearby *comment* rather than the operative code:
  `pursue_committed_goal` removal is at `:54` (`_ALWAYS_EXCLUDE`), not `:1140-1142`. Worth fixing so
  implementers don't edit the comment expecting an effect.
- **6 of 20 "used" functions are no longer selectable.** Several entries in `decision_stats`
  (`update_affect_state`, `pursue_committed_goal`, `fade_goals`, …) were added to `_ALWAYS_EXCLUDE`
  *after* they'd accumulated usage. The "uses ~10" set therefore partly reflects *historical*
  picks of now-excluded functions — a small caveat on the headline that strengthens, not weakens,
  the argument.

---

## 4. Recommended corrections (smallest changes to make the plan executable)

1. **Rewrite Phase 1 around the denylist, not the manifest flip.** The denylist (`_ALWAYS_EXCLUDE`)
   is the mechanism already wired into the pool. Primary task = run the Dig#1 audit, classify the
   287, and extend the denylist. Defer the manifest/tag approach to Phase 4 where it belongs.
2. **If the manifest path is kept in Phase 1, add the missing filter** at
   `cognition_registry.py:186` (and/or `_load_action_defs`) so `is_cognition` actually gates the
   persisted list — otherwise E1 makes it inert — **and** decorate real behaviors *before* flipping
   the default (E2), or the pool collapses.
3. **Gate Phase 2 exploration by reversibility**, reusing the existing `is_procedural` /
   `_PROCEDURAL_FNS` concept; make Phase 2 explicitly depend on Dig#2.
4. **Fold reward-health and safety into Phase 2 acceptance**, not just distinct-count.
5. **Treat Phases 3 and 4 as coupled** — semantic recruitment wants curated capability text, which
   is the tag work; consider tagging a small high-value subset early rather than strictly last.
6. **Add a dead-code cleanup** of the stale `pursue_committed_goal` scoring branches as part of
   whichever phase re-touches goal scoring.

**Overall:** ship-worthy diagnosis; the plan needs Phase 1 re-grounded on the denylist (the
manifest lever is disconnected and the manifest store is empty) and Phases 2–3 given explicit
safety/quality gates. None of these invalidate the strategy — they correct the *mechanism* and the
*sequencing* so the first phase actually moves the 287.
