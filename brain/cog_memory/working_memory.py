from __future__ import annotations
from core.runtime_log import get_logger

import time as _time
from datetime import datetime, timezone
from typing import Any, List, Optional
import uuid
import numpy as np

from utils.affect_utils import detect_affect_keyword
from utils.embedder import get_embedding
from utils.json_utils import load_json, save_json, modify_json, AbortModify
from utils.log import log_private, log_error
from cog_memory.summarize_w_memory import summarize_and_promote_working_memory
from brain.paths import WORKING_MEMORY_FILE, AFFECT_STATE_FILE
import os as _os
_log = get_logger(__name__)

import re as _re
_MACHINE_KV_RE = _re.compile(r"\b\w+=[\w.\-]+")


def _looks_machine_content(c: str) -> bool:
    """A serialized structure or a key=value diagnostic line is machine telemetry, not
    a thought. Entries whose content matches are tagged ``internal_telemetry`` so the
    expression membrane never offers them as speech and LM consolidation skips them.
    FINDINGS 2026-06-16: cognition return-dicts ({'trigger': 'cognition', 'skipped':
    True}) and health-summary lines ("cpu=0.00, hb=0.00, err=0.00") reached his voice
    as "Earlier I was thinking: …". This tags them at the write boundary — the source —
    complementing the speak.py membrane backstop.

    Deliberately matches only a dict repr ('{') and key=value telemetry — NOT a '['
    prefix, which the codebase uses for legitimate human-readable memories
    ([research], [Goal pursuit], …) that must still consolidate into long memory."""
    c = (c or "").lstrip()
    if c.startswith("{"):
        return True
    return len(_MACHINE_KV_RE.findall(c)) >= 2


MAX_WORKING_LOGS: int = 25

# ── Working-memory-cap plasticity (proactive_resource_plan §5, final item) ──────
# The effective WM cap flexes with resource state, mirroring humans: fatigue narrows
# working memory, freshness widens it. Gated on a *verified* bottleneck (WM sits pinned
# at the cap with constant chunking/compaction) before enabling — per the plan.
# Anti-reward-hack BY CONSTRUCTION: capacity only GROWS when the resource deficit is
# genuinely LOW, and effort/stress strictly RAISE the deficit — so inducing load
# *shrinks* WM, never expands it. There is no incentive to manufacture stress to win
# capacity (plan §6 reward-hacking mitigation: "not stress metrics"). Smoothed +
# integer-rounded so the cap can't thrash cycle-to-cycle (plan A4: no thrash).
# Refs: Baddeley & Hitch 1974 (WM); fatigue/load → WM-narrowing (ego-depletion lit).
_WM_PLASTICITY: bool = _os.getenv("ORRIN_WM_PLASTICITY", "1") == "1"
_WM_CAP_FLOOR: int = 18          # depleted (energy→0): WM narrows
_WM_CAP_CEIL: int = 32           # fresh (energy→1): WM widens
_WM_CAP_SPAN: float = float(_WM_CAP_CEIL - _WM_CAP_FLOOR)  # 14
_wm_cap_ema: float = float(MAX_WORKING_LOGS)   # smoothed effective cap (anti-thrash)
_wm_cap_last_read: float = 0.0
_wm_cap_cached_energy: float = 0.5
_WM_CAP_READ_TTL_S: float = 4.0
_wm_cap_logged: int = MAX_WORKING_LOGS


