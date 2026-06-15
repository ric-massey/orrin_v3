#!/usr/bin/env python3
"""
packaging/set_version.py — bake the release version into brain/version.py before a freeze.

CI calls this on a tagged build so the frozen app reports its real version to the
auto-update check (I7). Cross-platform (pure Python — runs identically on the macOS,
Windows, and Linux runners; no sed). Version source, in order:
  1. argv[1]   2. $ORRIN_VERSION   3. $GITHUB_REF_NAME (the tag, e.g. "v0.1.0")
A leading "v" is stripped. No-op (exit 0) if none is set, so local freezes keep the
checked-in default.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path


def main() -> int:
    raw = (sys.argv[1] if len(sys.argv) > 1 else "") or os.environ.get("ORRIN_VERSION") or os.environ.get("GITHUB_REF_NAME") or ""
    version = raw.strip().lstrip("vV")
    if not version:
        print("[set_version] no version provided — keeping the checked-in default")
        return 0
    vf = Path(__file__).resolve().parent.parent / "brain" / "version.py"
    text = vf.read_text(encoding="utf-8")
    new, n = re.subn(r'^__version__ = ".*"', f'__version__ = "{version}"', text, count=1, flags=re.M)
    if n != 1:
        print(f"[set_version] could not find the __version__ line in {vf}", file=sys.stderr)
        return 1
    vf.write_text(new, encoding="utf-8")
    print(f"[set_version] brain/version.py → {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
