# brain/cognition/intrinsic_goals.py
# Orrin generates goals that come from inside — from his values, world state,
# active threads, and refusal patterns — not from external prompts.
# Goals are marked source="intrinsic" and injected into context["proposed_goals"]
# for goal_io to pick up. Runs from dream cycle on slower cadence.
from __future__ import annotations
from brain.core.runtime_log import get_logger

import json
import random
import re
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from brain.utils.generate_response import generate_response, llm_ok
from brain.utils.log import log_activity, log_private
from brain.utils.json_utils import load_json, save_json
from brain.cog_memory.long_memory import update_long_memory
from brain.paths import (
    THREADS_FILE, LONG_MEMORY_FILE, VALUE_REVISIONS, COMPLETED_GOALS_FILE,
    RECENTLY_COMPLETED_FILE,
    ENERGY_MODE_FILE, BODY_SENSE_FILE, DATA_DIR,
)
from brain.utils.llm_gate import llm_callable_by
from brain.utils.failure_counter import record_failure
# The aspiration subsystem was extracted to intrinsic_aspirations.py (Phase 4.5C).
# Re-imported here so the generators/commit-selection below + external callers
# (finalize.credit_aspirations, goals.mark_aspiration_contribution) keep their
# existing `from …intrinsic_goals import …` paths.
from brain.cognition.intrinsic_aspirations import (  # noqa: F401
    credit_aspirations, aspiration_pressure, mark_aspiration_contribution,
    _serves_aspiration, _fairness_default_drive, _ensure_aspirations,
    _ASPIRATIONS, _DRIVE_TO_ASPIRATION,
)
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
# NOTE: the narrow _SYMBOLIC_GOAL_SEEDS table and _symbolic_intrinsic_goals()
# fallback were removed (Goal Origination Fix Plan, Phase 1 / Fix A). Both the
# LLM-disabled branch and the LLM-empty fallback now route through the rich
# _varied_symbolic_goal() path (KG concepts + open questions + recent research),
# so the default tool-only deployment no longer degrades to a fixed seed title.


# NOTE: the fixed emotion/note goal templates (_EMOTION_GOAL_TEMPLATES,
# _DEFAULT_EMOTION_GOAL_TEMPLATE) and _template_goal_from_emotion() were removed.
# LLM-free origination now draws ONLY from real mental content via
# _varied_symbolic_goal(); when there's nothing real to pursue it originates
# nothing rather than emitting a canned note. This is what stopped the goal tree
# from collapsing onto 'leave a note' goals.


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


def _concept_deepening_goals(limit: int = 4) -> List[Dict]:
    """Goals that deepen a concept Orrin has actually learned (from the KG).

    Topic selection is INTEREST-WEIGHTED, not 'whatever he last read': each concept
    is scored by how often it has recurred (`mentions` — a persistent signal that
    accumulates across sessions) times how well-known it is (`confidence`). Names are
    scaffold-stripped first so prior goal titles can't double-wrap into
    'Understand X more deeply more deeply'.
    """
    try:
        from brain.cognition.knowledge_graph import _load_graph
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
                from brain.symbolic.intrinsic_motivation import uncertainty as _uncertainty
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
                driven_by="world_knowledge",
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
            # Title is noun-phrased ("Open question: …") so it survives the
            # _acceptable_goal_subject title-filter in _varied_symbolic_goal — a
            # leading imperative ("Find out: …") is rejected there as a verb-phrase.
            out.append(_mk_goal(
                f"Open question: {q}",
                f"This question surfaced: '{q}'. Investigate it with research/search/fetch "
                f"and write what I find to long memory.",
                driven_by="world_knowledge",
                milestones=[f"Investigated: {q[:50]}", "A finding was written to long memory."],
            ))
            if len(out) >= limit:
                return out
    return out


# ── Phase 2 / Fix B: goals sourced from learned structure and from his own history.
# These widen origination past research/concept/question so a goal reads less like a
# lookup and more like "wanting something specific." Each returns List[Dict] via
# _mk_goal and is wired into _varied_symbolic_goal's candidate pool, where the
# existing dedup / cooldown / _acceptable_goal_subject filters already gate them.

# A best-known cause weaker than this is a genuine hole in the learned causal model.
_CAUSAL_LEAD_MIN_SCORE = 0.50


