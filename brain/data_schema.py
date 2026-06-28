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

# 4.7 — data-FILE name renames (biological -> engineering). The on-disk filename
# is a persisted surface just like the keys inside it. Old files (and out-of-tree
# backups) keep loading: load_json / modify_json / the backend reader fall back to
# the old-named sibling via resolve_read_path() when the new name is absent, and
# the one-time backfill (migrate_schema_v2.py) renames them on disk. Keyed by
# basename (old -> new). The paths.py constant *identifiers* are unchanged; only
# the filename they point at moved.
FILE_RENAMES: Dict[str, str] = {
    # control-signals (was affect)
    "affect_state.json": "control_signals_state.json",
    "affect_model.json": "control_signals_model.json",
    "affect_drift.json": "control_signals_drift.json",
    "affect_function_map.json": "control_signals_function_map.json",
    # signals (was emotion)
    "emotion_function_map.json": "signal_function_map.json",
    "emotion_sensitivity.json": "signal_sensitivity.json",
    "emotion_drift.json": "signal_drift.json",
    "custom_emotion.json": "custom_signal.json",
    # smoothed state (was mood)
    "mood_state.json": "smoothed_state.json",
    # attention workspace (was consciousness)
    "conscious_stream.json": "workspace_broadcast.json",
    # idle consolidation (was dreams)
    "dream_log.json": "idle_consolidation_log.json",
    "symbolic_dream_log.json": "symbolic_idle_consolidation_log.json",
    # run history (was autobiography)
    "autobiography.json": "run_history.json",
    # resource self-monitoring (was body sense)
    "body_sense.json": "resource_self_monitor.json",
    "body_bands.json": "resource_bands.json",
    "body_bands_dream.json": "resource_bands_idle.json",
    "body_host_bands.json": "host_resource_bands.json",
    # cost prediction (was interoception)
    "interoceptive_model.json": "cost_prediction_model.json",
    # runtime lifetime (was lifespan)
    "lifespan.json": "runtime_lifetime.json",
    # identity (was self-model)
    "self_model.json": "identity_state.json",
    "symbolic_self_model.json": "symbolic_identity_state.json",
    "self_belief_revisions.json": "identity_belief_revisions.json",
    "self_model_backup.json": "identity_state_backup.json",
    # runtime state (was alive_brain_state)
    "alive_brain_state.json": "runtime_state.json",
    # demand/objective credit (was drive/aspiration)
    "drive_aspiration_credit.json": "demand_objective_credit.json",
}
# Reverse map: new basename -> old basename, for the read-old fallback.
_OLD_BASENAME: Dict[str, str] = {new: old for old, new in FILE_RENAMES.items()}

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
    "control_signals_state.json": {  # was affect_state.json (4.7 file rename)
        "top": {
            "homeostasis": "setpoint_proximity",  # setpoint regulation index
            "valence": "reward_signal",           # hedonic scalar, sign -1..1
            "mood": "smoothed_state",             # slow EMA of reward_signal
            # Tier C (FUNCTION_RENAME_COMPLETION_PLAN): the persisted regulatory
            # scalar + arbiter _SCALAR_TARGETS member. Read-old/write-new shim so a
            # restart keeps the live stability value instead of resetting to default.
            "affect_stability": "signal_stability",
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
    "signal_function_map.json": {  # was emotion_function_map.json (4.7 file rename)
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
    "runtime_lifetime.json": {  # was lifespan.json (4.7 file rename)
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


def resolve_read_path(path: Union[str, Path]) -> Path:
    """Read-old-path fallback (4.7). Callers request the NEW filename; if that file
    doesn't exist yet but the old-named sibling does, read the old one. Lets the
    running loop and old backups keep loading before the backfill renames files on
    disk. Returns the path to actually read (unchanged when no fallback applies)."""
    p = Path(path)
    old = _OLD_BASENAME.get(p.name)
    if old is not None and not p.exists():
        legacy = p.with_name(old)
        if legacy.exists():
            return legacy
    return p
