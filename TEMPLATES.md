# Templates in the Orrin v3 codebase

A catalog of every template used in the codebase and where to find it.
"Template" is interpreted broadly: reusable string-pattern collections with
`{placeholders}`, structured dict templates, external prompt stores, inline
LLM prompt scaffolds, path-format templates, and the frontend HTML template.

Generated 2026-06-13.

---

## 1. Text / phrase template collections

These are named constants (lists or dicts of strings) with `{...}` placeholders
that are filled at runtime to generate inner-monologue, speech, or ambient text.
Usually selected via `random.choice(...)` and formatted with `.format(...)`.

| Constant | File | Line | Purpose |
|---|---|---|---|
| `_ZEIGARNIK_TEMPLATES` | `brain/cognition/ambient_thought.py` | 116 | Unfinished-task intrusions (`{title}`) |
| `_MEMORY_ECHO_TEMPLATES` | `brain/cognition/ambient_thought.py` | 123 | Resurfacing-memory thoughts (`{snippet}`) |
| `_TENSION_TEMPLATES` | `brain/cognition/ambient_thought.py` | 129 | Unresolved-tension thoughts (`{tension}`) |
| `_EMOTIONAL_ECHOES` | `brain/cognition/ambient_thought.py` | 56 | Free-floating affect lines keyed by emotion |
| `_BROODING_TEMPLATES` | `brain/cognition/rumination.py` | 66 | Brooding rumination (`{seed}`) |
| `_REFLECTIVE_TEMPLATES` | `brain/cognition/rumination.py` | 74 | Reflective rumination (`{seed}`) |
| `_AFFECTIVE_BROODING` | `brain/cognition/rumination.py` | 88 | Object-less distress lines keyed by dominant emotion |
| `_ARC_TEMPLATES` | `brain/cognition/temporal_state.py` | 473 | Time-of-day narrative arc lines |
| `_THIN_TEMPLATES` | `brain/cognition/temporal_state.py` | 497 | "Thin time" subjective-time phrasing |
| `_DENSE_TEMPLATES` | `brain/cognition/temporal_state.py` | 516 | "Dense time" subjective-time phrasing |
| `_PARADOX_TEMPLATES` | `brain/cognition/temporal_state.py` | 536 | Temporal-paradox phrasing |
| `_WAITING_TEMPLATES` | `brain/cognition/temporal_state.py` | 553 | Waiting-state phrasing |
| `_TEMPLATES` | `brain/behavior/speech_gate.py` | 120 | Spoken-output lines keyed by `(intent, affect)` |
| `_TEMPLATES` | `brain/cognition/attention.py` | 139 | Attention-capture phrasing keyed by emotion (tuple pair) |
| `_DEFAULT_PHRASES` | `brain/cognition/seek_novelty.py` | 27 | Novelty-seeking phrase pools (e.g. `memory_revisit_phrases`, `{content}`) |
| `_ADVANCE_PHRASES` | `brain/cognition/threads.py` | 22 | Thread-advancement phrasing |

## 2. Structured dict templates (data scaffolds, not prose)

Dictionary templates copied/filled to build goals or world-models.

| Constant | File | Line | Purpose |
|---|---|---|---|
| `_EMOTION_GOAL_TEMPLATES` | `brain/cognition/intrinsic_goals.py` | 249 | Goal blueprints keyed by dominant emotion/drive |
| `_DEFAULT_EMOTION_GOAL_TEMPLATE` | `brain/cognition/intrinsic_goals.py` | 323 | Fallback goal blueprint |
| `_PATTERN_MODELS` | `brain/cognition/knowledge_formation.py` | 61 | Pattern→model templates (conditions + model shape) |

## 3. External prompt stores (loaded from disk)

