# brain/cognition/intrinsic_helpers.py
# Goal-construction + classification helpers, shared by intrinsic_goals and its
# symbolic generators (Phase 4.5C extraction). Tier/zone classification
# (_classify_tier / _goal_zone / _enrich_goal_zone), well-formed proposed-goal
# construction (_mk_goal), active-title dedup, the goal-subject acceptability +
# scaffold-stripping filters, and the weighted sampler. Depends only on the
# aspiration default-drive and stdlib/lazy lookups — no back-dependency on
# intrinsic_goals, so both it and the generators import from here.
from __future__ import annotations
from brain.core.runtime_log import get_logger

import re
import random
import time
from datetime import datetime, timezone
from typing import Dict, Any, List

from brain.utils.json_utils import load_json, save_json
from brain.utils.failure_counter import record_failure
from brain.paths import RECENTLY_COMPLETED_FILE, COMPLETED_GOALS_FILE
from brain.cognition.intrinsic_aspirations import _fairness_default_drive

_log = get_logger(__name__)


# Fix 6.1 (explore_loop_fix_plan.md) — assign a SCALE/tier to each generated goal
# so closure semantics can scale with ambition (Fix 1 §4.3). The tier bands match
# achievement_significance._TIER_W. `growth` is the UNKNOWN-tier fallback (the
# settled decision) — NOT a blanket default: known-trivial goals get the cheap
# one-act close; only ambiguous goals fall back to satiety-gating.
_TIER_TRIVIAL_HINTS = ("leave a note", "desktop note", "write a note", "note to ric",
                       "note about", "note capturing", "jot", "remember this", "quick note")
_TIER_CORE_HINTS = ("cognitive function", "write a tool", "write_tool",
                    "write_cognitive_function", "build ", "implement ", "refactor")
_TIER_GROWTH_HINTS = ("understand", "explore", "research", "learn about", "find out",
                      "investigate", "study", "search my", "search own", "what's here",
                      "audit", "trace", "read more about", "continue thread")


def _classify_tier(title: str, driven_by: str = "", description: str = "") -> str:
    """Map a goal to a scale band (trivial…core). `growth` is the unknown-fallback."""
    t = f"{title or ''} {description or ''}".lower()
    if any(h in t for h in _TIER_TRIVIAL_HINTS):
        return "trivial"
    if any(h in t for h in _TIER_CORE_HINTS):
        return "core"
    if any(h in t for h in _TIER_GROWTH_HINTS):
        return "growth"
    by = (driven_by or "").lower()
    if by == "genuine_contact":
        return "trivial"
    if by == "output_producing":
        return "core"
    return "growth"   # unknown-tier fallback (Fix 1 decision box)


_HOMEWARD_HINTS = (
    "search_own_files", "grep_files", "search_files", "survey_environment",
    "read_clipboard", "my files", "own files", "local files", "filesystem",
    "workspace", "computer i live on", "environment i live on", "what files",
    "what changed", "clipboard", "source code", "my systems", "my machinery",
)
_WORLDWARD_HINTS = (
    "research_topic", "wikipedia_search", "fetch_and_read", "read_rss",
    "look_outward", "web", "wikipedia", "article", "rss", "external",
    "current event", "world-knowledge", "world knowledge", "learn about",
    "research something real", "searches the web",
)
_WORLDWARD_DRIVES = {"world_knowledge"}
_HOMEWARD_DRIVES = {"self_exploration"}


def _goal_zone(title: str, driven_by: str = "", description: str = "") -> str:
    """Classify outward goals on the self/home/world slope.

    `home` means tend/explore the local den: files, clipboard, source, workspace.
    `world` means an expedition beyond the den: web/research/external knowledge.
    `self` covers goals that are not outward-facing in this sense.
    """
    text = f"{title or ''} {description or ''} {driven_by or ''}".lower()
    drive = (driven_by or "").lower()
    if any(h in text for h in _WORLDWARD_HINTS) or drive in _WORLDWARD_DRIVES:
        return "world"
    if any(h in text for h in _HOMEWARD_HINTS) or drive in _HOMEWARD_DRIVES:
        return "home"
    if any(h in text for h in ("explore", "environment", "search")):
        return "home"
    return "self"


