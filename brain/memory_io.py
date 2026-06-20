# brain/memory_io.py
# Brain-side memory I/O against the v2 memory engine — no adapter object.
#
# Replaces MemoryBridge: the cognitive loop calls these functions, which talk
# directly to the root memory/ engine (memory.models / memory.ingest /
# memory.retrieval). `import memory.X` resolves to root memory/ at runtime, so
# the old importlib-by-absolute-path shim is gone.
#
# v1 still owns its JSON working/long memory; these functions additionally
# ingest/query the v2 MemoryDaemon (embedding, salience, compaction). The daemon
# is passed in by the caller — this module holds no global state.
from __future__ import annotations
from core.runtime_log import get_logger

from typing import Any, Dict, List, Optional
from utils.failure_counter import record_failure
_log = get_logger(__name__)

_MOOD_KEYS = ("impasse_signal", "negative_valence", "exploration_drive",
              "positive_valence", "confidence", "threat_level")


def write(daemon: Any, kind: str, content: str, meta: Optional[Dict[str, Any]] = None) -> None:
    """Push a single event into the v2 MemoryDaemon."""
    if daemon is None:
        return
    try:
        from memory.models import Event
        daemon.ingest(Event(kind=kind, content=content, meta=dict(meta or {})))
    except Exception as e:
        _log.warning("memory_io.write failed: %s", e)


def _dominant_mood(context: Dict[str, Any]) -> Optional[str]:
    emo = context.get("affect_state") or {}
    core = emo.get("core_signals") or emo
    if not core:
        return None
    mood = max(_MOOD_KEYS, key=lambda k: float(core.get(k) or 0.0))
    return mood if float(core.get(mood) or 0.0) >= 0.15 else None


def flush_working_memory(daemon: Any, context: Dict[str, Any]) -> None:
    """Push the last few working-memory entries into v2 so recent thoughts are searchable."""
    if daemon is None:
        return
    wm: List[Any] = context.get("working_memory") or []
    if not wm:
        return
    tail = wm[-3:] if len(wm) > 3 else wm
    mood_tag = _dominant_mood(context)
    cc = context.get("cycle_count") or {}
    cycle = cc.get("count", 0) if isinstance(cc, dict) else int(cc or 0)
    for entry in tail:
        text = entry if isinstance(entry, str) else str(entry)
        meta: Dict[str, Any] = {"cycle": cycle}
        if mood_tag:
            meta["mood"] = mood_tag
        write(daemon, "thought", text, meta)


def backfill_long_memory_to_v2(daemon: Any, max_items: int = 10) -> int:
    """Ingest the most recent long_memory.json entries into v2 (dedup by content prefix)."""
    if daemon is None:
        return 0
    try:
        from utils.json_utils import load_json
        from paths import LONG_MEMORY_FILE
        from memory.models import Event
        long_mem = load_json(LONG_MEMORY_FILE, default_type=list)
        if not isinstance(long_mem, list) or not long_mem:
            return 0
        candidates = [e for e in long_mem[-max_items:] if isinstance(e, dict) and e.get("content")]
        store = daemon.store
        try:
            existing = {str(getattr(it, "content", "") or "")[:60]
                        for it in (getattr(store, "_items", {}) or {}).values()}
        except Exception:
            existing = set()
        added = 0
        for entry in candidates:
            content = str(entry.get("content", "")).strip()
            if not content or content[:60] in existing:
                continue
            emotion = str(entry.get("emotion", "") or "")
            daemon.ingest(Event(
                kind=entry.get("event_type", "long_memory"),
                content=content,
                meta={
                    "source": "long_memory_backfill",
                    "emotion": emotion,
                    "mood": emotion or None,
                    "emotional_context": entry.get("emotional_context") or {},
                    "importance": entry.get("importance", 1),
                    "agent": entry.get("agent", "orrin"),
                },
            ))
            existing.add(content[:60])
            added += 1
        return added
    except Exception as e:
        _log.warning("memory_io.backfill_long_memory_to_v2 failed: %s", e)
        return 0


def promote_summaries_to_long_memory(daemon: Any, max_items: int = 5) -> int:
    """Copy high-salience v2 compaction summaries into v1 long_memory.json (dedup by prefix)."""
    if daemon is None:
        return 0
    try:
        store = daemon.store
        if hasattr(store, "items_by_kind"):
            summary_items = store.items_by_kind("summary")
        else:
            summary_items = [it for it in (getattr(store, "_items", {}) or {}).values()
                             if getattr(it, "kind", "") == "summary"]
        if not summary_items:
            return 0
        summary_items.sort(
            key=lambda x: float(getattr(x, "salience", 0) or 0) + float(getattr(x, "strength", 0) or 0),
            reverse=True,
        )
        summary_items = summary_items[:max_items]

        from utils.json_utils import load_json, save_json
        from paths import LONG_MEMORY_FILE
        from datetime import datetime, timezone
        long_mem = load_json(LONG_MEMORY_FILE, default_type=list)
        if not isinstance(long_mem, list):
            long_mem = []
        existing = {str(e.get("content", ""))[:60] for e in long_mem if isinstance(e, dict)}
        added = 0
        for it in summary_items:
            content = str(getattr(it, "content", "") or "").strip()
            if not content or content[:60] in existing:
                continue
            long_mem.append({
                "content": content,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_type": "v2_summary",
                "importance": 3, "priority": 3, "source": "v2_compaction",
            })
            existing.add(content[:60])
            added += 1
        if added:
            save_json(LONG_MEMORY_FILE, long_mem)
        return added
    except Exception as e:
        _log.warning("memory_io.promote_summaries_to_long_memory failed: %s", e)
        return 0


