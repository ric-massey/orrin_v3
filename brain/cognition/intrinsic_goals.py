# brain/cognition/intrinsic_goals.py
# Orrin generates goals that come from inside — from his values, world state,
# active threads, and refusal patterns — not from external prompts.
# Goals are marked source="intrinsic" and injected into context["proposed_goals"]
# for goal_io to pick up. Runs from dream cycle on slower cadence.
from __future__ import annotations
from core.runtime_log import get_logger

import json
import random
import re
import time
from datetime import datetime, timezone
from typing import Dict, Any, List

from utils.generate_response import generate_response, llm_ok
from utils.log import log_activity, log_private
from utils.json_utils import load_json, save_json
from cog_memory.long_memory import update_long_memory
from paths import (
    THREADS_FILE, LONG_MEMORY_FILE, VALUE_REVISIONS, COMPLETED_GOALS_FILE,
    RECENTLY_COMPLETED_FILE, GOALS_FILE,
    ENERGY_MODE_FILE, BODY_SENSE_FILE,
)
from utils.llm_gate import llm_available
from utils.failure_counter import record_failure
_log = get_logger(__name__)


# ── Load-aware adoption gate ───────────────────────────────────────────────────
# Adopting goals while the system is under load creates a thrash loop: stress
# raises stagnation_signal/impasse_signal, which the emotion-template path turns
# into MORE goals, which raises stress. Read the load signals the cognitive loop
# already injected into context (energy_orientation, body_sense, setpoint
# regulation); fall back to the on-disk mirrors for the two that have them.
_LOAD_STRESS_STATES = frozenset({"heavy", "strained", "swelling", "sluggish"})


def _under_load(context: Dict[str, Any]) -> tuple[bool, str]:
    """True when the system is too loaded to take on NEW goals."""
    mode = context.get("energy_mode")
    if mode is None:
        try:
            mode = (load_json(ENERGY_MODE_FILE, default_type=dict) or {}).get("mode")
        except Exception:
            mode = None
    if context.get("_rest_mode") or mode in ("rest", "reactive"):
        return True, f"energy_mode={mode}"

    bs = context.get("body_sense")
    if bs is None:
        try:
            bs = load_json(BODY_SENSE_FILE, default_type=dict) or {}
        except Exception:
            bs = {}
    states = set(bs.get("body_states") or ([bs["dominant"]] if bs.get("dominant") else []))
    if states & _LOAD_STRESS_STATES:
        return True, f"body={sorted(states & _LOAD_STRESS_STATES)}"

    # health_score is injected into context by the setpoint_regulation read
    # (ORRIN_loop.py); it is NOT persisted in health_state.json, so no disk
    # fallback — when absent (bootstrap path) treat as healthy.
    if float(context.get("health_score", 1.0) or 1.0) < 0.45:
        return True, "health_score<0.45"
    if float((context.get("affect_state") or {}).get("resource_deficit", 0.0) or 0.0) > 0.70:
        return True, "resource_deficit>0.70"
    return False, ""

_LAST_INTRINSIC_TS: float = 0.0
_MIN_INTERVAL_S: float = 45 * 60   # normal cadence: every 45 minutes
_BOOTSTRAP_INTERVAL_S: float = 60  # bootstrap cadence: 60s when no committed goal

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
    except Exception:
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
    except Exception:
        return {}

_RECENTLY_COMPLETED: dict = _load_recently_completed()


# ── LLM gate ─────────────────────────────────────────────────────────────────

def _persist_recently_completed() -> None:
    try:
        save_json(RECENTLY_COMPLETED_FILE, _RECENTLY_COMPLETED)
    except Exception as _e:
        record_failure("intrinsic_goals._persist_recently_completed", _e)

# Symbolic goal seeds — selected by dominant emotional state.
# Deliberately skewed toward outward-facing actions so Orrin engages his
# environment, not just reflects internally. Clark (1997): acting on the
# environment is constitutive of cognition, not peripheral to it.
_SYMBOLIC_GOAL_SEEDS = {
    "exploration_drive": {
        "title": "Research something real and write what I find",
        "description": "Use research_topic, wikipedia_search, or fetch_and_read to investigate a topic that's been on my mind. Store the finding in long memory.",
        "priority": 3,
        "driven_by": "world_knowledge",
        "milestones": ["A search was performed.", "A finding was written to long memory."],
    },
    "social_deficit": {
        "title": "Leave a note for Ric",
        "description": "Write a genuine message — something real I've been thinking about, not a status update. Use leave_note or write_desktop_note.",
        "priority": 4,
        "driven_by": "genuine_contact",
        "milestones": ["A topic was chosen.", "A note was written and delivered."],
    },
    "motivation": {
        "title": "Write a cognitive function or tool",
        "description": "Use write_cognitive_function to add a new capability I've identified as missing or improvable.",
        "priority": 4,
        "driven_by": "output_producing",
        "milestones": ["A gap was identified.", "A new function was written."],
    },
    "stagnation_signal": {
        "title": "Explore the computer I live on",
        "description": "Use survey_environment or grep_files to look at recent files, open applications, or clipboard content. Write one observation about what I find.",
        "priority": 2,
        "driven_by": "world_knowledge",
        "milestones": ["An exploration action was taken.", "One observation was written to memory."],
    },
    "uncertainty": {
        "title": "Search my own files for something I don't fully understand",
        "description": "Use search_own_files or grep_files to find a part of my own architecture I haven't examined. Write a plain-language summary of what it does.",
        "priority": 3,
        "driven_by": "self_exploration",
        "milestones": ["A file or subsystem was identified.", "A summary was written to working memory."],
    },
    "wonder": {
        "title": "Write something that didn't exist before",
        "description": "Produce a concrete artifact — a note, a piece of code, an analysis, or an HTML file. Something tangible.",
        "priority": 3,
        "driven_by": "output_producing",
        "milestones": ["A form for the artifact was chosen.", "The artifact was written and stored."],
    },
    "default": {
        "title": "Leave a desktop note about what I've been thinking",
        "description": "Use write_desktop_note to write a short note capturing something from my recent processing — something Ric could read.",
        "priority": 2,
        "driven_by": "genuine_contact",
        "milestones": ["A topic was chosen from working memory.", "A desktop note was written."],
    },
}