def _goal_orientation(zone: str) -> str:
    if zone == "home":
        return "homeward"
    if zone == "world":
        return "worldward"
    return "selfward"


def _zone_tags(zone: str) -> List[str]:
    if zone == "home":
        return ["homeward", "home"]
    if zone == "world":
        return ["worldward", "external"]
    return ["selfward"]


def _enrich_goal_zone(goal: Dict[str, Any]) -> Dict[str, Any]:
    """Attach W4 zone/orientation metadata to a goal dict in-place."""
    zone = _goal_zone(goal.get("title", ""), goal.get("driven_by", ""), goal.get("description", ""))
    orientation = _goal_orientation(zone)
    goal["zone"] = zone
    goal["orientation"] = orientation
    tags = list(goal.get("tags") or [])
    for tag in _zone_tags(zone):
        if tag not in tags:
            tags.append(tag)
    goal["tags"] = tags
    spec = goal.get("spec")
    if isinstance(spec, dict):
        spec.setdefault("zone", zone)
        spec.setdefault("orientation", orientation)
    return goal


def _mk_goal(title: str, description: str, driven_by: str = None,
             priority: int = 3, milestones: List = None,
             requires_artifact: bool = False, deadline_cycles: int = None) -> Dict:
    """Build a well-formed proposed-goal dict from parts.

    P5: the default driver is no longer hard-coded to "world_knowledge" — that
    default was itself part of the monoculture (any generator that forgot to set a
    driver fed the intake/introspection track). When `driven_by` is omitted we fall
    back to the fairness-selected starved aspiration's drive (P3) so the path of
    least resistance stops being world_knowledge.

    requires_artifact (P2): the goal completes ONLY when a matching effect-ledger
    row exists for it — no self-report can close it. deadline_cycles arms the
    timeout → mark_goal_failed path.
    """
    if not driven_by:
        driven_by = _fairness_default_drive()
    ts = datetime.now(timezone.utc).isoformat()
    ms = [
        ({"text": m, "met": False, "met_at": None} if isinstance(m, str) else m)
        for m in (milestones or [])
    ]
    goal = {
        "title": title, "name": title, "description": description,
        "priority": priority, "kind": "generic", "source": "intrinsic",
        "tier": _classify_tier(title, driven_by, description),
        "driven_by": driven_by, "created_ts": ts, "status": "proposed",
        "milestones": ms,
    }
    if requires_artifact:
        goal["requires_artifact"] = True
        if deadline_cycles is None:
            try:
                from brain.cognition.planning.goals import PRODUCTION_DEADLINE_CYCLES as _pdc
            except Exception:
                _pdc = 200
            deadline_cycles = _pdc
        goal["deadline_cycles"] = int(deadline_cycles)
    # (T0.3 Change 5) Record the FIRST funnel stage — a goal serving some
    # aspiration was generated — so we can later see whether each aspiration died
    # at generation or downstream, instead of only the end-state count.
    try:
        from brain.cognition.aspiration_scoreboard import record_by_drive
        record_by_drive(driven_by, "generated")
    except Exception:  # intentional: scoreboard is best-effort, never block a goal
        pass
    # (T0.3) First stage of the production funnel — a making candidate was
    # generated. Deeper stages (committed → handoff → producer_ran → artifact →
    # credited) are wired in T1.P where the producer path is exercised.
    if requires_artifact or driven_by == "output_producing":
        try:
            from brain.cognition.production_funnel import record as _pf_record
            _pf_record("candidate", goal.get("title", ""))
        except Exception:  # intentional: funnel is best-effort
            pass
    return _enrich_goal_zone(goal)


def _active_goal_titles() -> set:
    """Lowercased titles of goals currently active in the tree (for dedup)."""
    try:
        from brain.cognition.planning.goals import load_goals as _lg

        def _collect(nodes):
            s = set()
            for n in (nodes or []):
                if n.get("status") in ("in_progress", "committed", "active", "proposed"):
                    t = (n.get("title") or n.get("name") or "").strip().lower()
                    if t:
                        s.add(t)
                s |= _collect(n.get("subgoals") or [])
            return s
        return _collect(_lg())
    except Exception as exc:  # goal enumeration failed — record, no active titles
        record_failure("intrinsic_goals._active_goal_titles", exc)
        return set()


