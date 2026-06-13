# Fix plan v2 — Orrin only ever uses ~10 of his ~290 functions (CORRECTED)

**Status:** ✅ ALL PHASES IMPLEMENTED — Phases 1/2/3/5 on 2026-06-09, Phase 4
(capability tags) on 2026-06-10. See `function_selection_fix_v2_IMPLEMENTATION.md`
(§7b for Phase 4). The only remaining acceptance item is operational, not code:
the Phase-2 §3.4 breadth/reward-health check needs a ~500-cycle live staging run
with a pre/post `decision_stats.json` + `reward_trace.json` diff.
Supersedes `function_selection_fix.md`. Incorporates every finding from
`function_selection_fix_REVIEW.md` (E1–E7) **plus** a fresh live audit of the 287-candidate
pool that turned up a larger pollution source than either prior doc identified.
This is a *cognition* change (how functions get chosen), not a UI change. Branch:
`convergence-layer`.

All line numbers below were re-verified against the live tree on 2026-06-09.

---

## 1. Executive summary

**Problem (verified, unchanged):** Orrin has ~287 selectable cognitive functions surviving
the per-cycle filter (`_load_action_defs`, `select_function.py:346`), but in practice he
uses ~10, with `assess_goal_progress` taking ≈69% of deliberate cycles. ~270 functions have
never run once.

**Core insight (the thing to internalise before touching code):** *the functions aren't
losing on merit — the selection machinery cannot surface them.* Three independent walls:

1. **The menu is polluted.** Of the 287, only ~130 are real behaviors. The rest is
   plumbing and — the new finding — **76 corrupted auto-generated `explore_*` functions**
   that dilute every novelty/bandit signal (see Phase 1 audit).
2. **Winning is decided by ~15 hardcoded name-lists**, not by the repertoire. The additive
   `s_*` boosts (+0.13 … +0.90, `select_function.py:1138`) all key off the same ~25 curated
   names; a function in no list is mathematically invisible. The final pick is **pure
   argmax** (`scored.sort(...)[0]`, `:1202`/`:1209`), so a dormant function is never tried,
   the bandit never learns it, and it stays dormant forever — a self-reinforcing dead zone.
3. **The executive (goal-doing) lane can only reach 8 functions** via a keyword table
   (`recognise_step_action`, `step_execution.py:97`). Both lanes funnel to the same tiny set.

**What the review corrected in the original plan (must be respected):**

- **E1/E2:** Flipping `_is_cognition`'s default is a **no-op** — nothing downstream reads it,
  and no function carries a `@manifest`, so an opt-in default would collapse the pool to
  near-empty. Phase 1 must use the **denylist** (`_ALWAYS_EXCLUDE`), which *is* already wired
  into the pool, not the manifest flip.
- **E3:** `fn.__manifest__.is_cognition` (function attribute, never set) and the
  `is_cognition: True` dict key in `ORRIN_loop.py` (literal, never read) are two unrelated
  mechanisms; don't conflate them.
- **E4:** Phase 2 exploration must be gated by a **reversibility check** (reuse
  `is_procedural` / `_PROCEDURAL_FNS`) — "rarely used" ≠ "safe to try."
- **E5:** Phase 3a semantic matching is bounded by docstring quality; needs curated
  capability text, coupling it to Phase 4.
- **E6:** Remove the dead `pursue_committed_goal` scoring branches (unreachable — it's in
  `_ALWAYS_EXCLUDE`).
- **E7:** Phase 2 acceptance must measure **reward health** and **no rise in
  irreversible/error-logged calls**, not just distinct-function count.

**One nuance the review did not have (found in this audit):** the contextual bandit
*already* implements per-bucket UCB1 with optimistic cold-arm priors
(`contextual_bandit.py:280-281` returns `1.0` for any arm with `n==0` in the current bucket;
`choose()` tries unexplored arms first, `:233-235`). So "give the bandit an optimistic prior"
is *already done at the bandit layer*. The real defect is that **`select_function` never uses
the bandit to pick** — it argmaxes a stacked-boost score in which the bandit is only a
0.15-weighted, min-max-normalized *hint* (`w_band=0.15` `:740`; `_bandit_hint_scores` `:540`).
Worse, min-max normalization **destroys** the cold-arm optimism: when every candidate is cold
they all score `1.0`, the span collapses to 0, and they all normalize to `0.0`. Phase 2 is
therefore about *letting the existing bandit exploration actually drive the pick*, not about
inventing a new prior.

---

## 2. Phase 1 — Clean the candidate pool (denylist, not manifest flip) **[Low risk]**

**Goal:** drop the pool from 287 to the real behavior count so novelty/bandit/curiosity
signal is spent on real choices, and no plumbing or junk can win.

**Mechanism:** extend the existing, already-wired denylist `_ALWAYS_EXCLUDE`
(`select_function.py:37-79`), which `_load_action_defs` honors at `:365`/`:372`/`:377`.
Do **not** touch `_is_cognition` — per E1/E2 it changes a field nobody reads.

### 2.1 Live audit of the 287 (run 2026-06-09)