def _causal_frontier_goals(limit: int = 2) -> List[Dict]:
    """Goals from holes in the LEARNED CAUSAL MODEL.

    For each outcome Orrin has actually observed, if even his best-known cause is
    weak (causal_score below _CAUSAL_LEAD_MIN_SCORE), the cause is a genuine gap —
    so investigating what really brings that outcome about is a goal that emerges
    from the structure of what he's learned, not from an affect bucket. (Newell &
    Simon means-ends: the gap itself is the motivation.)
    """
    try:
        from brain.symbolic.causal_graph import get_all_edges
        edges = get_all_edges()
    except Exception:
        return []
    # Group edges by effect; keep the best (max) causal_score and total evidence.
    by_effect: Dict[str, Dict] = {}
    for e in edges:
        if not isinstance(e, dict):
            continue
        # Causal effects can be multi-clause traces ("X; goal recedes; Y rises").
        # Keep the first clause so the goal subject is one picturable thing.
        raw = re.split(r"[;—]| - ", str(e.get("effect", "")))[0]
        effect = _strip_goal_scaffold(raw.strip())[:70].strip()
        if len(effect) <= 3 or not _acceptable_goal_subject(effect):
            continue
        score = float(e.get("causal_score", 0) or 0)
        ev    = float(e.get("evidence_count", 0) or 0)
        slot = by_effect.setdefault(effect.lower(), {"name": effect, "best": 0.0, "ev": 0.0})
        slot["best"] = max(slot["best"], score)
        slot["ev"]  += ev
    # Frontiers: outcomes with a weak best-known cause, weighted by how much
    # evidence (recurrence) they carry — a recurring outcome he can't yet explain
    # is the strongest pull. The (min - best) term makes a bigger gap weigh more.
    frontiers = [
        (s["name"], (1.0 + s["ev"]) ** 0.5 * (_CAUSAL_LEAD_MIN_SCORE - s["best"]))
        for s in by_effect.values()
        if 0.0 < s["best"] < _CAUSAL_LEAD_MIN_SCORE
    ]
    if not frontiers:
        return []
    return [
        _mk_goal(
            f"The causes of {name}",
            f"My causal model says I've seen '{name}' happen but I don't really know "
            f"what causes it. Use research_topic / wikipedia_search / fetch_and_read to "
            f"investigate what actually brings '{name}' about, then write what I learn "
            f"to long memory.",
            driven_by="world_knowledge",
            milestones=[f"A possible cause of '{name}' was investigated.",
                        f"A finding about what brings '{name}' about was written to long memory."],
        )
        for name in _weighted_sample(frontiers, limit)
    ]


def _tension_goals(context: Dict[str, Any], limit: int = 1) -> List[Dict]:
    """Goals from an internal contradiction — a conflicting belief/rule pair he holds.

    Fully symbolic: reads contradictions he's already logged and scans his own
    rules + self-model (detect_rule_contradictions), never the LLM. Provenance is
    internal and specific — "resolve whether X or Y", not a generic prompt.
    """
    out: List[Dict] = []
    seen: set = set()

    # 1. Concrete contradictions previously logged to disk (specific summaries).
    try:
        from brain.paths import CONTRADICTIONS_FILE
        for block in reversed((load_json(CONTRADICTIONS_FILE, default_type=list) or [])[-5:]):
            items = block.get("contradictions", []) if isinstance(block, dict) else []
            for c in items:
                summary = str((c or {}).get("summary", "")).strip()
                low = summary.lower()
                if not summary or low in seen or not _acceptable_goal_subject(summary):
                    continue
                seen.add(low)
                out.append(_mk_goal(
                    f"Resolve the tension: {summary[:80]}",
                    f"I noticed a contradiction in my own thinking: '{summary}'. Work out "
                    f"which side I actually hold — reason it through, check it against what "
                    f"I know, and write the resolution to long memory.",
                    driven_by="self_exploration",
                    milestones=[f"The two sides of '{summary[:50]}' were laid out.",
                                "A resolution was reasoned and written to long memory."],
                ))
                if len(out) >= limit:
                    return out
    except Exception as exc:
        record_failure("intrinsic_goals.contradiction_file_goals", exc)

    # 2. Symbolic rule/belief conflicts (no LLM, no persisted file required).
    try:
        from brain.symbolic.symbolic_cognition import detect_rule_contradictions
        for c in detect_rule_contradictions(context.get("self_model") or {}):
            if c.get("type") != "belief_rule_conflict":
                continue
            belief = str(c.get("belief", "")).strip()
            low = belief.lower()
            if not belief or low in seen or not _acceptable_goal_subject(belief):
                continue
            seen.add(low)
            out.append(_mk_goal(
                f"Work out whether I really hold: {belief[:80]}",
                f"Some of my rules push against the belief '{belief}'. Examine whether I "
                f"actually hold it — weigh the conflicting rules, decide, and record the "
                f"conclusion in long memory.",
                driven_by="self_exploration",
                milestones=[f"The conflict around '{belief[:50]}' was examined.",
                            "A decision was written to long memory."],
            ))
            if len(out) >= limit:
                return out
    except Exception as exc:
        record_failure("intrinsic_goals.symbolic_conflict_goals", exc)
    return out


