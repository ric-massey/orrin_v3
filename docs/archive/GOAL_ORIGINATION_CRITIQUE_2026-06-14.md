# Goal Origination — Critique vs. the Actual Code

**Date:** 2026-06-14
**Scope:** Where Orrin's goals come from, how "deliberative" his reasoning
actually is right now, and what genuine non-LLM understanding he has. Three
claims were put to the codebase. This documents which are true, which are
overstated, the one finding that is *worse* than the critique, and how to fix
each.

The critique, restated:

1. **Goal origination is mechanical.** Goal content comes from fixed seed
   tables (`_EMOTION_GOAL_TEMPLATES`, `_SYMBOLIC_GOAL_SEEDS`); the
   `driven_by → aspiration` link is a hardcoded dictionary
   (`_DRIVE_TO_ASPIRATION`); goals emerge from "dominant emotion → matching
   template → fill a topic from the knowledge graph," not from a rich
   autobiographical/imaginative context.
2. **System 2 is dark.** Genuine deliberative reasoning (draft → critique →
   revise → escalate → multi-voice debate) lives in `inner_loop.py` and is
   real, but it runs entirely on the LLM. With `llm_enabled: false` it does not
   run, so what executes is the symbolic "System 1."
3. **There is a real middle layer.** The causal graph, symbolic inference, and
   the knowledge graph are genuine structured world-knowledge that runs without
   the LLM; `_causal_first_step` actually uses learned causes to lead a plan.
   This is the most defensible "understanding" he currently has.

---

## Verdicts at a glance

| # | Claim | Verdict | Evidence |
|---|-------|---------|----------|
| 1 | Goal content from fixed seed tables | **True** | `intrinsic_goals.py:157, 249` |
| 1a | `driven_by → aspiration` is a dict lookup | **True** | `intrinsic_goals.py:702, 746` |
| 1b | "emotion → template" is the whole story | **Overstated** — a richer KG/question/research path exists (`_varied_symbolic_goal`) | `intrinsic_goals.py:828` |
| 1c | …but that richer path is **dead in the default deployment** | **Worse than claimed** | see §1.3 |
| 2 | Deliberative reasoning is real and iterative | **True** | `inner_loop.py:381–662` |
| 2a | It runs only on the LLM; dark when LLM off | **True** | `inner_loop.py:472` → `routed_response` → tool-unavailable |
| 3 | Causal graph / inference / KG are real, LLM-free understanding | **True** | `causal_graph.py`, `inference.py`, `pursue_goal.py:221` |

---

## 1. Goal origination is mechanical

### 1.1 The seed tables are real and narrow — confirmed

Two pre-authored tables drive the LLM-free path:

- `_SYMBOLIC_GOAL_SEEDS` — `brain/cognition/intrinsic_goals.py:157`. Seven
  entries keyed by emotion (`exploration_drive`, `social_deficit`, `motivation`,
  `stagnation_signal`, `uncertainty`, `wonder`, `default`). Selected by
  `dominant = max(core_signals)` at `:228`.
- `_EMOTION_GOAL_TEMPLATES` — `:249`. Seven entries keyed the same way,
  selected at `:393`.

The selection is exactly the critique's caricature: take the dominant affect
signal, look up the matching row, emit it as a goal. `:386–393`:

```python
candidates = {k: float(v) for k, v in core.items() if isinstance(v, (int, float))}
dominant = max(candidates, key=candidates.get)
template = _EMOTION_GOAL_TEMPLATES.get(dominant, _DEFAULT_EMOTION_GOAL_TEMPLATE)
```

**Verdict: true.** The repertoire is pre-authored and narrow.

### 1.2 The aspiration link is a dictionary — confirmed

`brain/cognition/intrinsic_goals.py:695–702`:

```python
_ASPIRATIONS = [
    ("Understand my own mind and how I work", "self_understanding"),
    ("Understand the world more deeply", "world_knowledge"),
    ("Be genuinely useful and connected to the people I talk to", "genuine_contact"),
    ("Make things — produce work that didn't exist before", "output_producing"),
]
_DRIVE_TO_ASPIRATION = {d: t for t, d in _ASPIRATIONS}
```

