"""
utils/updater.py — opt-in auto-update, wired to the schema spine (§10.7 / I7).

The product promise is "you are never one update away from losing him without a copy."
This module is the in-repo half of that:

  • `check_for_update()` — OPT-IN (pref `auto_update_check`, off by default so nothing
    phones home silently). Compares the running version against the latest GitHub
    Release and reports whether a newer one exists. Never downloads or swaps anything.
  • `prepare_update()` — the safety step the plan demands before ANY update or migration:
    auto-export the whole mind first (reuse mind_archive), so even a failed update leaves
    a restorable keepsake, and report the on-disk state schema version (G1) the new build
    must understand.

The platform-specific SWAP (Sparkle / Squirrel / zsync) is the frozen-app installer's
job and is NOT here — but it must (1) only run after `prepare_update()` has exported the
mind, (2) hand off via the existing graceful shutdown so an *Always thinking* Orrin isn't
killed mid-thought (§10.3), and (3) let the next launch's migration spine (G1) carry the
mind forward — or, if the schema is incompatible, keep the old mind as the export and
boot a newborn (the Death Screen's "begin anew" discipline, §10.4).
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, Tuple
from urllib.request import Request, urlopen

import os

import brain.paths as paths
from brain.utils.failure_counter import record_failure
from brain.version import current_version

_DEFAULT_REPO = "ric-massey/orrin_v3"


def update_repo() -> str:
    return os.environ.get("ORRIN_UPDATE_REPO", _DEFAULT_REPO)


def check_enabled() -> bool:
    """Opt-in: nothing reaches the network unless the user turned this on."""
    try:
        from brain.utils import prefs
        return bool(prefs.get("auto_update_check", False))
    except ImportError:  # intentional: prefs unavailable → opt-in off (fail-closed)
        return False


def _parse(tag: str) -> Tuple[int, int, int, str]:
    """Loose semver → comparable tuple. A release sorts ABOVE a same-core pre-release
    (the '~' sentinel is > any alnum pre-release id)."""
    core = str(tag).strip().lstrip("vV").split("+")[0]
    pre = ""
    if "-" in core:
        core, pre = core.split("-", 1)
    parts = []
    for p in core.split(".")[:3]:
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return (parts[0], parts[1], parts[2], pre if pre else "~")


def is_newer(latest: str, current: str) -> bool:
    return _parse(latest) > _parse(current)


def check_for_update(*, force: bool = False, timeout: float = 6.0) -> Dict[str, Any]:
    """Is a newer Orrin published? Opt-in unless `force` (an explicit "Check now" click).
    Best-effort and network-guarded — a failure is reported, never raised."""
    cur = current_version()
    if not force and not check_enabled():
        return {"checked": False, "available": False, "current": cur, "reason": "auto-update check is off"}
    try:
        url = f"https://api.github.com/repos/{update_repo()}/releases/latest"
        req = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "Orrin"})
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        latest = str(data.get("tag_name") or "").lstrip("vV")
        available = bool(latest) and is_newer(latest, cur)
        return {
            "checked": True,
            "available": available,
            "current": cur,
            "latest": latest,
            "url": data.get("html_url"),
            "notes": (data.get("body") or "")[:2000],
        }
    except Exception as e:  # noqa: BLE001 — surface the reason, never crash a UI poll
        record_failure("updater.check_for_update", e)
        return {"checked": True, "available": False, "current": cur, "error": str(e)[:200]}


def prepare_update() -> Dict[str, Any]:
    """ALWAYS export the mind before an update is applied (§10.7) — the safety net that
    makes auto-update tolerable given how fast the schema moves. Returns the keepsake path
    and the state schema version the new build must be able to load."""
    try:
        from brain.utils import mind_archive as _ma
        from brain.utils import schema_migration as _sm

        snap_dir = paths.DATA_DIR / "_backups"
        snap_dir.mkdir(parents=True, exist_ok=True)
        snap = snap_dir / f"pre-update-{time.strftime('%Y%m%d-%H%M%S')}.orrindmind"
        snap.write_bytes(_ma.export_bytes())
        return {
            "ok": True,
            "backup": str(snap),
            "state_schema_version": _sm.read_version(),
            "version": current_version(),
        }
    except Exception as e:  # noqa: BLE001
        record_failure("updater.prepare_update", e)
        return {"ok": False, "error": str(e)[:200]}
