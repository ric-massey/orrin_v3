"""Group H — pluggable LLM providers (Part 11). Adapter tests prove tool calls and
text round-trip on every provider WITHOUT network: each adapter's vendor client is
replaced by a fake that records the request and returns a canned response. Also covers
the resolver (selection from prefs + key from secrets) and back-compat defaults.

Runs under conftest's ORRIN_DATA_DIR + ORRIN_KEYRING=0 isolation.
"""
import json
import types

import pytest

from utils import llm_providers as providers
from utils.llm_providers.openai_provider import OpenAIProvider, OpenAICompatibleProvider
from utils.llm_providers.anthropic_provider import AnthropicProvider, tools_openai_to_anthropic
from utils.llm_providers.gemini_provider import GeminiProvider, tools_openai_to_gemini

_TOOLS = [{
    "type": "function",
    "function": {
        "name": "lookup",
        "description": "look something up",
        "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
    },
}]
_MSGS = [{"role": "system", "content": "be brief"}, {"role": "user", "content": "hi"}]


def _obj(**kw):
    return types.SimpleNamespace(**kw)


# ── OpenAI (Responses API, verbatim path) ────────────────────────────────────
def test_openai_provider_text_and_tool_roundtrip():
    p = OpenAIProvider(model="gpt-4.1", api_key="sk-test")
    captured = {}

    class _Resp:
        responses = None

    def _create(**kwargs):
        captured.update(kwargs)
        return _obj(
            output_text="hello there",
            output=[_obj(type="function_call", call_id="c1", name="lookup", arguments='{"q":"x"}')],
            usage=_obj(input_tokens=5, output_tokens=7),
        )

    p._client = _obj(responses=_obj(create=_create))
    out = p.generate(_MSGS, model="gpt-4.1", tools=_TOOLS, max_tokens=100, expect_json=True)

    # system → instructions, single user turn → plain string input (verbatim shaping).
    assert captured["instructions"] == "be brief"
    assert captured["input"] == "hi"
    assert captured["max_output_tokens"] == 100
    assert captured["text"] == {"format": {"type": "json_object"}}
    assert out["content"] == "hello there"
    assert out["tool_calls"] == [{"id": "c1", "name": "lookup", "arguments": '{"q":"x"}'}]
    assert out["usage"] == {"input": 5, "output": 7}


def test_openai_compatible_uses_chat_completions_with_base_url():
    p = OpenAICompatibleProvider(model="llama3", base_url="http://localhost:11434/v1", local=True)
    captured = {}

    def _create(**kwargs):
        captured.update(kwargs)
        msg = _obj(content="local reply", tool_calls=None)
        return _obj(choices=[_obj(message=msg)], usage=_obj(prompt_tokens=3, completion_tokens=4))

    p._client = _obj(chat=_obj(completions=_obj(create=_create)))
    out = p.generate(_MSGS, max_tokens=50)
    assert captured["model"] == "llama3"
    assert captured["messages"][0] == {"role": "system", "content": "be brief"}
    assert out["content"] == "local reply"
    assert out["usage"] == {"input": 3, "output": 4}
    assert p.local is True and p.egress_name == "local"


# ── Anthropic (Messages API + tool translation) ──────────────────────────────
def test_anthropic_tool_schema_translation():
    a = tools_openai_to_anthropic(_TOOLS)
    assert a == [{
        "name": "lookup",
        "description": "look something up",
        "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}},
    }]


def test_anthropic_provider_parses_text_and_tool_use():
    p = AnthropicProvider(model="claude-sonnet-4-6", api_key="ak-test")
    captured = {}

    def _create(**kwargs):
        captured.update(kwargs)
        return _obj(
            content=[
                _obj(type="text", text="thinking… "),
                _obj(type="tool_use", id="tu1", name="lookup", input={"q": "x"}),
            ],
            usage=_obj(input_tokens=9, output_tokens=2),
        )

    p._client = _obj(messages=_obj(create=_create))
    out = p.generate(_MSGS, tools=_TOOLS, expect_json=True)
    # System pulled out; JSON steer appended; tools translated.
    assert captured["system"].startswith("be brief")
    assert captured["messages"] == [{"role": "user", "content": "hi"}]
    assert captured["tools"][0]["name"] == "lookup"
    assert out["content"] == "thinking…"
    assert out["tool_calls"] == [{"id": "tu1", "name": "lookup", "arguments": json.dumps({"q": "x"})}]
    assert out["usage"] == {"input": 9, "output": 2}


# ── Gemini (function-call translation) ───────────────────────────────────────
def test_gemini_tool_translation_and_parse():
    g = tools_openai_to_gemini(_TOOLS)
    assert g[0]["function_declarations"][0]["name"] == "lookup"

    p = GeminiProvider(model="gemini-2.5-flash", api_key="gk-test")
    captured = {}

    def _gen(**kwargs):
        captured.update(kwargs)
        fc = _obj(id="g1", name="lookup", args={"q": "x"})
        part = _obj(function_call=fc)
        cand = _obj(content=_obj(parts=[part]))
        return _obj(text="gem reply", candidates=[cand], usage_metadata=_obj(prompt_token_count=6, candidates_token_count=8))

    p._client = _obj(models=_obj(generate_content=_gen))
    out = p.generate(_MSGS, tools=_TOOLS)
    assert captured["model"] == "gemini-2.5-flash"
    assert captured["config"]["system_instruction"] == "be brief"
    assert out["content"] == "gem reply"
    assert out["tool_calls"] == [{"id": "g1", "name": "lookup", "arguments": json.dumps({"q": "x"})}]
    assert out["usage"] == {"input": 6, "output": 8}


# ── Resolver ─────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _reset_provider_state():
    providers.reinit()
    yield
    providers.reinit()
    from utils import prefs
    prefs.set("llm_provider", "openai")
    prefs.set("llm_model", "")


def test_resolver_defaults_to_openai_for_backcompat():
    from utils import prefs, secrets
    prefs.set("llm_provider", "openai")
    secrets.set_key("openai", "sk-live")
    providers.reinit()
    p = providers.resolve(default_model="gpt-4.1")
    assert isinstance(p, OpenAIProvider)
    assert p.model == "gpt-4.1" and p.is_configured()


def test_resolver_none_is_symbolic_only():
    from utils import prefs
    prefs.set("llm_provider", "none")
    providers.reinit()
    assert providers.resolve() is None


def test_resolver_selects_anthropic_with_keychain_key():
    from utils import prefs, secrets
    prefs.set("llm_provider", "anthropic")
    prefs.set("llm_model", "claude-opus-4-8")
    secrets.set_key("anthropic", "ak-live")
    providers.reinit()
    p = providers.resolve()
    assert isinstance(p, AnthropicProvider)
    assert p.model == "claude-opus-4-8" and p.is_configured()
    secrets.set_key("anthropic", None)


def test_catalog_exposes_no_secret_values():
    cat = providers.catalog()
    ids = {c["id"] for c in cat}
    assert {"none", "local", "openai", "anthropic", "google", "custom"} <= ids
    assert all("value" not in c and "key" not in c for c in cat)