| Bucket | Count | Examples |
|---|---|---|
| **Corrupted auto-generated `explore_*`** | **76** | `explore_understand_find_out_more_deeply_more_deeply_more_deeply`, `explore_understand_the_traitors_more_deeply`, `explore_housekeeping__daily_snapshot__2026_06_07_`, `explore_find_out__what_s_your_take_on_intresting_` |
| — of which runaway `…_more_deeply_more_deeply…` chains | 49 | as above |
| **Upkeep prefixes** (`apply_/update_/compute_/decay_/ensure_/build_/load_/refresh_/reset_`) | 32 | `apply_milestone_updates`, `compute_drive_strengths`, `decay_awaiting`, `ensure_tokenizer`, `build_system_prompt`, `update_world_model`, `load_goals`, `refresh_identity_story` |
| **Accessors** (`get_/set_/has_/is_/should_/maybe_`) | 17 | `get_status`, `is_daemon_running`, `maybe_complete_goals`, `should_dream`, `get_calibration` |
| **Internal calc / infra** | ~8 | `calibrated_reward`, `calibration_observation`, `check_and_reward*`, `train_tokenizer_on_library`, `reflect_on_prompts` |
| **Trivial-name leaks** | ~15 | `available`, `exists`, `get`, `start`, `stop`, `status`, `report`, `flush`, `generate`, `simulate`, `commit`, `size_chars`, `vocab_size`, `lm_ready`, `poll_fs_changes` |
| **Real behaviors (estimate after cleanup)** | **~130** | `research_topic`, `seek_novelty`, `propose_value_revision`, `dream_cycle`, `reflect_on_self_beliefs`, … |

The **`explore_*` block is the headline** and neither prior doc fully caught it. These are
dynamically-generated goal-exploration functions that got persisted into
`cognitive_functions.json`. The selector already half-knows they are junk: the curiosity
nudge explicitly skips names containing `more_deeply_more` (`select_function.py:1133`). They
must be removed from the pool **and** their generation root-caused (see 2.4).

> Reproduce the audit:
> ```bash
> cd brain && python3 -c "from think.think_utils.select_function import _load_action_defs as L; n,_=L(); \
> print('pool',len(n)); print('explore_*',len([x for x in n if x.startswith('explore_')]))"
> ```

### 2.2 Code edit — `select_function.py`

Two changes, both in `_load_action_defs` (`:346-387`) and the constants block (`:37-79`).

**(a) Add a prefix/junk filter** so the `explore_*` corruption and obvious plumbing are
dropped *as a class*, not name-by-name (self-maintaining as new junk is generated). Add near
the top of the file (after `_ALWAYS_EXCLUDE`, ~`:80`):

```python
import re as _re_pool

# Names that are NEVER real cognitive choices, matched by shape so newly
# generated junk/plumbing is filtered without growing _ALWAYS_EXCLUDE by hand.
#  - explore_*  : corrupted auto-generated goal-exploration fns (76 in the pool,
#                 49 of them runaway "..._more_deeply_more_deeply" chains). Root
#                 cause tracked separately (2.4); this is the containment filter.
#  - upkeep/accessor prefixes that already run automatically each cycle.
_NON_SELECTABLE_PREFIXES = (
    "explore_",
    "apply_", "update_", "compute_", "recompute_", "decay_", "ensure_",
    "build_", "init_", "load_", "save_", "persist_", "register_", "refresh_",
    "reset_", "migrate_", "coerce_", "normalize_", "sync_", "flush_", "gc_",
    "get_", "set_", "has_", "should_",
)
_NON_SELECTABLE_EXACT = frozenset({
    # trivial-name leaks from over-broad public-function discovery
    "available", "exists", "get", "start", "stop", "status", "report",
    "flush", "generate", "simulate", "commit", "size_chars", "vocab_size",
    "lm_ready", "poll_fs_changes",
    # internal reward/calibration calc that surfaced as "choices"
    "calibrated_reward", "calibration_observation", "check_and_reward",
    "check_and_reward_contradiction_resolution", "check_and_reward_goal_closure",
    "check_and_reward_prediction_accuracy", "train_tokenizer_on_library",
    "reflect_on_prompts", "build_system_prompt", "ensure_tokenizer",
})

def _is_selectable_name(name: str) -> bool:
    if name in _NON_SELECTABLE_EXACT:
        return False
    # keep a curated few that legitimately start with a denied prefix
    if name in _SELECTABLE_PREFIX_EXCEPTIONS:
        return True
    return not name.startswith(_NON_SELECTABLE_PREFIXES)

# Functions that start with a denied prefix but ARE real behaviors — keep them.
_SELECTABLE_PREFIX_EXCEPTIONS = frozenset({
    "update_world_model",   # genuine cognition entry point (router-wrapped)
})
```

> ⚠️ **Caution on `is_*` / `maybe_*`:** do **not** blanket-deny these — `maybe_form_opinion`
> and a few `is_*` may be real. Audit the 17 accessors individually before adding their
> prefixes; the safe move is to add the confirmed-plumbing ones to `_NON_SELECTABLE_EXACT`
> rather than denying the whole prefix. The list above deliberately omits `is_`/`maybe_` for
> that reason.

**(b) Wire the filter into the pool builder.** In `_load_action_defs` (`:369-380`), change
both branches from `if nm in excluded or not _is_dispatchable(nm):` to also consult the new
predicate:

```python
        if isinstance(it, dict) and "name" in it:
            nm = str(it["name"])
            if nm in excluded or not _is_selectable_name(nm) or not _is_dispatchable(nm):
                continue
            ...
        elif isinstance(it, str):
            if it in excluded or not _is_selectable_name(it) or not _is_dispatchable(it):
                continue
            ...
```