def _autobiographical_continuity_goals(limit: int = 2) -> List[Dict]:
    """Goals from his own history — a thread he hasn't advanced in a while.

    This is the "specific thing you can picture" the critique says origination was
    missing: a concrete next step on an inquiry he already started, sourced from
    threads.json rather than a fresh affect bucket.
    """
    out: List[Dict] = []
    active = _active_goal_titles()
    try:
        threads = load_json(THREADS_FILE, default_type=list) or []
    except Exception:
        return []
    alive = [t for t in threads if isinstance(t, dict) and t.get("status") == "alive"]
    # Oldest-touched first — the threads most at risk of silently dropping.
    alive.sort(key=lambda t: str(t.get("last_touched_ts", "")))
    for t in alive:
        title = str(t.get("title", "")).strip()
        if not title or not _acceptable_goal_subject(title):
            continue
        gtitle = f"Pick up my thread on {title}"
        if gtitle.lower() in active:
            continue
        state = str(t.get("state_of_thinking", "")).strip()[:200]
        out.append(_mk_goal(
            gtitle,
            f"I've had an open thread on '{title}' that I haven't advanced lately. "
            f"Where I left off: {state or '(no notes yet)'}. Take it one concrete step "
            f"further and write the new state to long memory.",
            driven_by="world_knowledge",
            milestones=[f"The thread on '{title[:50]}' was reopened.",
                        "One new observation advanced it, written to long memory."],
        ))
        if len(out) >= limit:
            break
    return out




# ── Intake → output laddering (P5 / G2) ────────────────────────────────────────
# Completing an "Understand X" intake goal should ladder INTO making something
# with X, not loop back into re-understanding X. note_intake_completed queues the
# topic; _making_goals drains it first.
_MAKING_BACKLOG_FILE = DATA_DIR / "making_backlog.json"
_MAKING_BACKLOG_CAP = 20


def note_intake_completed(topic: str) -> None:
    topic = _strip_goal_scaffold(str(topic or "")).strip()
    if not topic or not _acceptable_goal_subject(topic):
        return
    try:
        backlog = load_json(_MAKING_BACKLOG_FILE, default_type=list) or []
        if not isinstance(backlog, list):
            backlog = []
        low = topic.lower()
        backlog = [b for b in backlog if isinstance(b, dict)
                   and str(b.get("topic", "")).lower() != low]
        backlog.append({"topic": topic, "ts": datetime.now(timezone.utc).isoformat()})
        save_json(_MAKING_BACKLOG_FILE, backlog[-_MAKING_BACKLOG_CAP:])
    except Exception as _e:
        record_failure("intrinsic_goals.note_intake_completed", _e)


def _drain_making_backlog(topic: str) -> None:
    """Remove a topic from the backlog once a making goal for it is generated."""
    low = str(topic or "").strip().lower()
    if not low:
        return
    try:
        backlog = load_json(_MAKING_BACKLOG_FILE, default_type=list) or []
        kept = [b for b in backlog if isinstance(b, dict)
                and str(b.get("topic", "")).lower() != low]
        if len(kept) != len(backlog):
            save_json(_MAKING_BACKLOG_FILE, kept)
    except Exception:
        pass


