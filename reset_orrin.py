#!/usr/bin/env python3
"""
reset_orrin.py — wipe Orrin's runtime state for a clean run.

Usage:
    python3 reset_orrin.py           # clear runtime, keep config/knowledge
    python3 reset_orrin.py --hard    # also clear bandit/decision learning
    python3 reset_orrin.py --dry-run # print what would be cleared, don't touch files

Files kept regardless:
    knowledge_base.json, concepts.json, vocabulary.json, vocab_weights.json,
    model_config.json, emotion_model.json, self_model.json, meta_rules.json,
    symbolic_rules.json, behavioral_functions_list.json, cognitive_functions.json,
    attention_value_weights.json
"""

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "brain" / "data"
ARCHIVE_DIR = DATA_DIR / "_archive"

# Always kept — config and knowledge that takes effort to rebuild
ALWAYS_KEEP = {
    "knowledge_base.json",
    "concepts.json",
    "vocabulary.json",
    "vocab_weights.json",
    "model_config.json",
    "emotion_model.json",      # will become affect_model.json after rename
    "self_model.json",
    "meta_rules.json",
    "symbolic_rules.json",
    "behavioral_functions_list.json",
    "cognitive_functions.json",
    "attention_value_weights.json",
    "capability_descriptions.json",   # curated fn→goal match manifest (config/knowledge)
}

# Kept by default, cleared with --hard (learned bandit/decision state)
SOFT_KEEP = {
    "bandit_state.json",
    "decision_stats.json",
    "depth_stats.json",
    "emotion_function_map.json",
    "habituation.json",
    "intuition_patterns.json",
    "reward_trace.json",
    "reflection_stats.json",
}

# Files with specific default structures (everything else gets [] or {})
DEFAULTS: dict = {
    "cycle_count.json":     {"count": 0},
    "world_model.json":     {"entities": {}, "relations": [], "facts": [], "events": [], "concepts": [], "forces": []},
    "world_model_stats.json": {},
    "health_state.json":    {"status": "nominal", "cycle": 0},
    "energy_mode.json":     {"mode": "normal", "level": 1.0},
    "mode.json":            {"current": "default"},
    "temporal_state.json":  {},
    "emotion_state.json":   {},
    "cognition_state.json": {},
    "context.json":         {},
    "last_active.json":     {},
    "lifespan.json":        {},
    "speaker_state.json":   {},
    "body_sense.json":      {},
    "bandit_state.json":    {},
    "decision_stats.json":  {},
    "depth_stats.json":     {},
    "emotion_function_map.json": {},
    "reflection_stats.json": {},
}


def _detect_default(path: Path) -> object:
    """Return the right empty value for a file by peeking at its current type."""
    if path.name in DEFAULTS:
        return DEFAULTS[path.name]
    try:
        with open(path, encoding="utf-8") as f:
            first = f.read(1).strip()
        return [] if first == "[" else {}
    except Exception:
        return {}


def snapshot(label: str = "") -> Path:
    """Archive current data/*.json to a timestamped folder."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"snapshot_{ts}" + (f"_{label}" if label else "")
    dest = ARCHIVE_DIR / name
    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    for f in DATA_DIR.glob("*.json"):
        shutil.copy2(f, dest / f.name)
        count += 1
    print(f"  Snapshot: {dest} ({count} files)")
    return dest


def reset(hard: bool = False, dry_run: bool = False) -> None:
    keep = ALWAYS_KEEP | (set() if hard else SOFT_KEEP)

    to_clear = [
        f for f in sorted(DATA_DIR.glob("*.json"))
        if f.name not in keep
    ]

    if dry_run:
        print(f"\nDRY RUN — would clear {len(to_clear)} files:")
        for f in to_clear:
            print(f"  {f.name}")
        print(f"\nWould keep {len(keep)} files:")
        for n in sorted(keep):
            exists = "✓" if (DATA_DIR / n).exists() else "✗"
            print(f"  {exists} {n}")
        return

    print(f"\nClearing {len(to_clear)} runtime files...")
    for f in to_clear:
        default = _detect_default(f)
        with open(f, "w", encoding="utf-8") as fh:
            json.dump(default, fh)
        print(f"  ✓ {f.name}")

    # Clear outbox notes
    outbox_notes = Path(__file__).resolve().parent / "outbox" / "notes.json"
    if outbox_notes.exists():
        with open(outbox_notes, "w", encoding="utf-8") as fh:
            json.dump([], fh)
        print(f"  ✓ outbox/notes.json")

    # Clear log files (keep the files, just empty them)
    logs_dir = Path(__file__).resolve().parent / "brain" / "logs"
    if logs_dir.exists():
        for log in logs_dir.glob("*.txt"):
            log.write_text("")
            print(f"  ✓ logs/{log.name}")
        for log in logs_dir.glob("*.log"):
            log.write_text("")
            print(f"  ✓ logs/{log.name}")

    print(f"\nKept {len(keep)} config/knowledge files untouched.")
    print("Orrin is reset and ready for a clean run.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reset Orrin's runtime state.")
    parser.add_argument("--hard", action="store_true", help="Also clear learned bandit/decision state")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be cleared without doing it")
    parser.add_argument("--no-snapshot", action="store_true", help="Skip automatic snapshot before clearing")
    args = parser.parse_args()

    print("=== Orrin Reset ===")

    if not args.dry_run and not args.no_snapshot:
        print("\nSnapshotting current state first...")
        snapshot("pre_reset")

    reset(hard=args.hard, dry_run=args.dry_run)
