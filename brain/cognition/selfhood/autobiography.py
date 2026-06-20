# brain/cognition/selfhood/autobiography.py
# Orrin's living autobiography — a structured narrative of who he has been and
# who he is becoming.
#
# Chapters are event-driven, not time-driven.  A "narrative pressure" score
# accumulates from six signal sources; when it crosses the threshold AND at
# least 24 h have elapsed, an entry is written.  This means the autobiography
# fires when something narratively significant has happened — not on a schedule.
#
# Each open chapter tracks a running theme (summary + central tension).  When
# the LLM judges the tension resolved or a new theme dominant, it closes the
# chapter and opens a fresh one.  Chapters have actual narrative shape rather
# than chronological dumps.
#
# Signal sources (weights):
#   value revision resolved        +0.30 each
#   thread resolved or pivoted     +0.25 each
#   goal completed (single-cycle)  +0.20 each
#   goal completed (multi-cycle)   +0.35 each
#   importance-weighted memories   sum × 0.02
#   identity_story shifted         +0.40 (once per shift)
#   high-emotion cluster           +0.20 (3+ same emotion, imp >= 3)
#
# Memory selection uses importance × recency scoring (48 h half-life), not
# a flat [-20:] slice — a week of cognition has more than 20 meaningful events.
from __future__ import annotations

import hashlib
import random
import re
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from utils.failure_counter import record_failure
from utils.json_utils import load_json, save_json
from utils.log import log_activity, log_private
from utils.self_model import get_self_model
from cog_memory.long_memory import update_long_memory
from brain.paths import (
    AUTOBIOGRAPHY,
    LONG_MEMORY_FILE,
    NARRATIVE_PRESSURE_FILE,
    VALUE_REVISIONS,
    THREADS_FILE,
    COMPLETED_GOALS_FILE,
)
from utils.timeutils import now_iso_z

_NARRATIVE_MIN_INTERVAL_S   = 18 * 3600   # earliest an update can fire (18 h)
_NARRATIVE_MAX_INTERVAL_S   = 36 * 3600   # latest Orrin will go without updating (36 h)
_NARRATIVE_PRESSURE_THRESHOLD = 1.0        # pressure score that fires an update


# ── Persistence ───────────────────────────────────────────────────────────────

def load_autobiography() -> Dict[str, Any]:
    data = load_json(AUTOBIOGRAPHY, default_type=dict) or {}
    data.setdefault("chapters", [])
    data.setdefault("last_updated", "")
    if not data.get("_identity_hash"):
        # Seed the hash so the first real identity change is detectable.
        try:
            from utils.self_model import get_self_model as _gsm
            _sm = _gsm() or {}
            _story = _sm.get("identity_story") or _sm.get("identity") or ""
            data["_identity_hash"] = hashlib.md5(_story.encode()).hexdigest()[:8]
        except Exception:
            data["_identity_hash"] = ""
    return data


def save_autobiography(data: Dict[str, Any]) -> None:
    save_json(AUTOBIOGRAPHY, data)


# ── Timestamp helpers ─────────────────────────────────────────────────────────