def _making_goals(context: Dict[str, Any], long_mem: list, limit: int = 2) -> List[Dict]:
    """P5: emit `output_producing` goals whose completion test is an ARTIFACT (P2).

    Seeded from what Orrin ALREADY has — the laddering backlog (topics he just
    learned) and recent research findings — so making is the natural next step
    after intake, not a cold task. The artifact (a written synthesis / note with
    novel content) is producible OFFLINE, so 'make things' can't silently collapse
    back into empty notes in the native-LM deployment (Guard: offline-degradation).
    """
    topics: List[str] = []
    try:
        backlog = load_json(_MAKING_BACKLOG_FILE, default_type=list) or []
        for b in reversed(backlog if isinstance(backlog, list) else []):
            t = _strip_goal_scaffold(str((b or {}).get("topic", ""))).strip()
            if t and _acceptable_goal_subject(t):
                topics.append(t)
    except Exception:
        pass
    if len(topics) < limit:
        try:
            for entry in reversed(list(long_mem or [])[-30:]):
                content = str(entry.get("content", entry) if isinstance(entry, dict) else entry)
                m = _RESEARCH_FINDING_RE.search(content)
                if m:
                    t = _strip_goal_scaffold(m.group(1).strip())[:70].strip()
                    if t and _acceptable_goal_subject(t):
                        topics.append(t)
        except Exception:
            pass
    seen, uniq = set(), []
    for t in topics:
        k = t.lower()
        if k not in seen:
            seen.add(k)
            uniq.append(t)
    out: List[Dict] = []
    for topic in uniq[:limit]:
        _drain_making_backlog(topic)
        out.append(_mk_goal(
            f"Turn what I know about {topic} into a written synthesis",
            f"I've been learning about {topic}. Make something that didn't exist "
            f"before: write a clear, novel synthesis of what I now understand about "
            f"{topic} — in my own words, connecting at least two things I know — and "
            f"deliver it as a note / write it to long memory. A real artifact, not a "
            f"restatement of one fact.",
            driven_by="output_producing",
            requires_artifact=True,
            milestones=[f"A novel synthesis about '{topic[:50]}' was produced and delivered."],
        ))
    return out


def _contact_goals(context: Dict[str, Any], long_mem: list, limit: int = 1) -> List[Dict]:
    """P5: emit `genuine_contact` goals keyed to a present/recent person. Silent
    when no peer is around (like the other generators when their pool is empty)."""
    ctx = context or {}
    recent_user = bool(ctx.get("user_present_recent")) or bool(str(ctx.get("latest_user_input") or "").strip())
    if not recent_user:
        return []
    out: List[Dict] = []
    unanswered = str(ctx.get("latest_user_input") or "").strip()
    if unanswered:
        out.append(_mk_goal(
            "Answer Ric's last message",
            f"Ric said: '{unanswered[:160]}'. Give a real, useful reply — not a "
            f"deflection — and actually send it.",
            driven_by="genuine_contact",
            requires_artifact=True,
            milestones=["A genuine reply to Ric was composed and delivered."],
        ))
    else:
        topic = None
        try:
            for entry in reversed(list(long_mem or [])[-20:]):
                content = str(entry.get("content", entry) if isinstance(entry, dict) else entry)
                m = _RESEARCH_FINDING_RE.search(content)
                if m:
                    cand = _strip_goal_scaffold(m.group(1).strip())[:60].strip()
                    if cand and _acceptable_goal_subject(cand):
                        topic = cand
                        break
        except Exception:
            topic = None
        if topic:
            out.append(_mk_goal(
                f"Share with Ric what I learned about {topic}",
                f"I recently looked into {topic}. Tell Ric something genuinely "
                f"interesting about it — share a real finding, or ask him a real "
                f"question about it — and send it.",
                driven_by="genuine_contact",
                requires_artifact=True,
                milestones=[f"A message about '{topic[:40]}' was shared with Ric."],
            ))
    return out[:limit]


# Research/web findings are written to long memory by look_outward as
#   "[world_perception] From searching '<query>': <result>"   (a finding), and
#   "[world_perception] I reached outward with a question: <query>"  (the intent).
# These markers let us source a follow-up goal from what Orrin actually went and
# learned, without depending on an `extra`/source field that long_memory.json
# doesn't persist.
_RESEARCH_FINDING_RE = re.compile(r"from searching '([^']{3,140})'\s*:\s*(.*)", re.I | re.S)
_RESEARCH_INTENT_RE = re.compile(r"reached outward with a question:\s*(.{3,140})", re.I)


