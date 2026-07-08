# Symbolic-First Design

The founding constraint of the whole system: **the brain never silently depends on an LLM.** Core
cognition is explicit, deterministic, and inspectable; the LLM is an optional, gated tool that a
cycle may choose to call. Remove the API key and Orrin still runs — it just skips LLM-backed tool
calls.

## The three principles

1. **LLM as a tool, not the controller.** Decision-making, goals, memory, and regulation are
   symbolic. LLM calls go through one gated chokepoint (see [LLM Integration](LLM_Integration)).
2. **Explicit, inspectable representations.** World models, predicates, causal graphs, and rules —
   not opaque weights ([Symbolic Reasoning](Symbolic_Reasoning)).
3. **Fail-closed.** When an external service is unreachable or a key is missing, the system degrades
   gracefully rather than fabricating or crashing.

## What runs with no LLM

Essentially everything: the cognitive loop, workspace and ignition, control-signal regulation, goal
management, memory and consolidation, symbolic reasoning and the rule lifecycle, host coupling, the
effect ledger, and the UI. The native language organ even learns to *produce language* from scratch
without an external model (see [Native Language Model](Native_Language_Model)).

## Where an LLM helps, when configured

- Richer natural-language phrasing for person-facing output (composed through the
  [Expression Membrane](Expression_Membrane)).
- Semantic synthesis where symbolic methods are weak.
- Optional self-shaping fine-tuning on its own successful traces.

## The trade-off, stated honestly

Symbolic systems buy determinism and interpretability at the cost of generalization; LLMs buy
generative flexibility at the cost of predictability and transparency. Orrin's bet is that an agent
you can *inspect and reason about* is worth more, for research, than one whose behavior lives inside
a model you can't open — so the symbolic core is primary and the LLM is contained.

## Code pointers

- `brain/utils/generate_response.py` — the gated LLM chokepoint
- `brain/symbolic/` — the LLM-free reasoning core
