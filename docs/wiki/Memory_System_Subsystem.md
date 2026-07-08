# Memory System Subsystem

Memory is split between the **memory daemon** (`memory/`, durable long-term storage with its own
WAL) and the brain's in-loop **working memory** (`brain/cog_memory/`). For the conceptual view see
[Memory System](Memory_System.md).

## The memory daemon (`memory/`)

- `memory_daemon.py` — the orchestrator: ingestion, embedding, consolidation scheduling.
- `wal.py` — write-ahead log (`data/memory/wal/`); ingestion is durable before it is indexed.
- `ingest.py` — normalizes incoming items; `novelty.py` dedupes near-duplicates on entry.
- `embedder.py` — sentence embeddings (`all-mpnet-base-v2` / `all-MiniLM-L6-v2`; runs offline with
  `HF_HUB_OFFLINE=1` in the Docker image).
- `retrieval.py` — similarity + recency + strength-weighted retrieval used by the recall phase.
- `strength.py` — per-memory strength that rises with use and decays without it; forgetting is a
  feature, not a leak.
- `compaction.py` — periodic compaction so the store stays bounded.
- `store/` — the persistent store; `lexicon/` — learned word associations; `media.py` — media
  attachments (`data/media/`); `health.py` / `metrics.py` — self-checks and stats.

## Working memory and consolidation

- `brain/cog_memory/` holds the small, fixed-size working memory the loop actually thinks with.
- During idle cycles the loop runs **consolidation**: working-memory items worth keeping are
  summarized and moved to long-term memory, and long-term memory is replayed/decayed. This is the
  "idle/consolidate" phase of [The Cognitive Loop](The_Cognitive_Loop.md).
- Retrieval quality is a learning signal: the delayed evaluator (`brain/eval/`) rewards the
  decision that stored a memory when that memory is later retrieved and used.

## Boundedness

Working memory is fixed-size; long-term memory consolidates, decays, and forgets rather than
growing without bound; append-only logs are capped (~3000 lines / 2 MB, atomic and line-safe). A
multi-day run should not need a reset for size reasons (see `docs/CONFIGURATION.md`).

## Code pointers

- `memory/memory_daemon.py`, `memory/wal.py`, `memory/retrieval.py`
- `brain/cog_memory/` — working memory
- [Debugging Memory Issues](Debugging_Memory_Issues.md) — practical diagnosis