def _effective_working_cap() -> int:
    """Resource-adaptive WM cap. energy = 1 − resource_deficit drives capacity:
    fresh → up to _WM_CAP_CEIL, depleted → down to _WM_CAP_FLOOR, neutral (0.5) → base.
    EMA-smoothed + integer-rounded so it can't thrash cycle-to-cycle (plan A4)."""
    global _wm_cap_ema, _wm_cap_last_read, _wm_cap_cached_energy, _wm_cap_logged
    if not _WM_PLASTICITY:
        return MAX_WORKING_LOGS
    now = _time.monotonic()
    if now - _wm_cap_last_read >= _WM_CAP_READ_TTL_S:
        _wm_cap_last_read = now
        try:
            _a = load_json(AFFECT_STATE_FILE, default_type=dict) or {}
            rd = float(_a.get("resource_deficit", 0.5) or 0.5)
            _wm_cap_cached_energy = max(0.0, min(1.0, 1.0 - rd))
        except Exception:
            pass  # keep last good energy reading
    # Target centred on base: energy 0.5 → base, 1.0 → ceil, 0.0 → floor.
    target = MAX_WORKING_LOGS + _WM_CAP_SPAN * (_wm_cap_cached_energy - 0.5)
    target = max(float(_WM_CAP_FLOOR), min(float(_WM_CAP_CEIL), target))
    _wm_cap_ema += 0.12 * (target - _wm_cap_ema)   # slow belief update (anti-thrash)
    cap = int(round(_wm_cap_ema))
    if cap != _wm_cap_logged:
        try:
            log_private(
                f"[working_memory] WM cap → {cap} (energy={_wm_cap_cached_energy:.2f}, "
                f"base {MAX_WORKING_LOGS}); fatigue narrows, freshness widens."
            )
        except Exception:
            pass
        _wm_cap_logged = cap
    return cap

_last_digest_time: float = 0.0
_DIGEST_RATE_LIMIT_S: float = 60.0


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

import re as _re
from utils.failure_counter import record_failure
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
            except Exception:
                pass
        return False

    idx_a, idx_b, mem_a, mem_b = best_pair
    # Truncate content to prevent chunk-of-chunk content explosion.
    # A chunk's label only needs to be a brief summary, not the full history.
    _MAX_CONTENT_LABEL = 120
    # Strip any existing [Chunk: …] wrapper first so the label stays exactly one
    # level deep — without this, re-chunking a chunk nests `[Chunk: [Chunk: …`.
    # Clean (boundary) truncation: a mid-word cut here is re-ingestible garbage.
    from utils.text_sanity import truncate_clean as _tc
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

def _emotion_name(e: Any) -> str:
    if isinstance(e, dict):
        return str(e.get("emotion", "neutral")).lower()
    return str(e or "neutral").lower()

def _safe_embedding(text: str) -> list:
    try:
        emb = get_embedding(text)
        if isinstance(emb, np.ndarray):
            return emb.tolist()
        if isinstance(emb, list) and emb and isinstance(emb[0], np.ndarray):
            return emb[0].tolist()
        return emb or []
    except Exception as exc:
        log_error(f"update_working_memory: embedding failed: {exc}")
        return []

