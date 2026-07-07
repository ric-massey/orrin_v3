# LLM Integration

Provider interface
- A simple adapter pattern with implementations for OpenAI, Anthropic, and other providers.

Fail-closed contract
- LLM calls are optional and must not block core behaviors. Timeouts and fallbacks required.

Token budgeting
- Track token usage and apply per-agent budgets to avoid runaway costs.
