"""
utils/llm_providers/gemini_provider.py — Google Gemini via the google-genai SDK (H2).

Same contract as the others. Gemini expresses function-calling differently again, so
this adapter translates Orrin's OpenAI-shaped tools OUT to Gemini function declarations
and parses function-call parts BACK into the common `tool_calls` shape. The `google-genai`
SDK is imported lazily so the dep is optional until Gemini is selected.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .base import LLMProvider, split_system

DEFAULT_MODEL = "gemini-2.5-flash"


def tools_openai_to_gemini(tools: Optional[List[Dict[str, Any]]]):
    """OpenAI function tools → a single Gemini Tool with function_declarations."""
    if not tools:
        return None
    decls = []
    for t in tools:
        fn = t.get("function", t) if isinstance(t, dict) else {}
        decls.append(
            {
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "parameters": fn.get("parameters") or {"type": "object", "properties": {}},
            }
        )
    return [{"function_declarations": decls}]


class GeminiProvider(LLMProvider):
    id = "google"
    egress_name = "google"

    def __init__(self, *, model: Optional[str] = None, api_key: Optional[str] = None, **_):
        super().__init__(model=model or DEFAULT_MODEL, api_key=api_key)
        self._client = None

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _get_client(self):
        if self._client is None:
            from google import genai  # lazy: optional dep
            self._client = genai.Client(api_key=self.api_key)
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
        # Gemini roles: "user" / "model" (not "assistant").
        contents = [
            {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
            for m in turns
        ] or [{"role": "user", "parts": [{"text": ""}]}]

        config: Dict[str, Any] = {}
        if system:
            config["system_instruction"] = system
        if max_tokens:
            config["max_output_tokens"] = max_tokens
        if expect_json:
            config["response_mime_type"] = "application/json"
        g_tools = tools_openai_to_gemini(tools)
        if g_tools:
            config["tools"] = g_tools

        resp = self._get_client().models.generate_content(
            model=model or self.model, contents=contents, config=config or None
        )

        content = (getattr(resp, "text", None) or "").strip()
        tool_calls: List[Dict[str, Any]] = []
        for cand in (getattr(resp, "candidates", None) or []):
            parts = getattr(getattr(cand, "content", None), "parts", None) or []
            for p in parts:
                fc = getattr(p, "function_call", None)
                if fc is not None:
                    args = getattr(fc, "args", {}) or {}
                    tool_calls.append(
                        {"id": getattr(fc, "id", "") or "", "name": getattr(fc, "name", ""), "arguments": json.dumps(dict(args))}
                    )
        usage = getattr(resp, "usage_metadata", None)
        u_in = int(getattr(usage, "prompt_token_count", 0) or 0) if usage else 0
        u_out = int(getattr(usage, "candidates_token_count", 0) or 0) if usage else 0
        return {"content": content, "tool_calls": tool_calls, "usage": {"input": u_in, "output": u_out}}
