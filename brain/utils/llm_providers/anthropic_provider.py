"""
utils/llm_providers/anthropic_provider.py — Claude via the Messages API (H2).

Tool-calling is the real translation work, not the HTTP. Orrin's tool schema is
OpenAI-shaped (`{"type":"function","function":{"name","description","parameters"}}`);
this adapter translates it OUT to Anthropic `tools` (`{"name","description",
"input_schema"}`) and parses `tool_use` content blocks BACK into the common
`tool_calls` shape (`{"id","name","arguments"}`). Covered by adapter tests so a provider
swap can't silently break `ask_llm`.

Models (Part 11.1): claude-opus-4-8 (flagship), claude-sonnet-4-6 (balanced),
claude-haiku-4-5 (fast/cheap). The `anthropic` SDK is imported lazily so the dep is
optional until this provider is actually selected.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .base import LLMProvider, split_system

DEFAULT_MODEL = "claude-sonnet-4-6"


def tools_openai_to_anthropic(tools: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
    if not tools:
        return None
    out: List[Dict[str, Any]] = []
    for t in tools:
        fn = t.get("function", t) if isinstance(t, dict) else {}
        out.append(
            {
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
            }
        )
    return out


class AnthropicProvider(LLMProvider):
    id = "anthropic"
    egress_name = "anthropic"

    def __init__(self, *, model: Optional[str] = None, api_key: Optional[str] = None, **_):
        super().__init__(model=model or DEFAULT_MODEL, api_key=api_key)
        self._client = None

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _get_client(self):
        if self._client is None:
            import anthropic  # lazy: optional dep
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def generate(
        self,
        messages: List[Dict[str, str]],
        *,
        model: Optional[str] = None,
        max_tokens: int = 2048,
        expect_json: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None,
        timeout: float = 8.0,
    ) -> Dict[str, Any]:
        system, turns = split_system(messages)
        # JSON mode: Anthropic has no json_object flag — steer via the system prompt.
        if expect_json:
            system = (system + "\n\nRespond ONLY with a single valid JSON object.").strip()

        kwargs: Dict[str, Any] = {
            "model": model or self.model,
            "max_tokens": max_tokens or 2048,
            "messages": [{"role": m["role"], "content": m["content"]} for m in turns] or
                        [{"role": "user", "content": ""}],
        }
        if system:
            kwargs["system"] = system
        a_tools = tools_openai_to_anthropic(tools)
        if a_tools:
            kwargs["tools"] = a_tools

        resp = self._get_client().messages.create(timeout=timeout, **kwargs)

        content_parts: List[str] = []
        tool_calls: List[Dict[str, Any]] = []
        for block in (getattr(resp, "content", None) or []):
            btype = getattr(block, "type", None)
            if btype == "text":
                content_parts.append(getattr(block, "text", "") or "")
            elif btype == "tool_use":
                tool_calls.append(
                    {
                        "id": getattr(block, "id", ""),
                        "name": getattr(block, "name", ""),
                        "arguments": json.dumps(getattr(block, "input", {}) or {}),
                    }
                )
        usage = getattr(resp, "usage", None)
        u_in = int(getattr(usage, "input_tokens", 0) or 0) if usage else 0
        u_out = int(getattr(usage, "output_tokens", 0) or 0) if usage else 0
        return {
            "content": "".join(content_parts).strip(),
            "tool_calls": tool_calls,
            "usage": {"input": u_in, "output": u_out},
        }
