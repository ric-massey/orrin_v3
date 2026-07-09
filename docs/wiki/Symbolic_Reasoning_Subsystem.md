# Symbolic Reasoning Subsystem

`brain/symbolic/` is the LLM-free reasoning core: world/causal/knowledge models plus a full rule
lifecycle. Everything here runs in symbolic-only mode.

## Module map

Reasoning and models

- `inference.py` — description-logic-style inheritance and queries over the world model.
- `causal_graph.py` — Pearl-style causal edges, structural updates, and intervention reasoning. The
  causal graph is a self-model: frontier goals derived from it point inward (search Orrin's own
  code and state), not at generic web research.
- `prediction_engine.py` — predictive-processing layer; prediction errors feed control signals.
- `concept_formation.py` / `analogy_engine.py` — forms new concepts, draws analogies across domains.
- `reasoning_router.py` — routes a question to the engine that can answer it.

The rule lifecycle

- `rule_engine.py` — evaluates rules each cycle; firings are logged.
- `rule_synthesis.py` — proposes new rules from observed regularities.
- `rule_abstraction.py` / `rule_compressor.py` — generalizes and compresses the rule base.
- `rule_verifier.py` — validates rules before they take effect.
- `rule_forgetting.py` — decays rules that stop earning their keep.
- `meta_rules.py` — rules about rules (seeded from `brain/data/meta_rules.json`).
- `crystallization.py` — hardens repeatedly successful reasoning into reusable skills.

Autonomy and measurement

- `autonomous_experiment.py` — designs and runs experiments to test its own hypotheses.
- `intrinsic_motivation.py` / `progress_tracker.py` / `pattern_scorer.py` — learning-progress
  signals that make reasoning self-directed.
- `ground_truth.py` / `benchmark.py` — checks conclusions against known facts; scores reasoning.
- `self_improvement.py` — turns recurring reasoning failures into improvement goals.
- `llm_gate.py` — the one place symbolic code may consult the LLM, subject to the global tool-only
  gate (see [LLM Integration](LLM_Integration)).

## Production is visible

Symbolic productions — synthesized principles, crystallized skills, resolved experiments,
established causal edges — are recorded as `symbolic_artifact` effects on the effect ledger via
`brain/symbolic/symbolic_effects.py`, so symbolic work earns production reward the same way file
outputs do (see [Production and the Effect Ledger](Production_and_Effect_Ledger)).

## Persistence

World and causal models persist as JSON under `brain/data/` and survive restarts; rule firings are
logged to `rule_firings.jsonl` (capped).
