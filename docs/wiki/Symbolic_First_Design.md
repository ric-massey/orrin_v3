# Symbolic-First Design

Principles
- Keep the LLM as a tool: all core cognition must function without LLM calls.
- Explicit, inspectable representations (world models, predicates, causal graphs).
- Fail-closed behavior: the agent should degrade gracefully when external services are unreachable.

What runs without an LLM
- Cognitive loop, memory consolidation, goal management, control-signal regulation, symbolic reasoning, host monitoring.

When to use an LLM
- Language generation for human-facing outputs
- High-level suggestion synthesis where semantic richness is needed
- Guided concept naming or explanation generation

Trade-offs
- Symbolic systems offer determinism and interpretability but limited generalization.
- LLMs provide generative flexibility at the cost of unpredictability and opacity.

Code pointers
- brain/utils/llm_providers, brain/cognition/tools/ask_llm.py
