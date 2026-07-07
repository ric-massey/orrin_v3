# Memory System

Architecture
- Working memory: transient, in-process structures used by the loop.
- Long-term memory: WAL-backed storage with periodic embedding and index snapshots.

WAL & checkpoints
- Memory writes append to a JSONL WAL. Checkpoints create compacted snapshots.

Consolidation
- Triggered during idle windows and scheduled intervals (configurable). Embeddings computed, similarity indices updated.

Retrieval
- Semantic (embedding) first; token overlap fallback; recency and source weighting applied.

Data structures
- memories: {id, content, timestamp, tags, embedding}

Debugging
- Common failure modes: embedding provider errors, index corruption, WAL growth — inspect logs and run recovery scripts in memory/.