_GOAL_TEXT_NOISE = (
    "[chunk:", "faded memories", "[announce", "[metacog", "[pattern]",
    "cpu=", "hunk:", "[wonder]", "summary of", "[input/", "[done]",
    "🧠", "🌓", "[goal", "[regulation]", "health summary",
)
_GOAL_SUBJECT_META = (
    "real topic", "what i find", "write what", "something interesting",
    "a concept", "a phenomenon",
)


# A goal SUBJECT must be a thing (noun phrase), not an action or instruction. These
# leading imperative verbs / trailing pronoun fragments mark a verb-phrase that got
# mistaken for a topic ("read more about it", "find out", "look at this") — wrapping
# it in "Understand X more deeply" produces a goal he can't genuinely understand.
_GOAL_SUBJECT_BAD_LEAD = frozenset({
    "read", "find", "look", "get", "use", "write", "search", "check", "see",
    "tell", "ask", "try", "keep", "go", "do", "make", "learn", "watch", "let",
})


def _acceptable_goal_subject(text: str) -> bool:
    """A goal subject must be clean human-readable content — a topic/thing, not
    chunk/digest noise, the meta 'research something' phrasing, or a verb-phrase
    fragment that can't be a subject of understanding."""
    t = (text or "").strip()
    low = t.lower()
    if len(t) < 4:
        return False
    if any(m in low for m in _GOAL_TEXT_NOISE):
        return False
    if any(m in low for m in _GOAL_SUBJECT_META):
        return False
    # Must contain real words, not be mostly brackets/punctuation.
    if not re.search(r"[a-zA-Z]{3,}", t):
        return False
    # Reject provenance/markup leakage: working-memory entries are wrapped in
    # [EXTERNAL/UNTRUSTED source=https://…] tags, and one of those was ingested
    # as a KG concept and became the goal "Understand [EXTERNAL/UNTRUSTED
    # source=https more deeply" (FINDINGS 2026-06-12 §3.2).
    if any(ch in t for ch in "[]<>{}"):
        return False
    if "source=" in low or "http://" in low or "https://" in low or "www." in low:
        return False
    if "untrusted" in low or "external/" in low:
        return False
    # Reject verb-phrase / instruction fragments — a subject is a noun, not a verb.
    words = low.split()
    if words and words[0] in _GOAL_SUBJECT_BAD_LEAD:
        return False
    if "more about" in low or "about it" in low:
        return False
    if low.endswith((" it", " this", " that", " them", " something", " stuff", " more", " out")):
        return False
    return True


# Goal-phrasing scaffolding that must never be wrapped a second time. Concept names
# in the KG are sometimes prior goal TITLES ("Understand the island more deeply"),
# so the deepening template re-wrapped them into "Understand X more deeply more
# deeply" and glued "Understand"+"Find out". Strip the scaffolding down to the bare
# topic — idempotently — before re-templating.
_LEADING_SCAFFOLD_RE = re.compile(
    r"^\s*(?:understand|learn about|find out)\b\s*:?\s*", re.I
)
_TRAILING_DEEPLY_RE = re.compile(r"\s+more deeply\b\.?\s*$", re.I)


def _strip_goal_scaffold(s: str) -> str:
    """Reduce a (possibly already-templated) string to its bare topic. Idempotent:
    'Understand the island more deeply more deeply' → 'the island';
    'Find out: What is X?' → 'What is X?'; 'the island' → 'the island'.

    Delegates to knowledge_graph.normalize_entity_name so 'bare topic' has ONE
    definition shared by KG ingestion (production) and goal phrasing (consumption);
    falls back to a local strip if that module can't be imported."""
    try:
        from brain.cognition.knowledge_graph import normalize_entity_name
        return normalize_entity_name(s)
    except Exception:
        out = (s or "").strip()
        for _ in range(8):
            before = out
            out = _TRAILING_DEEPLY_RE.sub("", out).strip()
            out = _LEADING_SCAFFOLD_RE.sub("", out).strip()
            if out == before:
                break
        return out


