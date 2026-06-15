"""
H2 — verify the Anthropic and Gemini adapters against the REAL vendor SDKs.

test_llm_providers.py covers the adapters with SimpleNamespace fakes (no SDK needed).
That proves our translation logic, but not that it matches the actual SDK contracts —
a vendor SDK could rename a create() param or restructure its response model and the
fake-based tests would stay green. These tests close that gap WITHOUT network:

  1. the kwargs the adapter passes bind cleanly to the real client method signature
     (catches param drift like a renamed/removed `system` / `config`), and
  2. the adapter's response parsing runs over REAL SDK response models (Message /
     GenerateContentResponse with their real block/part/usage types), not fakes.

Skips cleanly if the optional SDK isn't installed, so the suite still runs without them.
"""
import inspect

import pytest

from utils.llm_providers.anthropic_provider import AnthropicProvider
from utils.llm_providers.gemini_provider import GeminiProvider

_TOOLS = [{
    "type": "function",
    "function": {
        "name": "lookup",
        "description": "look something up",
        "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
    },
}]
_MSGS = [{"role": "system", "content": "be brief"}, {"role": "user", "content": "hi"}]


# ── Anthropic ────────────────────────────────────────────────────────────────
def test_anthropic_adapter_matches_real_sdk():
    anthropic = pytest.importorskip("anthropic")
    from anthropic.resources.messages import Messages
    from anthropic.types import Message, TextBlock, ToolUseBlock, Usage

    captured = {}

    class _FakeMessages:
        def create(self, **kwargs):
            # 1) The adapter's kwargs must be valid params of the real create().
            inspect.signature(Messages.create).bind_partial(self, **kwargs)
            captured.update(kwargs)
            # 2) Return a REAL SDK Message for the adapter to parse.
            return Message(
                id="msg_1", model=kwargs["model"], role="assistant", type="message",
                stop_reason="end_turn", stop_sequence=None,
                usage=Usage(input_tokens=5, output_tokens=7),
                content=[
                    TextBlock(type="text", text="hello"),
                    ToolUseBlock(type="tool_use", id="tu_1", name="lookup", input={"q": "z"}),
                ],
            )

    class _FakeClient:
        messages = _FakeMessages()

    p = AnthropicProvider(model="claude-sonnet-4-6", api_key="sk-test")
    p._client = _FakeClient()
    out = p.generate(_MSGS, tools=_TOOLS, expect_json=False)

    # Request translation landed in the shapes the real SDK expects.
    assert captured["system"].startswith("be brief")
    assert captured["messages"] == [{"role": "user", "content": "hi"}]
    assert captured["tools"][0]["input_schema"]["properties"]["q"]["type"] == "string"
    assert "name" in captured["tools"][0] and "description" in captured["tools"][0]
    # Response parsed off the real Message model.
    assert out["content"] == "hello"
    assert out["tool_calls"] == [{"id": "tu_1", "name": "lookup", "arguments": '{"q": "z"}'}]
    assert out["usage"] == {"input": 5, "output": 7}


def test_anthropic_json_mode_steers_via_system():
    pytest.importorskip("anthropic")
    from anthropic.types import Message, TextBlock, Usage

    captured = {}

    class _FakeClient:
        class messages:  # noqa: N801
            @staticmethod
            def create(**kwargs):
                captured.update(kwargs)
                return Message(
                    id="m", model=kwargs["model"], role="assistant", type="message",
                    stop_reason="end_turn", stop_sequence=None,
                    usage=Usage(input_tokens=1, output_tokens=1),
                    content=[TextBlock(type="text", text="{}")],
                )

    p = AnthropicProvider(model="claude-sonnet-4-6", api_key="sk-test")
    p._client = _FakeClient()
    p.generate(_MSGS, expect_json=True)
    # Anthropic has no json flag — the adapter must steer JSON via the system prompt.
    assert "JSON" in captured["system"]


# ── Gemini ───────────────────────────────────────────────────────────────────
def test_gemini_adapter_matches_real_sdk():
    genai = pytest.importorskip("google.genai")
    from google.genai import types as gt
    from google.genai.models import Models

    captured = {}

    class _FakeModels:
        def generate_content(self, **kwargs):
            # 1) Valid params of the real generate_content().
            inspect.signature(Models.generate_content).bind_partial(self, **kwargs)
            captured.update(kwargs)
            # The config dict must build a real GenerateContentConfig (catches a
            # renamed field like system_instruction / max_output_tokens / tools).
            cfg = kwargs.get("config")
            if cfg is not None:
                gt.GenerateContentConfig(**cfg)
            # 2) Return a REAL SDK response for the adapter to parse.
            return gt.GenerateContentResponse(
                candidates=[gt.Candidate(content=gt.Content(role="model", parts=[
                    gt.Part(text="hi there"),
                    gt.Part(function_call=gt.FunctionCall(id="fc1", name="lookup", args={"q": "z"})),
                ]))],
                usage_metadata=gt.GenerateContentResponseUsageMetadata(
                    prompt_token_count=11, candidates_token_count=13),
            )

    class _FakeClient:
        models = _FakeModels()

    p = GeminiProvider(model="gemini-2.5-flash", api_key="k-test")
    p._client = _FakeClient()
    out = p.generate(_MSGS, tools=_TOOLS, expect_json=True)

    # Request translation in the shapes the real SDK expects.
    cfg = captured["config"]
    assert cfg["system_instruction"].startswith("be brief")
    assert cfg["response_mime_type"] == "application/json"
    assert cfg["tools"][0]["function_declarations"][0]["name"] == "lookup"
    assert captured["contents"][0]["role"] == "user"
    # Response parsed off the real response model.
    assert out["content"] == "hi there"
    assert out["tool_calls"] == [{"id": "fc1", "name": "lookup", "arguments": '{"q": "z"}'}]
    assert out["usage"] == {"input": 11, "output": 13}


def test_gemini_maps_assistant_role_to_model():
    pytest.importorskip("google.genai")
    from google.genai import types as gt

    captured = {}

    class _FakeClient:
        class models:  # noqa: N801
            @staticmethod
            def generate_content(**kwargs):
                captured.update(kwargs)
                return gt.GenerateContentResponse(
                    candidates=[gt.Candidate(content=gt.Content(role="model", parts=[gt.Part(text="ok")]))],
                    usage_metadata=gt.GenerateContentResponseUsageMetadata(
                        prompt_token_count=1, candidates_token_count=1),
                )

    p = GeminiProvider(model="gemini-2.5-flash", api_key="k-test")
    p._client = _FakeClient()
    p.generate([{"role": "assistant", "content": "prior"}, {"role": "user", "content": "now"}])
    roles = [c["role"] for c in captured["contents"]]
    assert roles == ["model", "user"]  # Gemini uses "model", not "assistant"
