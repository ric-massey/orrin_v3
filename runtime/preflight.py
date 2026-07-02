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
    _check_data_writable()
    # Warn (don't block) if LLM key is absent — Orrin runs symbolically without it
    if not os.getenv("OPENAI_API_KEY"):
        print("[boot] WARNING: OPENAI_API_KEY not set — LLM tool calls will be skipped; symbolic-only mode")
    print("[boot] config check OK")


def _check_data_writable() -> None:
    """AR9/O1: verify the data dir accepts writes and FAIL LOUDLY if not.

    A macOS `uchg` immutable flag on brain/data silently turned every exemplar/
    artifact write into a failed goal for a whole run — the failure surfaced as
    thousands of record_failure entries, not as a boot error. A probe write
    catches that class (permissions, immutable flags, read-only volume) in one
    place, before any subsystem starts."""
    from brain.paths import DATA_DIR
    probe = Path(DATA_DIR) / ".boot_write_probe"
    try:
        Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as e:
        print(
            f"[boot] FAILED: data dir is not writable: {DATA_DIR}\n"
            f"        {type(e).__name__}: {e}\n"
            f"        Check permissions and immutable flags "
            f"(macOS: `ls -lO`, clear with `chflags -R nouchg`).",
            file=sys.stderr,
        )
        sys.exit(3)
