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
from brain.cognition.intrinsic_objectives import objective_pressure, _serves_aspiration
from brain.utils.felt_lexicon import felt_label

_log = get_logger(__name__)

# T2.3 — an aspiration whose recruitment pressure is at/above this is "starved":
# if the candidate pool can serve it, the coverage floor picks it deterministically.
_COVERAGE_FLOOR_PRESSURE = 0.5


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
                # AR2: route to the v2 ResearchHandler, whose extractive
                # synthesizer produces a sourced memo artifact LLM-free — not the
                # v1 self-report detour that produced hollow notes.
                kind="research", requires_artifact=True,
                spec={"queries": [name, f"{name} explained",
                                  f"what is not obvious about {name}"],
                      "synth_kind": "memo"},
            )
            for name in chosen
        ]
    except Exception as exc:  # KG unavailable/bad — record, originate nothing here
        record_failure("intrinsic_goals._concept_deepening_goals", exc)
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
                # AR2: a genuine open question is web research — v2 handler kind.
                kind="research", requires_artifact=True,
                spec={"queries": [q], "synth_kind": "memo"},
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
    # Introspection-skew gate (2026-06-30 run): this generator only ever serves
    # "Understand my own mind", and its goals complete CHEAPLY (searching his own
    # files), so left ungated it dominated the contribution ledger (93% of credit in
    # the 7.9k-cycle run) and starved the outward aspirations (make / connect, at
    # 0%). When self-understanding is already well-fed relative to the others, stop
    # flooding the pool with more introspective candidates. Self-balancing: as this
    # aspiration's pressure rises from neglect, the gate reopens.
    # SOFTENED 2026-06-30: the first version went fully silent (`return []`) when
    # self-understanding was well-fed, which over-corrected — it flipped the 7.9k-run's
    # 93%-introspection skew to 100%-"make things" / 0%-everything-else. The gate now
    # only ever EASES OFF (halves its output), never silences: introspection keeps a
    # minimum share, and the pre-existing pick-time fairness bias (_varied_symbolic_goal)
    # does the balancing. Self-balancing as pressure shifts.
    try:
        pressure = objective_pressure()
        self_asp = _serves_aspiration("self_exploration")
        if pressure and self_asp in pressure:
            mine = float(pressure.get(self_asp, 0.0))
            others = [v for k, v in pressure.items() if k != self_asp]
            mean_others = (sum(others) / len(others)) if others else 0.0
            if mine < mean_others - 0.10:        # clearly better-fed than the others → ease off
                limit = 1
    except Exception as exc:
        record_failure("intrinsic_goals._causal_frontier_goals.pressure_gate", exc)

    try:
        from brain.symbolic.causal_graph import get_all_edges
        edges = get_all_edges()
    except Exception as exc:  # causal graph unavailable — record, no frontier goals
        record_failure("intrinsic_goals._causal_frontier_goals", exc)
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
    # The causal graph is his SELF-MODEL: every effect in it is one of his own
    # internal states (impasse_signal, affective_regulation, reward_negative…), not
    # a world topic. So the answer to "what causes this" lives in his own substrate,
    # not on the web — framing these as research_topic/wikipedia goals made them
    # unplannable (there is no article on an internal signal), and they spun the
    # loop: generate → fail to plan 3× → abandon → regenerate the next variant.
    # Frame them as self-investigation instead (search_own_files / grep_files over
    # his own code via the "my own code" intent family), which is both plannable and
    # the tool that genuinely serves an internal causal gap. Drive is self_exploration
    # so the gap ladders under "Understand my own mind", not "Understand the world".
    # MEMBRANE (invariant #2): the effect name is one of his own raw signal keys
    # (conflict_signal, impasse_signal…). The perceivable TITLE/milestones must read
    # it as a FELT state ("being torn"), never the engineering token — otherwise the
    # key leaks into the workspace ("working toward: …'conflict_signal rises'"). The
    # DESCRIPTION keeps the raw key, because that is the literal code-search target
    # (find where 'conflict_signal' is computed); the description is execution spec,
    # not broadcast content.
    out: List[Dict] = []
    for name in _weighted_sample(frontiers, limit):
        felt = felt_label(name)
        out.append(_mk_goal(
            f"Trace in my own code what drives '{felt}'",
            f"My causal model says I keep feeling '{felt}' but I don't really know "
            f"what brings it about. It's one of my own internal states, so the answer "
            f"is in my substrate, not on the web: use search_own_files / grep_files to "
            f"find where '{name}' is computed and what moves it, then write what I "
            f"learn to long memory.",
            driven_by="self_exploration",
            milestones=[f"Where '{felt}' comes from in my own workings was located.",
                        f"A finding about what drives '{felt}' was written to long memory."],
        ))
    return out


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
    except Exception as exc:  # threads unreadable — record, no continuity goals
        record_failure("intrinsic_goals._autobiographical_continuity_goals", exc)
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
    except Exception as exc:  # backlog I/O best-effort — record
        record_failure("intrinsic_goals._drain_making_backlog", exc)


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
    except Exception as exc:  # backlog read best-effort — record, fall through
        record_failure("intrinsic_goals._making_goals.backlog", exc)
    if len(topics) < limit:
        try:
            for entry in reversed(list(long_mem or [])[-30:]):
                content = str(entry.get("content", entry) if isinstance(entry, dict) else entry)
                m = _RESEARCH_FINDING_RE.search(content)
                if m:
                    t = _strip_goal_scaffold(m.group(1).strip())[:70].strip()
                    if t and _acceptable_goal_subject(t):
                        topics.append(t)
        except Exception as exc:  # long-memory scan best-effort — record, fall through
            record_failure("intrinsic_goals._making_goals.research", exc)
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
            # RUN4_FIX_PLAN A3: give the make-goal a daemon-executable `synthesize`
            # lane so it gets PURSUED (reads prior memos, builds a synthesis,
            # writes a real artifact) instead of parking WAITING for a conscious
            # lane the ignition monopoly starved. HIGH priority (4 on v1's 1–5
            # scale) so it also ranks against core goals in the committed set.
            priority=4,
            spec={"synthesize": topic, "from_artifacts": True},
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
                # AR2: follow-up on prior web research is web research.
                kind="research", requires_artifact=True,
                spec={"queries": [topic, f"{topic} deeper analysis"],
                      "synth_kind": "memo"},
            )
    except Exception as exc:  # long-memory scan failed — record, no follow-up goal
        record_failure("intrinsic_goals._goal_from_recent_research", exc)
        return None
    return None


