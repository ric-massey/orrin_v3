from __future__ import annotations
from brain.core.runtime_log import get_logger

from datetime import datetime, timezone
from typing import Any, List, Optional
import re
import uuid

from brain.utils.signal_lexicon_utils import detect_signal_keyword
# update_values_with_lessons (cognition, L3) is imported deferred at its call site
# below so this storage module (L2) does not import cognition at load time.
from brain.paths import LONG_MEMORY_FILE, PRIVATE_THOUGHTS_FILE
from brain.utils.json_utils import AbortModify, load_json, modify_json, save_json
from brain.utils.log import log_error, log_private
from brain.utils.memory_utils import summarize_memories
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

# Constants defining behaviour
DUPLICATE_WINDOW: int = 10        # Number of recent entries to check for duplicates
MAX_LONG_MEMORY: int = 2000       # Maximum allowed entries in long-term memory
STRONG_EMOTIONS = {"reward_positive", "threat_level", "conflict_signal", "loss_signal", "pride", "exploration_drive"}

# High-volume, low-information event types that recur as exact/near-duplicates and
# slip past the 10-entry exact-match dedup window (verified: 'chunk' and
# 'file_search' dominate long_memory.json with identical blocks). For these we scan
# a much wider window and compare on a content prefix so repeats collapse.
_REPETITIVE_EVENT_TYPES = frozenset({
    "chunk", "file_search", "world_perception", "dream_insight", "body_sense_pattern",
    # Respawn-loop floods (DATA_FILE_AUDIT 2026-06-11 §4): identical intrinsic
    # goals, commitments, and metacog observations recur slower than the
    # 10-entry default window, so they need the wide prefix-match window too.
    "intrinsic_goal", "commitment", "metacog_pattern",
})
_REPETITIVE_DEDUP_WINDOW: int = 200
_REPETITIVE_PREFIX: int = 120


def _dedup_window_for(event_type: str) -> int:
    return _REPETITIVE_DEDUP_WINDOW if event_type in _REPETITIVE_EVENT_TYPES else DUPLICATE_WINDOW


# Self-identity affirmation blocks (e.g. "Orrin (AI): role=self; version=…").
# Identity is already permanent in self_model.json + the knowledge graph
# (never_decay); re-logging it as episodic memory clutters the semantic space.
_IDENTITY_AFFIRM_RE = re.compile(
    r"\borrin\b.*\brole\s*=\s*self\b|\brole\s*=\s*self\b.*\bversion\b", re.I
)


def _signal_name(e: Any) -> str:
    """Coerce an emotion (possibly dict from detect_signal) into a lowercase string."""
    if isinstance(e, dict):
        return str(e.get("emotion", "neutral")).lower()
    return str(e or "neutral").lower()


def _snapshot_signal(context: Optional[dict]) -> dict:
    """Capture key emotion intensities from context at the moment of storage."""
    if not context:
        return {}
    emo = context.get("affect_state") or {}
    core = emo.get("core_signals") or emo
    if not isinstance(core, dict):
        return {}
    keys = ("reward_positive", "reward_negative", "exploration_drive", "impasse_signal", "confidence",
            "motivation", "stagnation_signal", "expected_gain", "threat_level", "social_penalty")
    snapshot = {k: round(float(core.get(k) or 0.0), 3) for k in keys if float(core.get(k) or 0.0) >= 0.05}
    stability = emo.get("signal_stability")
    if stability is not None:
        snapshot["signal_stability"] = round(float(stability), 3)
    return snapshot


def _signal_importance_boost(emotional_snapshot: dict) -> int:
    """Return 0–2 importance bonus for memories formed during high-emotion moments."""
    if not emotional_snapshot:
        return 0
    peak = max(
        (emotional_snapshot.get(k, 0.0)
         for k in ("impasse_signal", "reward_negative", "reward_positive", "threat_level", "social_penalty", "exploration_drive")),
        default=0.0,
    )
    if peak >= 0.6:
        return 2
    if peak >= 0.35:
        return 1
    return 0


