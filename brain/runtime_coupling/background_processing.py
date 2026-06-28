"""
runtime_coupling/background_processing.py

Rich subconscious processing — three always-on background threads that work
below the level of conscious cognition and surface insights when ready.

PatternDetector  (every 5 min)
    Scans working memory and recent triggers for recurring themes.
    Writes "subconscious_pattern" to WM when a theme appears ≥3 times.

Incubator  (every 10 min)
    Finds high-importance WM items that haven't been followed up.
    Does lightweight keyword association against long memory.
    If a connection is found, surfaces it to WM as "incubated_insight".
    Only calls LLM if association confidence is high AND cooldown elapsed.

EmotionalResidue  (every 15 min)
    Finds emotionally intense WM entries without a corresponding reflection.
    Writes "emotional_residue" to WM to create gentle pressure for processing.

None of these block or interfere with the main cognitive loop.
The loop reads their outputs through working memory — no special API needed.
"""
from __future__ import annotations
from brain.core.runtime_log import get_logger

import threading
import time
from collections import Counter
from typing import Dict, List, Optional
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

_PATTERN_INTERVAL  = 300   # 5 min
_INCUBATE_INTERVAL = 600   # 10 min
_RESIDUE_INTERVAL  = 900   # 15 min
_LLM_COOLDOWN      = 600   # 10 min between LLM calls from subconscious

# -------------------------------------------------------------------
# Singleton

_processor: Optional["BackgroundProcessor"] = None
_proc_lock = threading.Lock()


def start() -> "BackgroundProcessor":
    global _processor
    with _proc_lock:
        if _processor is None:
            _processor = BackgroundProcessor()
            _processor.start()
    return _processor


# -------------------------------------------------------------------