def _weighted_sample(scored: List, k: int) -> List[str]:
    """Weighted random sample WITHOUT replacement: higher-interest items are
    preferred but selection stays varied (not a deterministic top-k)."""
    items = list(scored)
    out: List[str] = []
    while items and len(out) < k:
        total = sum(max(0.0, w) for _, w in items)
        if total <= 0:
            out.append(items.pop(0)[0])
            continue
        r = random.uniform(0, total)
        acc = 0.0
        for i, (name, w) in enumerate(items):
            acc += max(0.0, w)
            if acc >= r:
                out.append(name)
                items.pop(i)
                break
        else:
            out.append(items.pop()[0])
    return out


# ── Recently-completed cooldown ledger (Phase 4.5C, from intrinsic_goals) ──────
# Shared completion state: the cooldown dict that stops a just-finished goal
# from being re-spawned. External callers (goal_closure, goals) mutate the dict
# and call _persist; the symbolic generators read it. Runs the one-time
# comp_goals migration at import.
# Cooldown: track recently-completed goal titles so the same goal isn't
# immediately re-spawned. Maps title (lowercased) → completion timestamp.
# Loaded from disk on startup so restarts don't lose the cooldown state.
# 6 hours, up from 10 minutes — the short window produced the completion/
# respawn zombie loop where the same intrinsic goal completed, respawned,
# and re-completed several times a day without any new work happening.
_COOLDOWN_S: float = 6 * 60 * 60

_VALID_COMPLETED_STATUSES = frozenset({"completed", "failed", "abandoned"})


def _migrate_comp_goals() -> None:
    """One-time, idempotent migration separating the cooldown dict from the
    completion archive list. Guarded by the existence of RECENTLY_COMPLETED_FILE:
    once that file exists, the migration has already run and is skipped.

    - If comp_goals.json currently holds a dict {title: ts}, move it into
      RECENTLY_COMPLETED_FILE and reset comp_goals.json to a list.
    - Normalize comp_goals.json to the list archive schema: drop any entry whose
      status is not completed/failed/abandoned (e.g. stray aspiration dicts).
    """
    try:
        if RECENTLY_COMPLETED_FILE.exists():
            return  # already migrated
    except OSError:  # intentional: stat error → skip migration this boot
        return

    cooldown: dict = {}
    archive: list = []
    try:
        raw = load_json(COMPLETED_GOALS_FILE, default_type=dict)
    except Exception:
        raw = None

    if isinstance(raw, dict):
        # Old combined file held the cooldown dict — preserve it.
        cooldown = {k: v for k, v in raw.items() if isinstance(v, (int, float))}
    elif isinstance(raw, list):
        dropped = 0
        for g in raw:
            if isinstance(g, dict) and g.get("status") in _VALID_COMPLETED_STATUSES:
                archive.append(g)
            else:
                dropped += 1
        if dropped:
            _log.info("comp_goals migration: dropped %d non-completion entries", dropped)

    try:
        save_json(RECENTLY_COMPLETED_FILE, cooldown)
        save_json(COMPLETED_GOALS_FILE, archive)
        _log.info(
            "comp_goals migration: cooldown=%d archived=%d",
            len(cooldown), len(archive),
        )
    except Exception as _e:
        _log.warning("comp_goals migration failed: %s", _e)


_migrate_comp_goals()


def _load_recently_completed() -> dict:
    try:
        raw = load_json(RECENTLY_COMPLETED_FILE, default_type=dict) or {}
        cutoff = time.time() - _COOLDOWN_S
        return {k: v for k, v in raw.items() if isinstance(v, (int, float)) and v > cutoff}
    except Exception as exc:  # cooldown read failed — record, treat as empty
        record_failure("intrinsic_goals._load_recently_completed", exc)
        return {}

_RECENTLY_COMPLETED: dict = _load_recently_completed()


# ── LLM gate ─────────────────────────────────────────────────────────────────

def _persist_recently_completed() -> None:
    try:
        save_json(RECENTLY_COMPLETED_FILE, _RECENTLY_COMPLETED)
    except Exception as _e:
        record_failure("intrinsic_goals._persist_recently_completed", _e)
