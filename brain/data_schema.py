"""Persisted-schema versioning + on-disk key migration (analogue-removal Phase 4).

The on-disk JSON keys and data-file names are a stable wire contract. Phase 3
renamed every *code* identifier from the biological dialect to engineering
terms but deliberately froze the persisted surfaces, because renaming a key in
place would invalidate existing `brain/data` files, out-of-tree backups, and the
*learned* weights keyed on signal names. Phase 4 flips those persisted keys too,
safely: this module is the single read-old/write-new shim.

Mechanism (the plan's "readers accept both old and new"):
  * `load_json()` / `modify_json()` route every read through `migrate_loaded()`,
    which upgrades any registered old key to its new spelling *in memory* and
    stamps the file's schema version. Writers then persist the new keys.
  * A one-time backfill (`brain/scripts/migrate_schema_v2.py`) rewrites existing
    files so a static `grep` of the data tree also comes back clean.

The migration is keyed by data-file *basename* so it only ever touches the files
it is meant to — an unrelated file that happens to contain the word "mood" is
never rewritten. Renames are idempotent and non-destructive: the old value is
moved to the new key, and an already-present new key always wins.

Frozen-by-design (NOT migrated): the engineering-neutral core signals
(`threat_level`, `confidence`, `motivation`, …), scientific-citation prose, and
verbatim runtime log text. Those are either already correct or are historical
data we never rewrite.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Union

# Bumped from the implicit v1 (no marker) to v2 when the first persisted key is
# renamed. Stamped into every registered file as it is migrated.
SCHEMA_VERSION = 2
SCHEMA_VERSION_KEY = "_schema_version"

# Per-file migration registry. Keyed by the data file's basename.
#
#   "top":    {old_key: new_key}                  rename at the dict's top level
#   "nested": {container_key: {old_key: new_key}}  rename inside data[container_key]
#
# Populated concept-by-concept across the Phase 4 slices (scalar keys, the signal
# vocabulary + the learned emotion_function_map, …). Empty here = pure
# infrastructure: the shim is a no-op until a slice registers a file.
MIGRATIONS: Dict[str, Dict[str, Any]] = {
    # 4.2 — top-level affect-state scalar keys (engineering names from the plan's
    # Term Map). The telemetry WIRE fields keep their old spelling for now; the
    # serializer reads the new state key and emits the old wire field, so the
    # frontend is untouched until the dedicated routes/frontend slice.
    # 4.5 — the biological core-signal names -> engineering names. These are the
    # most cross-referenced identifiers in the system: persisted in core_signals,
    # LEARNED in emotion_function_map.json (signal->function->value), and the keys
    # of the routing/setpoint/antagonist tables. The 14 engineering-neutral signals
    # (threat_level, confidence, …) are frozen — already correct. surprise/wonder
    # are added in their own slices (they collide with generic English / wonder.py).
    "affect_state.json": {
        "top": {
            "homeostasis": "setpoint_proximity",  # setpoint regulation index
            "valence": "reward_signal",           # hedonic scalar, sign -1..1
            "mood": "smoothed_state",             # slow EMA of reward_signal
        },
        # core_signals holds the per-signal vector; rename the biological names.
        "nested": {"core_signals": {
            "positive_valence": "reward_positive",
            "negative_valence": "reward_negative",
            "compassion": "affiliation_signal",
            "melancholy": "low_affect_signal",
            "jealousy": "social_comparison_signal",
            "contentment": "satisfaction_signal",
            "vitality": "vigor_signal",
            # 'surprise' -> 'prediction_error_signal' (the _signal suffix avoids
            # colliding with the existing prediction_error() scalar/function).
            "surprise": "prediction_error_signal",
            "wonder": "novelty_signal",
        }},
    },
    # The learned signal->function weight map is keyed by signal name at the top
    # level — migrate in lockstep or the learned associations silently reset.
    "emotion_function_map.json": {
        "top": {
            "positive_valence": "reward_positive",
            "negative_valence": "reward_negative",
            "compassion": "affiliation_signal",
            "melancholy": "low_affect_signal",
            "jealousy": "social_comparison_signal",
            "contentment": "satisfaction_signal",
            "vitality": "vigor_signal",
            "surprise": "prediction_error_signal",
            "wonder": "novelty_signal",
        },
    },
    # 4.6 — lifecycle start timestamp. The /life wire field stays "born_at" via
    # life_status() translation until the routes/frontend slice.
    "lifespan.json": {
        "top": {"born_at": "start_time"},
    },
}


def _rename_keys(d: Dict[str, Any], mapping: Dict[str, str]) -> bool:
    """Rename old->new keys in `d` in place. Idempotent and non-clobbering: the
    old value moves to the new key, but an already-present new key is preserved
    (it is authoritative — a half-migrated file keeps the new write, not the
    stale duplicate). Returns True if anything changed."""
    changed = False
    for old, new in mapping.items():
        if old in d:
            val = d.pop(old)
            if new not in d:
                d[new] = val
            changed = True
    return changed


def migrate_loaded(
    path: Union[str, Path],
    data: Any,
    registry: Dict[str, Dict[str, Any]] = MIGRATIONS,
) -> Any:
    """Upgrade a just-loaded JSON value to the current schema.

    No-op unless `path`'s basename is registered and `data` is a dict. Applies
    the file's top-level and nested key renames, then stamps the schema version.
    `registry` is injectable for testing; production passes the module default.
    """
    if not isinstance(data, dict):
        return data
    spec = registry.get(Path(path).name)
    if spec is None:
        return data
    top = spec.get("top")
    if top:
        _rename_keys(data, top)
    for container, mapping in spec.get("nested", {}).items():
        sub = data.get(container)
        if isinstance(sub, dict):
            _rename_keys(sub, mapping)
    if data.get(SCHEMA_VERSION_KEY) != SCHEMA_VERSION:
        data[SCHEMA_VERSION_KEY] = SCHEMA_VERSION
    return data


def is_registered(path: Union[str, Path]) -> bool:
    """True if a file would be migrated (used by the backfill script)."""
    return Path(path).name in MIGRATIONS