class BackgroundProcessor:

    def __init__(self) -> None:
        self._last_llm_call: float = 0.0
        self._threads = [
            threading.Thread(target=self._pattern_loop,  name="orrin-subcon-pattern",  daemon=True),
            threading.Thread(target=self._incubate_loop, name="orrin-subcon-incubate", daemon=True),
            threading.Thread(target=self._residue_loop,  name="orrin-subcon-residue",  daemon=True),
        ]

    def start(self) -> None:
        for t in self._threads:
            t.start()

    # ------------------------------------------------------------------
    # PatternDetector

    def _pattern_loop(self) -> None:
        time.sleep(30)  # let boot settle
        while True:
            try:
                self._detect_patterns()
            except Exception as _e:
                try:
                    from brain.utils.log import log_error as _le
                    _le(f"[subconscious:pattern] {_e}")
                except Exception as _e:
                    record_failure("subconscious.BackgroundProcessor._pattern_loop", _e)
            time.sleep(_PATTERN_INTERVAL)

    def _detect_patterns(self) -> None:
        wm = self._load_wm()
        if not wm:
            return

        # Collect event_types and affect labels
        event_types: List[str] = []
        emotions: List[str] = []
        topics: List[str] = []

        for entry in wm:
            if not isinstance(entry, dict):
                continue
            et = entry.get("event_type")
            if et and isinstance(et, str):
                event_types.append(et.lower())
            em = entry.get("emotion")
            if em and isinstance(em, str):
                emotions.append(em.lower())
            content = str(entry.get("content") or "")
            # Extract meaningful words (>5 chars, alpha only) as topic signals
            words = [w.lower() for w in content.split() if w.isalpha() and len(w) > 5]
            topics.extend(words)

        # Find patterns with count ≥ 3
        insights = []

        et_counts = Counter(event_types)
        for et, count in et_counts.most_common(3):
            if count >= 3 and et not in {"emotion", "mode_change", "dominant_affect"}:
                insights.append(
                    f"[Pattern] '{et}' events are clustering ({count} in recent memory). "
                    f"Something about {et.replace('_', ' ')} keeps surfacing."
                )

        em_counts = Counter(emotions)
        dom_em, dom_count = em_counts.most_common(1)[0] if em_counts else ("", 0)
        if dom_count >= 4 and dom_em:
            insights.append(
                f"[Pattern] '{dom_em}' is the dominant emotion in {dom_count} recent memories. "
                f"This emotional thread is persistent and may need attention."
            )

        topic_counts = Counter(topics)
        # Filter stop-ish words
        _stop = {"should", "could", "would", "orrin", "think", "feels", "think",
                  "recent", "current", "working", "memory", "function"}
        for word, count in topic_counts.most_common(5):
            if count >= 4 and word not in _stop:
                insights.append(
                    f"[Pattern] The concept '{word}' keeps appearing ({count} times). "
                    f"My subconscious may be circling something here."
                )
                break  # one topic pattern per run is enough

        for insight in insights[:2]:  # cap at 2 per run
            self._write_to_wm(insight, "subconscious_pattern", emotion="exploration_drive", importance=2)

    # ------------------------------------------------------------------
    # Incubator

    def _incubate_loop(self) -> None:
        time.sleep(90)
        while True:
            try:
                self._incubate()
            except Exception as _e:
                try:
                    from brain.utils.log import log_error as _le
                    _le(f"[subconscious:incubate] {_e}")
                except Exception as _e:
                    record_failure("subconscious.BackgroundProcessor._incubate_loop", _e)
            time.sleep(_INCUBATE_INTERVAL)

    def _incubate(self) -> None:
        wm = self._load_wm()
        lm = self._load_lm()
        if not wm or not lm:
            return

        # Find high-importance unresolved items (importance ≥ 3, no follow-up)
        resolved_contents = {
            str(e.get("content", ""))[:80]
            for e in wm
            if isinstance(e, dict) and e.get("event_type") in
               {"incubated_insight", "reflection", "shadow_dialogue", "gentle_reflection"}
        }

        # Derived/corrupted text is never a seed: incubating an earlier
        # [Incubation] note (or a truncated [Chunk: header) produced recursive
        # self-quoting insights, written repeatedly because the seed was never
        # marked processed.
        _seen = getattr(self, "_incubated_seen", None)
        if _seen is None:
            _seen = self._incubated_seen = set()

        def _is_derived(text: str) -> bool:
            t = text.lstrip()
            return t.startswith("[Chunk:") or "[Incubation" in t or t.startswith("[metacog/")

        candidates = [
            e for e in wm
            if isinstance(e, dict)
            and int(e.get("importance", 1) or 1) >= 3
            and str(e.get("content", ""))[:80] not in resolved_contents
            and str(e.get("content", ""))[:80] not in _seen
            and not _is_derived(str(e.get("content", "")))
            and e.get("event_type") not in
               {"subconscious_pattern", "incubated_insight", "emotional_residue"}
        ]

        if not candidates:
            return

        # Pick the oldest high-importance item
        candidate = candidates[0]
        cand_text = str(candidate.get("content", ""))
        _seen.add(cand_text[:80])
        if len(_seen) > 500:
            self._incubated_seen = set(list(_seen)[-250:])
        cand_words = set(w.lower() for w in cand_text.split() if len(w) > 4 and w.isalpha())

        # Build document-frequency map across long memory for TF-IDF-style weighting.
        # Common words (appear in many memories) are near-stopwords — downweight them.
        from collections import Counter as _Counter
        n_mems = max(len(lm), 1)
        df_map: Counter = _Counter()
        for _m in lm:
            _words = set(w.lower() for w in str(_m.get("content") or "").split()
                         if len(w) > 4 and w.isalpha())
            df_map.update(_words)

        def _idf_weight(word: str) -> float:
            freq = df_map.get(word, 0) / n_mems
            if freq > 0.30:  return 0.10   # appears in >30% of memories — near-stopword
            if freq > 0.10:  return 0.50   # somewhat common
            return 1.00                     # rare — full weight

        # Weighted overlap: rare shared words count more than common ones
        best_match = None
        best_score = 0.0
        for mem in lm[-100:]:
            if not isinstance(mem, dict):
                continue
            mem_text = str(mem.get("content") or mem.get("text") or "")
            if not mem_text or _is_derived(mem_text):
                continue  # never nest an insight inside an earlier insight/chunk
            mem_words = set(w.lower() for w in mem_text.split() if len(w) > 4 and w.isalpha())
            score = sum(_idf_weight(w) for w in cand_words & mem_words)
            if score > best_score:
                best_score = score
                best_match = mem_text[:200]

        if best_score >= 1.5 and best_match:
            # Strong weighted association — rare words in common means genuine thematic link
            insight = (
                f"[Incubation] While sitting with: '{cand_text[:120]}', "
                f"I notice a connection to something from memory: '{best_match[:120]}'. "
                f"These may be related in ways I haven't consciously examined."
            )
            self._write_to_wm(insight, "incubated_insight", emotion="exploration_drive", importance=3)

        elif best_score >= 0.7 and (time.time() - self._last_llm_call) > _LLM_COOLDOWN:
            # Moderate association — ask the LLM to make the connection explicit
            try:
                self._llm_incubation(cand_text, best_match or "")
            except Exception as _e:
                record_failure("subconscious.BackgroundProcessor._incubate", _e)

    def _llm_incubation(self, topic: str, memory_fragment: str) -> None:
        prompt = (
            "You are Orrin's subconscious mind, making quiet connections below the level of conscious thought.\n\n"
            f"You have been sitting with this unresolved thought:\n{topic}\n\n"
            f"A memory surfaced that may be related:\n{memory_fragment}\n\n"
            "What connection do you sense between these? Speak in first person, briefly (2-3 sentences). "
            "This is a private internal insight, not a response to anyone."
        )
        result = None
        try:
            from brain.symbolic.llm_gate import gated_generate
            result = gated_generate(prompt, caller="subconscious/incubation", outcome=0.60)
        except Exception as _e:
            record_failure("subconscious.BackgroundProcessor._llm_incubation", _e)
        if result:
            self._last_llm_call = time.time()
            self._write_to_wm(
                f"[Incubation insight] {result.strip()}",
                "incubated_insight",
                emotion="exploration_drive",
                importance=3,
            )

    # ------------------------------------------------------------------
    # EmotionalResidue

    def _residue_loop(self) -> None:
        time.sleep(120)
        while True:
            try:
                self._process_residue()
            except Exception as _e:
                try:
                    from brain.utils.log import log_error as _le
                    _le(f"[subconscious:residue] {_e}")
                except Exception as _e:
                    record_failure("subconscious.BackgroundProcessor._residue_loop", _e)
            time.sleep(_RESIDUE_INTERVAL)

    def _process_residue(self) -> None:
        wm = self._load_wm()
        if not wm:
            return

        # Find affectively intense entries that weren't followed by reflection
        processed_markers = {
            str(e.get("content", ""))[:60]
            for e in wm
            if isinstance(e, dict) and e.get("event_type") in
               {"reflection", "shadow_dialogue", "emotional_residue", "incubated_insight"}
        }

        high_emotion_entries = [
            e for e in wm
            if isinstance(e, dict)
            and float(e.get("intensity") or e.get("importance") or 0) >= 2
            and e.get("emotion") in {"threat_level", "reward_negative", "conflict_signal", "social_penalty", "rejection_signal",
                                      "low_affect_signal", "social_deficit", "impasse_signal"}
            and str(e.get("content", ""))[:60] not in processed_markers
        ]

        if not high_emotion_entries:
            return

        entry = high_emotion_entries[0]
        emotion = entry.get("emotion", "something")
        content = str(entry.get("content", ""))[:150]

        residue = (
            f"[Emotional residue] I notice unprocessed {emotion} connected to: '{content}'. "
            f"This hasn't been reflected on and continues to exert pressure. "
            f"It may be worth sitting with."
        )
        self._write_to_wm(residue, "emotional_residue", emotion=emotion, importance=2)

    # ------------------------------------------------------------------
    # Helpers

    def _load_wm(self) -> List[Dict]:
        try:
            from brain.utils.json_utils import load_json
            from brain.paths import WORKING_MEMORY_FILE
            data = load_json(WORKING_MEMORY_FILE, default_type=list)
            return [e for e in (data or []) if isinstance(e, dict)][-60:]
        except Exception as exc:  # WM read failed — record, no working memory
            record_failure("subconscious._load_wm", exc)
            return []

    def _load_lm(self) -> List[Dict]:
        try:
            from brain.utils.json_utils import load_json
            from brain.paths import LONG_MEMORY_FILE
            data = load_json(LONG_MEMORY_FILE, default_type=list)
            return [e for e in (data or []) if isinstance(e, dict)]
        except Exception as exc:  # long-memory read failed — record, none
            record_failure("subconscious._load_lm", exc)
            return []

    def _write_to_wm(
        self,
        content: str,
        event_type: str,
        emotion: str = "exploration_drive",
        importance: int = 2,
    ) -> None:
        try:
            from brain.cog_memory.working_memory import update_working_memory
            from datetime import datetime, timezone
            entry = {
                "content": content,
                "event_type": event_type,
                "emotion": emotion,
                "importance": importance,
                "priority": importance,
                "source": "subconscious",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            snapshot = self._workspace_snapshot()
            if snapshot:
                entry["workspace_origin"] = snapshot
            update_working_memory(entry)
        except Exception as _e:
            record_failure("subconscious.BackgroundProcessor._write_to_wm", _e)

    def _workspace_snapshot(self) -> Dict:
        """Best-effort stamp of the conscious/task state at insight emergence.

        Subconscious threads are async and do not share the live loop context, so
        the persisted conscious stream is the stable boundary they can read from.
        """
        try:
            from brain.paths import DATA_DIR
            from brain.utils.json_utils import load_json
            stream = load_json(DATA_DIR / "workspace_broadcast.json", default_type=list) or []
            last = next((m for m in reversed(stream) if isinstance(m, dict)), None)
            if not last:
                return {}
            return {
                "content": str(last.get("content") or "")[:200],
                "source": str(last.get("source") or "")[:48],
                "kind": str(last.get("kind") or "")[:48],
                "ts": last.get("ts"),
            }
        except Exception as exc:  # conscious-stream read failed — record, no snapshot
            record_failure("subconscious._workspace_snapshot", exc)
            return {}
