# brain/cognition/leave_note.py
# Orrin leaves a note for the user. The note is *composed* by Orrin through the
# one expression door (behavior.express_to_user) from his motive + felt state —
# it is NOT populated by scraping working memory. The backend (raw WM,
# symbolic/causal tags, telemetry) is unreachable from here.
# (EXPRESSION_MEMBRANE_FIX_PLAN E1/E4, 2026-06-14.)
from __future__ import annotations
from brain.cognition.global_workspace import bound_goal

import re
from typing import Any, Dict, Optional, Tuple

from brain.utils.log import log_activity
from brain.utils.failure_counter import record_failure

# ── Seed-provenance quality gate (PRODUCTION_LOOP_CLOSURE D6 / F5) ─────────────
# The 2026-06-19 life wrote junk notes seeded from filesystem/path output and
# lock/data fragments. A note seed must be human-meaningful prose, never machine
# output. These reject the three failure classes the proposal names: path
# listings, lock/data file fragments, empty-delimiter output, and low-information
# token soup. Conservative by design — if it looks like machine output, drop it.
_PATHY_RE = re.compile(r"(?:[\w.\-]+/){2,}[\w.\-]+")          # a/b/c style path
_LOCKY_RE = re.compile(r"\.(?:lock|jsonl?|pyc?|tmp|log|db)\b", re.IGNORECASE)
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]{2,}")
_MIN_SEED_CHARS = 40
_MIN_DISTINCT_WORDS = 6


def _qualifies_as_seed(text: str) -> bool:
    """True only for prose worth seeding a note with — not paths, lock/data
    fragments, delimiter noise, or a low-information token set (D6)."""
    s = (text or "").strip()
    if len(s) < _MIN_SEED_CHARS:
        return False
    low = s.lower()
    # path listings / home paths / lock + data file fragments
    if "/users/" in low or _PATHY_RE.search(s) or _LOCKY_RE.search(low):
        return False
    # empty-delimiter / punctuation-only output (e.g. "[] {} === ----")
    if sum(ch.isalnum() for ch in s) < 0.5 * len(s):
        return False
    # low-information: needs enough DISTINCT real words to carry meaning
    distinct = {w.lower() for w in _WORD_RE.findall(s)}
    if len(distinct) < _MIN_DISTINCT_WORDS:
        return False
    return True


def _serving_criterion(goal: Dict[str, Any]) -> str:
    """The first not-yet-met definition-of-done criterion this note serves."""
    for row in (goal.get("definition_of_done") or []):
        if isinstance(row, dict) and not row.get("met"):
            crit = str(row.get("criterion") or "").strip()
            if crit:
                return crit
    return ""


def _seed_from_goal(goal: Dict[str, Any]) -> Optional[str]:
    """Ground the note in the committed goal's own comprehension (F5 #1): the
    degraded acquire-knowledge subject, or the hydrated grounded_parts plus the
    criterion being served. Returns a meaning kernel (the door rewords it)."""
    title = str(goal.get("title") or "")
    if "what i already know about" in title.lower():
        topic = title.split(":", 1)[-1].strip()
        orig = str(goal.get("_original_title")
                   or (goal.get("_predegrade") or {}).get("title") or "")
        subject = topic or orig
        if subject:
            return f"what I actually know about {subject}"
    parts = [str(p).strip() for p in (goal.get("grounded_parts") or []) if str(p).strip()]
    if parts:
        body = "; ".join(parts[:3])
        crit = _serving_criterion(goal)
        seed = f"what I actually know about {title or 'this'}: {body}"
        if crit:
            seed += f" — toward: {crit}"
        # T2.4 — this branch is the goal's grounded_parts PLANNING SKELETON, the
        # ×56 template note ("...: question or desired change; relevant evidence;
        # reasoned conclusion"). Route a real finding instead (see
        # _seed_from_goal_finding, tried first in leave_note); only let the skeleton
        # through if the SHARED T0.5 predicate judges it real work against this goal
        # — which it won't when it is purely the template, closing the loophole.
        if not _qualifies_as_seed(seed):
            return None
        try:
            from brain.cognition.quality_predicate import is_real_work
            if not is_real_work(seed, goal=goal):
                return None
        except Exception as exc:  # predicate unavailable — fall back to the weak gate
            record_failure("leave_note.seed_quality", exc)
        return seed
    return None


def _seed_from_goal_finding(goal: Dict[str, Any]) -> Optional[str]:
    """T2.4 — route the note body from the goal's ACTUAL finding / produced content,
    not its grounded_parts planning skeleton. Reads the same real-evidence fields the
    T0.5 predicate grounds against (finding / answer / conclusion / produced_content /
    result), and returns the finding as a seed only when it passes that shared
    predicate — so provenance reaches the ANSWER, not just the topic."""
    if not isinstance(goal, dict):
        return None
    title = str(goal.get("title") or "this")
    for k in ("finding", "answer", "conclusion", "produced_content", "result"):
        v = goal.get(k)
        if isinstance(v, str) and v.strip():
            text = " ".join(v.split())[:240]
            seed = f"what I found out about {title}: {text}"
            try:
                from brain.cognition.quality_predicate import is_real_work
                if not is_real_work(seed, goal=goal):
                    continue
            except Exception as exc:
                record_failure("leave_note.finding_quality", exc)
            return seed
    return None


