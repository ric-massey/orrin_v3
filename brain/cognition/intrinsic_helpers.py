# brain/cognition/intrinsic_helpers.py
# Goal-construction + classification helpers, shared by intrinsic_goals and its
# symbolic generators (Phase 4.5C extraction). Tier/zone classification
# (_classify_tier / _goal_zone / _enrich_goal_zone), well-formed proposed-goal
# construction (_mk_goal), active-title dedup, the goal-subject acceptability +
# scaffold-stripping filters, and the weighted sampler. Depends only on the
# aspiration default-drive and stdlib/lazy lookups — no back-dependency on
# intrinsic_goals, so both it and the generators import from here.
from __future__ import annotations

import re
import random
from datetime import datetime, timezone
from typing import Dict, Any, List

from brain.cognition.intrinsic_aspirations import _fairness_default_drive


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
    except Exception:
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