def query(daemon: Any, text: str, k: int = 6, use_mmr: bool = True,
          affect_state: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Return up to k semantically similar items from the v2 store (mood-congruent boost)."""
    if daemon is None:
        return []
    query_text = text
    dominant_mood: Optional[str] = None
    if affect_state:
        try:
            core = affect_state.get("core_signals") or affect_state
            cand = {kk: float(core.get(kk) or 0) for kk in
                    ("impasse_signal", "negative_valence", "exploration_drive", "positive_valence", "confidence")}
            dominant_mood = max(cand, key=cand.get)
            if cand[dominant_mood] >= 0.4:
                query_text = f"[mood:{dominant_mood}] {text}"
            else:
                dominant_mood = None
        except Exception:
            dominant_mood = None
    try:
        from memory.retrieval import retrieve
        store = daemon.store
        fetch_k = k * 2 if dominant_mood else k
        items = retrieve(store, query_text=query_text, top_k=fetch_k, use_mmr=use_mmr, reinforce=True)
        if dominant_mood and items:
            def _boost(it: Any) -> float:
                return 0.15 if (getattr(it, "meta", None) or {}).get("mood", "") == dominant_mood else 0.0
            items = sorted(
                items,
                key=lambda it: float(getattr(it, "salience", 0) or 0)
                             + float(getattr(it, "strength", 0) or 0) + _boost(it),
                reverse=True,
            )[:k]
        results = [{
            "id": it.id, "content": it.content, "kind": it.kind, "ts": it.ts,
            "salience": getattr(it, "salience", 0.0), "strength": getattr(it, "strength", 0.0),
            "mood": (getattr(it, "meta", None) or {}).get("mood"),
            "private": (getattr(it, "meta", None) or {}).get("private", False),
            "meta": dict(getattr(it, "meta", None) or {}),
        } for it in items]
        return [r for r in results if not r.get("private")]
    except Exception:
        return []


def inject_into_context(daemon: Any, context: Dict[str, Any],
                        query_text: Optional[str] = None, k: int = 5) -> int:
    """Query v2 for relevant memories and inject into context['retrieved_memories']."""
    if daemon is None:
        return 0
    goal = context.get("committed_goal") or {}
    lens = context.get("goal_lens") or {}
    goal_text = " ".join([
        str(goal.get("title") or goal.get("name") or "").strip(),
        " ".join(str(x) for x in (lens.get("grounded_parts") or [])[:6]),
    ]).strip()
    recent_thought = ""
    for entry in reversed((context.get("working_memory") or [])[-8:]):
        text = entry if isinstance(entry, str) else (entry.get("content", "") if isinstance(entry, dict) else "")
        text = str(text or "").strip()
        if len(text) > 20:
            recent_thought = text[:200]
            break
    q = query_text or f"{goal_text} {recent_thought}".strip() or "recent experience reflection"
    results = query(daemon, q, k=k, use_mmr=True, affect_state=context.get("affect_state"))
    if not results:
        return 0
    try:
        from cognition.goal_lens import relevance as _goal_relevance
        for item in results:
            if isinstance(item, dict):
                rel = _goal_relevance(lens, item.get("content") or "")
                item["goal_lens_relevance"] = round(rel, 3)
        results.sort(
            key=lambda row: float(row.get("salience", 0.0) or 0.0)
            + float(row.get("strength", 0.0) or 0.0)
            + 0.35 * float(row.get("goal_lens_relevance", 0.0) or 0.0),
            reverse=True,
        )
        telemetry = context.setdefault("_goal_lens_telemetry", {})
        rels = [float(row.get("goal_lens_relevance", 0.0) or 0.0) for row in results]
        telemetry["retrieval_mean_relevance"] = round(sum(rels) / len(rels), 3) if rels else 0.0
    except Exception:
        pass
    try:
        from cog_memory.reconstruction import reconstruct as _recon
        mood = float((context.get("affect_state") or {}).get("mood") or 0.0)
        for item in results:
            if isinstance(item, dict):
                item["reconstructed"] = _recon(item, current_mood=mood)
    except Exception as _e:
        record_failure("memory_io.inject_into_context", _e)
    context["retrieved_memories"] = results
    return len(results)
