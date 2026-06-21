# brain/cognition/selfhood/tensions.py
# Formative tensions — ongoing contradictions Orrin is actively working through.
#
# A tension is a named contradiction that has narrative weight: it is something
# Orrin is actively trying to resolve, not just a logged event. Tensions make the
# "becoming" process directional by giving Orrin a persistent sense of what is
# unresolved in itself.
#
# Sources:
#   - Pending value revisions (a belief is known to be unstable but not yet settled)
#   - Recurring site failures (aspiration vs. demonstrated capability gap)
#   - Active autobiography chapter themes (the central tension in the current chapter)
#
# Active tensions are injected into working_memory once per cycle so they remain
# salient to function selection, inner_loop reasoning, and the draft/critique cycle.
# Function selection's emotion weight is also amplified for functions that help
# resolve tensions (reflection, values_check, plan_self_evolution).
from __future__ import annotations
from brain.core.runtime_log import get_logger

import random
import uuid
from typing import Any, Dict, List

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_activity
from brain.paths import VALUE_REVISIONS, TENSIONS_FILE
from brain.utils.timeutils import now_iso_z
_log = get_logger(__name__)

_MAX_ACTIVE         = 5     # cap so working memory isn't overwhelmed
_MAX_RESOLVED       = 50    # keep last N resolved for historical context
_INJECTION_PROB_BASE = 0.30  # probability for a brand-new tension (cycles_active ≈ 0)
_INJECTION_PROB_MAX  = 0.75  # ceiling — even the oldest tension doesn't dominate every cycle
_ESCALATION_SPAN     = 80    # cycles over which probability climbs from base to max

# TTL (BEHAVIOR_FIX_PLAN 2.3): a tension active this long without resolution
# progress is downgraded to a logged open question and cleared from the active
# set — targetless rumination must not run for 647 cycles (audit §5).
_TENSION_TTL_CYCLES = 200

# Registry-tool outages are facts to route around, never unresolved inner
# conflicts (plan §0.3) — they may not seed tensions.
_TOOL_OUTAGE_MARKERS = ("llm", "language model", "tool unavailable", "api key",
                        "wikipedia", "web_search", "scrape")

import re as _re
from brain.utils.failure_counter import record_failure
# Known self-nesting prefixes: re-surfacing must rebuild from the RAW source
# text, never from an already-prefixed title ("Value under tension: Value
# under tension: …" — same bug class as "I am blocked: I am blocked").
_TITLE_PREFIX_RE = _re.compile(
    r"^\s*(?:🔴|⚠️)?\s*(?:\[tension\]\s*|value under tension\s*:\s*|"
    r"chapter tension\s*:\s*|recurring gap\s*:\s*)+",
    _re.IGNORECASE,
)


def _strip_title_prefixes(text: str) -> str:
    out = str(text or "").strip()
    for _ in range(8):
        new = _TITLE_PREFIX_RE.sub("", out).strip()
        if new == out:
            break
        out = new
    return out



def load_tensions() -> List[Dict]:
    data = load_json(TENSIONS_FILE, default_type=list) or []
    return [t for t in data if isinstance(t, dict)]


def save_tensions(tensions: List[Dict]) -> None:
    save_json(TENSIONS_FILE, tensions)


# ── Detection ─────────────────────────────────────────────────────────────────