def _goal_from_recent_research(long_mem: list, scan: int = 30) -> Optional[Dict]:
    """A goal to FOLLOW UP on something Orrin recently went and looked into.

    Scans the most recent long-memory entries for a web/research finding and, if
    one has a clean subject, proposes taking it one concrete step further. Returns
    a single candidate (the caller pools/dedupes/cooldown-gates it) or None when
    there's no recent research worth continuing — originate nothing, not a template.
    """
    try:
        for entry in reversed(list(long_mem or [])[-scan:]):
            content = str(entry.get("content", entry) if isinstance(entry, dict) else entry)
            low = content.lower()
            topic = snippet = ""
            m = _RESEARCH_FINDING_RE.search(content)
            if m:
                topic = _strip_goal_scaffold(m.group(1).strip())
                snippet = " ".join(m.group(2).split())[:200]
            elif "reached outward with a question" in low:
                mi = _RESEARCH_INTENT_RE.search(content)
                if mi:
                    topic = _strip_goal_scaffold(mi.group(1).strip().rstrip("?."))
            topic = topic[:80].strip()
            if not topic or not _acceptable_goal_subject(topic):
                continue
            note = (
                f"I recently looked into '{topic}'"
                + (f" and found: {snippet}. " if snippet else ". ")
                + "Take it one concrete step further — use research_topic / wikipedia_search / "
                "fetch_and_read to learn something NEW about it, then write the new finding to long memory."
            )
            return _mk_goal(
                f"Follow-up on {topic}",
                note,
                driven_by="world_knowledge",
                milestones=[f"A new angle on '{topic[:50]}' was researched.",
                            "A new finding was written to long memory."],
            )
    except Exception:
        return None
    return None


def _varied_symbolic_goal(context: Dict[str, Any], long_mem: list) -> Optional[Dict]:
    """
    LLM-free goal generation with real variety. Draws candidates ONLY from Orrin's
    own mental content — concepts he's learned, open questions, causal-model gaps,
    tensions, his own history — then filters out anything already active or recently
    completed and picks one. Deliberately NO fixed emotion/note template: if there's
    nothing real to pursue this cycle, originate nothing (return None) rather than
    emit a canned note. Callers must handle None by simply not proposing a goal.
    """
    candidates: List[Dict] = []
    rg = _goal_from_recent_research(long_mem)
    if rg:
        candidates.append(rg)
    candidates += _concept_deepening_goals()
    candidates += _open_question_goals(context, long_mem)
    # Phase 2 / Fix B — origination from learned structure and his own history.
    candidates += _causal_frontier_goals()
    candidates += _tension_goals(context)
    candidates += _autobiographical_continuity_goals()
    # P5 — polyculture: making + contact generators so the pool can finally serve
    # ALL FOUR aspirations, not just intake/introspection. These emit artifact-gated
    # output_producing / genuine_contact goals (fail-able via P2).
    candidates += _making_goals(context, long_mem)
    candidates += _contact_goals(context, long_mem)

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
        return None   # nothing real to pursue right now — originate nothing, not a template
    # P3 — bias the pick toward starved aspirations so a 0%-progress direction
    # ("Make things") actually gets recruited instead of losing every uniform draw
    # to the abundant intake candidates.
    try:
        pressure = aspiration_pressure(context)
        if pressure:
            scored = [
                (g, 1.0 + 2.0 * float(pressure.get(_serves_aspiration(str(g.get("driven_by", ""))), 0.0)))
                for g in pool
            ]
            picked = _weighted_sample(scored, 1)
            if picked:
                return picked[0]
    except Exception:
        pass
    return random.choice(pool)


# ── P7: commitment competition (close the self-commit bypass) ──────────────────
# generate_intrinsic_goals used to commit the FIRST goal it produced directly into
# context["committed_goal"], so the competition/arbiter layer was moot and P1's
# gradient + P3's pressure were evaluated AFTER the choice was already locked.
# These helpers let the committed goal be CHOSEN among the live proposals, weighted
# by aspiration pressure + the (rewired) usefulness drive, so an artifact-gated
# production goal can actually win commitment over a cheap intake goal.

