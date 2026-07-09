# Extending Symbolic Operations

How to add new symbolic capability — predicates, entity types, causal edges, rules, or a whole new
reasoning operation — without breaking the invariants the rest of the system relies on.

## Where things live

- World-model entities/predicates and inheritance queries: `brain/symbolic/inference.py`.
- Causal edges and interventions: `brain/symbolic/causal_graph.py`.
- Rules (the full lifecycle — synthesis, verification, compression, forgetting):
  `brain/symbolic/rule_engine.py` and its sibling `rule_*.py` modules.
- Routing: a new operation must be reachable from `brain/symbolic/reasoning_router.py`, otherwise
  nothing will ever call it.

## Ground rules

1. **Stay symbolic-first.** A new operation must work with no LLM configured. If it can optionally
   consult the LLM, route that through `brain/symbolic/llm_gate.py` so the global tool-only gate
   and fail-closed contract apply.
2. **Validate before effect.** New rules go through `rule_verifier.py`; don't add a path that lets
   an unverified rule fire.
3. **Persist through the existing stores.** Models persist as JSON under `brain/data/` — resolve
   paths via `brain/paths.py` constants, never hand-built paths.
4. **Record productions.** If the operation produces something durable (a new principle, edge, or
   resolved experiment), record it via `brain/symbolic/symbolic_effects.py` so it lands on the
   effect ledger and earns production reward.
5. **Keep it bounded.** Anything that accumulates (rules, edges, concepts) needs a decay or
   compression path — `rule_forgetting.py` and `rule_compressor.py` are the patterns to follow.

## Testing

- Unit-test queries and inference behavior under `tests/brain/`.
- `make verify` must stay green — it enforces import layering and module size caps in addition to
  the suite, so a new module that reaches into the wrong layer fails fast.
- For behavioral verification, `brain/symbolic/benchmark.py` scores reasoning against
  `ground_truth.py`; extend the ground-truth set alongside a new operation.

## Code pointers

- `brain/symbolic/` — the whole subsystem, mapped in
  [Symbolic Reasoning Subsystem](Symbolic_Reasoning_Subsystem)
- `tests/brain/` — existing test patterns to copy
