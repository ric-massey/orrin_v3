# Top-Down Write-Back — Implementation Plan (2026-06-27)

**Status:** proposed → to build on the main code path (no feature flag).
**Unblocks when:** built on the main path, or explicitly dropped.
**Closes:** the "broadcast→substrate write-back is still missing" limitation
(`docs/ARCHITECTURE.md` §Global workspace; `README.md` §Known limitations).
**Supersedes the parking of:** Seam #4, but in its *decaying-only* form (see §1).

---

## 0. The decision this plan commits to

The architecture has been one-directional: the global-workspace winner is
**broadcast outward** — it biases the action pick (`ORRIN_WORKSPACE_PRIOR`) and can
recruit `inner_loop` on conflict — but nothing writes the conscious conclusion
**back down** into the substrate's priors. Feedback never reshapes a drive or a
salience prior, so across long runs Orrin acts on conclusions he never lets change
him.

The original Seam #4 design (`archive/UNIFIED_EMBODIED_DEVELOPMENT_PLAN_2026-06-15.md`
§3.2) bundled write-back with a full developmental arc ("born impoverished, becomes
himself"). That bundling was a *risk-tolerance judgment*, not a mechanical
dependency. We are **decoupling** them and keeping only the coherence half:

- **WE BUILD:** a permanent, bounded, **decaying** downward path. Conscious
  conclusions nudge priors, then those nudges drain back toward the shipped-adult
  baseline. The substrate *tracks* recent conclusions (long-run coherence) but never
  *becomes* a different substrate (no ontogeny).
- **WE PERMANENTLY OMIT:** the consolidation→**permanent** promotion path. There is
  no mechanism by which a write-back becomes a durable, baseline-shifting prior. That
  omission is the whole "coherent-but-adult" fork, and it is a design decision we
  keep — not a flag, not a TODO.

This is **on the main path, on by default, not reversible by config.** Decay is the
permanence; absence of promotion is the permanence. Those two properties *are* the
design — not a safety dial we might later turn off.

---

## 1. Design principles (load-bearing)

1. **One write-down spine, not three.** Reappraisal→drives and Hebbian→salience
   priors are the same downward path hitting different priors. Build one module.
2. **Reuse the existing primitive.** Affect-target writes route through the
   already-built single-writer inbox `brain/control_signals/arbiter.py::submit_affect`
   (`weight=`, `ttl_cycles=`) — a write that is already weighted, time-boxed, and
   decaying. We do **not** fork a second affect writer.
3. **Decay is mandatory and intrinsic.** Every write has a finite TTL (affect) or a
   per-cycle decay (salience prior). A wrong conclusion produces a bounded
   *transient*, never an entrenched prior.
4. **No promotion path. Ever.** Nothing in this spine writes to a durable baseline,
   to `concept_memory`, to identity, or to learned setpoints. (See §6 for why
   `concept_memory` model-correction — the third Seam #4 target — is deliberately
   excluded.)
5. **Reflex floors are untouchable.** The autonomic layer (`HostResourceGuard`,
   `resource_floor`, absolute safety floors) never receives a write-back proposal.
   Write-back only ever nudges *cortical/relative* priors, never absolute floors —
   "refuse-to-imprint" by construction.
6. **The workspace decides; write-back only reshapes priors.** Write-back never
   forces a winner, flips an "is conscious" flag, or preempts selection (consistent
   with I7). It biases the *next* competition, exactly like every other prior.

---

## 2. Where it hooks (verified call sites)

> **CORRECTION (2026-06-29, after an 8h validation run found write-back never
> fired).** The original claim below — that the conscious winner is set by the
> *end-of-cycle* `update_workspace` in `finalize.py` — is **wrong**. There are TWO
> `update_workspace` calls per cycle. The **pre-think** call in
> `brain/loop/deliberate.py` (after the Monitor offers + binding) is the one that
> decides the substantive winner (binding/monitor conclusions) **and then consumes
> `_bound_candidates` / `_workspace_offers`**. By the `finalize` call those candidates
> are gone, so it only ever sees a starved low-salience leftover → `_is_conclusion`
> is False → `write_back` silently no-ops. **Fix: the hook lives at the pre-think
> call in `deliberate.py`, not `finalize.py`.** The unit tests passed because they
> call `write_back` directly with a qualifying moment and never exercise the
> two-call ordering — only a live run surfaced it.

The conscious winner of a cycle is set by the end-of-cycle
`update_workspace(context)` in `brain/loop/finalize.py:466-467`. Crucially,
`commit_affect(context)` already ran earlier in the same cycle
(`finalize.py:277`). Therefore:

> A write-back derived from **this** cycle's winner is queued via `submit_affect`
> and integrated by `commit_affect` on the **next** cycle. One-cycle latency,
> gradual, decaying — the correct human-like shape. No reordering of finalize is
> required.

**Insertion point:** immediately after `finalize.py:467` (`_moment = _uw(context)`),
call the new spine with the freshly-chosen moment:

```python
    if _moment:
        from brain.cognition.workspace_writeback import write_back
        write_back(context, _moment)          # queues decaying downward proposals
        ...existing bridge update...
```

The salience-prior half is consumed back inside
`brain/cognition/global_workspace.py::update_workspace` (the natural reader of
salience priors), added as one more additive term alongside the existing
`goal_lens_relevance` / `subconscious_relevance` / habituation terms.

---

## 3. The module — `brain/cognition/workspace_writeback.py`

A single fail-safe module. Public surface:

```python
def write_back(context: dict, moment: dict) -> None: ...
def salience_prior(context: dict, content: str) -> float: ...   # read side
def tick_salience_priors(context: dict) -> None: ...            # per-cycle decay
```

### 3.1 `write_back(context, moment)` — the spine

Runs once per cycle on the chosen conscious moment. Two targets:

**(a) Reappraisal → drives (affect targets).**
Map the *kind* of conclusion to a small signed nudge on a core signal, submitted
through the existing inbox:

```python
submit_affect(context, target=<core_signal>, delta=<small>, weight=<low>,
              source="workspace_writeback", ttl_cycles=<short>)
```

Eligible targets are cortical/relative core signals only (e.g. `impasse_signal`,
`motivation`, novelty/curiosity signals) — **never** `_SCALAR_TARGETS` absolute
floors or reflex state. Example mappings (final list set in build, kept short):
- a conclusion that the current approach is stuck (source = monitor breakthrough /
  `wants` = escalate) → small **+impasse_signal** nudge so the next cycle inherits
  the felt impasse instead of rediscovering it cold.
- a conclusion that resolves/closes a goal step (binding moment carrying the
  committed `goal_id`, goal in focus) → small **+motivation / −impasse** nudge.
- a salient novel insight (subconscious insight that won) → small **+novelty**
  nudge so follow-on exploration is primed.

All deltas are bounded (|delta| ≤ `_MAX_AFFECT_DELTA`, low weight) so a single
cycle can only ever nudge, never lurch; `ttl_cycles` keeps it draining.

**(b) Hebbian → salience priors (the new decaying store).**
The content that just won consciousness primes its own tokens so that *related*
content is slightly more likely to win next time — continuity of theme across
cycles, which is what "coherent over long runs" concretely means. Implementation:
`_prime(context, moment["content"], boost)` adds/refreshes token weights in the
decaying store (§3.2).

`write_back` is gated (§4) so only genuine *conclusions* write — not every
flicker of awareness.

### 3.2 The salience-prior store

A small, bounded, decaying token→weight map, persisted alongside the workspace
stream (`DATA_DIR / "workspace_priors.json"`), mirrored on
`context["_workspace_priors"]`.

- **Prime:** `weight[token] = min(_CAP, weight[token] + boost)` for the winner's
  content tokens (reuse `global_workspace._tokens` / stopwords).
- **Decay:** `tick_salience_priors` multiplies every weight by `_DECAY` (< 1.0)
  each cycle and drops entries below `_FLOOR`. Bounded to `_MAX_TOKENS` (evict
  lowest). This is the only persistence — it is *designed to forget*.
- **Read:** `salience_prior(context, content)` = bounded sum of primed weights for
  the content's tokens, clamped to `≤ _PRIOR_CEIL` (small, e.g. 0.12).

`tick_salience_priors` is called once per cycle (cheap; alongside the existing
`tick_commitment` in finalize, or at the top of `update_workspace`).

### 3.3 Consumption in `update_workspace`

Inside the per-candidate scoring loop in
`global_workspace.py::update_workspace`, add one additive term mirroring the
existing prior terms:

```python
sp = salience_prior(context, c.get("content") or "")
if sp:
    c["salience_prior"] = round(sp, 3)
    c["salience"] += sp
```

and surface `salience_prior` in the `_workspace_candidates` telemetry block so the
UI can show *why* something stayed in focus. The winner's own priming is applied by
`write_back` after selection, so a content can't bootstrap itself within a single
cycle.

---

## 4. What counts as a "conclusion" worth writing

Not every conscious moment should reshape the substrate; idle percepts shouldn't.
`write_back` writes only when **all** hold:

- `moment["salience"] >= _WRITE_THRESHOLD` (it actually won decisively), **and**
- `moment["source"]` ∈ {`thought`, `binding`, `subconscious`, `monitor`/offer with
  `wants`} — i.e. a *conclusion or breakthrough*, not a bare `user`/`signal`
  echo (those are inputs, already represented elsewhere), **and**
- the content is not pure noise (`global_workspace._is_noise`).

The affect-target nudge additionally requires a recognizable *kind* (§3.1); absent
one, only the salience-prior (theme-continuity) half fires. This keeps the affect
side conservative and the salience side broad.

---

## 5. Safety, bounds, and the properties that make this permanent

| Property | Mechanism | Why it's safe to keep on |
|---|---|---|
| No entrenchment | affect TTL drain + salience `_DECAY` per cycle | every write is a transient; nothing accumulates without bound |
| No lurch | per-cycle `_MAX_AFFECT_DELTA`, low weight, `_PRIOR_CEIL` | one cycle can only nudge; weighted-sum in `commit_affect` keeps weak sources weak |
| No reflex capture | targets restricted to cortical/relative signals; floors excluded | "refuse-to-imprint": absolute floors never bend |
| No ontogeny | **no promotion path exists** | substrate cannot become a different substrate; born adult, stays adult |
| Fail-safe | whole module wrapped; `record_failure` on any error | a write-back fault can never break a cycle |
| Bounded store | `_MAX_TOKENS` eviction, `_FLOOR` pruning | the salience prior cannot grow without bound |

Numeric constants (`_MAX_AFFECT_DELTA`, `_DECAY`, `_FLOOR`, `_CAP`, `_PRIOR_CEIL`,
`_MAX_TOKENS`, `_WRITE_THRESHOLD`, `ttl_cycles`) are tuned conservative-first in
build; starting points proposed inline above.

---

## 6. Why `concept_memory` model-correction is excluded

Seam #4's third target was "model-correction → `concept_memory`." We **omit** it
here, deliberately and (for now) permanently:

- A durable rewrite of `concept_memory` from a conscious conclusion *is*
  entrenchment — it's the one target with no decay, i.e. the ontogeny we forked
  away from.
- The coherence win the user asked for comes from drives + salience priors (recent
  conclusions shaping the next cycles). Concept rewriting buys "becoming," not
  coherence, and carries the corruption-amplified-by-replay risk.

If a durable-learning path is ever wanted, it is a *separate* future decision with
its own consolidation gate — not part of this spine.

---

## 7. Telemetry

- `write_back` logs one bounded private line per actual write
  (`log_private("[writeback] (kind) target Δ … primed N tokens")`).
- `update_workspace` already emits `_workspace_candidates`; add `salience_prior`
  to each entry so the Attention/Workspace UI can show theme-continuity influence.
- A bounded `workspace_writeback.jsonl` (cycle, source, affect target+delta, primed
  token count) so a run *archive* can answer "did closing the loop change behavior?"
  without process memory — mirroring the existing `production_loop.jsonl` pattern.

---

## 8. Tests (`tests/brain/test_workspace_writeback.py`)

1. **Decay returns to baseline** — prime a token, tick N cycles, assert
   `salience_prior` → 0 (no entrenchment).
2. **Affect nudge is queued, not applied** — `write_back` adds a proposal to
   `context[_PROP_KEY]`; `commit_affect` integrates it next cycle; bounded by
   `_MAX_AFFECT_DELTA`.
3. **Reflex floors excluded** — a moment that would map to an absolute floor target
   produces no proposal.
4. **Gating** — low-salience / `user` / `signal` / noise moments do not write.
5. **Theme continuity** — priming content A raises A-related candidate salience next
   cycle; an unrelated candidate is unaffected; the winner can't self-boost within
   its own cycle.
6. **Bounded store** — exceeding `_MAX_TOKENS` evicts lowest; never unbounded.
7. **Fail-safe** — a malformed moment / store can't raise out of `write_back` or
   `update_workspace`.

---

## 9. Build order

1. Module `workspace_writeback.py` with the salience-prior store + `write_back` +
   `salience_prior` + `tick_salience_priors`. Unit tests 1,5,6,7.
2. Wire the read side into `update_workspace` (additive term + telemetry field).
3. Wire `write_back` + `tick_salience_priors` into `finalize.py` after line 467.
   Tests 2,3,4.
4. Telemetry: private log + `workspace_writeback.jsonl`.
5. **Validation run** (not a flag — it's live): one staging run with the
   `workspace_writeback.jsonl` audited — confirm writes are sane, decay works, no
   stuck attractor in `affect_state.json` (watch `impasse_signal`/`motivation`),
   and the salience store stays bounded.
6. **Docs:** update `docs/ARCHITECTURE.md` (§Global workspace — replace "the
   broadcast→substrate write-back is still missing" with the decaying-write-back
   description) and `README.md` §Known limitations (remove the
   broadcast→substrate bullet; note the permanent coherent-but-adult decision).

---

## 10. Acceptance criteria

- Conscious conclusions measurably reshape next-cycle priors (visible in
  `workspace_writeback.jsonl` and the candidate telemetry).
- Over a long run, affect signals touched by write-back show **transient** excursions
  that **decay**, never a stuck attractor (the §3.3 allostatic-load failure mode must
  not recur).
- The salience store stays bounded and forgets (no monotonic growth).
- Action-selection coherence (the README open question "does the workspace prior make
  action selection more coherent?") is now testable end-to-end, since the prior is no
  longer one-directional.
- Reflex floors and `concept_memory` are provably untouched by write-back.