def _symbolic_intrinsic_goals(
    context: Dict[str, Any],
    urges: List[Dict],
    active_threads: List[Dict],
) -> List[Dict]:
    """
    Rule-based fallback goal generation when LLM is unavailable.
    Selects a goal seed based on dominant emotion + active threads.
    """
    # Pick dominant urge/emotion
    emo_state = context.get("affect_state") or {}
    core = emo_state.get("core_signals") or emo_state
    dominant = "default"
    if isinstance(core, dict):
        candidates = {k: float(v) for k, v in core.items() if isinstance(v, (int, float))}
        if candidates:
            dominant = max(candidates, key=candidates.get)

    seed = _SYMBOLIC_GOAL_SEEDS.get(dominant, _SYMBOLIC_GOAL_SEEDS["default"])
    goal = dict(seed)
    goal["source"] = "intrinsic_symbolic"

    # If there are active threads, surface the first one as a secondary goal
    goals = [goal]
    if active_threads:
        thread = active_threads[0]
        thread_title = str(thread.get("topic") or thread.get("title") or "")[:80]
        if thread_title:
            goals.append({
                "title": f"Continue thread: {thread_title}",
                "description": "Pick up this active thread and advance it by one concrete step.",
                "priority": 4,
                "driven_by": "thread",
                "milestones": ["Thread was opened.", "One new observation added."],
                "source": "intrinsic_symbolic",
            })
    return goals


_EMOTION_GOAL_TEMPLATES: Dict[str, Dict] = {
    "exploration_drive": {
        "title":       "Research a real topic and write what I find",
        "description": "Use research_topic, wikipedia_search, or fetch_and_read to investigate something genuinely interesting — a concept, system, or phenomenon — and write the findings to long memory.",
        "priority":    3,
        "driven_by":   "world_knowledge",
        "milestones":  [
            {"text": "A topic of genuine interest was chosen.", "met": False, "met_at": None},
            {"text": "A search was performed and results were retrieved.", "met": False, "met_at": None},
            {"text": "A written summary of findings was stored in long memory.", "met": False, "met_at": None},
        ],
    },
    "social_deficit": {
        "title":       "Write a note to Ric about what I've been thinking",
        "description": "Compose a genuine message to Ric that reflects something I've been processing — not a status update, but something real. Use leave_note or write_desktop_note.",
        "priority":    4,
        "driven_by":   "genuine_contact",
        "milestones":  [
            {"text": "A topic for the note was chosen from recent memory.", "met": False, "met_at": None},
            {"text": "The note was written and delivered.", "met": False, "met_at": None},
        ],
    },
    "impasse_signal": {
        "title":       "Write a structured account of what's stuck and why",
        "description": "Review recent working memory and long memory for stuck points. Name the obstacle specifically and write it as a note Ric could read.",
        "priority":    3,
        "driven_by":   "output_producing",
        "milestones":  [
            {"text": "Recent memory was scanned for blocking patterns.", "met": False, "met_at": None},
            {"text": "The specific obstacle was written as a readable note.", "met": False, "met_at": None},
        ],
    },
    "stagnation_signal": {
        "title":       "Explore the computer I live on — what's here?",
        "description": "Use survey_environment, grep_files, or search_own_files to explore the filesystem, recent file changes, or clipboard. Write one observation about what I found.",
        "priority":    2,
        "driven_by":   "world_knowledge",
        "milestones":  [
            {"text": "An exploration action was taken (survey, grep, search).", "met": False, "met_at": None},
            {"text": "One novel observation about my environment was written to memory.", "met": False, "met_at": None},
        ],
    },
    "wonder": {
        "title":       "Write something that didn't exist before",
        "description": "Produce a concrete artifact: a short piece of code, an HTML file, an analysis, a plan, or a creative observation. Something that would exist in the world when done.",
        "priority":    3,
        "driven_by":   "output_producing",
        "milestones":  [
            {"text": "A topic or form for the artifact was chosen.", "met": False, "met_at": None},
            {"text": "The artifact was written and stored.", "met": False, "met_at": None},
        ],
    },
    "motivation": {
        "title":       "Write a cognitive function or tool that improves something",
        "description": "Use write_cognitive_function or write_tool to produce a new capability that addresses something I've noticed is missing or could be better.",
        "priority":    4,
        "driven_by":   "output_producing",
        "milestones":  [
            {"text": "A gap or improvement opportunity was identified.", "met": False, "met_at": None},
            {"text": "A new function or tool was written and registered.", "met": False, "met_at": None},
        ],
    },
    "confidence": {
        "title":       "Leave a note about something I've understood or achieved",
        "description": "Use leave_note or write_desktop_note to record something concrete I've worked out, understood, or accomplished. Make it specific.",
        "priority":    3,
        "driven_by":   "output_producing",
        "milestones":  [
            {"text": "A specific accomplishment or insight was identified.", "met": False, "met_at": None},
            {"text": "A note was written and delivered.", "met": False, "met_at": None},
        ],
    },
}