def detect_tensions(context: Dict[str, Any] = None) -> List[str]:
    """
    Scan live data for new formative tensions. Called from dream cycle.
    Returns titles of newly detected tensions.
    """
    context = context or {}
    tensions = load_tensions()
    active_titles = {
        t["title"]
        for t in tensions
        if t.get("status") in ("active", "resolving")
    }
    newly = []
    ts = now_iso_z()

    # ── Source 1: pending value revisions ────────────────────────────────────
    try:
        vr = load_json(VALUE_REVISIONS, default_type=list) or []
        pending = [r for r in vr if isinstance(r, dict) and r.get("status", "pending") == "pending"]
        for rev in pending[:3]:
            evidence = _strip_title_prefixes(str(rev.get("evidence") or ""))[:80]
            title = f"Value under tension: {evidence[:60]}"
            if title not in active_titles:
                tensions.append(_make(title, f"A core value is contested: {evidence}", "value_revision", ts))
                active_titles.add(title)
                newly.append(title)
    except Exception as _e:
        record_failure("tensions.detect_tensions", _e)

    # ── Source 2: recurring failures (aspiration/capability gap) ─────────────
    try:
        from brain.utils.failure_counter import get_summary as _fs
        summary = _fs() or {}  # {site: {"count": N, ...}, ...}
        for site, data in summary.items():
            count = int((data.get("count") or 0) if isinstance(data, dict) else 0)
            # Tool outages are facts, not inner conflicts — never tension seeds.
            if any(m in site.lower() for m in _TOOL_OUTAGE_MARKERS):
                continue
            if count >= 3 and any(k in site.lower() for k in ("goal", "plan", "pursue")):
                title = f"Recurring gap: {site}"
                if title not in active_titles:
                    tensions.append(_make(
                        title,
                        f"Repeated failures at '{site}' ({count}×) reveal a gap between aspiration and ability.",
                        "goal_failure",
                        ts,
                    ))
                    active_titles.add(title)
                    newly.append(title)
    except Exception as _e:
        record_failure("tensions.detect_tensions.2", _e)

    # ── Source 3: autobiography chapter theme tension ─────────────────────────
    try:
        from brain.cognition.selfhood.autobiography import load_autobiography
        auto = load_autobiography()
        chapters = auto.get("chapters") or []
        if chapters:
            chapter_tension = _strip_title_prefixes((chapters[-1].get("theme_tension") or "").strip())
            if chapter_tension and len(chapter_tension) > 10:
                title = f"Chapter tension: {chapter_tension[:60]}"
                if title not in active_titles:
                    tensions.append(_make(title, chapter_tension, "autobiography", ts))
                    active_titles.add(title)
                    newly.append(title)
    except Exception as _e:
        record_failure("tensions.detect_tensions.3", _e)

    # ── Prune / cap ───────────────────────────────────────────────────────────
    active   = [t for t in tensions if t.get("status") in ("active", "resolving")]
    resolved = [t for t in tensions if t.get("status") not in ("active", "resolving")]

    if len(active) > _MAX_ACTIVE:
        active = sorted(active, key=lambda t: t.get("detected_ts", ""), reverse=True)[:_MAX_ACTIVE]

    save_tensions(active + resolved[-_MAX_RESOLVED:])

    if newly:
        log_activity(f"[tensions] {len(newly)} new: {newly[:3]}")

    return newly


def _make(title: str, description: str, source: str, ts: str) -> Dict:
    return {
        "id":           str(uuid.uuid4())[:8],
        "title":        title,
        "description":  description,
        "source":       source,
        "status":       "active",
        "detected_ts":  ts,
        "resolved_ts":  None,
        "cycles_active": 0,
    }


# ── Per-cycle injection ───────────────────────────────────────────────────────

def _auto_resolve_stale(tensions: List[Dict]) -> int:
    """
    Auto-resolve value_revision-sourced tensions whose revision is no longer pending.
    Returns the number of tensions resolved.
    """
    resolved_count = 0
    try:
        vr = load_json(VALUE_REVISIONS, default_type=list) or []
        if not vr:
            # Can't tell which revisions are pending when file is missing/empty — skip
            return 0
        pending_evidences = {
            str(r.get("evidence", ""))[:80]
            for r in vr
            if isinstance(r, dict) and r.get("status", "pending") == "pending"
        }
    except Exception:
        return 0

    ts = now_iso_z()
    for t in tensions:
        if t.get("status") not in ("active", "resolving"):
            continue
        if t.get("source") != "value_revision":
            continue
        # The title encodes the evidence snippet; check if the revision is still pending
        title = t.get("title", "")
        snippet = title.replace("Value under tension: ", "")
        if not any(snippet in ev or ev in snippet for ev in pending_evidences):
            t["status"] = "resolved"
            t["resolved_ts"] = ts
            resolved_count += 1
            log_activity(f"[tensions] Auto-resolved '{title[:60]}' — source revision no longer pending.")

    return resolved_count


def _tension_urgency_prefix(cycles_active: int) -> str:
    """Return an urgency marker that escalates the longer a tension goes unresolved."""
    if cycles_active > 30:
        return "🔴 "
    if cycles_active > 10:
        return "⚠️ "
    return ""