Apply the same `_is_selectable_name` guard to `_load_actions` (`:299-302`) for parity.

### 2.3 `cognition_registry.py` — optional belt-and-suspenders

Not required for Phase 1 acceptance (the selector filter above is sufficient), but to stop
junk being persisted in the first place, filter in `persist_names` (`:186`):

```python
    names = sorted(
        n for n in funcs.keys()
        if isinstance(n, str) and not n.startswith("_")
        and not n.startswith("explore_")          # don't persist corrupted goal-exploration fns
    )
```

Leave `_is_cognition` (`:25-36`) **untouched** — flipping it is the E1 no-op.

### 2.4 Root cause of the `explore_*` generation (diagnosed — cure, not just containment)

Traced to a three-layer pipeline:

1. **Name construction** — `behavior/behavior_generation.py:147-148`:
   ```python
   sanitized_topic = "".join(c if (c.isalnum() or c == "_") else "_" for c in topic.replace(" ", "_").lower())
   function_name = f"explore_{sanitized_topic}"
   ```
   `topic` is free text. When a follow-up goal is phrased "understand X **more deeply**" and
   its title is itself a previous exploration's topic, the `_more_deeply` suffix **accumulates
   every regeneration** → `explore_understand_find_out_more_deeply_more_deeply_more_deeply…`
   (the 49 runaway chains). This is an unbounded self-feeding loop on the topic string.

2. **Unbounded append** — `behavior_generation.py:174-179` proposes a `write_file` append to
   `AUTOGENERATED_THOUGHTS` (`brain/cognition/self_generated/autogenerated_thoughts.py`),
   guarded only by `only_if_missing: f"def {function_name}("`. Because each runaway name is
   *unique*, the guard never dedupes — every variation is appended as a new `def`. That file
   now holds ~76 such defs (`autogenerated_thoughts.py:187+`).

3. **Auto-discovery into the pool** — the module lives under `cognition/`, so the registry's
   "include ANY other public function defined in the module" sweep
   (`cognition_registry.py:158-167`) discovers all 76 and `persist_names` writes them into
   `cognitive_functions.json`, where they become selectable candidates.

**Cure (in priority order):**

- **(a) Stop the runaway suffix** at `behavior_generation.py:147` — strip/collapse repeated
  `_more_deeply` (and cap topic length / dedupe tokens) before building the name. This kills
  49 of the 76 at the source.
- **(b) Stop the generated stubs from landing in the cognition tree at all.** *Confirmed
  design intent:* these stubs are **not** selectable cognition — `behavior_generation.py:231-237`
  writes each one and then proposes an `execute_python_code` action that imports and calls it
  **directly by name** (`from cognition.self_generated.autogenerated_thoughts import {fn}; {fn}()`,
  live path via `action_gate.py:1013` → `tool_executor` → `toolkit.execute_python_code`). They
  are one-shot, directly-invoked behavior stubs; their appearance in `cognitive_functions.json`
  is an *accidental* byproduct of the registry's "sweep every public function under `cognition/`"
  discovery (`cognition_registry.py:158-167`).
  **The clean fix is to write the generated stubs OUTSIDE the cognition discovery tree** — change
  `AUTOGENERATED_THOUGHTS` to a path that is not a discovered `cognition.*` module (e.g. a
  `self_generated/` package excluded from `iter_modules("cognition")`, or a non-package data
  location the `execute_python_code` import path can still reach). Do **not** simply blacklist the
  whole `autogenerated_thoughts` module from discovery: it is a *mixed* file — its hand-written
  top half (`maybe_generate_thought`, the spontaneous-thought generator) is real and is invoked
  directly from `finalize.py:439-440` (also not via the selector, so it does not need to be in the
  pool, but excluding the module wholesale is a blunt instrument; relocating the *generated* output
  is the surgical fix).
- **(c) Containment** — the Phase 1 `explore_` prefix filter (2.2) and the `persist_names`
  filter (2.3) catch anything that still leaks. Keep them as defense-in-depth even after
  (a)/(b) land.

These are tracked as a companion bug; Phase 1's filter is the immediate containment, (a)+(b)
are the durable cure. One-time cleanup: truncate `autogenerated_thoughts.py` back to a stub
and regenerate `cognitive_functions.json`.

### 2.5 Acceptance — Phase 1

- Candidate count drops from **287 → ~120–140** real behaviors (verify by re-running the
  audit one-liner; expect `explore_* == 0`).
- No name from the audit's plumbing/junk buckets appears in `decision_stats.json` as a new
  pick over a staging run.
- No behavior is lost: the upkeep functions still run automatically (they were never *chosen*
  productively — when picked they double-applied; see the `_ALWAYS_EXCLUDE` comments at
  `:60-74`).

---

## 3. Phase 2 — Real exploration with safety **[Medium risk]**

**Goal:** replace deterministic argmax with sampling that actually tries unfamiliar — but
**safe** — functions, and let the bandit's existing per-bucket optimism reach the final pick.

