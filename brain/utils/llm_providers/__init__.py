"""
utils/llm_providers — pluggable LLM providers (Part 11).

The brain stays SYMBOLIC-FIRST: every provider is optional and "none" keeps today's
keyless behavior. `resolve()` builds the provider selected in Settings from three
sources — the selected id (prefs `llm_provider`), that provider's key (OS keychain via
`utils.secrets`), and the model (prefs `llm_model`, else the provider's default). The
result is cached; `reinit()` drops it so a Settings change takes effect via the same
graceful path as a key change.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from .base import LLMProvider
from .openai_provider import OpenAIProvider, OpenAICompatibleProvider
from .anthropic_provider import AnthropicProvider, DEFAULT_MODEL as _ANTHROPIC_DEFAULT
from .gemini_provider import GeminiProvider, DEFAULT_MODEL as _GEMINI_DEFAULT

# UI/metadata catalog (drives the Settings menu, §11.1). `secret` is the utils.secrets
# key name for that provider's API key (None ⇒ no key needed). `local` ⇒ zero egress.
CATALOG: List[Dict[str, Any]] = [
    {"id": "none", "label": "None — symbolic-only", "secret": None, "local": True,
     "models": [], "default_model": "", "needs_base_url": False},
    {"id": "local", "label": "Local / on-device", "secret": None, "local": True,
     "models": [], "default_model": "", "needs_base_url": True},
    {"id": "anthropic", "label": "Anthropic (Claude)", "secret": "anthropic", "local": False,
     "models": ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5"],
     "default_model": _ANTHROPIC_DEFAULT, "needs_base_url": False},
    {"id": "openai", "label": "OpenAI", "secret": "openai", "local": False,
     "models": ["gpt-4.1", "gpt-4o", "gpt-4o-mini"], "default_model": "gpt-4.1",
     "needs_base_url": False},
    {"id": "google", "label": "Google (Gemini)", "secret": "google", "local": False,
     "models": ["gemini-2.5-pro", "gemini-2.5-flash"], "default_model": _GEMINI_DEFAULT,
     "needs_base_url": False},
    {"id": "custom", "label": "Custom OpenAI-compatible", "secret": "custom", "local": False,
     "models": [], "default_model": "", "needs_base_url": True},
]

VALID_IDS = frozenset(c["id"] for c in CATALOG)
_DEFAULT_ID = "openai"  # back-compat: an unconfigured install behaves exactly as before


def catalog() -> List[Dict[str, Any]]:
    """The provider menu for the UI — never includes any secret value."""
    return [dict(c) for c in CATALOG]


def _meta(provider_id: str) -> Dict[str, Any]:
    for c in CATALOG:
        if c["id"] == provider_id:
            return c
    return {}


_lock = threading.Lock()
_cached: Optional[LLMProvider] = None
_cached_key: Optional[tuple] = None


def selected_id() -> str:
    try:
        from utils import prefs
        pid = str(prefs.get("llm_provider", _DEFAULT_ID) or _DEFAULT_ID)
    except Exception:
        pid = _DEFAULT_ID
    return pid if pid in VALID_IDS else _DEFAULT_ID


def _key_for(provider_id: str) -> Optional[str]:
    meta = _meta(provider_id)
    name = meta.get("secret")
    if not name:
        return None
    try:
        from utils import secrets
        return secrets.get_key(name)
    except Exception:
        return None


def _build(provider_id: str, *, default_model: Optional[str] = None) -> Optional[LLMProvider]:
    if provider_id == "none":
        return None
    meta = _meta(provider_id)
    try:
        from utils import prefs
        model = str(prefs.get("llm_model", "") or "") or meta.get("default_model") or default_model or ""
        base_url = str(prefs.get("llm_base_url", "") or "") or None
    except Exception:
        model, base_url = (meta.get("default_model") or default_model or ""), None
    key = _key_for(provider_id)

    if provider_id == "openai":
        # Preserve today's behavior: when no explicit model is chosen, fall back to the
        # model generate_response already resolved from model_config.
        return OpenAIProvider(model=model or default_model or "gpt-4.1", api_key=key)
    if provider_id == "anthropic":
        return AnthropicProvider(model=model or _ANTHROPIC_DEFAULT, api_key=key)
    if provider_id == "google":
        return GeminiProvider(model=model or _GEMINI_DEFAULT, api_key=key)
    if provider_id in ("local", "custom"):
        return OpenAICompatibleProvider(
            model=model or "local-model", api_key=key, base_url=base_url, local=(provider_id == "local")
        )
    return None


def resolve(*, default_model: Optional[str] = None) -> Optional[LLMProvider]:
    """The selected provider, cached. `default_model` is generate_response's
    model_config-resolved model — used only as the OpenAI fallback when the user hasn't
    chosen a model, so it does NOT fragment the cache (callers pass it inconsistently:
    None from llm_available(), the model name from generate_response()). Returns None for
    the "none" (symbolic-only) selection."""
    global _cached, _cached_key
    pid = selected_id()
    with _lock:
        if _cached_key == pid and (_cached is not None or pid == "none"):
            return _cached
        _cached = _build(pid, default_model=default_model)
        _cached_key = pid
        return _cached


def reinit() -> None:
    """Drop the cached provider so a newly-saved key/provider/model takes effect."""
    global _cached, _cached_key
    with _lock:
        _cached = None
        _cached_key = None