| Reference | Defined in | On-disk path | Notes |
|---|---|---|---|
| `REF_PROMPTS` (reflection prompt templates) | path: `brain/paths.py:80`; loaded: `brain/cognition/repair/repair.py:23` | `brain/data/prompts.json` | **File not present on disk** — loads as empty dict via `load_json(..., default_type=dict)`. Consumed in `repair.py` (`reflect_on_cognition_rhythm`) and `brain/cognition/reflection/self_reflection.py:204`. Reflection modules also read a per-call `instructions`/`prompts` field from context. |
| `LLM_PROMPT` | `brain/paths.py:42` | `brain/data/llm_prompt.txt` | Runtime scratch file holding the most recent LLM prompt text. |

## 4. Inline LLM prompt templates (built in code)

The bulk of prompting is done with f-string / parenthesized-concatenation
prompt scaffolds assigned to local variables (`prompt`, `decompose_prompt`,
`rate_prompt`, etc.) right before an LLM call. There are **~98 such assignments
across ~54 files**. These are templates in the sense that they interpolate
runtime state, but they are inline rather than centralized.

Notable named/multiline ones:

| Constant / variable | File | Line |
|---|---|---|
| `_PARSE_PROMPT` (message-parse, returns JSON) | `brain/cognition/comprehension.py` | 26 |
| `clarification_prompt`, `decompose_prompt`, `justification_prompt` | `brain/behavior/behavior_generation.py` | 115 / 138 / 148 |
| `consolidate_prompt`, `recombine_prompt`, `process_prompt`, `prompts{}` | `brain/cognition/dreaming/dream_cycle.py` | 168 / 177 / 187 / 221 |
| multiple `prompt` / `rate_prompt` | `brain/cognition/experimentation.py` | 126, 204, 239, 266, 470, 595 |
| multiple `prompt` | `brain/cognition/sandbox.py` | 60, 78, 94, 104, 113, 121, 136 |
| `prompt` (+ `_EXTERNAL_CONTENT_NOTE` prefix) | `brain/cognition/knowledge_graph.py` | 1176, 1188 |
| `prompt` | `brain/cognition/planning/pursue_goal.py` | 295, 921 |
| `prompt` (various) | `brain/cognition/planning/{goals,evolution,introspection,motivations,reflection}.py` | see grep below |
| `prompt` (reflection family) | `brain/cognition/reflection/*.py` | reflect_on_conversation/outcome/self_belief/internal_agents, rule_reflection |
| `prompt` | `brain/affect/{affect,affect_drift,discovery}.py` | 99/191, 65, 38 |

To regenerate the full list of inline prompt assignments:

```bash
grep -rnE '\bprompt[a-z_]*[[:space:]]*=[[:space:]]*[\(f"]' --include='*.py' brain/
```

## 5. Path / string-format templates

| Constant | File | Line | Purpose |
|---|---|---|---|
| `BANDIT_JSON_TEMPLATE` | `brain/paths.py` | 234 | `bandit_{ctx}.json` filename template |
| `CACHE_JSON_TEMPLATE` | `brain/paths.py` | 235 | `{k}.json` cache filename template |

## 6. Frontend template

| File | Purpose |
|---|---|
| `frontend/index.html` | Vite HTML entry/shell — mounts the React app into `#root` via `/src/main.tsx`. The only `.html` template in the repo. |

## 7. Test-only pattern lists (for completeness, not production templates)

| Constant | File | Line |
|---|---|---|
| `_LEAK_PATTERNS` | `tests/llm/test_no_error_leakage.py` | 32 |
| `templates` (LLM stub responses) | `brain/utils/llm_stub.py` | 173 |

---

### Quick rediscovery commands

```bash
# Named template-collection constants
grep -rnE '_?[A-Z][A-Z0-9_]*(TEMPLATE|TEMPLATES)[A-Z0-9_]*[[:space:]]*[:=]' --include='*.py'

# Phrase/echo/brooding pools
grep -rnE '_(ECHOES|BROODING|PHRASES|PATTERN_MODELS)' --include='*.py'

# External prompt stores
grep -rnE 'prompts\.json|REF_PROMPTS|LLM_PROMPT' --include='*.py'
```