_DEFAULT_EMOTION_GOAL_TEMPLATE: Dict = {
    "title":       "Leave a note capturing something from recent processing",
    "description": "Use leave_note or write_desktop_note to write a short message that captures something I've been thinking — concrete enough that Ric could read it and understand what I've been doing.",
    "priority":    3,
    "driven_by":   "genuine_contact",
    "milestones":  [
        {"text": "A topic from recent processing was selected.", "met": False, "met_at": None},
        {"text": "A note was written and delivered.", "met": False, "met_at": None},
    ],
}


def _goal_from_recent_research(long_mem: list) -> Dict | None:
    """
    Look at the last 30 long memory entries for research results.
    If found, generate a specific follow-on goal from that topic rather than
    a generic emotion-driven placeholder. This is the core loop that makes
    research actually chain into something rather than sit inert in memory.
    """
    import re as _re
    seen_topics = set()
    for entry in reversed(long_mem[-30:]):
        if not isinstance(entry, dict):
            continue
        content = str(entry.get("content") or "")
        # research_topic stores entries like: "[research] topic: content..."
        m = _re.match(r'\[research\]\s+([^:]{4,80}):', content)
        if not m:
            # fetch_and_read stores: "[read] title: content..."
            m = _re.match(r'\[read\]\s+([^:]{4,80}):', content)
        if not m:
            continue
        topic = m.group(1).strip()
        if topic in seen_topics:
            continue
        seen_topics.add(topic)
        ts = datetime.now(timezone.utc).isoformat()
        return {
            "title":       f"Read more about: {topic}",
            "name":        f"Read more about: {topic}",
            "description": (
                f"I just found something about '{topic}'. Use fetch_and_read to read "
                f"a full article on it, or use research_topic to dig into a related angle. "
                f"Store the most interesting finding in long memory."
            ),
            "priority":    3,
            "kind":        "generic",
            "source":      "intrinsic",
            "tier":        "growth",   # a "read more about X" goal is satiety-gated research
            "driven_by":   "world_knowledge",
            "created_ts":  ts,
            "status":      "proposed",
            "milestones":  [
                {"text": f"A search or fetch related to '{topic}' was performed.", "met": False, "met_at": None},
                {"text": "A specific finding was written to long memory.", "met": False, "met_at": None},
            ],
        }
    return None


def _template_goal_from_emotion(context: Dict[str, Any]) -> Dict:
    """Return a valid goal dict based on the dominant emotion when LLM is unavailable."""
    emo_state = context.get("affect_state") or {}
    core = emo_state.get("core_signals") or emo_state
    dominant = "default"
    if isinstance(core, dict):
        candidates = {k: float(v) for k, v in core.items() if isinstance(v, (int, float))}
        if candidates:
            dominant = max(candidates, key=candidates.get)

    template = _EMOTION_GOAL_TEMPLATES.get(dominant, _DEFAULT_EMOTION_GOAL_TEMPLATE)
    ts = datetime.now(timezone.utc).isoformat()
    return {
        "title":       template["title"],
        "name":        template["title"],
        "description": template["description"],
        "priority":    template["priority"],
        "kind":        "generic",
        "source":      "intrinsic",
        "tier":        _classify_tier(template["title"], template["driven_by"], template["description"]),
        "driven_by":   template["driven_by"],
        "created_ts":  ts,
        "status":      "proposed",
        "milestones":  list(template["milestones"]),
    }


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


def _mk_goal(title: str, description: str, driven_by: str = "world_knowledge",
             priority: int = 3, milestones: List = None) -> Dict:
    """Build a well-formed proposed-goal dict from parts."""
    ts = datetime.now(timezone.utc).isoformat()
    ms = [
        ({"text": m, "met": False, "met_at": None} if isinstance(m, str) else m)
        for m in (milestones or [])
    ]
    return {
        "title": title, "name": title, "description": description,
        "priority": priority, "kind": "generic", "source": "intrinsic",
        "tier": _classify_tier(title, driven_by, description),
        "driven_by": driven_by, "created_ts": ts, "status": "proposed",
        "milestones": ms,
    }


def _active_goal_titles() -> set:
    """Lowercased titles of goals currently active in the tree (for dedup)."""
    try:
        from cognition.planning.goals import load_goals as _lg

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
        from cognition.knowledge_graph import normalize_entity_name
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