def update_long_memory(
    new: Any,
    emotion: Optional[str] = None,
    event_type: str = "summary",
    agent: str = "orrin",
    importance: int = 1,
    priority: int = 1,
    referenced: int = 0,
    pin: bool = False,
    private: bool = False,
    related_memory_ids: Optional[List[str]] = None,
    recall_count: int = 0,
    embedding: Optional[List[float]] = None,
    context: Optional[dict] = None,
    extra: Optional[dict] = None,
) -> None:
    """Append a new event to long-term memory, with duplicate prevention and embedding generation."""
    now = datetime.now(timezone.utc).isoformat()

    emotional_snapshot = _snapshot_signal(context)
    emotion_boost = _signal_importance_boost(emotional_snapshot)

    # Build the entry from either a dict or a string
    if isinstance(new, dict):
        content = str(new.get("content", "")).strip()
        entry: dict = new.copy()
        entry.setdefault("id", str(uuid.uuid4()))
        entry.setdefault("timestamp", now)
        entry["content"] = content
        entry.setdefault("event_type", event_type)
        entry.setdefault("agent", agent)
        entry.setdefault("importance", min(10, importance + emotion_boost))
        entry.setdefault("priority", priority)
        entry.setdefault("referenced", referenced)
        entry.setdefault("pin", pin)
        entry.setdefault("related_memory_ids", related_memory_ids or [])
        entry.setdefault("recall_count", recall_count)
        entry.setdefault("private", private)
        if extra and isinstance(extra, dict):
            for k, v in extra.items():
                entry.setdefault(k, v)
        entry["emotion"] = _signal_name(emotion or detect_signal_keyword(content))
        if emotional_snapshot and not entry.get("emotional_context"):
            entry["emotional_context"] = emotional_snapshot
    elif isinstance(new, str):
        content = new.strip()
        entry = {
            "id": str(uuid.uuid4()),
            "timestamp": now,
            "content": content,
            "emotion": _signal_name(emotion or detect_signal_keyword(content)),
            "emotional_context": emotional_snapshot,
            "event_type": event_type,
            "agent": agent,
            "importance": min(10, importance + emotion_boost),
            "priority": priority,
            "referenced": referenced,
            "pin": pin,
            "related_memory_ids": related_memory_ids or [],
            "recall_count": recall_count,
            "private": private,
            **(extra or {}),
        }
    else:
        log_error("update_long_memory: Invalid 'new' argument.")
        return

    # Don’t store empty/noise-only entries
    if not entry.get("content"):
        log_private("[long_memory] Skipped empty content entry.")
        return

    # Don't re-log self-identity affirmations — they live in self_model.json + the
    # knowledge graph (never_decay). Skip unless this is an explicit foundational
    # (pinned read-only core) write, which is allowed through deliberately.
    if not entry.get("pin") and _IDENTITY_AFFIRM_RE.search(entry.get("content", "")):
        log_private("[long_memory] Skipped identity-affirmation block (lives in self_model/KG).")
        return

    # Cap content to prevent runaway entries from bloating the file.
    # Boundary-safe: a raw slice can cut through an [EXTERNAL/UNTRUSTED …]
    # wrapper and store a corrupt, re-ingestible tag fragment.
    if len(entry.get("content", "")) > 2000:
        from brain.utils.text_sanity import truncate_clean
        entry["content"] = truncate_clean(entry["content"], 2000)

    # Embeddings are indexed by the v2 memory daemon and not stored in this file
    # to keep long_memory.json small enough to load efficiently each cycle.
    entry.pop("embedding", None)

    # Dedup check + append run inside modify_json, which holds the advisory
    # lock across the whole read→modify→write — so a concurrent writer can't
    # interleave between our read and our save (the lost-update race that the
    # plain load_json→mutate→save_json sequence leaves open).
    _et = entry.get("event_type", "")
    _new_content = entry.get("content", "")
    _repetitive = _et in _REPETITIVE_EVENT_TYPES
    _new_key = _new_content[:_REPETITIVE_PREFIX] if _repetitive else _new_content

    _edge_window: list = []
    _over_cap = False
    try:
        with modify_json(LONG_MEMORY_FILE, default_type=list) as memories:
            if not isinstance(memories, list):
                raise AbortModify("corrupt")
            # Check for duplicates in the most recent window. Repetitive/low-
            # information event types (chunk, file_search, …) use a wider window
            # and a content-prefix comparison so near-identical blocks that
            # recur slowly still collapse.
            for m in memories[-_dedup_window_for(_et):]:
                if m.get("event_type", "") != _et:
                    continue
                _m_content = m.get("content", "")
                _m_key = _m_content[:_REPETITIVE_PREFIX] if _repetitive else _m_content
                if _m_key == _new_key:
                    raise AbortModify("duplicate")
            memories.append(entry)
            _edge_window = memories[-21:-1]
            _over_cap = len(memories) > MAX_LONG_MEMORY
    except AbortModify as _abort:
        if str(_abort) == "duplicate":
            log_private(f"[long_memory] Skipped duplicate memory: {_new_content[:50]}")
            return
        # Non-list store (corrupt): rebuild with just this entry.
        log_error("update_long_memory: long_memory store was not a list; rebuilding.")
        save_json(LONG_MEMORY_FILE, [entry])

    # Side effects stay outside the lock so file contention stays low.
    # Memory graph: link semantically similar entries by word overlap (Jaccard ≥ 0.18)
    try:
        from brain.utils.memory_graph import add_edges
        add_edges(entry, _edge_window)  # compare against up to 20 preceding entries
    except Exception as _e:
        record_failure("long_memory.update_long_memory", _e)

    # Optionally trigger a reward signal for important/priority memories
    if context is not None and (importance >= 2 or priority >= 2 or referenced >= 3):
        try:
            from brain.control_signals.reward_signals.reward_signals import release_reward_signal
            intensity = min(1.0, importance * 0.5 + priority * 0.5 + 0.1 * referenced)
            release_reward_signal(
                context=context,
                signal_type="reward_signal",
                actual_reward=intensity,
                expected_reward=0.5,
                effort=0.4,
                mode="phasic",
                source="memory_update",
            )
        except Exception as exc:
            log_error(f"update_long_memory: reward signalling failed: {exc}")

    # The append is already committed (under the lock); prune re-reads the
    # just-saved file so it operates on the freshest state.
    if _over_cap:
        prune_long_memory(max_total=MAX_LONG_MEMORY)


