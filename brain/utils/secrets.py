"""
utils/secrets.py — Orrin's API keys, stored in the OS keychain (Phase 4 / §4).

A shipped app must never carry secrets in its bundle or a plaintext `.env`. Keys the
user pastes in Settings live in the OS keychain — Keychain (macOS) / Credential
Manager (Windows) / libsecret (Linux) — via `keyring`. This module is the one place
that reads/writes them; the backend's `POST /api/settings` and main.py's boot both go
through here.

Resolution order for a key's value:
  1. process env (a dev `.env` / explicit override always wins),
  2. the OS keychain,
  3. an in-process memory fallback — used only when no keychain backend is available
     (headless CI, `ORRIN_KEYRING=0`). Never a plaintext file: "never written to disk
     in the clear" is the contract, so when there's no secure store we keep secrets in
     RAM for the session rather than degrade to a file.

Set `ORRIN_KEYRING=0` to force the memory backend (the test suite does this so it
never touches the developer's real Keychain).
"""
from __future__ import annotations

import os
from typing import Dict, Optional

# The keychain service name and the canonical env-var each secret maps to. The short
# UI name ("openai"/"serper") is what callers pass; the env var is what the rest of
# the brain reads (generate_response → OPENAI_API_KEY, the web tools → SERPER_API_KEY).
SERVICE = "Orrin"
ENV_VARS: Dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "serper": "SERPER_API_KEY",
    # Pluggable LLM providers (Part 11) — each provider's key lives in the keychain
    # under its own env var; the resolver in utils.llm_providers reads them by name.
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
    "custom": "ORRIN_LLM_CUSTOM_KEY",
}

# Session-only fallback when no secure keychain backend exists. Never persisted.
_MEM: Dict[str, str] = {}


def _keyring_disabled() -> bool:
    return os.getenv("ORRIN_KEYRING", "1").strip().lower() in ("0", "false", "no")


def _keyring():
    """Return the keyring module if a backend is usable, else None (→ memory)."""
    if _keyring_disabled():
        return None
    try:
        import keyring  # lazy: optional dep, and import is non-trivial
        return keyring
    except Exception:
        return None


def _env_for(name: str) -> str:
    try:
        return ENV_VARS[name]
    except KeyError:
        raise ValueError(f"unknown secret {name!r}; expected one of {sorted(ENV_VARS)}")


def set_key(name: str, value: Optional[str]) -> None:
    """Store (or, with an empty/None value, clear) a secret. Updates the process env
    immediately so the change takes effect this session, and persists to the keychain
    (or the memory fallback) so it survives a restart."""
    env = _env_for(name)
    value = (value or "").strip()
    kr = _keyring()
    if value:
        os.environ[env] = value
        if kr is not None:
            try:
                kr.set_password(SERVICE, env, value)
                _MEM.pop(env, None)
                return
            except Exception:
                pass
        _MEM[env] = value
    else:
        os.environ.pop(env, None)
        _MEM.pop(env, None)
        if kr is not None:
            try:
                kr.delete_password(SERVICE, env)
            except Exception:
                pass


def get_key(name: str) -> Optional[str]:
    """Resolve a secret's value (env → keychain → memory), or None if unset."""
    env = _env_for(name)
    from_env = os.environ.get(env)
    if from_env:
        return from_env
    kr = _keyring()
    if kr is not None:
        try:
            v = kr.get_password(SERVICE, env)
            if v:
                return v
        except Exception:
            pass
    return _MEM.get(env)


def configured() -> Dict[str, bool]:
    """Which secrets are set, as booleans only — the value is never exposed."""
    return {name: bool(get_key(name)) for name in ENV_VARS}


def load_into_env() -> None:
    """At boot: hydrate the process env from the keychain for any secret not already
    set (a dev `.env`, loaded first, keeps precedence). Lets a packaged app with no
    `.env` pick up keys the user saved in a previous session."""
    for name, env in ENV_VARS.items():
        if os.environ.get(env):
            continue
        v = get_key(name)
        if v:
            os.environ[env] = v