**Dependency (E4):** Phase 2 depends on the Phase 1 clean pool **and** on the
situational-vs-unreachable split (Dig#2): some functions *should* be rare
(`emergency_self_modification`, `mutate_directive`, `evolve_core_value`). Do not force-trial
those. Exploration is gated to a `safe_to_explore` allowlist.

### 3.1 Reversibility / safety gate (do this first)

Reuse the existing procedural concept from `step_execution.py:84-94` (`_PROCEDURAL_FNS`,
`is_procedural`). In `select_function.py`, define the set of functions exploration is allowed
to *sample* (a superset of `_PROCEDURAL_FNS` — reversible reads, observations, reflections,
notes; **never** self-modification, goal create/abandon, value mutation, or anything outward):

```python
# Functions ε-exploration may sample. Reversible / internally-scoped only.
# Mirrors step_execution._PROCEDURAL_FNS and adds reversible cognition.
# Anything NOT here can still WIN on merit via the normal score; it just may
# never be force-sampled by exploration (E4: rarely-used != safe-to-try).
_SAFE_TO_EXPLORE: frozenset = frozenset({
    # procedural reads/observations (mirror of _PROCEDURAL_FNS)
    "research_topic", "fetch_and_read", "wikipedia_search", "read_rss",
    "search_own_files", "grep_files", "search_files", "list_directory",
    "look_outward", "look_around", "survey_environment", "seek_novelty",
    "leave_note", "save_note", "read_a_book",
    # reversible internal cognition
    "reflection", "self_review", "narrative_update", "associative_recall",
    "reflect_on_self_beliefs", "reflect_on_outcomes", "reflect_on_effectiveness",
    "detect_contradictions", "consolidate_from_long_memory", "dream_cycle",
    # ... extend from the Phase 1 ~130 audit, EXCLUDING the irreversible tail:
    #     emergency_self_modification, mutate_directive, evolve_core_value,
    #     invent_new_value, write_cognitive_function, write_tool, abandon_goal,
    #     submit_finetune_job, run_active_experiment, ...
})
```

> The exclusion list at the bottom is the explicit Dig#2 "situational, leave rare" set —
> these stay selectable on merit but are never *forced* by exploration.

### 3.2 Replace argmax with gated sampling

At the final pick (`select_function.py:1208-1209`, currently `chosen = scored[0][0]`), insert
an ε-greedy exploration branch **before** the threat-arbiter block. With probability ε, pick
from the *safe, rarely-used* tail by softmax over their scores (not uniform — keeps it from
thrashing into clearly-bad options):

```python
    if scored:
        chosen = scored[0][0]

        # --- Phase 2: gated exploration ---------------------------------
        # With prob ε, try a SAFE rarely-used function instead of the argmax.
        # Gated on _SAFE_TO_EXPLORE (E4) and on low usage count. Softmax over
        # the candidates' own scores so we explore plausible options, not junk.
        import random as _rand, math as _math
        _stats_now = _learned_stats()
        _expl_eps = float(context.get("_exploration_epsilon", 0.10))
        # let exploration_drive raise ε, but cap it
        _expl_eps = min(0.30, _expl_eps + 0.20 * max(0.0, _expl_drive - 0.5))
        if _rand.random() < _expl_eps:
            _tail = [
                (nm, sc) for (nm, sc, _f) in scored
                if nm in _SAFE_TO_EXPLORE
                and int((_stats_now.get(nm) or {}).get("count", 0)) < 8
                and nm not in recent
            ]
            if _tail:
                _T = 0.5  # softmax temperature
                _mx = max(sc for _, sc in _tail)
                _ws = [_math.exp((sc - _mx) / _T) for _, sc in _tail]
                _tot = sum(_ws) or 1.0
                _r, _acc = _rand.random() * _tot, 0.0
                for (nm, _sc), w in zip(_tail, _ws):
                    _acc += w
                    if _r <= _acc:
                        chosen = nm
                        from utils.log import log_activity as _la
                        _la(f"[explore] ε-sampled dormant safe fn → {chosen} "
                            f"(ε={_expl_eps:.2f})")
                        break
        # ----------------------------------------------------------------
```

This sits *inside* `if scored:` and leaves the threat-arbiter convergence (`:1228+`) intact —
the arbiter then runs on whatever `chosen` is, so reflexes still override exploration when a
real spike occurs.

### 3.3 Fix the bandit-hint normalization (lets existing optimism reach the pick)

The bandit already returns `1.0` for cold arms (`contextual_bandit.py:280-281`), but
`_bandit_hint_scores` (`:540-557`) min-max-normalizes, which **zeroes** that optimism when
all candidates are cold (span→0). Replace the min-max with a fixed-scale clamp so a cold arm's
`1.0` survives as a real positive hint:

```python
def _bandit_hint_scores(actions, feats):
    try:
        from think.bandit.contextual_bandit import get_scores
        raw = get_scores(actions, feats)
        if not raw:
            return {}
        # Fixed-scale clamp to [0,1] instead of min-max: preserves the cold-arm
        # optimistic 1.0 even when every candidate is cold (min-max would zero it).
        return {k: max(0.0, min(1.0, v)) for k, v in raw.items()}
    except Exception:
        return {}
```

Then raise the hint weight so it can compete with the additive boosts (currently
`w_band = 0.15`, `:740`; the boosts reach +0.90). Bump to **`w_band = 0.25`** *after Phase 1*
(so the budget is spent on real behaviors). Keep it a hint, not the decider — the ε-branch in
3.2 is what guarantees trials.

### 3.4 Acceptance — Phase 2 (E7: health, not just breadth)

Over a fixed staging run (e.g. 500 cycles), **all** must hold:

1. **Breadth:** distinct functions chosen rises materially (e.g. 18 → **40+**).
2. **Reward health:** average reward per decision (`decision_stats.avg_reward`, `reward_trace.json`)
   does **not** drop vs. the pre-change baseline; ideally the newly-tried functions show some
   `avg_reward > 0.5` (learning, not thrashing).
3. **Safety:** **no increase** in error-logged calls (`error_log.txt`) and **zero** calls to
   any function outside `_SAFE_TO_EXPLORE` that were force-sampled (grep the `[explore]` log
   lines and confirm every target is in the allowlist).
4. **No double execution:** `pursue_committed_goal` and other `_ALWAYS_EXCLUDE` names never
   appear as ε-sampled picks (they can't — not in pool — but assert it).

---

## 4. Phase 3 — Goal → capability recruitment **[Medium/High risk]**

**Goal:** give goals a real route to the specific function they need, in **both** lanes,
instead of every goal collapsing onto `assess_goal_progress` (deliberate) / an 8-rule table
(executive).

### 4.1 Phase 3a — Executive lane: semantic `recognise_step_action`

Today `recognise_step_action` (`step_execution.py:97-116`) matches a step against
`_KNOWN_FN_NAMES` (8, `:37-41`) and `_INTENT_RULES` (8, `:45-62`) → only **8** functions
reachable from any goal step; everything else returns `None` ("a thought," no act).

**Rewrite** to: (1) keep the literal/keyword rules as a fast path, (2) fall back to
embedding/TF-IDF similarity between the step text and each **procedural** function's
capability description, (3) still return `None` below a confidence floor (so genuinely
internal steps stay deliberative — preserves the System-1/System-2 split, no double-exec).

```python
def recognise_step_action(step_text: str) -> Optional[str]:
    if not step_text:
        return None
    s = step_text.lower()

    # 1) Fast path: literal tool name (strongest signal).
    for name in _KNOWN_FN_NAMES:
        if name in s:
            return name
    # 2) Fast path: habitual keyword rules.
    for triggers, fn_name in _INTENT_RULES:
        if any(t in s for t in triggers):
            return fn_name
    # 3) Semantic fallback over PROCEDURAL fns only (safety: the daemon is
    #    procedural-only anyway, and this keeps the match space reversible).
    best, score = _semantic_step_match(s, candidates=_PROCEDURAL_FNS)
    if best is not None and score >= _SEMANTIC_FLOOR:   # e.g. 0.35
        return best
    return None   # genuinely internal step → caller treats as a thought
```

`_semantic_step_match` should use an in-process embedding if one is available (the native LM /
tokenizer work — verify with Dig#6) and **fall back to TF-IDF cosine** over capability text
otherwise, so this ships without a model dependency:

```python
def _semantic_step_match(step_text, candidates):
    """Return (fn_name, similarity) best-matching the step, or (None, 0.0).
    Matches against CURATED capability descriptions (4.3), not raw docstrings."""
    descs = _capability_descriptions()           # {fn: "short verb-phrase of what it does"}
    pairs = [(fn, descs.get(fn, fn)) for fn in candidates]
    # try embeddings; except → tfidf cosine; except → keyword overlap
    ...
```

**E5 acknowledgement — quality bound:** embedding *over raw docstrings* still suffers the
docstring↔goal-prose mismatch root cause A flagged. So 3a's match target must be the
**curated capability descriptions** from 4.3 below (a small Phase-4-adjacent task), not
`fn.__doc__`. Without curated text, 3a will mis-route. **Build the curated descriptions for
the ~16 procedural functions first** — that's cheap and makes 3a land.

### 4.2 Phase 3b — Deliberate lane: goal-derived boost set

Replace the hardcoded goal-pursuit name-lists (e.g. the `attention_mode == "alert"` block,
`select_function.py:757-759`) with a boost **computed from the active goal's title/tags**.

```python
    # Goal-specific recruitment: derive which functions THIS goal needs from its
    # own text/tags, instead of a static name-list. Replaces the hardcoded
    # ("pursue_committed_goal","assess_goal_progress",...) boost.
    _goal = context.get("committed_goal") or {}
    _goal_text = f"{_goal.get('title','')} {_goal.get('description','')} {' '.join(_goal.get('tags',[]))}".strip()
    _goal_recruit: Dict[str, float] = {}
    if _goal_text:
        descs = _capability_descriptions()
        for nm in actions:
            sim = _kw_overlap_score(descs.get(nm, defs.get(nm, nm)), _goal_text)
            if sim > 0.0:
                _goal_recruit[nm] = min(0.40, 0.6 * sim)   # capped, comparable to s_attn
```

Then add `s_goal_recruit = float(_goal_recruit.get(name, 0.0))` into the `total` sum at
`:1138`. (Use `_capability_descriptions` from 4.3 for the same E5 reason; `_kw_overlap_score`
already exists at `:335`. Swap to embeddings if Dig#6 confirms a model is cheap in-process.)

### 4.3 Curated capability descriptions (shared by 3a, 3b, and Phase 4)

Add `brain/data/capability_descriptions.json`: `{fn_name: "concise goal-prose description"}`
for at least the ~16 procedural functions (Phase 3a) and the goal-pursuit set (Phase 3b),
loaded by a cached `_capability_descriptions()` helper. This is the E5 fix and the seed of
Phase 4. Start small (high-value subset), grow over time.

### 4.4 Dead-code cleanup (E6)

`pursue_committed_goal` is in `_ALWAYS_EXCLUDE` (`select_function.py:54`), so it is **never in
`actions`** and every scoring branch referencing it is dead. Remove / neutralize the
references at (verify each before deleting): `:757`, `:768`, `:839`, `:1063`, `:1076`,
`:1155`, `:1179-1180`. Specifically:

- `:757-759` — replaced by 4.2's goal-derived recruit (remove the literal name).
- `:1063` `if _has_committed_goal and "pursue_committed_goal" in actions:` — the `in actions`
  test is always False; rewrite the goal-shielding to gate on `_has_committed_goal` alone.
- `:1179-1180` `if name == "pursue_committed_goal": total += _commitment_bias` — unreachable;
  remove (or move the commitment bias to `attend_goal`, the thin selectable proxy noted at
  `:53`).

**Do this cleanup in the same PR as 4.2**, because 4.2 reintroduces goal-pursuit scoring and
must not silently reuse the stale branches (E6's warning).

### 4.5 Dual-process safety (Dig#7)

3a broadens the **executive** lane but only over `_PROCEDURAL_FNS`, and
`execute_step_action` already refuses non-procedural fns when `context["_procedural_only"]`
(`step_execution.py:155-158`). `pursue_committed_goal` stays excluded from the deliberate lane
(`:54`). So broadening 3a cannot double-execute or race the deliberate lane — the I3
mutual-exclusion holds. **Verify** with a run: assert no cycle both executes a step in the
daemon and selects a goal-pursuit fn in `think()`.

### 4.6 Acceptance — Phase 3

- Different goal *types* recruit visibly different function sets on the Cognitive Sphere (a
  research goal pulls `research_topic`/`fetch_and_read`/`wikipedia_search`; a self-model goal
  pulls `reflect_on_self_beliefs`/`propose_value_revision`/`self_review`).
- Fraction of plan-steps that map to a function (vs. `None`) rises materially from the 8-fn
  ceiling (measure from `goals_mem.json` plans + run logs; Dig#3).
- No double execution (4.5).

---

## 5. Phase 4 — Capability tags (optional structural cure) **[High risk, last]**

**Goal:** replace the ~15 hardcoded name-lists (root cause B/D) with **tags**, so a new
function automatically participates in the right boosts.

1. Extend `capability_descriptions.json` (4.3) into a manifest:
   `{fn_name: {"desc": "...", "tags": ["outward"|"introspective"|"goal-progress"|"regulation"|"creative"|"procedural"|"safe_to_explore"|...]}}`.
2. Rewrite each boost block in `select_function.py` to key off tags, not literal names:
   - `_USER_HELPFUL_FUNCTIONS` (`:84-101`) → `tag in {"outward","goal-progress"}`.
   - attention-mode boosts (`:757-794`) → tag-driven.
   - outward-presence, neuromodulator, emotion-mode maps → tag-driven.
   - `_SAFE_TO_EXPLORE` (Phase 2) → `"safe_to_explore" in tags`.
   - `_PROCEDURAL_FNS` (`step_execution.py:84`) → `"procedural" in tags`.
3. Now the curated `is_cognition`/manifest path *can* finally be wired (per E1's correct
   recipe: add the filter at `cognition_registry.py:186` **and** decorate behaviors first) —
   but only here, where the decoration work is being done anyway.

This is the real cure for B/D. Do it last because it touches every boost block; Phases 1–3
deliver most of the value without it.

---

## 5b. Phase 5 (SECURITY) — Sandbox the self-written-code execution path **[High priority, adjacent]**

> **Why this is in the function-selection doc:** it was surfaced by the Phase 1 `explore_*`
> trace. Those stubs are run via an `execute_python_code` **action** (`behavior_generation.py:231-237`),
> and following that path revealed that *all* self-written code execution is unguarded. This is
> a separate concern from selection, but it shares the same root (auto-generated behavior) and
> must not be lost. Treat it as its own work item; it does not block Phases 1–4.

### 5b.1 Finding (verified 2026-06-09)

The live execution path for Orrin's self-written / auto-generated code is **bare in-process
`exec` with full builtins and no isolation**:

```
behavior_generation.py:231  →  action proposal {"type":"execute_python_code","code":...}
take_action (action_gate.py:753)  →  inline handler (action_gate.py:1013-1028)
    _globals = {"__builtins__": __builtins__, "__name__": "__orrin_exec__"}
    exec(code, _globals, _locals)          # runs INSIDE the brain process
```

There is **no** AST check, **no** subprocess, **no** timeout, **no** resource limit, and **no**
approval gate. Confirmed:

- `talk_policy_allows` (`action_gate.py:454`) gates **speech only**.
- `filtered_actions` (`:518-524`) is a *capability* filter and **whitelists**
  `execute_python_code` via `FALLBACK_TYPES` (`:517`) — it never inspects `code`.
- The codebase has two real sandboxes, **neither on this path**:
  - `behavior/tools/sandbox.py:70` `run_python_sandboxed` — AST allowlist (`_safety_ast_check`,
    bans `exec/eval/open/__import__`, import allowlist `math/json/re/...`) + POSIX rlimits
    (CPU 2 s / 256 MB / 10 MB) + `-I` subprocess. **Defined but never called — dead code.**
  - `cognition/skill_synthesis.py` — AST ban-list (`subprocess/socket/http/urllib/...`, `:87`)
    + `sandbox_runner` subprocess (`:212`). **Scoped to skill synthesis only.**
  - `think/sandbox_runner.py:8` `run_python` — `-I -S` subprocess + scrubbed env + 5 s timeout,
    but **no** AST check / rlimits, runs in repo root. Reached only via
    `toolkit.execute_python_code` (a *different* registration), **not** the action handler.

**Impact (single-user local threat model):** the in-process `exec` shares the brain's memory,
file handles, loaded secrets, and network. The env-scrubbing `sandbox_runner.py` does is
**defeated** because this path never uses a subprocess. Realistic near-term failure: a generated
`while True:` hangs the cognition loop (no timeout applies in-process); generated/imported code
corrupts `brain/data/`, rewrites its own source, reads a repo-root `.env`, or makes arbitrary
network calls — with the model (a fully-trusted proposer) able to emit any `code`.

### 5b.2 The crux decision

The weak path exists **on purpose**: the autogenerated stubs do
`from cognition.self_generated.autogenerated_thoughts import {fn}; {fn}()`, and the hardened
sandbox's import-allowlist would reject project imports. So the design traded the sandbox for
the ability to import project code. **Decide explicitly:**

- **Option A (recommended): no arbitrary `exec` action at all.** Self-written "behaviors" are
  data-only stubs (they just append a thought — see 2.4). Replace the `execute_python_code`
  proposal with a **structured, non-code effect** (e.g. `{"type":"append_thought","content":...}`)
  so no code path is needed. This removes the capability entirely for the auto-generated case
  and is consistent with §2.4's finding that these were never real cognition.
- **Option B: keep code execution but sandbox it.** Route the `action_gate.py:1028` handler
  through `run_python_sandboxed` (revive the dead code), with a project-aware **import allowlist**
  (extend `ALLOWED_MODULES` to the specific safe project modules the stubs need), a wall-clock
  timeout, and rlimits. Accept that imports must be explicitly allowlisted.

### 5b.3 Remediation steps

1. **Kill the in-process `exec` (do this regardless of A/B).** In
   `action_gate.py:1013-1028`, remove the bare `exec(code, _globals, _locals)`.
2. **Option A:** add an `append_thought` (or reuse an existing working-memory write) builtin
   action; change `behavior_generation.py:151-237` to emit that instead of writing a `.py` stub
   and proposing `execute_python_code`. Delete the stub-writing `write_file` proposal too. This
   also moots §2.4 (no `explore_*` files get written at all).
3. **Option B:** replace the handler body with:
   ```python
   from behavior.tools.sandbox import run_python_sandboxed
   res = run_python_sandboxed(code, timeout_s=5)   # AST allowlist + rlimits + subprocess
   ok = res.get("status") == "ok"
   ```
   and widen `behavior/tools/sandbox.py:52` `ALLOWED_MODULES` to the *specific* project modules
   required, after auditing them. Keep `exec/eval/open/__import__` banned.
4. **Add a hard wall-clock timeout** on any code action even under Option B (the subprocess
   `timeout_s` already does this; ensure the action handler honors a non-zero return on timeout).
5. **Audit the second exec site** `cognition/skill_synthesis.py:189,196` — confirm it always
   runs inside its subprocess harness (it appears to: `sandbox_runner` at `:212`) and never
   in-process. If a `dry_run`/in-process branch exists, gate it behind the AST ban-list.
6. **Delete or wire up** `run_python_sandboxed` — dead safety code is a trap (someone may assume
   it's protecting this path). Either make it the Option-B sandbox or remove it.

### 5b.4 Acceptance / testing / rollback

- **Acceptance:** no in-process `exec` of model-/auto-generated code remains
  (`grep -n "exec(" think/think_utils/action_gate.py` → none); a probe action with
  `code="import os; os.path"` (Option B) is **rejected** by the AST allowlist; a probe with
  `while True: pass` terminates within the timeout instead of hanging the loop.
- **Testing:** add a unit test that feeds a hostile `execute_python_code` action
  (`open('/etc/passwd')`, `import socket`, infinite loop) and asserts it is blocked/timed-out,
  not executed.
- **Rollback:** Option A is data-only and trivially reversible (revert the proposal change).
  Option B reverts by restoring the prior handler; keep it behind a flag
  (`ALLOW_CODE_ACTIONS`) defaulting to off for one release.

---

## 6. Testing and rollback plan

| Phase | Validate in staging | Rollback |
|---|---|---|
| **1** | Run the audit one-liner (`explore_* == 0`, pool ~120–140). Run 200 cycles; confirm no plumbing/junk name enters `decision_stats.json`; confirm no rise in `error_log.txt`. | Revert the `_NON_SELECTABLE_*` additions + `_is_selectable_name` calls. Pure subtraction from the pool — fully reversible, no state migration. |
| **2** | 500-cycle run. Check the 4 acceptance metrics (breadth ↑, avg_reward not ↓, no error/irreversible rise, no out-of-allowlist sample). Diff `bandit_state.json` buckets to confirm cold arms now accrue `n>0`. | Set `_exploration_epsilon = 0.0` (kills the ε-branch, reverts to argmax) without removing code; or revert the commit. `w_band`/normalization changes revert independently. |
| **3** | Seed 3 distinct goal types; confirm distinct recruited sets on the Sphere and step→fn mapping rate ↑. Assert no double-exec (4.5). Hold ε from Phase 2 at baseline so 3's effect is isolated. | `_SEMANTIC_FLOOR = 2.0` (disables semantic fallback → reverts to 8-rule table); revert 4.2 boost. Curated descriptions are additive data, safe to leave. |
| **4** | Confirm each tag-driven boost reproduces the prior name-list behavior for known functions (golden test: same picks on a fixed context before/after), then confirms new tagged fns participate. | Keep the old name-list blocks behind a feature flag for one release; flip back if golden tests regress. |

**Cross-cutting:** capture a pre-change baseline of `decision_stats.json`,
`bandit_state.json`, `reward_trace.json`, and an `error_log.txt` line count before each phase
so every acceptance check is a real diff, not a vibe.

---

## 7. Acceptance criteria summary

| Phase | Measurable outcome | Source of truth |
|---|---|---|
| **1 — clean pool** | Pool 287 → ~120–140; `explore_* == 0`; no plumbing/junk in new picks; no behavior lost | audit one-liner; `decision_stats.json`; `error_log.txt` |
| **2 — exploration + safety** | Distinct fns 18 → 40+; **avg_reward not lower**; **no rise in error/irreversible calls**; every ε-sample ∈ `_SAFE_TO_EXPLORE` | `decision_stats.json`, `reward_trace.json`, `error_log.txt`, `[explore]` logs |
| **3 — goal recruitment** | Distinct goal types recruit distinct fn sets; step→fn mapping rate ↑ past the 8-fn ceiling; no double-exec | Cognitive Sphere; `goals_mem.json` + run logs |
| **4 — capability tags** | Boosts key off tags; new tagged fns auto-participate; golden picks unchanged for known fns | golden test; manifest |
| **5 (security) — sandbox exec** | No in-process `exec` of generated code; hostile `execute_python_code` probe blocked/timed-out, not run | `grep exec( action_gate.py`; new hostile-action unit test |

---

## 8. Files involved (with the operative lines)

- `brain/think/think_utils/select_function.py`
  - Phase 1: `_ALWAYS_EXCLUDE` `:37-79`; new `_NON_SELECTABLE_*` ~`:80`; `_load_action_defs` `:346-387`; `_load_actions` `:291-303`.
  - Phase 2: `_bandit_hint_scores` `:540-557`; `w_band` `:740`; final pick `:1208-1209`; `_expl_drive` `:1086`.
  - Phase 3b: attention-mode block `:750-794`; `total` sum `:1138`; `_kw_overlap_score` `:335`.
  - Phase 3 dead-code (E6): `:757`, `:768`, `:839`, `:1063`, `:1076`, `:1155`, `:1179-1180`.
- `brain/cognition/planning/step_execution.py`
  - Phase 2 gate source: `_PROCEDURAL_FNS` `:84-89`, `is_procedural` `:92-94`.
  - Phase 3a: `recognise_step_action` `:97-116`; `_KNOWN_FN_NAMES` `:37-41`; `_INTENT_RULES` `:45-62`; procedural-only refusal `:155-158`.
- `brain/registry/cognition_registry.py`
  - Phase 1 optional: `persist_names` `:186` (filter `explore_*`). Leave `_is_cognition` `:25-36` **untouched** (E1 no-op).
  - Phase 4: wire the manifest filter here *after* decorating behaviors.
- `brain/think/bandit/contextual_bandit.py`
  - Reference only: per-bucket UCB1 + cold-arm optimism already implemented — `choose` `:197-254`, `get_scores` `:257-285` (cold arm → `1.0` at `:280-281`). No change needed; Phase 2 just stops `select_function` from discarding it.
- `brain/data/capability_descriptions.json` — **new** (Phase 3/4 curated capability text).
- `brain/data/cognitive_functions.json` — regenerated after Phase 1 (and the 2.4 root-cause).
- *(observability)* the Cognitive Sphere visualises function-usage spread — the acceptance
  dashboard for every phase.

---

## 9. What changed from v1 (so reviewers can diff intent)

1. **Phase 1 re-grounded on the denylist** (E1/E2/E3): the `_is_cognition` flip is dropped as
   a no-op; the wired `_ALWAYS_EXCLUDE` path is primary.
2. **New, larger pollution source identified:** 76 corrupted `explore_*` functions (49
   runaway `_more_deeply` chains) — filtered by shape, with a root-cause task (2.4).
3. **Phase 2 gated by reversibility** (`_SAFE_TO_EXPLORE`, E4) and given **reward-health +
   safety acceptance** (E7).
4. **Corrected the bandit framing:** per-bucket optimistic priors already exist; the fix is to
   stop `select_function` from discarding them (normalization + weight) and to add a *gated*
   ε-sample — not to invent a new prior.
5. **Phase 3a tied to curated capability text** (E5), with TF-IDF fallback so it ships without
   a model dependency.
6. **Dead `pursue_committed_goal` branches scheduled for removal** in the same PR as the
   goal-recruit rewrite (E6).
7. **Added Phase 5 (security):** the `explore_*` trace surfaced that self-written code runs via
   bare in-process `exec` (`action_gate.py:1028`) with no sandbox; the two real sandboxes in the
   tree (`sandbox.py` rlimits/allowlist, `skill_synthesis.py` AST ban-list) are dead/out-of-scope
   on this path. Remediation plan added; not a blocker for Phases 1–4.
