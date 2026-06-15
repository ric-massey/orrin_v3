"""
utils/schema_migration.py — the state schema version + migration spine (§10.7).

Known-limitations today: "State formats … and on-disk layouts change between versions
WITHOUT migrations — a long-running 'mind' may not survive an upgrade." Tolerable for a
dev checkout (`reset_orrin.py`); catastrophic for a shipped app whose whole premise is a
months-old mind you've grown attached to. This module is the spine that makes an upgrade
non-destructive:

  • A single `state_schema_version` is stamped into the per-user data dir (and into the
    export `meta.json`, §9.6).
  • On launch, if the on-disk version is OLDER than this build expects, ordered
    migrations bring the mind forward; if it's NEWER (the user downgraded), we REFUSE to
    load rather than corrupt it.
  • Before applying ANY migration, the mind is auto-exported (reuse `mind_archive`), so
    even a failed migration leaves a restorable keepsake — the safety net that makes
    auto-update (I7) tolerable given how fast the schema moves.

This GLOBAL version subsumes the one per-store version that already exists —
`cognition/knowledge_graph.py` stamps `_SCHEMA_VERSION = 1` into its graph meta. The
baseline here is 1, so global-v1 == that store's v1 today; a future graph-format change
gets a migration registered here and bumps the global version, rather than each store
versioning itself in isolation.
"""
from __future__ import annotations

import json
import time
from typing import Callable, Dict, List, Optional

import paths

# The schema version THIS build writes/expects. Bump whenever an on-disk format changes
# in a way a migration must reason about, and register the migration below.
CURRENT_SCHEMA_VERSION = 1

# The version at which this spine was introduced. Any mind with no stamp predates the
# spine and is, by construction, at this baseline — NOT at CURRENT (so when CURRENT
# later moves ahead, unstamped minds still get migrated forward from here).
_BASELINE_VERSION = 1

_STAMP_FILE = paths.DATA_DIR / "schema_version.json"


class SchemaTooNewError(Exception):
    """The on-disk mind was written by a newer build than this one. Refuse to load it —
    loading would silently corrupt state the current build doesn't understand."""


def read_version() -> int:
    """The schema version of the mind currently on disk. An unstamped mind is treated as
    the baseline (it predates the stamp), never as CURRENT."""
    try:
        data = json.loads(_STAMP_FILE.read_text(encoding="utf-8"))
        return int(data.get("state_schema_version", _BASELINE_VERSION))
    except Exception:
        return _BASELINE_VERSION


def stamp_version(version: int = CURRENT_SCHEMA_VERSION) -> None:
    try:
        paths.DATA_DIR.mkdir(parents=True, exist_ok=True)
        _STAMP_FILE.write_text(
            json.dumps({"state_schema_version": int(version), "updated_at": time.time()}, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


# ── Migration registry ───────────────────────────────────────────────────────
# Each entry upgrades the on-disk mind from version N to N+1, in place, idempotently.
# Keyed by the FROM version. Empty today (we ship at the baseline); the first on-disk
# format change adds `1: _migrate_1_to_2` here and bumps CURRENT_SCHEMA_VERSION to 2.
_MIGRATIONS: Dict[int, Callable[[], None]] = {}


def _auto_export_before_migrate() -> Optional[str]:
    """Always snapshot the mind before touching it (§10.7 safety net). Best-effort: a
    snapshot failure must not block a migration the user needs, but we record that it
    didn't happen."""
    try:
        from utils import mind_archive as _ma

        snap_dir = paths.DATA_DIR / "_backups"
        snap_dir.mkdir(parents=True, exist_ok=True)
        snap = snap_dir / f"pre-migrate-{time.strftime('%Y%m%d-%H%M%S')}.orrindmind"
        snap.write_bytes(_ma.export_bytes())
        return str(snap)
    except Exception:
        return None


def check_and_migrate(*, auto_export: bool = True) -> Dict[str, object]:
    """The boot entrypoint. Reconciles the on-disk schema version with this build:

      • equal   → ensure the stamp exists, no-op.
      • newer   → REFUSE (raise SchemaTooNewError); caller must not continue booting.
      • older   → auto-export, run ordered migrations forward, re-stamp CURRENT.

    Returns a status dict for the boot log / UI. Raises only on the refuse case, so a
    routine launch stays quiet."""
    disk = read_version()
    cur = CURRENT_SCHEMA_VERSION

    if disk == cur:
        stamp_version(cur)  # idempotent; ensures an unstamped current mind gets stamped
        return {"action": "none", "from": disk, "to": cur}

    if disk > cur:
        raise SchemaTooNewError(
            f"on-disk state schema is v{disk}, but this build understands only up to "
            f"v{cur} — refusing to load so the mind isn't corrupted (downgrade?)."
        )

    # disk < cur → migrate forward, one step at a time.
    backup = _auto_export_before_migrate() if auto_export else None
    applied: List[Dict[str, int]] = []
    v = disk
    while v < cur:
        fn = _MIGRATIONS.get(v)
        if fn is not None:
            fn()
        applied.append({"from": v, "to": v + 1})
        v += 1
    stamp_version(cur)
    return {"action": "migrated", "from": disk, "to": cur, "applied": applied, "backup": backup}