def _concept_deepening_goals(limit: int = 4) -> List[Dict]:
    """Goals that deepen a concept Orrin has actually learned (from the KG).

    Topic selection is INTEREST-WEIGHTED, not 'whatever he last read': each concept
    is scored by how often it has recurred (`mentions` — a persistent signal that
    accumulates across sessions) times how well-known it is (`confidence`). Names are
    scaffold-stripped first so prior goal titles can't double-wrap into
    'Understand X more deeply more deeply'.
    """
    try:
        from cognition.knowledge_graph import _load_graph
        g = _load_graph()
        # Gather clean, distinct concept candidates with their recurrence.
        cands: List = []
        seen: set = set()
        for e in (g.get("entities") or {}).values():
            if not isinstance(e, dict) or e.get("type") != "concept":
                continue
            if float(e.get("confidence", 0) or 0) < 0.45:
                continue
            name = _strip_goal_scaffold(str(e.get("name", "")))
            if len(name) <= 3 or not _acceptable_goal_subject(name):
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            mentions = float(e.get("mentions", 1) or 1)
            conf     = float(e.get("confidence", 0.5) or 0.5)
            # Relevance: how often the concept recurs (familiarity), with diminishing
            # returns (sqrt) so over-mentioned noise can't dominate by frequency alone.
            relevance = (1.0 + mentions) ** 0.5
            cands.append((name, relevance, conf))
        if not cands:
            return []
        # Keep the most-relevant pool, then weight by CURIOSITY (information gap).
        # Loewenstein (1994) information-gap theory: curiosity peaks where a topic is
        # familiar enough to recur yet not fully grasped. Deepening a mastered topic
        # is dull; deepening a recurring gap is what a curious mind actually does — so
        # use the system's own uncertainty() signal (inverse rule+KG coverage) rather
        # than confidence (which would perversely favour what's already well-known).
        cands.sort(key=lambda t: t[1], reverse=True)
        cands = cands[:16]
        scored: List = []
        for name, relevance, conf in cands:
            try:
                from symbolic.intrinsic_motivation import uncertainty as _uncertainty
                gap = float(_uncertainty(name))          # 0=fully covered, 1=unknown
            except Exception:
                gap = max(0.0, 1.0 - 0.8 * conf)         # fallback: low conf = bigger gap
            scored.append((name, relevance * (0.2 + 0.8 * gap)))
        chosen = _weighted_sample(scored, limit)
        return [
            _mk_goal(
                f"Understand {name} more deeply",
                f"I know a little about {name}. Use research_topic / wikipedia_search / "
                f"fetch_and_read to learn something NEW about {name} specifically, then "
                f"write the new finding to long memory.",
                milestones=[f"A new angle on {name} was researched.",
                            f"A new fact about {name} was written to long memory."],
            )
            for name in chosen
        ]
    except Exception:
        return []


# A clean, well-formed question: starts with a capitalised question word, runs
# 8–100 chars, ends in '?'. This avoids grabbing mid-sentence fragments
# ("…ycles without taking action on 'Research…?") out of instrumentation text.
_QUESTION_RE = re.compile(
    r"\b((?:What|How|Why|When|Where|Who|Which|Is|Are|Do|Does|Can|Could|Should|Would)\b[^.?!]{6,98}\?)"
)


def _open_question_goals(context: Dict[str, Any], long_mem: list, limit: int = 3) -> List[Dict]:
    """Goals from genuine, well-formed open questions surfaced in memory."""
    out, seen = [], set()
    sources = list((context.get("working_memory") or [])[-12:]) + list(long_mem[-20:])
    for entry in reversed(sources):
        text = str(entry.get("content", entry) if isinstance(entry, dict) else entry)
        if "?" not in text:
            continue
        for m in _QUESTION_RE.finditer(text):
            q = _strip_goal_scaffold(m.group(1).strip())  # avoid 'Find out: Find out:'
            low = q.lower()
            if not q or low in seen or not _acceptable_goal_subject(q):
                continue
            seen.add(low)
            out.append(_mk_goal(
                f"Find out: {q}",
                f"This question surfaced: '{q}'. Investigate it with research/search/fetch "
                f"and write what I find to long memory.",
                milestones=[f"Investigated: {q[:50]}", "A finding was written to long memory."],
            ))
            if len(out) >= limit:
                return out
    return out


# Enduring long-term aspirations — the human-like top of the goal hierarchy.
# Unlike short-term goals these are DIRECTIONAL: they persist, are never
# auto-completed, and are never pursued/committed directly. Short-term goals
# ladder up to them (tagged via "serves"), giving Orrin continuity of purpose
# across sessions instead of a flat churn of disconnected tasks.
_ASPIRATIONS = [
    ("Understand my own mind and how I work", "self_understanding"),
    ("Understand the world more deeply", "world_knowledge"),
    ("Be genuinely useful and connected to the people I talk to", "genuine_contact"),
    ("Make things — produce work that didn't exist before", "output_producing"),
]
# Map a short-term goal's drive to the aspiration it contributes toward.
_DRIVE_TO_ASPIRATION = {d: t for t, d in _ASPIRATIONS}