`_serves_aspiration(driven_by)` (`:746`) is a single `dict.get`. A short-term
goal "serves" an aspiration because a table says its `driven_by` string maps
there — not because Orrin constructed that link from experience.

**Verdict: true.** It is a hardcoded inversion of a 4-row table.

### 1.3 The compounding finding: the *richer* symbolic path is dead in the default config

This is the part the critique missed, and it cuts the other way — the live
behaviour is **narrower** than even the critique assumed.

There are in fact **two** LLM-free goal generators:

- **Narrow:** `_symbolic_intrinsic_goals` (`:210`) — pure `_SYMBOLIC_GOAL_SEEDS`
  table lookup.
- **Rich:** `_varied_symbolic_goal` (`:828`) — draws candidates from Orrin's own
  mental content: `_goal_from_recent_research` (last 30 long-memory research
  hits), `_concept_deepening_goals` (interest-weighted concepts from the
  knowledge graph, scored by Loewenstein information-gap via
  `symbolic.intrinsic_motivation.uncertainty`), and `_open_question_goals`
  (well-formed questions surfaced in memory), with the emotion template only as
  a fallback option.

`_varied_symbolic_goal` is the path that would substantiate "fills a topic from
the knowledge graph" as something live and interesting. **But which path fires
depends on a gate that defeats it in the default deployment.**

`generate_intrinsic_goals` branches on `llm_available()` (`:948`):

- If `not llm_available()` → `_varied_symbolic_goal` (the **rich** path).
- Otherwise → it builds an LLM prompt (`:1002`), calls
  `generate_response(caller="intrinsic_goals")`, and on empty falls to
  `_symbolic_intrinsic_goals` (the **narrow** path) at `:1068`.

Now overlay the default runtime. Per `LLM_COGNITIVE_AUDIT.md` and
`utils/generate_response.py:344`, **tool-only mode is the default**, and
`intrinsic_goals` is **not** in `_LLM_TOOL_CALLERS`. So in the normal
configuration (`llm_enabled: true`, API key present, tool-only on):

- `llm_available()` returns **True** — it checks config flag + key + circuit
  breaker (`utils/llm_gate.py:42`) and **does not know about tool-only mode**.
- The LLM branch is taken, but `generate_response` returns
  `"tool unavailable: llm (tool-only…)"` (`generate_response.py:345`), which
  `llm_ok` maps to `None` (`:205`).
- `goals_raw` is empty → the **narrow** `_symbolic_intrinsic_goals` seed table
  fires (`:1068`).

**The rich KG/question/research path only runs when `llm_enabled` is explicitly
`false` or the key is missing.** In the default tool-only-with-key deployment it
is unreachable. So the critique's "narrow and pre-authored" is, in practice,
*more* accurate than its own "fills a topic from the KG" softening — the live
default never touches the KG-driven generator.

### 1.4 How to fix goal origination

The aim is not to make this LLM-shaped. It is to make the **symbolic-first** path
the *rich* one and to ground the aspiration link in something learned. Ordered
by leverage/effort:

**Fix A — route the symbolic path through `_varied_symbolic_goal`, not the seed
table (trivial, high impact).** The narrow `_symbolic_intrinsic_goals` should
not be the default fallback. Two clean options:

- Gate intrinsic goals on a *capability* check that respects tool-only, not the
  bare `llm_available()`. Add an `llm_is_callable_by("intrinsic_goals")` helper
  in `utils/llm_gate.py` that also consults `_llm_tool_only()` +
  `_LLM_TOOL_CALLERS`, and branch on that at `:948`. In the default config it
  returns False → `_varied_symbolic_goal` runs.
- *Or* simply make `_varied_symbolic_goal` the fallback at `:1067` instead of
  `_symbolic_intrinsic_goals`, deleting the narrow generator. There is no reason
  the LLM-empty fallback should be poorer than the LLM-disabled one.

This single change moves the default from "7-row emotion table" to
"interest-weighted concepts + open questions + recent research."