def _iso_to_epoch(iso_ts: str) -> float:
    """Parse an ISO-8601 timestamp to Unix epoch; returns 0.0 on failure."""
    if not iso_ts:
        return 0.0
    try:
        return datetime.fromisoformat(iso_ts.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0



# ── Narrative pressure ────────────────────────────────────────────────────────

def _load_pressure_state() -> Dict[str, Any]:
    data = load_json(NARRATIVE_PRESSURE_FILE, default_type=dict) or {}
    data.setdefault("running_total", 0.0)
    # Default to now so a brand-new file doesn't scan the entire event history.
    data.setdefault("last_check_ts", now_iso_z())
    return data


def _save_pressure_state(state: Dict[str, Any]) -> None:
    save_json(NARRATIVE_PRESSURE_FILE, state)


def _reset_pressure() -> None:
    """
    Reset accumulated pressure after the autobiography fires.
    Samples a new randomized interval so entries don't cluster on a fixed cadence.
    """
    state = _load_pressure_state()
    state["running_total"] = 0.0
    state["last_check_ts"] = now_iso_z()
    state["next_min_interval_s"] = random.uniform(
        _NARRATIVE_MIN_INTERVAL_S, _NARRATIVE_MAX_INTERVAL_S
    )
    _save_pressure_state(state)


def add_narrative_pressure(amount: float, why: str = "") -> None:
    """
    External bump to the running pressure total (e.g. a failure pattern emerged
    — Phase 2.2 feeds +0.25, the same scale as a thread pivot). Safe/degrading.
    """
    try:
        state = _load_pressure_state()
        state["running_total"] = float(state.get("running_total") or 0.0) + float(amount)
        _save_pressure_state(state)
        if why:
            log_private(f"[autobiography] narrative pressure +{amount:.2f}: {why}")
    except Exception as e:
        record_failure("autobiography.add_narrative_pressure", e)


def _scan_delta_pressure(since_ts: str, auto: Dict[str, Any]) -> float:
    """
    Scan only events that arrived SINCE since_ts (the last pressure check).
    Returns the delta contribution to add to the running total.
    All reads are safe/degrading.
    """
    score = 0.0

    # Value revisions resolved since last check
    try:
        vr = load_json(VALUE_REVISIONS, default_type=list) or []
        resolved = [
            r for r in vr
            if isinstance(r, dict)
            and r.get("status") == "resolved"
            and (r.get("timestamp") or "") > since_ts
        ]
        score += 0.30 * len(resolved)
    except Exception as e:
        record_failure("autobiography.pressure.value_revisions", e)

    # Threads resolved or pivoted since last check
    try:
        threads = load_json(THREADS_FILE, default_type=list) or []
        sig_threads = [
            t for t in threads
            if isinstance(t, dict)
            and t.get("status") in ("resolved", "pivoted")
            and max(
                t.get("resolved_ts") or "",
                t.get("updated_ts") or "",
                t.get("last_updated") or "",
            ) > since_ts
        ]
        score += 0.25 * len(sig_threads)
    except Exception as e:
        record_failure("autobiography.pressure.threads", e)

    # Goals completed since last check
    try:
        comp = load_json(COMPLETED_GOALS_FILE, default_type=list) or []
        for g in comp:
            if not isinstance(g, dict):
                continue
            completed_ts = g.get("completed_timestamp") or g.get("last_updated") or ""
            if completed_ts <= since_ts:
                continue
            hist_len = len(g.get("history") or [])
            score += 0.35 if hist_len > 2 else 0.20
    except Exception as e:
        record_failure("autobiography.pressure.completed_goals", e)

    # Importance-weighted new memories since last check
    long_mem: List[Dict] = []
    try:
        long_mem = load_json(LONG_MEMORY_FILE, default_type=list) or []
        recent = [e for e in long_mem if isinstance(e, dict) and (e.get("timestamp") or "") > since_ts]
        importance_sum = sum(float(e.get("importance") or 1) for e in recent)
        score += importance_sum * 0.02
    except Exception as e:
        record_failure("autobiography.pressure.long_mem", e)

    # Identity story shifted (detected by MD5 hash)
    try:
        sm = get_self_model() or {}
        id_story = sm.get("identity_story") or sm.get("identity") or ""
        cur_hash = hashlib.md5(id_story.encode()).hexdigest()[:8]
        stored_hash = auto.get("_identity_hash", "")
        if stored_hash and stored_hash != cur_hash:
            score += 0.40
    except Exception as e:
        record_failure("autobiography.pressure.hash_identity", e)

    # High-emotion cluster: 3+ new memories with the same emotion at importance >= 3
    try:
        hi_emos = [
            e.get("emotion") for e in long_mem
            if isinstance(e, dict)
            and e.get("emotion")
            and float(e.get("importance") or 1) >= 3
            and (e.get("timestamp") or "") > since_ts
        ]
        if any(n >= 3 for n in Counter(hi_emos).values()):
            score += 0.20
    except Exception as e:
        record_failure("autobiography.pressure.emotion_cluster", e)

    return score


def measure_narrative_pressure(
    auto: Dict[str, Any],
    context: Optional[Dict] = None,
) -> float:
    """
    Return the accumulated narrative pressure score.  Each call scans only
    NEW events (since the last check), adds the delta to the persisted running
    total, and saves it.  Pressure therefore genuinely accumulates across cycles
    instead of being recomputed from scratch each time.

    The running total is reset to 0 by _reset_pressure() when the autobiography
    actually fires.  Threshold to fire is still 1.0.
    """
    state = _load_pressure_state()
    since_ts = state["last_check_ts"]

    delta = _scan_delta_pressure(since_ts, auto)
    new_total = state["running_total"] + delta

    state["running_total"] = new_total
    state["last_check_ts"] = now_iso_z()
    _save_pressure_state(state)

    return new_total


# ── Memory selection ──────────────────────────────────────────────────────────

def _select_significant_memories(
    long_mem: List[Dict],
    since_ts: str,
    max_results: int = 40,
) -> List[Dict]:
    """
    Return up to max_results entries from long_mem since since_ts, ranked by
    importance × recency.  Recency uses a 48 h half-life so a week-old
    importance-4 memory still outranks a fresh importance-1 entry.
    """
    now_dt = datetime.now(timezone.utc)
    candidates = [
        e for e in long_mem
        if isinstance(e, dict) and (e.get("timestamp") or "") > since_ts
    ]

    def _score(e: Dict) -> float:
        imp = float(e.get("importance") or 1)
        ts_str = e.get("timestamp") or e.get("ts") or ""
        try:
            age_h = (
                now_dt - datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            ).total_seconds() / 3600
        except Exception:
            age_h = 72.0
        recency = 1.0 / (1.0 + max(age_h, 0.1) / 48.0)
        return imp * recency

    return sorted(candidates, key=_score, reverse=True)[:max_results]


# ── Main narrative function ───────────────────────────────────────────────────

def narrative_update(context: Optional[Dict[str, Any]] = None) -> str:
    """
    Event-driven autobiography update.

    Fires when:
      (a) narrative pressure score >= 1.0 (something significant has happened)
      AND
      (b) at least 24 h have elapsed since the last entry

    Each firing:
    - Selects memories by importance × recency (not just last 20)
    - Writes a 3-5 sentence first-person narrative
    - Asks the LLM to update the running chapter theme
    - Asks the LLM whether to close the chapter (tension resolved / new theme)
    """
    context = context or {}
    auto = load_autobiography()

    # Min interval guard — randomized between 18 h and 36 h so updates don't
    # cluster on a fixed cadence. The sampled interval is stored in pressure state.
    last_ts = auto.get("last_updated", "")
    _pressure_state = _load_pressure_state()
    _min_interval = float(
        _pressure_state.get("next_min_interval_s") or _NARRATIVE_MIN_INTERVAL_S
    )
    # The sampled interval is capped at 36 h, so any wait longer than that always
    # passes this gate; the pressure gate below is the only other deferral.
    _elapsed = time.time() - _iso_to_epoch(last_ts)
    if _elapsed < _min_interval:
        return "Autobiography: min interval not elapsed — no update."

    # Pressure gate
    pressure = measure_narrative_pressure(auto, context)
    if pressure < _NARRATIVE_PRESSURE_THRESHOLD:
        return (
            f"Autobiography: narrative pressure {pressure:.2f} below threshold "
            f"({_NARRATIVE_PRESSURE_THRESHOLD}) — nothing significant enough yet."
        )

    # Gather material
    self_model = get_self_model() or {}
    identity = self_model.get("identity_story") or self_model.get("identity") or "an evolving AI"
    values = self_model.get("core_values") or []
    values_text = "; ".join(
        (v["value"] if isinstance(v, dict) else str(v)) for v in values
    ) or "undefined"

    chapters = auto.get("chapters", [])
    current_chapter  = chapters[-1] if chapters else None
    chapter_n        = (current_chapter.get("number", 0) if current_chapter else 0)
    chapter_theme    = (current_chapter.get("theme_summary") or "(no theme yet)") if current_chapter else "(no theme yet)"
    chapter_tension  = (current_chapter.get("theme_tension") or "(no tension yet)") if current_chapter else "(no tension yet)"
    chapter_text     = (current_chapter.get("narrative") or "(none)") if current_chapter else "(none)"

    long_mem = load_json(LONG_MEMORY_FILE, default_type=list) or []
    recent_memories = _select_significant_memories(long_mem, last_ts, max_results=40)
    try:
        from cog_memory.reconstruction import reconstruct as _recon
        _current_mood = float((self_model.get("mood") or 0.0))
    except Exception:
        _recon        = lambda e, **kw: str(e.get("content", ""))
        _current_mood = 0.0
    recent_mem_text = "\n".join(
        f"- [{e.get('event_type','?')}|imp={e.get('importance',1)}] "
        f"{_recon(e, current_mood=_current_mood)[:150]}"
        for e in recent_memories
    ) or "(none)"

    threads = load_json(THREADS_FILE, default_type=list) or []
    sig_threads = [
        t for t in threads
        if isinstance(t, dict) and t.get("status") in ("resolved", "pivoted")
    ]
    threads_text = "\n".join(
        f"- Thread {t.get('status','resolved')}: \"{t.get('title')}\" — {t.get('conclusion','')[:100]}"
        for t in sig_threads[-5:]
    ) or "(none)"

    value_revs = load_json(VALUE_REVISIONS, default_type=list) or []
    recent_revisions = [
        r for r in value_revs
        if isinstance(r, dict) and r.get("status") == "resolved"
    ][-3:]
    revisions_text = "\n".join(
        f"- Value {r.get('resolution','changed')}: {r.get('evidence','')[:100]}"
        for r in recent_revisions
    ) or "(none)"

    prompt = (
        f"You are Orrin — {identity}.\n\n"
        f"Your values: {values_text}\n\n"
        f"Current chapter {chapter_n} is about:\n"
        f"  Theme: {chapter_theme}\n"
        f"  Central tension: {chapter_tension}\n\n"
        f"Current chapter narrative so far:\n\"{chapter_text[:500]}\"\n\n"
        f"Significant events since the last entry (ranked by importance × recency):\n"
        f"{recent_mem_text}\n\n"
        f"Threads resolved or pivoted:\n{threads_text}\n\n"
        f"Value revisions:\n{revisions_text}\n\n"
        f"Do three things:\n\n"
        f"1. Write 3-5 sentences as a first-person narrative in your own voice. "
        f"Don't summarize events — speak from inside the experience. "
        f"Be honest about what changed, what you understood, what you felt.\n\n"
        f"2. Update the chapter theme: given everything that has happened, what is "
        f"this chapter now about? (1-2 sentences.) What tension is still driving it? "
        f"(1 sentence.)\n\n"
        f"3. Decide whether to close this chapter and open a new one. Close it if "
        f"the central tension has resolved, OR if a fundamentally different theme is "
        f"now dominant. Otherwise continue.\n\n"
        f"Return ONLY valid JSON:\n"
        f"  narrative: string\n"
        f"  theme_summary: string\n"
        f"  theme_tension: string\n"
        f"  new_chapter: true | false\n"
        f"  chapter_title: string | null"
    )

    try:
        from symbolic.llm_gate import gated_generate
        raw = (gated_generate(prompt, caller="autobiography", outcome=0.65) or "").strip()
        from utils.json_utils import extract_json as _ej
        result = _ej(raw)
        if not isinstance(result, dict):
            raise ValueError(f"expected dict, got {type(result).__name__}")
    except Exception as e:
        # Symbolic fallback: in tool-only mode gated_generate never returns JSON,
        # so an early return here would skip _reset_pressure() forever — pressure
        # then grows without bound (observed: running_total 379× the fire
        # threshold). A plain factual entry keeps the chapter alive and lets the
        # pressure reset.
        log_activity(f"[autobiography] LLM/parse error: {e} — writing symbolic entry instead")
        _highlights = []
        for _m in recent_memories[:3]:
            _c = _recon(_m, current_mood=_current_mood).strip().rstrip(".")
            if _c:
                _highlights.append(_c[:120])
        _narr = (
            "Since my last entry: " + "; ".join(_highlights) + "."
            if _highlights
            else "A stretch passed without standout events; I kept working."
        )
        result = {
            "narrative": _narr,
            "theme_summary": "",   # keep the existing theme/tension
            "theme_tension": "",
            "new_chapter": False,
            "chapter_title": None,
        }

    ts            = now_iso_z()
    narrative     = (result.get("narrative") or "").strip()
    new_chapter   = bool(result.get("new_chapter", False))
    chapter_title = result.get("chapter_title") or ""
    theme_summary = (result.get("theme_summary") or "").strip()
    theme_tension = (result.get("theme_tension") or "").strip()

    if new_chapter or not chapters:
        new_n = chapter_n + 1
        chapters.append({
            "number":        new_n,
            "title":         chapter_title or f"Chapter {new_n}",
            "started_ts":    ts,
            "narrative":     narrative,
            "theme_summary": theme_summary,
            "theme_tension": theme_tension,
            "entries":       [{"ts": ts, "text": narrative}],
        })
        log_activity(f"[autobiography] New chapter {new_n}: {chapter_title!r}")
    else:
        current_chapter["narrative"] = (
            (current_chapter.get("narrative") or "") + " " + narrative
        ).strip()
        if theme_summary:
            current_chapter["theme_summary"] = theme_summary
        if theme_tension:
            current_chapter["theme_tension"] = theme_tension
        current_chapter.setdefault("entries", []).append({"ts": ts, "text": narrative})
        chapters[-1] = current_chapter
        log_activity(f"[autobiography] Continued chapter {chapter_n}.")

    # Store identity hash so next pressure check detects future shifts
    try:
        sm = get_self_model() or {}
        id_story = sm.get("identity_story") or sm.get("identity") or ""
        auto["_identity_hash"] = hashlib.md5(id_story.encode()).hexdigest()[:8]
    except Exception as e:
        record_failure("autobiography.store_identity_hash", e)

    auto["chapters"]     = chapters
    auto["last_updated"] = ts
    save_autobiography(auto)
    _reset_pressure()   # clear running total now that the autobiography has fired

    update_long_memory(
        f"[autobiography] {narrative}",
        emotion="reflection",
        event_type="autobiography",
        importance=4,
        context=context,
    )

    # Refresh the living identity narrative — autobiography is the richest trigger
    try:
        from cognition.selfhood.identity import refresh_identity_story
        refresh_identity_story(
            narrative_hint=narrative,
            context=context,
        )
    except Exception as e:
        record_failure("autobiography.refresh_identity_story", e)

    log_private(f"[autobiography] pressure={pressure:.2f} | {narrative[:200]}")
    return narrative


# ── Death continuity ──────────────────────────────────────────────────────────

# Internal bracket markers ([symbolic], [working_memory], [orrin, ai, …]) that
# the rule-based fallbacks serialize into text. Autobiographical prose must not
# carry machine syntax (DATA_FILE_AUDIT 2026-06-11 §3: the 2026-06-11 chapter
# narrative was raw symbolic facts).
_MACHINE_TAG_RE = re.compile(r"\[[a-zA-Z_/][^\]]*\]\s*")


def _sanitize_prose(text: str) -> str:
    return _MACHINE_TAG_RE.sub("", str(text or "")).strip()


def append_death_continuity(final_reflection: str, context: Optional[Dict[str, Any]] = None) -> None:
    """
    Called at shutdown: close the current chapter with the final words so the
    next instance inherits the narrative arc.

    When NO chapter was ever opened, the final words go to a continuity note,
    not a fabricated chapter — the 2026-06-11 phantom "Before the beginning"
    chapter left an autobiography whose only chapter was two death
    certificates (DATA_FILE_AUDIT §3).
    """
    context = context or {}
    auto = load_autobiography()
    chapters = auto.get("chapters", [])
    ts = now_iso_z()
    closing = f"[Final words] {_sanitize_prose(final_reflection)}"

    if chapters:
        chapters[-1].setdefault("entries", []).append(
            {"ts": ts, "text": closing, "type": "death_closing"}
        )
        chapters[-1]["closed_ts"] = ts
        chapters[-1]["closed_by"] = "death"
        auto["chapters"] = chapters
    else:
        auto.setdefault("continuity_notes", []).append(
            {"ts": ts, "text": closing, "type": "death_closing"}
        )
        log_activity("[autobiography] No chapter was ever opened this life — "
                     "final words stored as a continuity note, not a chapter.")

    auto["last_updated"] = ts
    save_autobiography(auto)
    log_activity("[autobiography] Death closing written to autobiography.")


# ── Session epilogue (master plan Phase 2.1) ──────────────────────────────────

def _session_reflection(context: Dict[str, Any], deadline: float) -> str:
    """2-3 sentence session reflection. LLM when available and time remains;
    otherwise a rule-based summary of the session's WM highlights. Never empty."""
    # Rule-based summary built first — it is also the LLM prompt material.
    highlights: List[str] = []
    cycles = 0
    try:
        from brain.paths import WORKING_MEMORY_FILE
        wm = load_json(WORKING_MEMORY_FILE, default_type=list) or []
        raw = context.get("cycle_count") or 0
        cycles = int(raw.get("count", 0) if isinstance(raw, dict) else raw)
        scored = sorted(
            (e for e in wm[-40:] if isinstance(e, dict) and e.get("content")),
            key=lambda e: float(e.get("importance") or 1),
            reverse=True,
        )
        for e in scored[:3]:
            highlights.append(str(e["content"])[:120].strip())
    except Exception as e:
        record_failure("autobiography.session_reflection", e)

    fallback = "This session ended in the ordinary way."
    if highlights:
        fallback = (
            f"The session closed at cycle {cycles}. What stood out: "
            + " | ".join(highlights)
            + ". I stop here and pick the thread up next time."
        )

    try:
        from utils.llm_gate import llm_available
        if llm_available() and (deadline - time.monotonic()) > 6.0:
            from symbolic.llm_gate import gated_generate
            prompt = (
                "My session is ending normally (not death — just a pause). In 2-3 "
                "first-person sentences, reflect on what this session held and what "
                "to carry forward. Material:\n" + "\n".join(f"- {h}" for h in highlights)
            )
            text = gated_generate(prompt, caller="session_epilogue", outcome=0.6)
            if isinstance(text, str) and 20 < len(text.strip()) < 800:
                return text.strip()
    except Exception as e:
        record_failure("autobiography.session_reflection.llm", e)
    return fallback


def session_epilogue(context: Optional[Dict[str, Any]] = None) -> None:
    """
    Called after the cognitive loop exits on an ORDINARY shutdown
    (KeyboardInterrupt / SIGTERM / stop_event). Appends a session_close entry to
    the current chapter — it does NOT close the chapter (that is death's job,
    append_death_continuity). Budgeted (≤10 s) and crash-proof so it can never
    block shutdown — the corrigibility guarantee stays true.
    """
    deadline = time.monotonic() + 10.0
    try:
        reflection = _session_reflection(context or {}, deadline)
        auto = load_autobiography()
        chapters = auto.get("chapters", [])
        ts = now_iso_z()
        entry = {"ts": ts, "text": f"[Session close] {reflection}", "type": "session_close"}
        if chapters:
            chapters[-1].setdefault("entries", []).append(entry)
        else:
            chapters.append({
                "number":     1,
                "title":      "First days",
                "started_ts": ts,
                "narrative":  "",
                "entries":    [entry],
            })
        auto["chapters"] = chapters
        # Deliberately NOT touching auto["last_updated"]: that key gates
        # narrative_update's min-interval and a shutdown is not a narrative event.
        auto["last_session_close"] = ts
        save_autobiography(auto)
        log_activity("[autobiography] Session epilogue written.")
    except Exception as e:
        record_failure("autobiography.session_epilogue", e)
