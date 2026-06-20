# Binding Stage — Implementation Plan

**Date:** 2026-06-19
**Companion to:** `BINDING_WORKSPACE_AUDIT_2026-06-19.md`
**Goal:** Add a **binding stage between `signal_router` and `global_workspace`**
that clusters this cycle's signals / affect / memory / goal by **shared
referent** and emits **bound composite candidates** — e.g.
`{object: cat, motion: approaching, affect: warmth, memory: <recall>}` as *one
item* — so the workspace can ignite and broadcast a **unified situation** rather
than a single winning fragment.

This closes the only weak stage in the four-stage pipeline (the audit found
competition / ignition / broadcast all strong; binding only partial).

---

## 1. Design principles (constraints this must respect)

1. **Symbolic, no LLM.** Like `global_workspace.py` and `appraisal.py`. Binding
   runs every cycle; it must be cheap and fail-safe.
2. **Bias, never preempt (invariant I7).** Binding *adds* composite candidates to
   the competition. It does not flip an "is conscious" flag and does not remove
   the atomic candidates — a bound composite must still *win* on salience like
   anything else. If binding produces nothing, the workspace behaves exactly as
   today.
3. **Reuse existing materials.** No new perception. Bind from what already exists
   this cycle: `top_signals`, `affect_state`, `committed_goal`,
   `working_memory`, the `world_model` entity/relation graph, and
   `appraisal` event→affect links.
4. **Fail-closed to current behaviour.** Any exception → no composites → atomic
   candidates only. Binding can never break the cycle.
5. **Bounded.** Cap clusters, cap members per cluster, cap composite count, so a
   noisy cycle can't flood the workspace.

---

## 2. Where it slots in (data flow)

```
ORRIN_loop:
  process_inputs(context)            # signal_router → context["top_signals"]   (salience, 3-slot cap)
  ┌─────────────────────────────────────────────────────────────────────┐
  │  NEW:  bind_situation(context)   # binding.py → context["_bound_candidates"]│
  └─────────────────────────────────────────────────────────────────────┘
  ...
  update_workspace(context)          # global_workspace: _candidates() now also
                                     # ingests _bound_candidates, competes, ignites, broadcasts
```

The binding stage **writes** `context["_bound_candidates"]` (a bounded list of
composite dicts). `global_workspace._candidates()` **reads** it — exactly the
pattern already used for `context["_workspace_offers"]` (see
`offer_to_workspace`). No new emit path, no bridge coupling inside binding.

---

## 3. What a "referent" is, and how to cluster

A **referent** is the thing several signals are *about*. We cluster this cycle's
items by referent using three cheap, independent signals (any one can link two
items; union them):

1. **Entity overlap** — shared named entities. `world_model.py` already extracts
   entities and `_KNOWN_PERSONS`; reuse its tokenizer/entity set to tag each
   candidate with the entities it mentions. Two candidates sharing an entity are
   linked. *(Strongest link.)*
