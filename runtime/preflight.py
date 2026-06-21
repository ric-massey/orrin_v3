"""Boot-time preflight checks (Phase 4B, from main.py).

Fast, no-LLM checks run before subsystems start: load env + keychain secrets, and
verify the brain/ tree exists. Exits non-zero on a fatal misconfiguration so the
failure is loud, not a confusing downstream crash.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def boot_config_check() -> None:
    """Verify critical paths and config files exist before subsystems start."""
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(override=True)
    # Hydrate API keys the user saved in the OS keychain (Phase 4). A dev `.env`,
    # loaded just above, keeps precedence; this only fills what's absent — so a
    # packaged app with no `.env` still picks up keys pasted in Settings last session.
    try:
        from brain.utils.secrets import load_into_env as _load_secrets_env
        _load_secrets_env()
    except Exception as _e:
        print(f"[boot] keychain load skipped ({_e})")
    brain_dir = _REPO_ROOT / "brain"
    if not brain_dir.exists():
        print(f"[boot] FAILED: brain/ directory not found at {brain_dir}", file=sys.stderr)
        sys.exit(2)
    # Warn (don't block) if LLM key is absent — Orrin runs symbolically without it
    if not os.getenv("OPENAI_API_KEY"):
        print("[boot] WARNING: OPENAI_API_KEY not set — LLM tool calls will be skipped; symbolic-only mode")
    print("[boot] config check OK")
