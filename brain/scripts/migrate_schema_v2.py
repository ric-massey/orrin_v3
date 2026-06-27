"""One-time backfill for the persisted-schema migration (analogue-removal Phase 4).

`load_json()` already upgrades old keys to new ones in memory on every read, so
the running loop is correct the moment Phase 4 lands. This script makes the
*on-disk* files match too, so a static `grep` of the data tree comes back clean
and old backups can be normalised ahead of time.

It rewrites only the files registered in `brain.data_schema.MIGRATIONS`, under
both persisted-state trees (`DATA_DIR` = the mind, `STATE_DIR` = the daemon
durability tree). Atomic per file via `save_json`. Idempotent — running it twice
is a no-op the second time.

ALWAYS run `--dry-run` against the Phase-0 data snapshot first.

    python -m brain.scripts.migrate_schema_v2 --dry-run
    python -m brain.scripts.migrate_schema_v2
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

import brain.paths as paths
from brain.data_schema import MIGRATIONS, SCHEMA_VERSION, migrate_loaded
from brain.utils.json_utils import save_json


def _candidate_dirs() -> List[Path]:
    seen: List[Path] = []
    for d in (paths.DATA_DIR, paths.STATE_DIR):
        if d.exists() and d not in seen:
            seen.append(d)
    return seen


def migrate_tree(*, dry_run: bool) -> int:
    """Migrate every registered file found under the state trees. Returns the
    number of files that changed (or would change, under --dry-run)."""
    changed = 0
    for root in _candidate_dirs():
        for name in MIGRATIONS:
            for path in root.rglob(name):
                if not path.is_file():
                    continue
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    continue  # corrupt/unreadable — leave for load_json's healing
                before = json.dumps(raw, sort_keys=True)
                migrated = migrate_loaded(path, raw)
                after = json.dumps(migrated, sort_keys=True)
                if before == after:
                    continue
                changed += 1
                print(f"{'WOULD MIGRATE' if dry_run else 'MIGRATED'}: {path}")
                if not dry_run:
                    save_json(path, migrated)
    return changed


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change without writing")
    args = ap.parse_args()
    if not MIGRATIONS:
        print("No persisted-key migrations registered yet (schema "
              f"v{SCHEMA_VERSION}); nothing to do.")
        return
    n = migrate_tree(dry_run=args.dry_run)
    verb = "would migrate" if args.dry_run else "migrated"
    print(f"\nSchema v{SCHEMA_VERSION}: {verb} {n} file(s).")


if __name__ == "__main__":
    main()