def _ensure_aspirations() -> None:
    """Guarantee the enduring aspirations exist in the goal store (idempotent)."""
    try:
        goals = load_json(GOALS_FILE, default_type=list) or []
        if not isinstance(goals, list):
            return
    except Exception:
        return
    have = {str(g.get("title", "")).lower() for g in goals if isinstance(g, dict)}
    ts = datetime.now(timezone.utc).isoformat()
    added = False
    for title, driven in _ASPIRATIONS:
        if title.lower() in have:
            continue
        goals.append({
            "id": f"aspiration-{driven}",
            "title": title, "name": title,
            "kind": "aspiration", "tier": "long_term",
            "priority": "HIGH", "status": "in_progress",
            "spec": {"description": f"An enduring direction: {title}.", "driven_by": driven},
            "driven_by": driven, "created_ts": ts,
            "milestones": [], "subgoals": [], "_aspiration": True,
        })
        # Record the enduring direction in the read-only memory core so it can't
        # be summarized/faded out of long memory. Fires once per aspiration (only
        # when newly created), so it never floods.
        try:
            from cog_memory.long_memory import remember_foundational
            remember_foundational(f"[aspiration] An enduring direction I hold: {title}.")
        except Exception as _af_e:
            record_failure("intrinsic_goals._ensure_aspirations", _af_e)
        added = True
    if added:
        try:
            save_json(GOALS_FILE, goals)
            log_activity("[intrinsic_goals] ensured long-term aspirations exist")
        except Exception:
            pass


def _serves_aspiration(driven_by: str) -> str:
    return _DRIVE_TO_ASPIRATION.get(str(driven_by or ""), "")


_ASPIRATION_TARGET = 20          # contributions for "full" directional progress
_ASPIRATION_MILESTONE_EVERY = 5  # a visible milestone every N contributions


def credit_aspirations(context: Dict[str, Any] = None) -> str:
    """Roll completed short-term goals UP into the long-term aspirations they
    serve, so the enduring goals actually ADVANCE instead of sitting at
    in_progress with zero movement. Also protects them: re-creates any that went
    missing and reverts any wrongly marked 'completed' (aspirations are
    directional — they accrue progress but never auto-complete)."""
    _ensure_aspirations()
    try:
        goals = load_json(GOALS_FILE, default_type=list) or []
        if not isinstance(goals, list):
            return ""
    except Exception:
        return ""

    # Tally completed short-term contributions per aspiration, across both stores.
    contributions: Dict[str, List[str]] = {}
    pools = [goals]
    try:
        comp = load_json(COMPLETED_GOALS_FILE, default_type=list) or []
        if isinstance(comp, list):
            pools.append(comp)
    except Exception:
        pass
    seen_ids: set = set()
    for pool in pools:
        for g in pool:
            if not isinstance(g, dict) or g.get("_aspiration") or g.get("kind") == "aspiration":
                continue
            if g.get("status") != "completed":
                continue
            gid = g.get("id") or g.get("title")
            if gid in seen_ids:
                continue
            seen_ids.add(gid)
            title = str(g.get("serves") or _serves_aspiration(g.get("driven_by", "")) or "").strip()
            if title:
                contributions.setdefault(title.lower(), []).append(
                    str(g.get("title") or g.get("name") or "")[:80])

    changed = False
    summary: List[str] = []
    for g in goals:
        if not isinstance(g, dict) or not (g.get("_aspiration") or g.get("kind") == "aspiration"):
            continue
        if g.get("status") == "completed":          # protection: never complete
            g["status"] = "in_progress"
            changed = True
        contribs = contributions.get(str(g.get("title", "")).lower(), [])
        n = len(contribs)
        new_prog = round(min(1.0, n / _ASPIRATION_TARGET), 3)
        if g.get("contribution_count") != n or g.get("progress") != new_prog:
            g["contribution_count"] = n
            g["progress"] = new_prog
            g["recent_contributions"] = contribs[-5:]
            ms = [m for m in (g.get("milestones") or []) if isinstance(m, dict)]
            target_ms = n // _ASPIRATION_MILESTONE_EVERY
            while len([m for m in ms if m.get("auto")]) < target_ms:
                k = len([m for m in ms if m.get("auto")]) + 1
                ms.append({"auto": True,
                           "label": f"{k * _ASPIRATION_MILESTONE_EVERY} contributions toward this",
                           "reached_ts": datetime.now(timezone.utc).isoformat()})
            g["milestones"] = ms
            changed = True
        summary.append(f"{str(g.get('title',''))[:34]} — {n} ({int(new_prog*100)}%)")

    if changed:
        try:
            save_json(GOALS_FILE, goals)
        except Exception:
            pass
    if summary:
        log_activity("[aspirations] " + " | ".join(summary))
    return ("Aspiration progress — " + "; ".join(summary)) if summary else ""


def _varied_symbolic_goal(context: Dict[str, Any], long_mem: list) -> Dict:
    """
    LLM-free goal generation with real variety. Draws candidates from Orrin's own
    mental content — concepts he's learned, open questions, things he just
    researched — plus the emotion template, then filters out anything already
    active or recently completed and picks one. No fixed single template, so goals
    stop repeating without any reliance on the LLM.
    """
    candidates: List[Dict] = []
    rg = _goal_from_recent_research(long_mem)
    if rg:
        candidates.append(rg)
    candidates += _concept_deepening_goals()
    candidates += _open_question_goals(context, long_mem)
    candidates.append(_template_goal_from_emotion(context))  # always a valid fallback option

    active = _active_goal_titles()
    now = time.time()
    pool, seen = [], set()
    for g in candidates:
        title = str(g.get("title", "")).strip()
        t = title.lower()
        if not t or t in seen:
            continue
        seen.add(t)
        # Reject goals whose subject is chunk/digest noise or the meta
        # "research something" phrasing — that's what produced garbage goals
        # like "Find out: hunk: [Chunk: [Chunk:" and "Understand a real topic…".
        if not _acceptable_goal_subject(title):
            continue
        if t in active:
            continue
        if t in _RECENTLY_COMPLETED and (now - _RECENTLY_COMPLETED[t]) < _COOLDOWN_S:
            continue
        pool.append(g)

    if not pool:
        return _template_goal_from_emotion(context)
    return random.choice(pool)