def _proposal_commit_score(g: Dict, pressure: Dict[str, float], strengths: Dict[str, float]) -> float:
    drive = str(g.get("driven_by") or "")
    serves = _serves_aspiration(drive)
    score = 1.0 + 2.0 * float(pressure.get(serves, 0.0))
    try:
        score += 0.1 * (float(g.get("priority", 3) or 3) / 3.0)
    except Exception:
        pass
    if drive in ("output_producing", "genuine_contact"):
        score += float(strengths.get("usefulness", 0.0)) * 0.5
    return max(0.0, score)


def _select_commit_proposal(proposals: List[Dict], context: Dict[str, Any]) -> Optional[Dict]:
    cands = [g for g in (proposals or []) if isinstance(g, dict) and g.get("title")]
    if not cands:
        return None
    try:
        pressure = aspiration_pressure(context)
    except Exception:
        pressure = {}
    strengths = {}
    try:
        from brain.cognition.goal_competition import compute_drive_strengths
        strengths = compute_drive_strengths(context) or {}
    except Exception:
        strengths = {}
    scored = [(g, _proposal_commit_score(g, pressure, strengths)) for g in cands]
    picked = _weighted_sample(scored, 1)
    return picked[0] if picked else cands[0]


def _build_committed_goal(g: Dict, gid: str) -> Dict:
    """Build the context committed_goal dict from a proposal — crucially carrying
    requires_artifact / deadline_cycles so P2's artifact gate + deadline survive
    the v1 commit path (the old inline blocks dropped them)."""
    drive = g.get("driven_by", "")
    cg = {
        "id": gid, "title": g["title"], "name": g["title"], "kind": "generic",
        "tier": g.get("tier") or _classify_tier(g["title"], drive, g.get("description", "")),
        "priority": "NORMAL",
        "tags": ["intrinsic", g.get("driven_by", "exploration_drive"), *_zone_tags(g.get("zone", "self"))],
        "zone": g.get("zone", "self"), "orientation": g.get("orientation", "selfward"),
        "spec": {"description": g.get("description", ""), "driven_by": drive,
                 "zone": g.get("zone", "self"), "orientation": g.get("orientation", "selfward")},
        "next_action": None, "status": "in_progress",
        "milestones": g.get("milestones", []),
        "serves": _serves_aspiration(drive),
    }
    if g.get("requires_artifact"):
        cg["requires_artifact"] = True
        cg["deadline_cycles"] = g.get("deadline_cycles")
    try:
        from brain.cognition.planning.goal_comprehension import hydrate_goal_model
        return hydrate_goal_model(cg)
    except Exception as exc:
        record_failure("intrinsic_goals._build_committed_goal.hydrate", exc)
        return cg


