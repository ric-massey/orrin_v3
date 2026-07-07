# FAQ

This FAQ collects short answers to common questions.

Q: Why isn't the LLM the center of Orrin?
A: Orrin is designed to be symbolic-first: core control, memory, and reasoning are implemented with deterministic, inspectable mechanisms. LLMs are treated as tools to augment reasoning where needed, not the single source of truth.

Q: How does Orrin work without prompts?
A: Orrin runs a continuous cognitive loop that perceives, retrieves memory, proposes actions, and selects via bandits and control signals rather than ad-hoc prompts.

Q: Can Orrin run offline?
A: Yes for core functionality. LLM-dependent features require internet access or local model providers. Orrin provides fail-closed behavior when LLMs are unavailable.

Q: What happens when Orrin gets confused?
A: Confusion lowers reward signals and raises activation, triggering deliberation or safe fallback behaviors; the system logs the condition for later consolidation and debugging.

Q: How long does a cycle take?
A: Defaults are configurable; typical loop cadence is several seconds per cycle with background consolidation happening on longer windows.

Q: Can I modify Orrin's goals?
A: Yes. Use the goals daemon API to create, pause, or complete goals. The Executive will coordinate short-term scheduling.

(Extend with more Qs from the running project.)
