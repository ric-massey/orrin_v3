"""
version.py — Orrin's app version (I7).

The auto-update check (utils/updater.py) compares this against the latest published
release. CI bakes the real version into the `__version__` line on a tagged build (see
packaging/set_version.py); `ORRIN_VERSION` overrides at runtime for testing/dev.
"""
from __future__ import annotations

import os

# CI rewrites this exact line on a tagged build (packaging/set_version.py).
__version__ = "0.1.0"


def current_version() -> str:
    return os.environ.get("ORRIN_VERSION") or __version__