def _injection_prob(cycles_active: int) -> float:
    """
    Escalating injection probability:
      cycles=0  → 0.30  (brand new — surfaces occasionally)
      cycles=40 → ~0.52
      cycles=80 → 0.75  (long-festering — hard to ignore)
    """
    return min(
        _INJECTION_PROB_MAX,
        _INJECTION_PROB_BASE + (cycles_active / _ESCALATION_SPAN) * (_INJECTION_PROB_MAX - _INJECTION_PROB_BASE),
    )


def inject_tension_signals(context: Dict[str, Any]) -> None:
    """
    Called once per cycle. Increments cycle counters, writes the most urgent
    tension into working_memory (probability escalates with age), and sets
    context["active_tensions"] so inner_loop and select_function can read it.
    """
    tensions = load_tensions()

    # Auto-resolve tensions whose underlying source has been cleared
    _n_resolved = _auto_resolve_stale(tensions)
    if _n_resolved:
        save_tensions(tensions)

    active = [t for t in tensions if t.get("status") in ("active", "resolving")]

    if not active:
        context["active_tensions"] = []
        return

    # Increment cycle counters and persist
    for t in active:
        t["cycles_active"] = int(t.get("cycles_active") or 0) + 1

    # TTL escalation (BEHAVIOR_FIX_PLAN 2.3): a tension past its TTL without
    # resolution is downgraded to a logged open question and cleared from the
    # active set — it stops feeding rumination but isn't silently forgotten.
    expired = [t for t in active if int(t.get("cycles_active") or 0) > _TENSION_TTL_CYCLES]
    for t in expired:
        t["status"] = "open_question"
        t["resolved_ts"] = now_iso_z()
        log_activity(
            f"[tensions] TTL expired ({t.get('cycles_active')} cycles) — downgraded "
            f"to open question: {str(t.get('title'))[:70]}"
        )
        try:
            from brain.cog_memory.long_memory import update_long_memory
            update_long_memory(
                f"Open question (was a tension, unresolved after "
                f"{t.get('cycles_active')} cycles): {_strip_title_prefixes(str(t.get('title')))[:120]}",
                event_type="open_question", importance=2,
            )
        except Exception as _e:
            record_failure("tensions.inject_tension_signals", _e)
    if expired:
        active = [t for t in active if t.get("status") in ("active", "resolving")]
    save_tensions(tensions)

    if not active:
        context["active_tensions"] = []
        return

    # Surface a tension into working memory with age-escalating probability.
    # Sort by cycles_active descending — oldest unresolved tension gets first
    # shot at surfacing, but younger ones can still fire on their own roll.
    wm: list = context.get("working_memory") or []
    already = any("[Tension]" in str(e) for e in (wm[-5:] if len(wm) >= 5 else wm))

    if not already:
        # Sort oldest-first so the most persistent tension leads the selection
        for t in sorted(active, key=lambda x: x.get("cycles_active", 0), reverse=True):
            cycles = int(t.get("cycles_active") or 0)
            prob = _injection_prob(cycles)
            if random.random() < prob:
                urgency = _tension_urgency_prefix(cycles)
                msg = (
                    f"{urgency}[Tension] {t['title']}: {t['description'][:100]}"
                    + (f" (unresolved for {cycles} cycles)" if cycles > 10 else "")
                )
                try:
                    from brain.cog_memory.working_memory import update_working_memory
                    update_working_memory(msg)
                except Exception as _e:
                    record_failure("tensions.inject_tension_signals.2", _e)
                break  # one tension per cycle — avoid WM flooding

    context["active_tensions"] = [
        {
            "title": t["title"],
            "cycles_active": t.get("cycles_active", 0),
            "urgency": _tension_urgency_prefix(int(t.get("cycles_active") or 0)).strip(),
        }
        for t in active
    ]


# ── Resolution ────────────────────────────────────────────────────────────────

def mark_tension_resolved(tension_id_or_title: str, context: Dict[str, Any] = None) -> bool:
    """Mark a tension resolved by id or title. Returns True if found."""
    tensions = load_tensions()
    found = False
    ts = now_iso_z()
    for t in tensions:
        if t.get("id") == tension_id_or_title or t.get("title") == tension_id_or_title:
            t["status"]      = "resolved"
            t["resolved_ts"] = ts
            found = True
    if found:
        save_tensions(tensions)
        log_activity(f"[tensions] resolved: {tension_id_or_title[:60]}")
    return found