def remember_foundational(
    content: str,
    *,
    event_type: str = "foundational",
    context: Optional[dict] = None,
) -> None:
    """Write a memory that is part of Orrin's read-only core: pinned (never
    summarized/faded by prune_long_memory), max importance, and exempt from the
    pin cap (event_type='foundational'). Use ONLY for identity axioms, the core
    directive, and enduring aspirations — not ordinary episodic content."""
    update_long_memory(
        content,
        event_type=event_type,
        importance=10,
        priority=5,
        pin=True,
        context=context,
        extra={"foundational": True},
    )


def reevaluate_memory_significance() -> None:
    """Recompute the 'effectiveness_score' of all entries in long-term memory."""
    long_memory = load_json(LONG_MEMORY_FILE, default_type=list)
    if not isinstance(long_memory, list):
        return

    for mem in long_memory:
        if not isinstance(mem, dict):
            continue

        content = str(mem.get("content", "")).lower()
        emotion = _signal_name(mem.get("emotion", "neutral"))
        score = int(mem.get("effectiveness_score") or 5)

        # Reward memories tagged as lessons or containing strong affective content
        if "lesson:" in content:
            score = min(score + 1, 10)
        if emotion in {"loss_signal", "reward_positive", "threat_level", "pride"}:
            score = min(score + 1, 10)

        # Adjust based on recall_count
        rc = int(mem.get("recall_count") or 0)
        if rc >= 5:
            score = min(score + 2, 10)
        elif rc >= 2:
            score = min(score + 1, 10)

        # Pins have a minimum significance
        if mem.get("pin", False):
            score = max(score, 8)

        # Age penalty
        try:
            ts = mem.get("timestamp")
            if ts:
                age_days = (datetime.now(timezone.utc) - datetime.fromisoformat(ts)).days
                if age_days > 30 and score > 3 and not mem.get("pin", False):
                    score -= 1
        except Exception as _e:
            record_failure("long_memory.reevaluate_memory_significance", _e)

        # Related memories bonus
        rids = mem.get("related_memory_ids")
        if isinstance(rids, list) and len(rids) > 2:
            score = min(score + 1, 10)

        mem["effectiveness_score"] = score

    save_json(LONG_MEMORY_FILE, long_memory)


