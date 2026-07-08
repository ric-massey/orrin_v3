# LLM Integration

Orrin's flagship design rule: **the LLM is the smallest part of the agent, not the whole of it.**
The decision loop, goals, memory, control signals, and action selection are fully symbolic. The LLM
is one explicit tool among many, and the brain never silently depends on it — with no provider key
configured, Orrin runs fully and simply skips LLM-backed tool calls.

## Why the LLM isn't running the show

The interpretability argument is real, but the deciding one is that **a pretrained external LLM is
stagnant while everything else in Orrin grows.** Goals, memory, causal models, rules, and control
set points all change with what the runtime lives through; the frozen weights behind an API call do
not. Putting that model in charge would make the only decision-maker the only component that can't
learn from its decisions. So the LLM stays a gated tool, and the language ability that would grow is
grown natively instead — a from-scratch transformer that trains on Orrin's own experience and
improves with it (see [Native Language Model](Native_Language_Model.md)). See
[Symbolic-First Design](Symbolic_First_Design.md) for the full argument.

## The tool-only gate

- `ORRIN_LLM_TOOL_ONLY=1` is the **default**. Free-form generation is off; the LLM is only reachable
  as an explicit tool call (`brain/cognition/tools/ask_llm.py`).
- `brain/utils/generate_response.py` is the single chokepoint for every LLM call. In tool-only mode
  it rejects any caller not on the `_LLM_TOOL_CALLERS` allowlist, so a new code path cannot quietly
  start using the LLM.
- The gate **fails closed**: disabled, keyless, or erroring calls return an error result, never
  fabricated content. `llm_ok(result, caller)` is the required check — error messages are never
  returned as content.
- A circuit breaker tracks per-caller failures (`llm_failure_counts.json`) and opens after repeated
  errors, so a broken provider degrades to symbolic-only instead of stalling the loop.
- Goals and cognitive functions carry an `llm_callable_by` marking, so symbolic goal generators and
  the symbolic inner loop keep working when the LLM is unavailable.

## Pluggable providers

`brain/utils/llm_providers/` defines a provider interface (`base.py`) with adapters for:

- OpenAI (`openai_provider.py`, key: `OPENAI_API_KEY`)
- Anthropic (`anthropic_provider.py`, key: `ANTHROPIC_API_KEY`)
- Gemini (`gemini_provider.py`, key: `GOOGLE_API_KEY`)
- Any OpenAI-compatible or local endpoint

The active provider is selected in the UI Settings page; `generate_response.py` resolves it per
call. The symbolic-first, fail-closed contract is identical regardless of provider. Keys pasted in
Settings are stored in the OS keychain (`brain/utils/secrets.py`), never in the app bundle.

## Cost control

- `ORRIN_LLM_DAILY_TOKEN_BUDGET` — hard daily token cap; unset means no cap.
- Token usage is tracked per call and surfaced in the UI's Cognition room ("Thinking cost").
- The cost-prediction layer (`brain/cognition/cost_prediction.py`) makes LLM-backed functions
  compete on expected value against cheap symbolic functions, so quiet cycles drift toward cheap
  work.

## Self-shaping fine-tuning (optional, OpenAI-only)

`brain/cognition/finetuning/finetune_pipeline.py` filters conversation traces with outcome ≥ 0.65,
submits a fine-tune job, and on completion repoints `model_config.json` so generation drifts toward
what has worked for this runtime. Symbolic-only mode never touches it.

## Code pointers

- `brain/utils/generate_response.py` — chokepoint, tool-only gate, caller allowlist
- `brain/utils/llm_gate.py` — availability checks used by planners before proposing LLM steps
- `brain/utils/llm_providers/` — provider adapters
- `brain/cognition/tools/ask_llm.py` — the tool interface the agent actually calls
- `brain/utils/secrets.py` — OS-keychain key storage