# ── AR5 (audit G2/AD4): goal BIRTH-RATE quota ────────────────────────────────
# ~95% of generated goals were "understand X" — even with a making path built
# (AR1–AR3), make/connect goals must actually be BORN to compete for slots.
# Pick-time pressure weighting (P3/T2.3 below) only fires on hard starvation;
# this quota watches the actual births over a rolling window and narrows the
# candidate pool when the mix drifts: make/connect births below the floor →
# this round must pick a maker/contact candidate if one exists; intake births
# above the cap → intake candidates sit this round out. Keyed to the same
# aspiration scoreboard mapping (_serves_aspiration) the pressure weighting
# uses, so a learned drive→aspiration link moves the quota too.
_BIRTH_WINDOW = 12
_MAKE_CONNECT_FLOOR = 0.25   # min share of output_producing + genuine_contact births
_INTAKE_CAP = 0.60           # max share of world_knowledge births
_MIN_BIRTHS_TO_JUDGE = 4     # don't enforce a ratio on a near-empty window
_recent_births: List[str] = []   # aspiration-drive keys of recent births


def _aspiration_drive_of(goal: Dict) -> str:
    """The aspiration-family drive a goal's driven_by serves (prior/learned)."""
    served = _serves_aspiration(str(goal.get("driven_by", "")))
    low = served.lower()
    if "make" in low or "produce" in low:
        return "output_producing"
    if "useful" in low or "connected" in low:
        return "genuine_contact"
    if "own mind" in low or "how i work" in low:
        return "self_understanding"
    if "world" in low:
        return "world_knowledge"
    return str(goal.get("driven_by", "")) or "other"


def _record_birth(goal: Dict) -> None:
    _recent_births.append(_aspiration_drive_of(goal))
    del _recent_births[:-_BIRTH_WINDOW]


_CANDIDATE_ASPIRATION_CAP = 0.50   # B4.2: max share of the candidate pool one aspiration may hold