def _seed_from_recent_finding() -> Optional[str]:
    """P4 fallback: ground the note in the most recent REAL finding, not the
    ambient affect status line — but only if it passes the D6 quality gate, so
    path/lock/noise fragments can never become a seed."""
    try:
        from brain.utils.json_utils import load_json as _lj
        from brain.paths import LONG_MEMORY_FILE as _LMF
        lm = _lj(_LMF, default_type=list) or []
        for entry in reversed(lm[-25:]):
            content = str(entry.get("content", entry) if isinstance(entry, dict) else entry)
            low = content.lower()
            if ("from searching" in low or "finding was written" in low
                    or "[world_perception]" in low):
                payload = content.split(":", 1)[-1].strip() if ":" in content else content
                payload = " ".join(payload.split())[:240]
                if _qualifies_as_seed(payload):
                    return f"something I actually found out: {payload}"
    except Exception as exc:  # memory scan for a seed best-effort — record
        record_failure("leave_note.seed_scan", exc)
    return None


_ABOUT_RE = re.compile(r"\babout\s+(.+?)(?:\s+that\b|\s+do\b|,|\?|$)", re.IGNORECASE)
_CHROME_RE = re.compile(r"\bv t e\b|\bCategory\b|\bportal\b|\bRetrieved\b|\[edit\]", re.IGNORECASE)


def recent_claims_finding(scan: int = 12) -> Optional[Tuple[str, str]]:
    """Run 13 item 7: (topic, finding) from the newest research claims.json with a
    relation that names its own subject — the structured findings the daemon writes
    (Run 12 produced 12; notes used none of them and 610 of 617 went out empty).
    None when there is nothing real to say. Never raises."""
    try:
        import json as _json
        from brain.paths import GOALS_DIR
        from brain.utils.subject_terms import matched_terms, subject_terms
        files = sorted((GOALS_DIR / "artifacts").glob("*/claims.json"),
                       key=lambda p: p.stat().st_mtime, reverse=True)[:scan]
        for f in files:
            try:
                data = _json.loads(f.read_text(encoding="utf-8", errors="replace"))
            except (OSError, ValueError):
                continue
            q = str(data.get("question") or "")
            m = _ABOUT_RE.search(q)
            topic = (m.group(1).strip() if m else " ".join(subject_terms(q))).strip(" .")
            terms = subject_terms(topic)
            if not topic or not terms:
                continue
            for r in data.get("relations") or []:
                if not isinstance(r, dict):
                    continue
                text = " ".join(f"{r.get('subject', '')} {r.get('predicate', '')} {r.get('object', '')}".split())
                if _CHROME_RE.search(text) or len(matched_terms(terms, text)) < min(2, len(terms)):
                    continue
                if _qualifies_as_seed(f"{topic}: {text}"):
                    return topic[:60], text[:200]
    except Exception as exc:
        record_failure("leave_note.recent_claims_finding", exc)
    return None


def _seed_from_recent_claims() -> Optional[str]:
    hit = recent_claims_finding()
    return f"something I found out about {hit[0]}: {hit[1]}" if hit else None


def leave_note(context: Dict[str, Any] = None) -> str:
    """Compose and deliver a note to the user via the expression door."""
    context = context or {}

    from brain.behavior.express_to_user import build_motive, express_to_user

    goal = bound_goal(context) or {}
    goal = goal if isinstance(goal, dict) else {}

    # Seed, best provenance first (T2.4 — route from the FINDING, not the template):
    # the goal's own produced finding, then a quality-gated recent finding, then —
    # only as a last resort and only if the shared T0.5 predicate accepts it — the
    # goal's grounded comprehension. This stops the note body from carrying the
    # grounded_parts planning skeleton (the ×56 template note). The seed is a meaning
    # kernel — the expression door rewords/sanitises it, so the membrane stays intact.
    seed = (_seed_from_goal_finding(goal)
            or _seed_from_recent_finding()
            or _seed_from_recent_claims()
            or _seed_from_goal(goal))

    # Run 13 item 7: no content, no note. The felt-state fallback ("something
    # present but hard to name") went out 610 times in Run 12 — a note Ric would
    # find carries a finding, or it is not written. (Supersedes the F5 #5 rule
    # that only applied this to requires_artifact goals.)
    if seed is None:
        return "Nothing worth noting right now — no grounded content to write."

    # The owning goal ID rides through build_motive (it stamps motive.goal_id),
    # so a goal-linked note can be alignment-scored against its goal (F5 #2).
    # AR7/G4: a note with no grounded finding (seed=None → felt-state kernel) is
    # still delivered — expression is legitimate — but earns NO effect credit;
    # only a finding-seeded note is production.
    motive = build_motive(context, intent="leave_note", recipient="Ric", seed=seed)
    result = express_to_user(motive, "note", context, credit=seed is not None)
    content = (result or {}).get("text") or ""
    if not content:
        return "Nothing worth noting right now."

    log_activity(f"[leave_note] {content[:80]}")

    # Reafference: report the real artifact into working memory so milestone
    # verification (env_snapshot, which only sees WM) can observe that a note was
    # actually written. This writes a marker INTO WM; it never reads raw WM out —
    # the membrane stays intact (EXPRESSION_MEMBRANE_FIX_PLAN §1.4).
    try:
        from brain.cog_memory.working_memory import update_working_memory
        update_working_memory({
            "content": f"[note_written] {content[:160]}",
            "event_type": "note_written",
            "importance": 2,
        })
    except Exception as exc:  # reafference WM write best-effort — record
        record_failure("leave_note.reafference", exc)

    return f"Left a note: {content[:120]}"