**Fix B — widen the candidate sources (moderate).** `_varied_symbolic_goal`
already pulls research/concepts/questions. Add generators that make origination
read less like a lookup:

- *Causal-frontier goals.* Use `causal_graph.get_causes` /
  `get_effects` to find an outcome Orrin values (an aspiration's `driven_by`)
  whose causes are weakly known, and propose "find out what brings about X."
  This makes a goal emerge from a gap in his **learned** causal model rather
  than from an affect bucket.
- *Tension/contradiction goals.* `inference.py` and `contradiction` checks can
  surface a belief pair that conflicts; "resolve whether X or Y" is a goal with
  genuine internal provenance.
- *Autobiographical continuity.* Read `autobiography.json` / threads for an
  unfinished commitment and propose its next step. This is the
  "wanting something specific you can picture" the critique correctly says is
  missing — sourced from his own history rather than a template.

**Fix C — ground the aspiration link (research → moderate).** Replace the static
`_DRIVE_TO_ASPIRATION` lookup with a *learned* association: weight which
aspiration a completed goal advanced by which one its **outcome** actually moved
(reward/causal credit already tracked in `domain_action_credits.json`,
`action_reward_ema.json`). Keep the table as the cold-start prior, but let the
mapping drift with evidence so "this goal serves that value" becomes a learned
link, not a dictionary constant. This is the structural answer to "a human
constructs that link from lived experience; his is a lookup."

---

## 2. Deliberative reasoning is real — and currently dark

### 2.1 The iteration is genuine — confirmed

`brain/think/inner_loop.py:381` (`run_inner_loop`) is not a thin wrapper. It
implements:

- bandit-chosen round count, energy/`resource_deficit`-modulated (`:414–448`);
- per-round **draft** (`:472`) → **meta-decision** (`:486`) →
  **3-way critique** (`_full_critique`, `:215`: reflect-on-internal-agents +
  contradiction detector + value-alignment) → **revise** (`:585`);
- **escalation** at round ≥4, confidence <0.65 (`:505`): deep model +
  Tree-of-Thought across 3 parallel angles with a judge (`_tot_branch`, `:264`);
- **3-voice debate** when still <0.45 after escalation (`:541`,
  `simulate.run_debate`);
- a meta-reflection that scores whether the rounds were worth it and feeds the
  depth bandit (`:602`, `:638`).

**Verdict: true.** This is real iterative reasoning, well beyond a single call.

### 2.2 It is entirely LLM-backed — confirmed

Every generative step calls `routed_response` (`utils/llm_router.py:219`):
draft `:472`, all three critiques `:171/:190/:210`, synthesis `:243`, revision
`:587`, ToT branches/judge `:298/:329`, deep revision `:525`, debate, and the
quality reflection `:370`. `routed_response` → `generate_response`. In tool-only
mode (default) `inner_loop/*` callers are not allowlisted, so each returns
`None` (`generate_response.py:344`). With `llm_enabled: false` the same is true
via `llm_available()` (`:347`).

The very first step guards on empty draft (`:473–474`):

```python
draft = (routed_response(draft_prompt, f"inner_loop/draft/r{round_num}") or "").strip()
if not draft:
    break
```

So with the LLM off, `run_inner_loop` produces an empty draft, breaks on round 1,
and returns effectively nothing. **The entire System-2 apparatus no-ops.**

**Verdict: true. System 2 is dark in the default/offline configuration.** What
executes is the symbolic System 1 — selection from tables, KG reads, causal
leads, rule engine.

### 2.3 How to fix the dark System 2

The honest framing (consistent with `LLM_COGNITIVE_AUDIT.md`): `inner_loop` has
an **LLM-shaped primary path with no symbolic equivalent**, so when the LLM is a
disabled tool, the loop has nothing to fall back to. The audit already maps each
step to a symbolic owner. Concretely:

**Fix D — give `run_inner_loop` a symbolic mode (difficult, the real work).**
When `routed_response` is unavailable, the loop should not return empty — it
should run the symbolic critics that already exist:

| inner_loop step | symbolic replacement (already in repo) |
|---|---|
| draft | `temporal_planner` / `symbolic_search` plan as the "draft" |
| `_critique_primary` | `rule_verifier`, `symbolic_reflection` |
| `_critique_contradiction` | `inference` + `causal_graph` + `knowledge_graph` |
| `_critique_value_alignment` | `symbolic_self_model` / `selfhood/values_check` |
| critique synthesis | rank by rule confidence (no LLM) |
| ToT branch judge | `pattern_scorer` / rule-confidence ranking |

This is the same "promote the symbolic path to primary" conversion the audit
prescribes elsewhere — `inner_loop` is just one of the call sites that never had
a symbolic path written. It is the highest-value one because it is the named
home of deliberation.

**Fix E — stop advertising deliberation that can't run (trivial, do first).**
Until Fix D lands, callers should know System 2 is unavailable rather than
silently getting empty content. Have `run_inner_loop` early-return a typed
`{"meta_decision": "defer", "reason": "deliberation requires llm tool"}` when no
generative path is callable, so the surrounding cognition routes to the symbolic
planner instead of treating an empty string as a failed thought.

---

## 3. The middle layer is real understanding — confirmed, and worth leaning on

This claim is correct and is the most important one for the fixes above.

- **Causal graph** — `brain/symbolic/causal_graph.py`. Grounded in Pearl's
  ladder (association/intervention/counterfactual) and Granger causality with a
  confound check; edges carry `causal_score`, `intervention_count`, `layer`.
  `get_causes` (`:220`) is a real means-ends query over learned structure.
- **Symbolic inference** — `brain/symbolic/inference.py`. Forward-chaining over
  the relation graph: description-logic `is_a` subsumption with an inheritance
  discount (0.80), transitive `leads_to`/`causes`/`depends_on` with per-hop
  decay (0.70), Gärdenfors similarity. This is structured reasoning over
  world-knowledge — not numbers, not language.
- **Knowledge graph** — `brain/cognition/knowledge_graph.py`, with a shared
  `normalize_entity_name` (`:363`) used by both ingestion and goal phrasing.
- **It already leads plans.** `pursue_goal._causal_first_step` (`:221`) reads
  `get_causes(goal_title, min_score=0.50)` and, when a strong learned cause
  exists, prepends "Act on what I've learned brings this about: …" to the plan
  (`:274–277`). This is genuine means-ends use of learned causes, exactly as the
  critique credits.

**Verdict: true.** This is the defensible understanding, and it runs with no
LLM.

### 3.1 Implication for the fixes

The middle layer is the asset the other two problems should be solved *with*:

- It is the substrate for **Fix B** (causal-frontier and tension goals come
  straight out of `causal_graph` + `inference`).
- It is the substrate for **Fix D** (the symbolic critics for `inner_loop` are
  `inference`/`causal_graph`/`symbolic_self_model`).
- It is what makes **Fix C** possible — a learned `driven_by → aspiration` link
  is a causal-credit edge, which is exactly what this layer represents.

The strategic point: Orrin's most genuine cognition is the symbolic middle
layer, yet both goal origination (default path) and deliberation (System 2)
currently route *around* it — origination falls to a 7-row emotion table, and
deliberation falls to an LLM that the default config disables. The fixes all
point the same direction: **make the symbolic middle layer the primary path for
both, and treat the LLM as the optional enrichment tool it is already
configured to be.**

---

## Priority order

1. **Fix A** (trivial) — route the default symbolic path through
   `_varied_symbolic_goal`; kill the dead-in-default narrow seed table.
2. **Fix E** (trivial) — make `run_inner_loop` defer honestly when no generative
   path is callable.
3. **Fix B** (moderate) — causal-frontier / tension / autobiographical goal
   generators.
4. **Fix D** (difficult) — symbolic mode for `inner_loop` (the real System-2
   restoration).
5. **Fix C** (research) — learned `driven_by → aspiration` association.

Fixes A and E are same-day changes that immediately make the default behaviour
match — and exceed — what the critique assumed was already happening.