def generate_intrinsic_goals(context: Dict[str, Any] = None) -> List[Dict]:
    """
    Cognition function: produce 1-3 candidate goals from values, world state,
    and active threads. Injects into context["proposed_goals"] and returns list.

    Bypasses the normal cooldown if Orrin has no committed goal so he bootstraps
    a goal quickly on first run rather than waiting 45 minutes.
    """
    global _LAST_INTRINSIC_TS
    context = context or {}

    if context.get("_suppress_intrinsic_goals") and context.get("committed_goal"):
        log_activity("[intrinsic_goals] Skipped while patch-leave suppression is active.")
        return []
    if int(context.get("action_debt", 0) or 0) > 0 and context.get("committed_goal"):
        log_activity("[intrinsic_goals] Skipped while the committed goal has open action debt.")
        return []

    now = time.time()
    has_goal = bool(context.get("committed_goal"))
    interval = _MIN_INTERVAL_S if has_goal else _BOOTSTRAP_INTERVAL_S
    # P4 — habituate goal-spawning against its own track record, the way exploration
    # already habituates. The run showed generate_intrinsic_goals learned to 0.39
    # (below neutral) yet was still picked #1 by a mile; stretching the cooldown when
    # its learned value is sub-neutral makes spawning stop being the free displacement
    # activity. Only lengthens when there IS already a committed goal (never strands a
    # cold start). Up to 3× when the action is proven empty.
    if has_goal:
        try:
            _ema = load_json(DATA_DIR / "action_reward_ema.json", default_type=dict) or {}
            _giv = float(_ema.get("generate_intrinsic_goals", 0.5) or 0.5)
            if _giv < 0.45:
                interval *= 1.0 + min(2.0, (0.45 - _giv) * 6.0)
        except Exception:
            pass
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

    if not llm_callable_by("intrinsic_goals"):
        # Branch on whether THIS caller can actually reach the API — not on bare
        # llm_available(), which ignores tool-only mode and over-reports. In the
        # default deployment (tool-only on, intrinsic_goals not allowlisted) the
        # rich symbolic path below now runs instead of falling to a seed table.
        # Keep the enduring long-term aspirations present — the top of the goal
        # hierarchy that the short-term goal below ladders up to.
        _ensure_aspirations()
        # LLM-free goal generation with genuine variety: draws from concepts he's
        # learned, open questions, and recent research — not one fixed template —
        # so goals (and the topics they drive) stop repeating without any LLM.
        _tgoal = _varied_symbolic_goal(context, long_mem)
        if not _tgoal:
            # Nothing real to originate this cycle — and no canned template to fall
            # back on by design. Stay quiet rather than manufacture a note goal.
            log_activity("[intrinsic_goals] No symbolic goal this cycle (empty pool, no template).")
            return []
        _tgoal = _enrich_goal_zone(_tgoal)
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
        log_activity(f"[intrinsic_goals] Symbolic goal proposed: '{_tgoal['title']}'")
        if not context.get("committed_goal"):
            ts = datetime.now(timezone.utc).isoformat()
            # P7 — choose the committed goal by competition among live proposals
            # (pressure + usefulness drive), not "first generated wins".
            _winner = _select_commit_proposal(context.get("proposed_goals"), context) or _tgoal
            context["committed_goal"] = _build_committed_goal(_winner, f"intrinsic-{ts}")
            log_activity(
                f"[intrinsic_goals] Committed goal: '{_winner['title']}'"
                + (f" (serves: {_serves_aspiration(_winner.get('driven_by',''))})"
                   if _serves_aspiration(_winner.get('driven_by','')) else "")
            )
            # Form an act of will around the new goal — resolve to see it through,
            # so follow-through is shielded from momentary impulse (the positive
            # half of free will, complementing inhibition).
            try:
                from brain.cognition.will import form_commitment as _form_commitment
                _form_commitment(context, f"pursue: {_winner['title']}")
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

    # Symbolic fallback when the LLM is callable but returned empty/garbage —
    # route through the same rich path the LLM-disabled branch uses, not a
    # poorer seed table. (Fix A: the LLM-empty fallback should be no worse than
    # the LLM-off fallback.)
    if not goals_raw:
        _vg = _varied_symbolic_goal(context, long_mem)
        if not _vg:
            # No real candidate and no template by design — originate nothing.
            log_activity("[intrinsic_goals] No symbolic fallback goal (empty pool, no template).")
            return []
        log_activity(f"[intrinsic_goals] Symbolic fallback goal (LLM empty): '{_vg['title']}'")
        goals_raw = [_vg]

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
        from brain.cognition.planning.goals import load_goals as _load_goals_ig
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
        # Accept both LLM-shaped string milestones and the dict milestones the
        # symbolic generators (_varied_symbolic_goal) already emit.
        milestones = []
        for m in raw_milestones[:5]:
            if isinstance(m, dict):
                text = str(m.get("text", "")).strip()
                if text:
                    milestones.append({"text": text[:200], "met": bool(m.get("met")), "met_at": m.get("met_at")})
            elif isinstance(m, str) and m.strip():
                milestones.append({"text": str(m)[:200], "met": False, "met_at": None})
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
        _enrich_goal_zone(goal)
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
            # P7 — competition among live proposals, not highest-priority-first.
            _winner = _select_commit_proposal(context.get("proposed_goals"), context) \
                or max(goals, key=lambda g: g.get("priority", 3))
            context["committed_goal"] = _build_committed_goal(_winner, f"intrinsic-{ts}")
            log_activity(f"[intrinsic_goals] Committed goal: '{_winner['title']}'")

    return goals
