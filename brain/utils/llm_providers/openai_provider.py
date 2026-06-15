"""
utils/llm_providers/openai_provider.py — OpenAI (H1) and any OpenAI-compatible
endpoint (Local / Custom, H1).

`OpenAIProvider` wraps today's path VERBATIM — the Responses API
(`client.responses.create`), the same instructions/input split, the same
`max_output_tokens` and `json_object` format, the same usage extraction — so existing
OpenAI users see zero behavior change. `OpenAICompatibleProvider` points a vanilla
OpenAI client at a `base_url` (Ollama / LM Studio / llama.cpp / vLLM / OpenRouter /
Azure) and uses the broadly-supported Chat Completions API, since local servers rarely
implement the Responses API.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import LLMProvider


def _messages_to_responses_input(messages: List[Dict[str, str]]):
    """Mirror generate_response's original Responses-API shaping: system → instructions,
    a single user turn → plain string, multiple turns → role/content array."""
    sys_msg = next((m for m in messages if m.get("role") == "system"), None)
    instructions = sys_msg["content"] if sys_msg else ""
    user_msgs = [m for m in messages if m.get("role") != "system"]
    if len(user_msgs) == 1:
        inp: Any = user_msgs[0]["content"]
    elif user_msgs:
        inp = [{"role": m["role"], "content": m["content"]} for m in user_msgs]
    else:
        inp = ""
    return instructions, inp


class OpenAIProvider(LLMProvider):
    id = "openai"
    egress_name = "openai"

    def __init__(self, *, model: str, api_key: Optional[str] = None, **_):
        super().__init__(model=model, api_key=api_key)
        self._client = None

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            try:
                self._client = OpenAI(api_key=self.api_key)
            except TypeError:
                import os
                os.environ["OPENAI_API_KEY"] = self.api_key or ""
                self._client = OpenAI()
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
        model_name = model or self.model
        instructions, inp = _messages_to_responses_input(messages)
        kwargs: Dict[str, Any] = dict(model=model_name, input=inp)
        if instructions:
            kwargs["instructions"] = instructions
        if max_tokens:
            kwargs["max_output_tokens"] = max_tokens
        if expect_json:
            kwargs["text"] = {"format": {"type": "json_object"}}
        if tools:
            kwargs["tools"] = tools  # Responses API accepts OpenAI function tools directly

        resp = self._get_client().responses.create(**kwargs, timeout=timeout)
        content = (getattr(resp, "output_text", None) or "").strip()

        tool_calls: List[Dict[str, Any]] = []
        for item in (getattr(resp, "output", None) or []):
            if getattr(item, "type", None) == "function_call":
                tool_calls.append(
                    {
                        "id": getattr(item, "call_id", None) or getattr(item, "id", ""),
                        "name": getattr(item, "name", ""),
                        "arguments": getattr(item, "arguments", "") or "",
                    }
                )

        usage = getattr(resp, "usage", None)
        u_in = int(getattr(usage, "input_tokens", 0) or getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
        u_out = int(getattr(usage, "output_tokens", 0) or getattr(usage, "completion_tokens", 0) or 0) if usage else 0
        return {"content": content, "tool_calls": tool_calls, "usage": {"input": u_in, "output": u_out}}


class OpenAICompatibleProvider(LLMProvider):
    """Local or custom OpenAI-compatible server. Uses Chat Completions (the API local
    runtimes actually implement). For Local, egress is reported as on-device."""

    id = "openai_compatible"
    egress_name = "local"

    def __init__(self, *, model: str, api_key: Optional[str] = None, base_url: Optional[str] = None, local: bool = True, **_):
        super().__init__(model=model, api_key=api_key, base_url=base_url)
        self.local = local
        self.egress_name = "local" if local else "custom"
        self._client = None

    def is_configured(self) -> bool:
        return bool(self.base_url)

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            # Local servers usually need no real key; OpenAI() requires a non-empty one.
            self._client = OpenAI(api_key=self.api_key or "not-needed", base_url=self.base_url)
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
        model_name = model or self.model
        kwargs: Dict[str, Any] = dict(
            model=model_name,
            messages=[{"role": m["role"], "content": m["content"]} for m in messages],
        )
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        if expect_json:
            kwargs["response_format"] = {"type": "json_object"}
        if tools:
            kwargs["tools"] = tools

        resp = self._get_client().chat.completions.create(**kwargs, timeout=timeout)
        choice = resp.choices[0]
        content = (getattr(choice.message, "content", None) or "").strip()
        tool_calls: List[Dict[str, Any]] = []
        for tc in (getattr(choice.message, "tool_calls", None) or []):
            fn = getattr(tc, "function", None)
            tool_calls.append(
                {
                    "id": getattr(tc, "id", ""),
                    "name": getattr(fn, "name", "") if fn else "",
                    "arguments": getattr(fn, "arguments", "") if fn else "",
                }
            )
        usage = getattr(resp, "usage", None)
        u_in = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
        u_out = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
        return {"content": content, "tool_calls": tool_calls, "usage": {"input": u_in, "output": u_out}}
