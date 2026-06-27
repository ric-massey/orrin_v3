# brain/cog_memory/working_memory_chunk.py
#
# Working-memory chunking for working_memory.py (CODEBASE_CLEANUP_PLAN 4.5C),
# lifted verbatim to bring that module under the 600-line soft limit. The
# similarity + chunk-merge layer: _content_similarity (token overlap),
# _strip_chunk_label (peel [chunk: ...] wrappers), and _chunk_two_most_similar
# (merge the two most-similar WM entries when they clear the _MIN_CHUNK_SIM
# floor). working_memory.py re-imports these for update_working_memory +
# external callers (prediction, clean_corrupted_memory).
from __future__ import annotations

import re as _re
import uuid
from datetime import datetime, timezone

from brain.core.runtime_log import get_logger
from brain.utils.log import log_private
from brain.utils.failure_counter import record_failure

_log = get_logger(__name__)

def _content_similarity(a: str, b: str) -> float:
    """Simple Jaccard similarity over lowercased word tokens."""
    if not a or not b:
        return 0.0
    wa = set(str(a).lower().split())
    wb = set(str(b).lower().split())
    _STOP = {"the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "at",
             "is", "was", "are", "i", "it", "this", "that", "for", "with"}
    wa -= _STOP
    wb -= _STOP
    if not wa or not wb:
        return 0.0
    inter = len(wa & wb)
    union = len(wa | wb)
    return inter / union if union else 0.0


# Chunk-merge similarity floor. Raised 0.15 → 0.55 (BEHAVIOR_FIX_PLAN Phase 1.3):
# the audit found chunks merging at sim 0.25–0.28, gluing unrelated items into
# noise labels that then distorted every future similarity comparison. Only
# genuinely related items merge now; near-misses are logged for tuning.
_MIN_CHUNK_SIM = 0.55

_CHUNK_WRAP_RE = _re.compile(r"^\s*\[chunk:\s*(.*)\]\s*$", _re.IGNORECASE | _re.DOTALL)
# A run of leading "[Chunk:" prefixes — catches TRUNCATED nesting where the disk
# 500-char cap chopped off the closing brackets (e.g. "[Chunk: [Chunk: [Chunk: … /"),
# which the balanced-wrapper regex above can't match because there's no trailing "]".
_CHUNK_LEAD_RE = _re.compile(r"^\s*(?:\[chunk:\s*)+", _re.IGNORECASE)
_CHUNK_TRAIL_RE = _re.compile(r"[\]\s]*$")

def _strip_chunk_label(s: str) -> str:
    """
    Remove an existing `[Chunk: … ]` wrapper so chunk labels never nest.
    Idempotent: already-clean text is returned unchanged. Applied repeatedly
    until no leading `[chunk:` remains, which heals legacy entries that already
    accumulated `[Chunk: [Chunk: …` to ~16 levels deep — including truncated ones
    whose closing brackets were lost to the disk content cap.
    """
    if not isinstance(s, str):
        return s
    out = s
    # Bound the loop defensively; corrupted entries top out around 16 levels.
    for _ in range(32):
        m = _CHUNK_WRAP_RE.match(out)
        if not m:
            break
        out = m.group(1).strip()
    # Fallback for unbalanced/truncated nesting: collapse a run of leading
    # "[Chunk:" prefixes and drop any dangling closers left behind.
    if _CHUNK_LEAD_RE.match(out):
        out = _CHUNK_LEAD_RE.sub("", out).strip()
        out = _CHUNK_TRAIL_RE.sub("", out).strip()
    return out