def prune_long_memory(max_total: int = MAX_LONG_MEMORY) -> None:
    """Reduce long-term memory to `max_total` items by removing low scoring entries and summarising them.

    The whole read→score→cap→write runs inside `modify_json` so concurrent
    appends can't be lost between the read and the save, and the surviving
    entries are re-sorted timestamp-ascending before saving so every reader
    that takes `long_memory[-N:]` (dedup window, recency scans) still gets
    genuinely recent entries after a prune.
    """

    def memory_score(mem: dict) -> int:
        try:
            score = 0
            emotion = _signal_name(mem.get("emotion", ""))
            content = str(mem.get("content", "")).lower()

            if emotion in STRONG_EMOTIONS:
                score += 3
            if "lesson:" in content:
                score += 4
            score += int(mem.get("effectiveness_score") or 5) // 2

            # Affective intensity at storage time — high-affect memories are harder to prune
            emo_ctx = mem.get("emotional_context") or {}
            if isinstance(emo_ctx, dict):
                peak_intensity = max(
                    (emo_ctx.get(k, 0.0)
                     for k in ("impasse_signal", "reward_negative", "reward_positive", "threat_level", "social_penalty", "exploration_drive")),
                    default=0.0,
                )
                if peak_intensity >= 0.6:
                    score += 4
                elif peak_intensity >= 0.35:
                    score += 2

            # Recency boost and age penalty
            try:
                ts = mem.get("timestamp", "")
                delta = datetime.now(timezone.utc) - datetime.fromisoformat(ts)
                days_old = delta.days
                if days_old < 3:
                    score += 3
                elif days_old < 7:
                    score += 1
                elif days_old > 30:
                    score -= 2
            except Exception as _e:
                record_failure("long_memory.prune_long_memory.memory_score", _e)

            # Pin multiplier
            if mem.get("pin", False):
                score += 10000

            # Recall bonus
            rc = int(mem.get("recall_count") or 0)
            if rc >= 5:
                score += 2
            elif rc >= 2:
                score += 1

            # Related memory bonus
            rids = mem.get("related_memory_ids")
            if isinstance(rids, list) and len(rids) > 2:
                score += 1

            score += int(mem.get("importance") or 1)
            score += int(mem.get("priority") or 1)
        except Exception as exc:
            log_error(f"prune_long_memory: scoring failed: {exc}")
            score = 0
        return score

    kept: list = []
    removed: list = []
    try:
        with modify_json(LONG_MEMORY_FILE, default_type=list) as long_memory:
            if not isinstance(long_memory, list) or len(long_memory) <= max_total:
                raise AbortModify("under-cap")

            # Collapse exact duplicates (same event_type + dedup key) before
            # scoring, keeping the earliest copy. High-importance duplicates
            # otherwise outscore ordinary memories and survive every prune,
            # so pollution self-entrenches.
            seen_keys: set = set()
            deduped: list = []
            for m in long_memory:
                if not isinstance(m, dict):
                    continue
                _et = m.get("event_type", "")
                _c = str(m.get("content", ""))
                _key = (_et, _c[:_REPETITIVE_PREFIX] if _et in _REPETITIVE_EVENT_TYPES else _c)
                if _key in seen_keys and not (m.get("pin") or m.get("foundational") or _et == "foundational"):
                    removed.append(m)
                    continue
                seen_keys.add(_key)
                deduped.append(m)

            # Sort by score then timestamp (desc) to pick survivors
            scored = sorted(deduped, key=lambda m: (memory_score(m), m.get("timestamp", "")), reverse=True)

            # Read-only core: foundational entries are NEVER capped or summarized — they are
            # Orrin's immutable axioms (identity, core directive, enduring aspirations).
            foundational = [m for m in scored if m.get("event_type") == "foundational" or m.get("foundational")]
            _foundational_ids = {id(m) for m in foundational}
            rest = [m for m in scored if id(m) not in _foundational_ids]
            pins = [m for m in rest if m.get("pin", False)]
            non_pins = [m for m in rest if not m.get("pin", False)]

            # Cap ordinary pins so a runaway pinner can't starve non-pins. Foundational
            # entries are excluded from this cap (and from the count) so the core always
            # survives. Without the cap, a fully-pinned list causes keep_count ≤ 0.
            _pin_cap = max_total // 2
            if len(pins) > _pin_cap:
                log_error(f"prune_long_memory: pin cap hit ({len(pins)} > {_pin_cap}); releasing lowest-priority pins.")
                pins = pins[:_pin_cap]

            keep_count = max_total - len(foundational) - len(pins)
            kept = foundational + pins + non_pins[: max(0, keep_count)]
            removed.extend(non_pins[max(0, keep_count):])

            if removed:
                summary = summarize_memories(removed)
                if summary:
                    _summary_content = f"Summary of faded memories:\n{summary}"
                    merged = {
                        "id": str(uuid.uuid4()),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "content": _summary_content,
                        "emotion": _signal_name(detect_signal_keyword(summary)),
                        "event_type": "memory_prune_summary",
                        "agent": "orrin",
                        "importance": 1,
                        "priority": 1,
                        "referenced": 0,
                        "pin": False,
                        "related_memory_ids": [],
                        "recall_count": 0,
                    }
                    kept.append(merged)

            # Restore chronological order: scoring decided WHO survives, but the
            # file must stay timestamp-ascending so `[-N:]` reads are "recent".
            kept.sort(key=lambda m: str(m.get("timestamp", "")))
            long_memory[:] = kept
    except AbortModify:
        return

    if removed:
        from brain.cognition.self_state.ethics import update_values_with_lessons  # deferred (keeps cog_memory L2 at load)
        # Pass the in-memory list so value-learning doesn't re-read the largest
        # state file from disk on the brain thread during a prune. Runs outside
        # the lock to keep file contention low.
        update_values_with_lessons(kept)

    # Log pruning to private thoughts file
    try:
        with open(PRIVATE_THOUGHTS_FILE, "a", encoding="utf-8") as f:
            f.write(
                f"\n[{datetime.now(timezone.utc)}] Orrin pruned {len(removed)} long memories. "
                f"{'Summarized and merged.' if removed else ''}\n"
            )
    except Exception as exc:
        log_error(f"prune_long_memory: failed writing to private thoughts: {exc}")