def _cap_candidate_aspiration_share(pool: List[Dict]) -> List[Dict]:
    """B4.2 (RUN4_FIX_PLAN §B4): cap any single aspiration's share of the CANDIDATE
    pool at ~50%, so generation itself can't be a monoculture (2026-07-03: 158/162
    candidates targeted one aspiration). Trims the over-represented aspiration's
    candidates down to the cap; never drops below one candidate per aspiration and
    never empties the pool. Complements _quota_filter (which watches actual births)
    by acting one stage earlier, on what's even offered."""
    if len(pool) <= 2:
        return pool
    by_asp: Dict[str, List[Dict]] = {}
    for g in pool:
        by_asp.setdefault(_aspiration_drive_of(g), []).append(g)
    if len(by_asp) <= 1:
        return pool   # only one aspiration available — nothing to balance against
    # A group's share is ≤ 50% iff it holds no more than the SUM of all the other
    # groups. Trim only the dominant group down to that bound (at most one group
    # can exceed 50%), so the result is balanced without emptying minorities.
    counts = {a: len(c) for a, c in by_asp.items()}
    dom = max(counts, key=counts.get)
    others_total = sum(c for a, c in counts.items() if a != dom)
    out: List[Dict] = []
    for a, cands in by_asp.items():
        if a == dom and len(cands) > others_total:
            cands = random.sample(cands, max(1, others_total))
        out.extend(cands)
    return out or pool


def _quota_filter(pool: List[Dict]) -> List[Dict]:
    """Narrow the candidate pool when recent births violate the quota.
    Never empties the pool — a constraint with no serving candidate is skipped
    (forcing unmakeable make-goals would just spam failures)."""
    births = list(_recent_births)
    if len(births) < _MIN_BIRTHS_TO_JUDGE:
        return pool
    n = len(births)
    make_share = sum(1 for b in births
                     if b in ("output_producing", "genuine_contact")) / n
    intake_share = sum(1 for b in births if b == "world_knowledge") / n
    if make_share < _MAKE_CONNECT_FLOOR:
        makers = [g for g in pool if _aspiration_drive_of(g)
                  in ("output_producing", "genuine_contact")]
        if makers:
            return makers
    if intake_share > _INTAKE_CAP:
        non_intake = [g for g in pool
                      if _aspiration_drive_of(g) != "world_knowledge"]
        if non_intake:
            return non_intake
    return pool


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
    # B4.2 — cap any single aspiration's share of the candidate pool at ~50% so
    # generation itself isn't a monoculture (before the birth-rate quota narrows it).
    pool = _cap_candidate_aspiration_share(pool)
    # AR5 — birth-rate quota: narrow the pool when the recent birth mix violates
    # the make/connect floor or the intake cap (see _quota_filter above).
    pool = _quota_filter(pool)
    chosen: Optional[Dict] = None
    # P3 — bias the pick toward starved aspirations so a 0%-progress direction
    # ("Make things") actually gets recruited instead of losing every uniform draw
    # to the abundant intake candidates.
    try:
        pressure = objective_pressure(context)
        if pressure:
            # T2.3 Change 2 — generation COVERAGE FLOOR (round-robin, on top of the
            # weighting). When an aspiration is genuinely starved (pressure above the
            # floor) AND the pool has a candidate that serves it, pick that candidate
            # DETERMINISTICALLY rather than leaving its recruitment to a probabilistic
            # draw it kept losing. Pressure decays as the direction gets contributions,
            # so the floor rotates across aspirations — every aspiration with an
            # available candidate gets a minimum share of generation over the window.
            starved = max(pressure, key=pressure.get)
            if float(pressure.get(starved, 0.0)) >= _COVERAGE_FLOOR_PRESSURE:
                floor_cands = [g for g in pool
                               if _serves_aspiration(str(g.get("driven_by", ""))) == starved]
                if floor_cands:
                    chosen = random.choice(floor_cands)
            if chosen is None:
                scored = [
                    (g, 1.0 + 2.0 * float(pressure.get(_serves_aspiration(str(g.get("driven_by", ""))), 0.0)))
                    for g in pool
                ]
                picked = _weighted_sample(scored, 1)
                if picked:
                    chosen = picked[0]
    except Exception as exc:  # aspiration weighting optional — record, pick at random
        record_failure("intrinsic_goals._varied_symbolic_goal.pressure", exc)
    if chosen is None:
        chosen = random.choice(pool)
    _record_birth(chosen)   # AR5 — the quota watches actual births
    return chosen