def _chunk_two_most_similar(memories: list) -> bool:
    """
    When WM is full, find the two most similar non-pin items and merge them
    into a single chunk entry. Returns True if a chunk was created.
    Returns False (so caller falls through to trim) when no pair is similar
    enough — chunking unrelated items just produces noise like
    `[Chunk: [metacog/pattern] ... / [Chunk: ⏳ Last active: ...]` which then
    distorts every future similarity comparison.
    """
    non_pins = [(i, m) for i, m in enumerate(memories)
                if isinstance(m, dict) and not m.get("pin")]
    if len(non_pins) < 2:
        return False

    best_pair = None
    best_score = -1.0
    for ai in range(len(non_pins)):
        for bi in range(ai + 1, len(non_pins)):
            idx_a, mem_a = non_pins[ai]
            idx_b, mem_b = non_pins[bi]
            # Truncate before similarity — chunk content strings can be huge
            ca = str(mem_a.get("content", ""))[:200]
            cb = str(mem_b.get("content", ""))[:200]
            score = _content_similarity(ca, cb)
            if score > best_score:
                best_score = score
                best_pair = (idx_a, idx_b, mem_a, mem_b)

    if not best_pair or best_score < _MIN_CHUNK_SIM:
        if best_pair and best_score > 0.0:
            try:
                log_private(
                    f"[working_memory] Chunk merge skipped (sim={best_score:.2f} "
                    f"< {_MIN_CHUNK_SIM}): '{str(best_pair[2].get('content',''))[:40]}' + "
                    f"'{str(best_pair[3].get('content',''))[:40]}'"
                )
            except (ValueError, TypeError, OSError):  # best-effort chunk-skip log
                pass
        return False

    idx_a, idx_b, mem_a, mem_b = best_pair
    # Truncate content to prevent chunk-of-chunk content explosion.
    # A chunk's label only needs to be a brief summary, not the full history.
    _MAX_CONTENT_LABEL = 120
    # Strip any existing [Chunk: …] wrapper first so the label stays exactly one
    # level deep — without this, re-chunking a chunk nests `[Chunk: [Chunk: …`.
    # Clean (boundary) truncation: a mid-word cut here is re-ingestible garbage.
    from brain.utils.text_sanity import truncate_clean as _tc
    ca = _tc(_strip_chunk_label(str(mem_a.get("content", ""))), _MAX_CONTENT_LABEL)
    cb = _tc(_strip_chunk_label(str(mem_b.get("content", ""))), _MAX_CONTENT_LABEL)

    # Flatten if either side is already a chunk so we don't get nested lists.
    items_a = (mem_a.get("items") or [mem_a]) if mem_a.get("chunk") else [mem_a]
    items_b = (mem_b.get("items") or [mem_b]) if mem_b.get("chunk") else [mem_b]

    # Cap items to prevent unbounded growth that bloats the WM file.
    # When a chunk grows too large, keep the most recent items — they're
    # the ones most likely to be relevant in the current context.
    _MAX_CHUNK_ITEMS = 8
    combined_items = list(items_a) + list(items_b)
    if len(combined_items) > _MAX_CHUNK_ITEMS:
        combined_items = combined_items[-_MAX_CHUNK_ITEMS:]

    chunk_entry = {
        "id": str(uuid.uuid4()),
        "chunk": True,
        "items": combined_items,
        "content": f"[Chunk: {ca} / {cb}]",
        "emotion": mem_a.get("emotion", "neutral"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": "chunk",
        "agent": mem_a.get("agent", "orrin"),
        "importance": max(int(mem_a.get("importance") or 1),
                          int(mem_b.get("importance") or 1)),
        "priority": max(int(mem_a.get("priority") or 1),
                        int(mem_b.get("priority") or 1)),
        "referenced": int(mem_a.get("referenced") or 0) + int(mem_b.get("referenced") or 0),
        "recall_count": int(mem_a.get("recall_count") or 0) + int(mem_b.get("recall_count") or 0),
        "pin": False,
        "decay": max(float(mem_a.get("decay") or 1.0), float(mem_b.get("decay") or 1.0)),
        "related_memory_ids": list(mem_a.get("related_memory_ids") or [])
                              + list(mem_b.get("related_memory_ids") or []),
        "embedding": mem_a.get("embedding") or mem_b.get("embedding") or [],
    }

    # Remove in descending order so indices stay valid
    for idx in sorted([idx_a, idx_b], reverse=True):
        memories.pop(idx)
    memories.append(chunk_entry)
    try:
        log_private(
            f"[working_memory] Chunked 2 similar items (sim={best_score:.2f}): "
            f"'{ca[:40]}' + '{cb[:40]}'"
        )
    except Exception as _e:
        record_failure("working_memory._chunk_two_most_similar", _e)
    return True
