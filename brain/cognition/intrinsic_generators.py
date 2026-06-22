# brain/cognition/intrinsic_generators.py
# The symbolic (LLM-free) intrinsic-goal generators, extracted from
# intrinsic_goals (Phase 4.5C). Each draws candidate goals from real mental
# content — KG concepts (_concept_deepening_goals), open questions, learned
# causal frontiers, active tensions, autobiographical threads, the intake->output
# making/contact ladders, and recent research — and builds them via the shared
# intrinsic_helpers._mk_goal. generate_intrinsic_goals (still in intrinsic_goals)
# orchestrates these; it re-imports them, so external callers and the orchestrator
# keep their existing references.
from __future__ import annotations
from brain.core.runtime_log import get_logger

import re
import time
import random
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from brain.utils.json_utils import load_json, save_json
from brain.utils.failure_counter import record_failure
from brain.paths import THREADS_FILE, DATA_DIR
from brain.cognition.intrinsic_helpers import (
    _mk_goal, _acceptable_goal_subject, _strip_goal_scaffold, _weighted_sample,
    _active_goal_titles, _RECENTLY_COMPLETED, _COOLDOWN_S,
)
from brain.cognition.intrinsic_aspirations import aspiration_pressure, _serves_aspiration

_log = get_logger(__name__)


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