def update_working_memory(
    new: Any,
    emotion: Optional[str] = None,
    event_type: str = "thought",
    agent: str = "orrin",
    importance: int = 1,
    priority: int = 1,
    referenced: bool = False,
    pin: bool = False,
    related_memory_ids: Optional[List[str]] = None,
) -> None:
    """
    Add a new entry to working memory and manage pruning.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Build or copy the entry
    if isinstance(new, dict):
        entry: dict = new.copy()
        entry.setdefault("id", str(uuid.uuid4()))
        entry.setdefault("timestamp", now)
        entry.setdefault("content", "")
        entry.setdefault("emotion", emotion or _emotion_name(detect_affect_keyword(entry.get("content", ""))))
        entry.setdefault("event_type", event_type)
        entry.setdefault("agent", agent)
        entry.setdefault("importance", importance)
        entry.setdefault("priority", priority)
        entry.setdefault("referenced", int(referenced))
        entry.setdefault("recall_count", 0)
        entry.setdefault("pin", pin)
        entry.setdefault("decay", 1.0)
        entry.setdefault("related_memory_ids", related_memory_ids or [])
        # Embeddings are stripped before disk save and never read back from WM —
        # they balloon working_memory.json from KB to MB. Skip computation entirely.
        entry["embedding"] = []
    elif isinstance(new, str):
        content = new.strip()
        entry = {
            "id": str(uuid.uuid4()),
            "content": content,
            "emotion": emotion or _emotion_name(detect_affect_keyword(content)),
            "timestamp": now,
            "event_type": event_type,
            "agent": agent,
            "importance": importance,
            "priority": priority,
            "referenced": int(referenced),
            "recall_count": 0,
            "pin": pin,
            "decay": 1.0,
            "related_memory_ids": related_memory_ids or [],
            "embedding": [],  # not computed — stripped before save anyway
        }
    else:
        # Unsupported type, nothing to do
        return

    # Machine-structured content (a cognition return-dict, a telemetry line) is never a
    # thought: tag it so the expression membrane won't voice it and LM promotion skips
    # it. This is the upstream source-fix; speak.py keeps a membrane-side backstop.
    if not entry.get("internal_telemetry") and _looks_machine_content(str(entry.get("content") or "")):
        entry["internal_telemetry"] = True

    # The whole load -> dedup/chunk/trim -> save cycle happens under one lock
    # (modify_json) so a concurrent update_working_memory call can't interleave
    # between our read and our save (lost-update race).
    _to_promote: list = []
    try:
        with modify_json(WORKING_MEMORY_FILE, default_type=list) as memories:
            if not isinstance(memories, list):
                raise AbortModify("corrupt")

            # Update decay and deduplicate.
            # If an existing non-pin entry has identical content: boost it and skip the
            # append — adding a duplicate AND boosting the original was the old (broken)
            # behaviour.  For pins, the replace-semantics block below handles dedup.
            _duplicate_found = False
            for m in memories:
                if not isinstance(m, dict):
                    continue
                if not m.get("pin"):
                    m["decay"] = max(0.0, (m.get("decay", 1.0) or 1.0) - 0.02)
                if m.get("content") == entry.get("content"):
                    m["referenced"] = m.get("referenced", 0) + max(1, int(entry.get("referenced") or 0))
                    m["decay"] = min(1.0, (m.get("decay", 1.0) or 1.0) + 0.1)
                    m["timestamp"] = entry.get("timestamp", m.get("timestamp"))  # freshen timestamp
                    if not entry.get("pin"):
                        _duplicate_found = True  # non-pin duplicate → boost only, no append

            # Pins use replace semantics: drop the old pin, append the refreshed one.
            if entry.get("pin"):
                memories[:] = [m for m in memories if not (m.get("pin") and m.get("content") == entry.get("content"))]

            if not _duplicate_found:
                memories.append(entry)

            # Sort by pin, then priority/importance/decay, then timestamp (newest last)
            memories.sort(
                key=lambda m: (
                    m.get("pin", False),
                    m.get("priority", 1),
                    m.get("importance", 1),
                    m.get("decay", 1.0),
                    m.get("timestamp", ""),
                ),
                reverse=True,
            )

            # Handle overflow: hard-cap pins at half the limit, then trim non-pins.
            # Cognitive interference: when WM is at capacity, memories near the trim boundary
            # decay faster — they've been partially displaced by newer content.
            # `cap` flexes with resource state (plasticity): narrower when fatigued, wider
            # when fresh. Computed once per update so the whole overflow pass is consistent.
            cap = _effective_working_cap()

            # Chunking: when WM is full, try to merge the two most similar non-pin items
            # into a single chunk to make room — this mirrors how humans compress
            # related items in working memory rather than always dropping the oldest.
            while len(memories) > cap:
                if not _chunk_two_most_similar(memories):
                    break  # nothing similar enough or not enough non-pins; fall through to trim
                # Re-sort after chunk so the chunk lands in correct priority position
                memories.sort(
                    key=lambda m: (
                        m.get("pin", False),
                        m.get("priority", 1),
                        m.get("importance", 1),
                        m.get("decay", 1.0),
                        m.get("timestamp", ""),
                    ),
                    reverse=True,
                )

            if len(memories) > cap:
                pins = [m for m in memories if m.get("pin")]
                non_pins = [m for m in memories if not m.get("pin")]

                _pin_cap = cap // 2
                if len(pins) > _pin_cap:
                    log_private(f"[working_memory] Pin cap hit ({len(pins)} > {_pin_cap}); demoting lowest-priority pins.")
                    excess_pins = pins[_pin_cap:]
                    for _m in excess_pins:
                        _m["pin"] = False   # demote — keeps them eligible for promotion, not silently lost
                    non_pins = excess_pins + non_pins
                    pins = pins[:_pin_cap]

                capacity_for_non_pins = max(0, cap - len(pins))
                _to_promote = non_pins[capacity_for_non_pins:]
                kept_non_pins = non_pins[:capacity_for_non_pins]

                # Interference: the 5 memories nearest the trim boundary pay an interference
                # penalty — they were crowded out by newer content and lose fidelity faster.
                _INTERFERENCE_ZONE = 5
                for _m in kept_non_pins[-_INTERFERENCE_ZONE:]:
                    _m["decay"] = max(0.0, (float(_m.get("decay") or 1.0)) - 0.12)

                memories[:] = pins + kept_non_pins

            # Sort chronologically and save working_memory BEFORE promoting to long memory
            # so a crash after promotion doesn't create long-memory duplicates
            memories.sort(key=lambda m: m.get("timestamp", ""))

            # Strip heavy fields before saving to disk:
            #   - embedding: large float vectors (768-1536 dims) that balloon the file to
            #     30+ MB and trigger REAPER kills via slow load/save on every cycle.
            #   - items (in chunks): the sub-item list can grow to 100+ entries; WM only
            #     needs the chunk's `content` summary string to function.
            # Both are recomputed/irrelevant at next load — no information is lost.
            _STRIP_KEYS = frozenset({"embedding", "items"})
            _MAX_DISK_CONTENT = 500  # chars — WM content is summaries, not full text
            _to_disk = []
            for _m in memories:
                if isinstance(_m, dict):
                    _slim = {k: v for k, v in _m.items() if k not in _STRIP_KEYS}
                    # Self-heal legacy nested chunk labels loaded from disk: collapse
                    # `[Chunk: [Chunk: …` down to a single wrapper before truncating.
                    _c = _slim.get("content")
                    if isinstance(_c, str) and "[chunk:" in _c.lower():
                        inner = _strip_chunk_label(_c)
                        if inner != _c:
                            _c = f"[Chunk: {inner}]" if _m.get("chunk") else inner
                            _slim["content"] = _c
                    # Truncate content in case a chunk built a massive label string.
                    # Sentence/whitespace boundary + clean ellipsis — byte-cap cuts
                    # (`"...may need atte]"`) were re-ingested as content (audit §8).
                    if isinstance(_slim.get("content"), str) and len(_slim["content"]) > _MAX_DISK_CONTENT:
                        from utils.text_sanity import truncate_clean as _tc
                        _slim["content"] = _tc(_slim["content"], _MAX_DISK_CONTENT)
                    _to_disk.append(_slim)
                else:
                    _to_disk.append(_m)
            memories[:] = _to_disk
    except AbortModify:
        # Non-list store (corrupt): rebuild with just this entry.
        log_error("update_working_memory: working memory store was not a list; rebuilding.")
        save_json(WORKING_MEMORY_FILE, [entry])

    # Emotional consolidation: significant events (importance >= 4) leave a
    # residual emotional tint that plays out over subsequent cycles.
    try:
        if int(entry.get("importance") or 0) >= 4:
            from affect.consolidation import maybe_trigger_from_event
            maybe_trigger_from_event(entry)
    except Exception as _e:
        record_failure("working_memory.update_working_memory", _e)

    if _to_promote:
        # Salience gate: only promote entries that are actually worth keeping.
        # Routine low-importance, never-referenced thoughts evaporate here —
        # long-term memory should hold signal, not noise.
        def _is_salient(m: dict) -> bool:
            if m.get("pin"):
                return True
            if int(m.get("importance") or 1) >= 3:
                return True
            if int(m.get("referenced") or 0) > 0:
                return True
            if int(m.get("recall_count") or 0) > 0:
                return True
            if m.get("event_type") in ("goal_achieved", "error", "emergency", "key_decision", "relationship"):
                return True
            return False

        salient = [m for m in _to_promote if _is_salient(m)]
        non_salient = [m for m in _to_promote if not _is_salient(m)]

        if salient:
            summarize_and_promote_working_memory(salient)
            log_private(f"[working_memory] Promoted {len(salient)} salient entries to long-term memory.")

        # Compact non-salient entries into a single summary line rather than silently dropping.
        # This preserves the arc of experience even for routine thoughts.
        # Rate-limited: at most one digest per minute to prevent overflow flooding long memory.
        if non_salient:
            global _last_digest_time
            _now = _time.monotonic()
            if _now - _last_digest_time >= _DIGEST_RATE_LIMIT_S:
                _last_digest_time = _now
                try:
                    from cog_memory.long_memory import update_long_memory as _ulm
                    _topics = list(dict.fromkeys(
                        str(m.get("event_type") or m.get("content", "")[:30])
                        for m in non_salient
                        if m.get("event_type") or m.get("content")
                    ))[:6]
                    if _topics:
                        _ulm(
                            f"[wm_overflow] {len(non_salient)} routine thoughts: {', '.join(_topics)}",
                            emotion="neutral",
                            event_type="wm_overflow_digest",
                            importance=1,
                            priority=1,
                        )
                except Exception as _e:
                    record_failure("working_memory.update_working_memory.2", _e)
            log_private(f"[working_memory] Compacted {len(non_salient)} routine entries into long-memory digest.")


# ── Emotionally-weighted retrieval ────────────────────────────────────────────
# Baddeley & Hitch (1974) working memory has a central executive that gates
# what is active. The threat_detector biases this gate toward emotionally congruent
# content — memories matching the current affective state get priority access
# (Bower 1981 mood-congruent memory; Kensinger & Schacter 2008 emotional memory).
#
# This function is the retrieval-time implementation of that bias: given the
# current dominant emotion, rank WM entries by combined salience score so that
# emotionally relevant content surfaces first for rumination seeding, appraisal,
# and attention filtering.

_EMOTION_VALENCE: dict = {
    "social_penalty": -1, "impasse_signal": -1, "threat_level": -1, "negative_valence": -1,
    "risk_estimate": -1, "conflict_signal": -1, "social_deficit": -1, "uncertainty": -1,
    "positive_valence": +1, "expected_gain": +1, "exploration_drive": +1, "confidence": +1,
    "motivation": +1, "wonder": +1, "gratitude": +1,
}

def _emotional_salience(entry: dict, dominant_emotion: str, dominant_intensity: float) -> float:
    """
    Score an entry by how salient it is given the current emotional state.
    Higher = more likely to surface in retrieval.
    """
    score = 0.0

    # Base: importance × decay (already in storage sort, kept for continuity)
    score += float(entry.get("importance", 1)) * float(entry.get("decay", 1.0))

    # Emotion congruence: entries matching the current dominant emotion get a boost
    # (threat_detector → hippocampus biasing, Kensinger & Schacter 2008)
    entry_emo = str(entry.get("emotion") or "")
    if entry_emo == dominant_emotion:
        score += dominant_intensity * 3.0

    # Valence congruence: negative dominant state → negative-valenced entries surface more
    dom_val   = _EMOTION_VALENCE.get(dominant_emotion, 0)
    entry_val = _EMOTION_VALENCE.get(entry_emo, 0)
    if dom_val != 0 and dom_val == entry_val:
        score += dominant_intensity * 1.5

    # Pinned entries always surface
    if entry.get("pin"):
        score += 100.0

    # Referenced/recalled entries are more retrievable (memory strengthening)
    score += float(entry.get("recall_count", 0)) * 0.5
    score += float(entry.get("referenced", 0)) * 0.3

    return score


def get_emotionally_salient_wm(
    dominant_emotion: str = "",
    dominant_intensity: float = 0.5,
    n: int = 7,
    activation_level: float = 0.5,
) -> list:
    """
    Return the top-n working memory entries ranked by emotional salience.
    Used by rumination seeding, appraisal, and attention filtering so that
    emotionally congruent content gets priority access — matching the threat_detector's
    role in gating working memory retrieval (Bower 1981; Kensinger & Schacter 2008).

    `activation_level` approximates gain_signal (NE) level (Sara 2009). High NE sharpens
    signal-to-noise: high-salience entries are amplified, low-salience entries are
    relatively suppressed — narrowing attentional focus under alert states. Low NE
    (drowsy) flattens the gradient, making retrieval more diffuse.
    """
    memories: list = load_json(WORKING_MEMORY_FILE, default_type=list)
    if not isinstance(memories, list):
        return []

    def _ne_salience(m: dict) -> float:
        base = _emotional_salience(m, dominant_emotion, dominant_intensity)
        # NE gain: high activation_level steepens the salience gradient so the most
        # charged items dominate. Entries below the noise floor get suppressed.
        if base > 2.0:
            return base * (1.0 + activation_level * 0.5)   # amplify high-salience
        return base * (1.0 - activation_level * 0.2)        # suppress low-salience

    scored = sorted(
        [m for m in memories if isinstance(m, dict)],
        key=_ne_salience,
        reverse=True,
    )
    return scored[:n]