"""
utils/llm_providers/base.py — the LLMProvider interface (Part 11 / H1).

Orrin's vendor call is concentrated in ONE place (the cached client inside
`generate_response()`), so swapping providers is a contained refactor, not a sprawl.
This defines the small contract every provider implements; `generate_response()` keeps
the circuit breaker, response cache, symbolic gate, and tool-only gate AROUND this
boundary, and `llm_router.py` keeps the daily-token budget ABOVE it — all
provider-agnostic.

The contract is one method:

    generate(messages, *, model=None, max_tokens, expect_json, tools=None, timeout)
        -> {"content": str, "tool_calls": list, "usage": {"input": int, "output": int}}

`messages` is the OpenAI-style [{role, content}] list `generate_response` already builds
(one system message + user/assistant turns). `tools`, when present, are OpenAI-style
function tool dicts; each adapter translates them to its vendor's format on the way out
and parses tool calls back into the common `tool_calls` shape on the way in. On any API
failure the provider RAISES (so generate_response's existing breaker/auth handling sees
the exception) rather than returning an error dict.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


class LLMProvider:
    """Base class — concrete providers override `generate` (and usually `is_configured`
    and `test_connection`)."""

    id: str = "base"
    # The label the egress ledger (§9.4) tags outbound calls with. "Nothing leaves your
    # machine" providers (none/local) report a name the Trust screen reads as on-device.
    egress_name: str = "llm"
    local: bool = False  # True ⇒ no cloud egress (zero data leaves the device)

    def __init__(self, *, model: str, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url

    def is_configured(self) -> bool:
        """True if this provider can make a call right now (e.g. its key is set)."""
        return True

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
        raise NotImplementedError

    def test_connection(self) -> Tuple[bool, str]:
        """A cheap round-trip to confirm the key/endpoint/model work. Returns
        (ok, human message)."""
        try:
            out = self.generate(
                [{"role": "user", "content": "Reply with the single word: ok"}],
                max_tokens=16,
                timeout=10.0,
            )
            txt = (out.get("content") or "").strip()
            return (bool(txt), f"Connected — {self.model} replied." if txt else "No reply from the model.")
        except Exception as e:  # noqa: BLE001 — intentional: surface any failure verbatim to the UI
            return (False, str(e)[:200])


# ── Message-shape helpers shared by adapters ─────────────────────────────────
def split_system(messages: List[Dict[str, str]]) -> Tuple[str, List[Dict[str, str]]]:
    """Pull the (single) system message out; return (system_text, remaining turns).
    Providers like Anthropic/Gemini take the system prompt as a separate field."""
    system = ""
    rest: List[Dict[str, str]] = []
    for m in messages:
        if m.get("role") == "system" and not system:
            system = str(m.get("content") or "")
        else:
            rest.append({"role": str(m.get("role", "user")), "content": str(m.get("content") or "")})
    return system, rest
