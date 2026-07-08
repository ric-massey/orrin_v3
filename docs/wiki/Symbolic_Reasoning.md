# Symbolic Reasoning

Orrin reasons with explicit, inspectable representations — world models, causal graphs, and a full
rule lifecycle — entirely **without an LLM**. This is the core of the symbolic-first design: the
decision loop and world understanding are deterministic and auditable, not hidden inside a model's
weights.

## What it does

- **World model** (`inference.py`) — description-logic-style inheritance and queries over entities
  and predicates.
- **Causal reasoning** (`causal_graph.py`) — Pearl-style causal edges, interventions, and
  counterfactuals. The causal graph is a *self-model*, so frontier questions point inward (search
  Orrin's own code and state), not at generic web research.
- **Prediction** (`prediction_engine.py`) — predictive-processing; prediction errors feed control
  signals.
- **Concepts and analogy** (`concept_formation.py`, `analogy_engine.py`) — forms new concepts and
  maps analogies across domains.

## The rule lifecycle

Rules are born, generalized, verified, and forgotten — a small self-maintaining knowledge base:

```mermaid
flowchart LR
    OBS[Observed regularity] --> SYN[Synthesize rule]
    SYN --> VER[Verify]
    VER --> ENG[Rule engine fires]
    ENG --> ABS[Abstract / compress]
    ABS --> FOR[Forget if it stops paying]
    FOR -.-> ENG
```

Autonomy comes from `autonomous_experiment.py` (designs and runs experiments to test its own
hypotheses) and the learning-progress signals in `intrinsic_motivation.py` /  `progress_tracker.py`.
Productions — synthesized principles, crystallized skills, resolved experiments, causal edges — are
recorded on the [effect ledger](Production_and_Effect_Ledger) so symbolic work earns reward the same
way file output does.

For the full module map and how to extend it, see
[Symbolic Reasoning Subsystem](Symbolic_Reasoning_Subsystem) and
[Extending Symbolic Operations](Extending_Symbolic_Operations).

## Code pointers

- `brain/symbolic/inference.py`, `causal_graph.py`, `prediction_engine.py`
- `brain/symbolic/rule_engine.py` and the `rule_*.py` lifecycle modules