2. **Lexical overlap** — token-set Jaccard over content, reusing
   `global_workspace._tokens()` / `_overlap()` (already stopword-filtered). Link
   if overlap ≥ θ (start θ = 0.34, same neighbourhood as the subconscious gate).
   *(Catches referents the world_model hasn't entity-ized yet.)*
3. **Co-timing / causal proximity** — items produced the same cycle that
   `appraisal` already related (event→affect `cause` field), plus the
   `committed_goal` (always part of the current situation), plus the
   `_hijacked_by` affect (the feeling that is *about* the pressing signal). These
   are *a-priori* links independent of text.

Clustering = connected components over the link graph (union-find on ≤ ~12 items
— trivial). Singletons stay atomic (no composite emitted; the existing atomic
candidate already covers them).

---

## 4. The composite candidate shape

A cluster with ≥ 2 bound members becomes one composite candidate:

```python
{
  "source": "binding",
  "kind": "situation",
  "content": "the cat is approaching — warmth, and I remember it from this morning",
  "salience": <aggregated>,          # see §5
  "object": "cat",                    # dominant entity (or None)
  "facets": {                         # the bound features, by role
      "object":  "cat",
      "motion":  "approaching",
      "affect":  {"warmth": 0.62},
      "memory":  "<recall snippet>",
      "goal":    "<committed goal title or None>",
  },
  "members": [<source tags of the atomic candidates absorbed>],
  "referent_links": ["entity:cat", "lexical", "appraisal_cause"],  # why these bound
}
```

- **Role assignment** (`facets` keys) is rule-based by the member's `source` /
  `routing_target` / tags:
  - `affect` / `emotion_cortex` / hijack signal → `affect`
  - `goal` / `committed_goal` → `goal`
  - `thought` / `working_memory` recall → `memory`
  - `signal` with motion/verb tokens → `motion` / `event`
  - `user` → `interlocutor` (a present other is part of the situation)
- **`content`** is a short symbolic template composed from the facets (no LLM),
  e.g. `"{object} {motion} — {affect_word}, {memory_clause}"`, falling back
  gracefully when a facet is absent. Keep ≤ 200 chars.

---

## 5. Salience of a composite (so binding actually changes outcomes)

A bound situation should be *more* likely to ignite than its loudest fragment —
that is the whole point ("the cat approaching" should beat "a vague warmth").
But it must not always dominate, or it defeats competition.

Proposed aggregation (tuneable, start conservative):

```
composite_salience = max(member_saliences)
                   + COHERENCE_BONUS * (n_members - 1)      # more bound facets = more coherent
                   + ENTITY_BONUS    * has_named_object
                   - REDUNDANCY      * 0                     # (reserved)
```

Start: `COHERENCE_BONUS = 0.06` (cap the bonus at +0.18 so ≥4 facets don't run
away), `ENTITY_BONUS = 0.05`. Then the *existing* workspace habituation /
hysteresis / subconscious gating in `update_workspace` apply to the composite
unchanged — including `exempt_habituation` if a member carried it.

**Do not remove the atomic members from the competition.** If the composite's
aggregated salience doesn't clear the field, the strongest atomic fragment still
wins, exactly as today. Binding only ever *adds an option*.

---

## 6. New module: `brain/cognition/binding.py`

Public surface (mirrors `global_workspace.py` conventions):

```python
def bind_situation(context: dict) -> list[dict]:
    """Cluster this cycle's candidate contents by shared referent and write
    bound composite candidates to context["_bound_candidates"]. Fail-safe:
    returns [] and writes [] on any error. Symbolic, no LLM."""
```

Internals (all private, all bounded):
- `_collect_items(context)` — gather the *same* sources `global_workspace._candidates`
  uses (user, dominant affect, top signal, goal, last action, recent thought,
  workspace offers), but keep them as structured items with `source` + tokens +
  entities, *before* they're flattened to atomic candidates.
- `_entities_of(text)` — reuse `world_model` entity extraction (import its helper;
  if unavailable, fall back to `_tokens`).
- `_link(a, b)` — entity overlap OR lexical overlap ≥ θ OR appraisal/goal/timing link.
- `_components(items, links)` — union-find → clusters.
- `_assign_roles(cluster)` → `facets`.
- `_render(facets)` → symbolic `content` string.
- `_score(cluster)` → composite salience (§5).
- Caps: `MAX_ITEMS = 12`, `MAX_CLUSTER = 5`, `MAX_COMPOSITES = 3`.

`bind_situation` returns the composites **and** stashes them on
`context["_bound_candidates"]` (consumed-once, like `_workspace_offers`).

---

## 7. Changes to `global_workspace.py`

Minimal, additive:

1. In `_candidates()`, after the existing `_workspace_offers` ingestion, append:
   ```python
   for comp in (context.get("_bound_candidates") or []):
       if isinstance(comp, dict) and comp.get("content"):
           out.append(dict(comp))
   ```
2. In `update_workspace()`, after selecting the winner, **clear**
   `context["_bound_candidates"] = []` (consume-once; binding re-emits next cycle
   if the situation persists), matching how `_workspace_offers` is cleared.
3. When the winner is a composite (`source == "binding"`), carry `facets` /
   `object` / `members` onto the `moment` so the broadcast is the *bound
   situation*, and downstream readers (select_function, UI) get the full picture,
   not just the rendered string. The conscious `moment` becomes the first place
   in the system that holds a genuinely unified situation.

No change to ignition logic, hysteresis, habituation, or the stream — they all
operate on the winner regardless of whether it's atomic or composite.

---

## 8. Wiring in `brain/ORRIN_loop.py`

One call, immediately after `process_inputs(...)` populates `top_signals`
(~line 1727), guarded and fail-safe:

```python
try:
    from cognition.binding import bind_situation as _bind
    _bind(context)        # writes context["_bound_candidates"]
except Exception as _be:
    record_failure("ORRIN_loop.bind_situation", _be)
```

Because the pre-think `update_workspace` (~line 2031) and the end-of-cycle one
(~line 3075) both read `context["_bound_candidates"]`, binding must run before
the first of them. Place it right after `process_inputs`.

---

## 9. Downstream beneficiaries (free wins once `facets` rides the broadcast)

- **`select_function.py`** — the awareness→action `_workspace_prior` can route on
  `moment["facets"]["object"]`/`goal` (act on the *situation*, not a fragment).
- **`express_to_user` / speech** — can narrate the bound situation ("the cat's
  coming over and it's landing as warmth") instead of one stray percept.
- **UI** — `_workspace_candidates` already shows the also-rans; add a "bound
  situation" badge when the winner is a composite, showing its facets. Directly
  addresses the "single winning fragment" feel in the live awareness line.
- **`world_model`** — bound situations are clean episodic units to persist
  (object + event + affect + outcome), better than logging disjoint signals.

---

## 10. Phasing

| Phase | Deliverable | Done when |
|---|---|---|
| **B0** | `binding.py` skeleton: collect items, lexical-overlap clustering only, render, score, caps; write `_bound_candidates`. No world_model/appraisal links yet. | Unit test: two lexically-overlapping signals bind into one composite; unrelated signals don't. |
| **B1** | `global_workspace.py` ingests + consumes `_bound_candidates`; composites carry `facets` onto the `moment`. | Workspace test: a composite with aggregated salience above the field ignites; clearing works (no stale carry). |
| **B2** | Wire `bind_situation` into `ORRIN_loop` after `process_inputs`, fail-safe. | Live cycle: `[aware] (binding) …` appears in `log_private` when ≥2 things share a referent. |
| **B3** | Entity-overlap links via `world_model`; appraisal/goal/timing a-priori links; role assignment by source/tags. | Test: an event signal + its appraisal affect + the named object bind into `{object, event, affect}`. |
| **B4** | Downstream reads `facets`: `select_function` prior routes on object/goal; UI "bound situation" badge. | Action selection demonstrably biased by a bound situation; UI shows facets. |
| **B5** | Tune `COHERENCE_BONUS` / `ENTITY_BONUS` / θ against a run; verify it doesn't lock the spotlight (habituation still releases composites). | Run audit: composites ignite when a real situation is present, atomic fragments still win otherwise. |

Each phase is independently shippable and fail-closes to current behaviour, so
binding can land incrementally without risk to the live loop.

> **Implementation status (2026-06-20): DONE (B0–B4); B5 is runtime tuning.**
> `brain/cognition/binding.py` is built and `bind_situation` is wired into
> `ORRIN_loop.py` after `process_inputs` (fail-safe). `global_workspace.py`
> ingests/consumes `_bound_candidates` and carries `facets`/`object`/`members`/
> `referent_links` onto the winning `moment`; downstream `select_function`,
> `goal_lens` and `memory_io` read the bound facets. Covered by
> `tests/brain/test_binding_stage.py` (green). **B5** (tuning
> `COHERENCE_BONUS`/`ENTITY_BONUS`/θ and confirming composites don't lock the
> spotlight) is a live run-audit activity — to be done on the next staging run,
> not a code change. Archived.

---

## 11. Risks & mitigations

- **Spotlight lock-in** (a composite is always loudest) → cap the coherence
  bonus; existing habituation in `update_workspace` decays repeated composites;
  B5 tunes thresholds. Don't remove atomic members from the competition.
- **Bad binds** (linking unrelated items) → require ≥2 *independent* link types
  for a high-salience composite, or keep θ conservative; a wrong composite simply
  loses the competition, it doesn't corrupt state.
- **Cost** → connected components over ≤12 items with token sets is negligible;
  caps bound the worst case. Reuse `_tokens`/`_overlap` (already compiled regex).
- **Double-counting salience** → composite salience is `max(members) + bonus`,
  not the *sum*, so a bound situation can't out-shout everything by mere
  member-count.

---

## 12. Theory note

This is the **integration** step GNWT presumes but Orrin's workspace currently
skips — and it is the closest Orrin gets to the IIT intuition that consciousness
is *unified* content, not just *broadcast* content. After B3, the conscious
`moment` is, for the first time, a genuinely bound multi-feature situation rather
than a winning fragment: *"that is my cat walking toward me"* instead of *motion*
OR *cat* OR *warmth* on alternating cycles.
