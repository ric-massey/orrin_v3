# brain/scripts/clean_corrupted_memory.py
#
# One-shot migration over existing state (BEHAVIOR_FIX_PLAN Phase 1.1/1.4/1.5):
#   - strip nested `[Chunk:` wrappers from stored content,
#   - drop entries that are mid-word truncations of other entries
#     (prefix-match against full versions),
#   - reset the runaway reference count on corrupted chunks,
#   - delete crystallized/symbolic rules whose source text fails the sanity
#     filter,
#   - prune number-only / unit-only junk entities from the knowledge graph.
#
# Idempotent: re-running on clean state changes nothing. Run from brain/:
#   python3 scripts/clean_corrupted_memory.py [--dry-run]
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.json_utils import load_json, save_json
from utils.text_sanity import is_corrupt_text, ends_mid_word
from cog_memory.working_memory import _strip_chunk_label
from cognition.knowledge_graph import is_valid_entity_name
from brain.paths import (
    WORKING_MEMORY_FILE, LONG_MEMORY_FILE, RUMINATION_FILE, TENSIONS_FILE,
    REFLECTION, KNOWLEDGE_GRAPH_FILE, SYMBOLIC_RULES_FILE,
)

DRY_RUN = "--dry-run" in sys.argv

# Reference counts above this on a chunk entry are runaway self-reinforcement
# (the audit found one corrupted chunk referenced 243×) — reset so it stops
# dominating recall.
_REF_RESET_THRESHOLD = 50

_TEXT_FIELDS = ("content", "seed", "title", "description")


def _clean_text(value: str) -> str:
    """Collapse nested chunk wrappers; keep one level if it was a chunk label."""
    if not isinstance(value, str) or "[chunk:" not in value.lower():
        return value
    inner = _strip_chunk_label(value)
    return inner if inner else value


def _migrate_entry_list(path, label: str) -> None:
    entries = load_json(path, default_type=list)
    if not isinstance(entries, list):
        print(f"  {label}: not a list — skipped")
        return

    stripped = 0
    for e in entries:
        if not isinstance(e, dict):
            continue
        for field in _TEXT_FIELDS:
            v = e.get(field)
            cleaned = _clean_text(v) if isinstance(v, str) else v
            if cleaned != v:
                e[field] = cleaned
                stripped += 1
        # Runaway reference counts on (formerly) corrupted chunks
        if e.get("event_type") == "chunk" or e.get("chunk"):
            for ref_field in ("referenced", "recall_count"):
                if int(e.get(ref_field) or 0) > _REF_RESET_THRESHOLD:
                    e[ref_field] = 1
                    stripped += 1

    # Drop mid-word truncations of other entries: an entry ending mid-word
    # whose content is a prefix of a longer entry's content is a byte-cap
    # artifact of that entry, not an independent memory.
    contents = [str(e.get("content", "")) for e in entries if isinstance(e, dict)]
    dropped_idx = set()
    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            continue
        c = str(e.get("content", "")).strip()
        if len(c) < 40 or not ends_mid_word(c):
            continue
        for j, other in enumerate(contents):
            if j != i and len(other) > len(c) and other.startswith(c):
                dropped_idx.add(i)
                break

    kept = [e for i, e in enumerate(entries) if i not in dropped_idx]
    print(f"  {label}: {stripped} field(s) cleaned, {len(dropped_idx)} truncation dup(s) dropped "
          f"({len(entries)} → {len(kept)} entries)")
    if not DRY_RUN and (stripped or dropped_idx):
        save_json(path, kept)


def _migrate_rules() -> None:
    rules = load_json(SYMBOLIC_RULES_FILE, default_type=list)
    if not isinstance(rules, list):
        print("  symbolic_rules: not a list — skipped")
        return
    kept, deleted = [], 0
    for r in rules:
        if isinstance(r, dict) and is_corrupt_text(str(r.get("conclusion", "") or "")):
            deleted += 1
            continue
        kept.append(r)
    print(f"  symbolic_rules: {deleted} corrupt-source rule(s) deleted ({len(rules)} → {len(kept)})")
    if not DRY_RUN and deleted:
        save_json(SYMBOLIC_RULES_FILE, kept)


def _migrate_knowledge_graph() -> None:
    g = load_json(KNOWLEDGE_GRAPH_FILE, default_type=dict)
    if not isinstance(g, dict) or not isinstance(g.get("entities"), dict):
        print("  knowledge_graph: unexpected shape — skipped")
        return
    entities = g["entities"]
    junk = [eid for eid, ent in entities.items()
            if not is_valid_entity_name(str((ent or {}).get("name", "")))]
    for eid in junk:
        del entities[eid]
    # Drop relations referencing pruned entities.
    relations = g.get("relations")
    pruned_rel = 0
    if isinstance(relations, dict):
        junk_set = set(junk)
        for rid in [rid for rid, rel in relations.items()
                    if isinstance(rel, dict)
                    and (rel.get("source") in junk_set or rel.get("target") in junk_set)]:
            del relations[rid]
            pruned_rel += 1
    if isinstance(g.get("meta"), dict):
        g["meta"]["entity_count"] = len(entities)
    print(f"  knowledge_graph: {len(junk)} junk entit(ies) pruned, {pruned_rel} dangling relation(s) removed")
    if not DRY_RUN and (junk or pruned_rel):
        save_json(KNOWLEDGE_GRAPH_FILE, g)


def _migrate_llm_failure_counts() -> None:
    """Delete test-pollution keys (test_*) from live failure counts."""
    path = Path(__file__).resolve().parent.parent / "data" / "llm_failure_counts.json"
    counts = load_json(path, default_type=dict)
    if not isinstance(counts, dict):
        return
    junk = [k for k in counts if str(k).startswith("test")]
    for k in junk:
        del counts[k]
    print(f"  llm_failure_counts: {len(junk)} test key(s) removed")
    if not DRY_RUN and junk:
        save_json(path, counts)


def main() -> None:
    print(f"clean_corrupted_memory {'(dry run)' if DRY_RUN else ''}")
    _migrate_llm_failure_counts()
    _migrate_entry_list(WORKING_MEMORY_FILE, "working_memory")
    _migrate_entry_list(LONG_MEMORY_FILE, "long_memory")
    _migrate_entry_list(RUMINATION_FILE, "rumination_loops")
    _migrate_entry_list(TENSIONS_FILE, "tensions")
    _migrate_entry_list(REFLECTION, "reflection_log")
    _migrate_rules()
    _migrate_knowledge_graph()
    print("done")


if __name__ == "__main__":
    main()