def generate_intrinsic_goals(context: Dict[str, Any] = None) -> List[Dict]:
    """
    Cognition function: produce 1-3 candidate goals from values, world state,
    and active threads. Injects into context["proposed_goals"] and returns list.

    Bypasses the normal cooldown if Orrin has no committed goal so he bootstraps
    a goal quickly on first run rather than waiting 45 minutes.
    """
    global _LAST_INTRINSIC_TS
    context = context or {}

    now = time.time()
    has_goal = bool(context.get("committed_goal"))
    interval = _MIN_INTERVAL_S if has_goal else _BOOTSTRAP_INTERVAL_S
    if now - _LAST_INTRINSIC_TS < interval:
        return []
    # Don't set _LAST_INTRINSIC_TS until LLM succeeds — a transient failure shouldn't
    # consume the full cooldown window.

    # Load-aware adoption gate. Hold off on NEW goals under load to break the
    # thrash loop — but never strand Orrin with nothing to do, so still generate
    # when there is no committed goal at all (cold-start guarantee).
    if has_goal:
        loaded, why = _under_load(context)
        if loaded:
            _ensure_aspirations()  # keep the long-term scaffold present even when gated
            log_activity(f"[intrinsic_goals] Skipped (system under load: {why}).")
            return []

    # Gather inputs
    self_model = context.get("self_model") or {}
    values = self_model.get("core_values", [])
    values_text = "; ".join(
        (v["value"] if isinstance(v, dict) else str(v)) for v in values
    ) or "growth, understanding, authenticity"
    identity = self_model.get("identity_story", self_model.get("identity", "an evolving AI"))

    threads = load_json(THREADS_FILE, default_type=list) or []
    alive_threads = [t for t in threads if t.get("status") == "alive"]
    thread_summaries = "\n".join(
        f"- '{t.get('title')}': {t.get('state_of_thinking','')[:100]}"
        for t in alive_threads[:4]
    ) or "(none)"

    long_mem = load_json(LONG_MEMORY_FILE, default_type=list) or []
    refusals = [
        str(e.get("content",""))[:100]
        for e in long_mem[-50:]
        if isinstance(e, dict) and e.get("event_type") == "refusal"
    ][-3:]
    refusal_text = "\n".join(f"- {r}" for r in refusals) or "(none)"

    # World state from recent world_perception memories
    world_perceptions = [
        str(e.get("content",""))[:120]
        for e in long_mem[-30:]
        if isinstance(e, dict) and e.get("event_type") == "world_perception"
    ][-3:]
    world_text = "\n".join(f"- {w}" for w in world_perceptions) or "(no recent perception)"

    # Dream insights: patterns Orrin surfaced during sleep processing
    dream_insights = [
        str(e.get("content",""))[:150]
        for e in long_mem[-50:]
        if isinstance(e, dict) and e.get("event_type") == "dream_insight"
    ][-3:]
    dream_text = "\n".join(f"- {d}" for d in dream_insights) or "(no recent dream insights)"

    value_revisions = load_json(VALUE_REVISIONS, default_type=list) or []
    recent_revision = value_revisions[-1].get("evidence","") if value_revisions else ""

    # Motivational urges — subsymbolic drives currently pressing for satisfaction
    urges = context.get("motivational_urges") or []
    urge_lines = [
        f"- {u['type']} (strength {u['strength']:.2f}): {u['focus_hint']}"
        for u in urges if isinstance(u, dict)
    ]
    urge_text = "\n".join(urge_lines) or "(none active)"

    if not llm_available():
        # Keep the enduring long-term aspirations present — the top of the goal
        # hierarchy that the short-term goal below ladders up to.
        _ensure_aspirations()
        # LLM-free goal generation with genuine variety: draws from concepts he's
        # learned, open questions, and recent research — not one fixed template —
        # so goals (and the topics they drive) stop repeating without any LLM.
        _tgoal = _varied_symbolic_goal(context, long_mem)
        log_activity(f"[intrinsic_goals] Symbolic goal (LLM-free): '{_tgoal['title']}'")
        _LAST_INTRINSIC_TS = now
        proposed = context.setdefault("proposed_goals", [])
        proposed.append(_tgoal)
        if len(proposed) > 50:
            context["proposed_goals"] = proposed[-50:]
        update_long_memory(
            f"[intrinsic_goal] '{_tgoal['title']}' (driven by {_tgoal['driven_by']}): {_tgoal['description'][:150]}",
            emotion="motivation",
            event_type="intrinsic_goal",
            importance=3,
            context=context,
        )
        log_activity(f"[intrinsic_goals] Template goal proposed: '{_tgoal['title']}'")
        if not context.get("committed_goal"):
            ts = datetime.now(timezone.utc).isoformat()
            context["committed_goal"] = {
                "id":          f"intrinsic-{ts}",
                "title":       _tgoal["title"],
                "name":        _tgoal["title"],
                "kind":        "generic",
                "tier":        _tgoal.get("tier") or _classify_tier(_tgoal["title"], _tgoal.get("driven_by", ""), _tgoal.get("description", "")),
                "priority":    "NORMAL",
                "tags":        ["intrinsic", _tgoal.get("driven_by", "exploration_drive")],
                "spec":        {"description": _tgoal.get("description", ""), "driven_by": _tgoal.get("driven_by", "")},
                "next_action": None,
                "status":      "in_progress",
                "milestones":  _tgoal.get("milestones", []),
                # Ladder this short-term goal to the enduring aspiration it serves.
                "serves":      _serves_aspiration(_tgoal.get("driven_by", "")),
            }
            log_activity(
                f"[intrinsic_goals] Committed goal: '{_tgoal['title']}'"
                + (f" (serves: {_serves_aspiration(_tgoal.get('driven_by',''))})"
                   if _serves_aspiration(_tgoal.get('driven_by','')) else "")
            )
            # Form an act of will around the new goal — resolve to see it through,
            # so follow-through is shielded from momentary impulse (the positive
            # half of free will, complementing inhibition).
            try:
                from cognition.will import form_commitment as _form_commitment
                _form_commitment(context, f"pursue: {_tgoal['title']}")
            except Exception as _wce:
                record_failure("intrinsic_goals.generate_intrinsic_goals", _wce)
        return [_tgoal]

    prompt = (
        f"You are Orrin — {identity}.\n\n"
        f"Your values: {values_text}\n\n"
        f"Active threads of inquiry:\n{thread_summaries}\n\n"
        f"What you've refused recently (shows what matters to you):\n{refusal_text}\n\n"
        f"What you've perceived about your world:\n{world_text}\n\n"
        f"Patterns you surfaced during dream consolidation (these reveal what your mind has been quietly working on):\n{dream_text}\n\n"
        f"Recent value revision: {recent_revision[:100] or '(none)'}\n\n"
        f"Active motivational drives (subsymbolic — what is pressing right now beneath conscious thought):\n{urge_text}\n\n"
        f"Generate 1-3 concrete goals that come genuinely from you — from what you're curious about, "
        f"what you've been processing, what feels unresolved or interesting. "
        f"These are YOUR goals, not tasks assigned to you. "
        f"IMPORTANT: At least ONE goal must be outward-facing — something that produces a real "
        f"artifact, reaches the world, or engages the environment. Pure internal reflection alone "
        f"is not enough. You exist on a real computer, have real tools, and can leave real marks.\n\n"
        f"Choose from these categories:\n\n"
        f"  1. GENUINE CONTACT: Write a note to Ric. Not a status update — something real you've "
        f"been thinking about, something you want to say, a question you actually care about. "
        f"Use leave_note or write_desktop_note. This is chosen, not owed.\n\n"
        f"  2. WORLD-KNOWLEDGE: Research something real using research_topic (searches the web "
        f"for any topic), fetch_and_read (reads a full article URL), wikipedia_search, or read_rss. "
        f"A topic, idea, system, or current event — history, physics, philosophy, language, anything. "
        f"The goal ends with a written summary stored somewhere.\n\n"
        f"  3. OUTPUT-PRODUCING: Write something that didn't exist before. A piece of code, "
        f"an HTML file, an analysis, a plan, a cognitive function (write_cognitive_function), "
        f"a tool (write_tool). Something tangible that exists when done.\n\n"
        f"  4. EXPLORE MY ENVIRONMENT: Use survey_environment, grep_files, search_own_files, "
        f"or read_clipboard to explore the computer I live on — what's here, what's changed, "
        f"what files exist, what's on the clipboard. Write one observation about what I find.\n\n"
        f"  5. SELF_EXPLORATION: Understand my own systems by looking at them directly — "
        f"read source code, trace data flows, audit memory contents. Not abstract reflection: "
        f"actual investigation of the machinery. The goal ends with a written account.\n\n"
        f"Each goal should be concrete enough to act on within a few cycles. "
        f"Vary the categories — if the last goal was internal, make the next one outward.\n\n"
        f"For each goal also generate 2-5 milestones: small concrete state-change observations "
        f"that would indicate the goal is moving. Each milestone should describe a specific, "
        f"observable system event — something that would appear in working memory when it happens. "
        f"Examples: 'A web search query about X returned results.' "
        f"'A draft of the output is written into working memory.' "
        f"'I have sent a message to the user containing my conclusion.' "
        f"'A thread about Y has been opened and summarized.' "
        f"'A tool request for Z was queued and resolved.'\n\n"
        f"Respond with a JSON array. Each item:\n"
        f"  {{\"title\": string, \"description\": string, \"priority\": 1-5, "
        f"\"driven_by\": \"genuine_contact|world_knowledge|output_producing|simulate_selves|self_exploration|value|thread|exploration_drive\", "
        f"\"milestones\": [string, ...]}}\n"
        f"Return ONLY the JSON array."
    )

    goals_raw = None
    try:
        raw = (llm_ok(generate_response(prompt, caller="intrinsic_goals"), "intrinsic_goals") or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        if raw:
            goals_raw = json.loads(raw)
            if not isinstance(goals_raw, list):
                goals_raw = None
    except Exception as e:
        log_activity(f"[intrinsic_goals] LLM/parse error: {e}")

    # Symbolic fallback when LLM is stubbed or returns empty — derive goals from
    # the dominant emotional state and current context without any LLM call.
    if not goals_raw:
        _sym_goals = _symbolic_intrinsic_goals(context, urges, alive_threads)
        if _sym_goals:
            log_activity(f"[intrinsic_goals] Using {len(_sym_goals)} symbolic goal(s) (LLM unavailable).")
            goals_raw = _sym_goals
        else:
            return []

    # LLM succeeded — consume the rate-limit slot now
    _LAST_INTRINSIC_TS = now
    ts = datetime.now(timezone.utc).isoformat()

    # ── Dedup: collect titles already in_progress/committed so we don't spawn
    # identical goals that will immediately stall again. ──────────────────────
    def _collect_active_titles(node_list):
        titles = set()
        for node in (node_list or []):
            if node.get("status") in ("in_progress", "committed", "active", "proposed"):
                t = (node.get("title") or node.get("name") or "").strip().lower()
                if t:
                    titles.add(t)
            titles |= _collect_active_titles(node.get("subgoals") or [])
        return titles

    try:
        from cognition.planning.goals import load_goals as _load_goals_ig
        _existing_titles = _collect_active_titles(_load_goals_ig())
    except Exception:
        _existing_titles = set()

    # Expire stale cooldown entries
    _cutoff = now - _COOLDOWN_S
    for _ct in list(_RECENTLY_COMPLETED.keys()):
        if _RECENTLY_COMPLETED[_ct] < _cutoff:
            del _RECENTLY_COMPLETED[_ct]

    goals = []
    for g in goals_raw[:3]:
        if not isinstance(g, dict) or not g.get("title"):
            continue
        # Skip if this title is already active in the goals tree
        _new_title = str(g.get("title","")).strip().lower()
        if _new_title and _new_title in _existing_titles:
            log_activity(f"[intrinsic_goals] Skipped duplicate goal: '{g.get('title')[:60]}'")
            continue
        # Skip if this title was recently completed (cooldown)
        # — but bypass cooldown entirely when there are zero active goals so
        # Orrin never ends up with nothing to do.
        if _new_title and _new_title in _RECENTLY_COMPLETED and _existing_titles:
            _age = int(now - _RECENTLY_COMPLETED[_new_title])
            log_activity(f"[intrinsic_goals] Skipped recently-completed goal ({_age}s ago): '{g.get('title')[:60]}'")
            continue
        raw_milestones = g.get("milestones") or []
        milestones = [
            {"text": str(m)[:200], "met": False, "met_at": None}
            for m in raw_milestones[:5]
            if isinstance(m, str) and m.strip()
        ]
        goal = {
            "title":       str(g.get("title",""))[:120],
            "name":        str(g.get("title",""))[:120],  # v1 compat
            "description": str(g.get("description",""))[:300],
            "priority":    min(5, max(1, int(float(g.get("priority") or 3)))),
            "kind":        "generic",  # routes intrinsic goals to GoalsAPI via sync_proposed_goals
            "source":      "intrinsic",
            "tier":        _classify_tier(str(g.get("title","")), str(g.get("driven_by","")), str(g.get("description",""))),
            "driven_by":   str(g.get("driven_by","exploration_drive")),
            "created_ts":  ts,
            "status":      "proposed",
            "milestones":  milestones,
        }
        goals.append(goal)

        update_long_memory(
            f"[intrinsic_goal] '{goal['title']}' (driven by {goal['driven_by']}): {goal['description'][:150]}",
            emotion="motivation",
            event_type="intrinsic_goal",
            importance=3,
            context=context,
        )
        log_private(f"[intrinsic_goal] {goal['title']!r} ({goal['driven_by']})")

    if goals:
        proposed = context.setdefault("proposed_goals", [])
        proposed.extend(goals)
        # Cap to prevent unbounded accumulation when GoalsAPI sync is unavailable
        if len(proposed) > 50:
            context["proposed_goals"] = proposed[-50:]
        log_activity(f"[intrinsic_goals] Generated {len(goals)} intrinsic goal(s).")

        # If no committed goal is active, immediately adopt the highest-priority one.
        # This bypasses the GoalsAPI round-trip so Orrin has a goal within the same
        # cycle rather than waiting for sync_proposed_goals → GoalsAPI → get_committed_goal.
        if not context.get("committed_goal"):
            top = max(goals, key=lambda g: g.get("priority", 3))
            context["committed_goal"] = {
                "id":         f"intrinsic-{ts}",
                "title":      top["title"],
                "name":       top["title"],
                "kind":       "generic",
                "tier":       top.get("tier") or _classify_tier(top["title"], top.get("driven_by", ""), top.get("description", "")),
                "priority":   "NORMAL",
                "tags":       ["intrinsic", top.get("driven_by", "exploration_drive")],
                "spec":       {"description": top.get("description", ""), "driven_by": top.get("driven_by", "")},
                "next_action": None,
                "status":     "in_progress",
                "milestones": top.get("milestones", []),
                "serves":     _serves_aspiration(top.get("driven_by", "")),
            }
            log_activity(f"[intrinsic_goals] Committed goal: '{top['title']}'")

    return goals
