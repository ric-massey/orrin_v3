# brain/utils/memory_graph.py
#
# Persistent similarity graph over long-term memories.
# Edges connect memory entries whose text has meaningful word overlap (Jaccard).
# Used during recall to fetch 1-hop neighbors — semantically related entries
# that wouldn't surface from a recency scan alone.
#
# Storage: brain/data/memory_graph.jsonl
# Each line: {"source": id, "target": id, "weight": float, "ts": iso}
#
# Threshold tuned so that incidental word sharing (the, is, memory) is filtered
# by the stopword list and doesn't produce spurious edges.
from __future__ import annotations
from brain.core.runtime_log import get_logger

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set, Tuple

from brain.paths import MEMORY_GRAPH_FILE
from brain.utils.json_utils import append_jsonl
from brain.utils.embed_similarity import text_similarity, embeddings_available
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

_STOPWORDS = frozenset({
    "the", "a", "an", "i", "is", "it", "in", "on", "at", "to", "of", "and",
    "or", "but", "not", "we", "you", "this", "that", "was", "are", "be",
    "have", "has", "do", "did", "will", "just", "now", "when", "how", "what",
    "which", "if", "so", "then", "there", "here", "with", "for", "as", "by",
    "from", "they", "he", "she", "its", "my", "your", "their", "our", "been",
    "were", "being", "would", "could", "should", "about", "into", "through",
    "orrin", "memory", "goal", "context", "summary", "recent", "current",
})

_EDGE_THRESHOLD = 0.18        # Jaccard cutoff for a meaningful link (fallback path)
_EDGE_THRESHOLD_EMBED = 0.40  # cosine cutoff when dense embeddings are active

# Cap edges written per new entry to its strongest links. Without this, a burst
# of near-identical memories (e.g. a stuck loop emitting "Goal avoidance: N
# cycles…" every cycle) links each new entry to ALL ~20 recent similars, so the
# graph regrew ~20k edges every 30 min (2026-06-12). Keeping only the top-K most
# similar preserves the meaningful structure while bounding per-entry growth.
_MAX_EDGES_PER_ENTRY = 6

# Compaction: the file is append-only and reached 11 MB / 64k lines with no
# rotation (DATA_FILE_AUDIT 2026-06-11 §7). Old edges point at memories the
# pruner has long since faded, so keeping a recent window loses little.
_GRAPH_MAX_BYTES  = 8_000_000
_GRAPH_KEEP_LINES = 30_000


def _maybe_compact(path: Path) -> None:
    try:
        if not path.exists() or path.stat().st_size <= _GRAPH_MAX_BYTES:
            return
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        kept = lines[-_GRAPH_KEEP_LINES:]
        tmp = path.with_suffix(".jsonl.tmp")
        tmp.write_text("\n".join(kept) + "\n", encoding="utf-8")
        tmp.replace(path)
        _log.info("memory_graph compacted: %d -> %d edges", len(lines), len(kept))
    except Exception as _e:
        record_failure("memory_graph._maybe_compact", _e)


def _tokenize(text: str) -> Set[str]:
    words = re.findall(r"[a-z]{4,}", text.lower())
    return {w for w in words if w not in _STOPWORDS}


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union > 0 else 0.0


def add_edges(new_entry: Dict, recent_entries: List[Dict]) -> None:
    """
    Compare new_entry against recent_entries; write edges to MEMORY_GRAPH_FILE
    for any pair with Jaccard similarity >= _EDGE_THRESHOLD.
    Safe to call with an empty or short recent_entries list.
    """
    try:
        new_id   = new_entry.get("id")
        new_text = str(new_entry.get("content") or "")
        if not new_id or not new_text.strip():
            return
        new_tokens = _tokenize(new_text)
        if len(new_tokens) < 4:
            return  # too short to form meaningful edges

        _maybe_compact(Path(MEMORY_GRAPH_FILE))

        use_embed = embeddings_available()
        threshold = _EDGE_THRESHOLD_EMBED if use_embed else _EDGE_THRESHOLD
        ts = datetime.now(timezone.utc).isoformat()

        # Score all qualifying candidates first, then keep only the strongest
        # links so one entry can't fan out to every recent similar at once.
        candidates: List[Tuple[float, str]] = []
        for other in recent_entries:
            if not isinstance(other, dict):
                continue
            other_id = other.get("id")
            if not other_id or other_id == new_id:
                continue
            other_text = str(other.get("content") or "")
            other_tokens = _tokenize(other_text)
            if len(other_tokens) < 4:
                continue
            sim = text_similarity(new_text, other_text) if use_embed else _jaccard(new_tokens, other_tokens)
            if sim >= threshold:
                candidates.append((sim, other_id))

        candidates.sort(key=lambda c: c[0], reverse=True)
        for sim, other_id in candidates[:_MAX_EDGES_PER_ENTRY]:
            append_jsonl(MEMORY_GRAPH_FILE, {
                "source": new_id,
                "target": other_id,
                "weight": round(sim, 3),
                "ts":     ts,
            })
    except Exception as _e:
        record_failure("memory_graph.add_edges", _e)


def get_neighbors(entry_id: str, n: int = 5) -> List[str]:
    """
    Return up to n memory IDs directly connected to entry_id, sorted by weight
    (highest first). Returns [] if no edges exist or the file is missing.
    """
    try:
        graph_path = Path(MEMORY_GRAPH_FILE)
        if not graph_path.exists():
            return []
        neighbors: Dict[str, float] = {}
        with open(graph_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    edge = json.loads(line)
                except Exception:
                    continue
                if not isinstance(edge, dict):
                    continue
                w = float(edge.get("weight") or 0.0)
                if edge.get("source") == entry_id:
                    other = edge.get("target")
                elif edge.get("target") == entry_id:
                    other = edge.get("source")
                else:
                    continue
                if other:
                    neighbors[other] = max(neighbors.get(other, 0.0), w)
        sorted_n = sorted(neighbors.items(), key=lambda x: x[1], reverse=True)
        return [nid for nid, _ in sorted_n[:n]]
    except Exception:
        return []
