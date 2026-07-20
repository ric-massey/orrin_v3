# brain/cognition/self_state/life_ambition.py
#
# L3 (Run 11 §7, LIFE_AMBITION_PROPOSAL_2026-07-09 — built 2026-07-20 after the
# smoke life confirmed C2's neglect-pressure: the monopoly antagonist this
# feature was parked behind). People don't have end goals; they have END-GOAL
# BELIEFS — a concrete, revisable conviction about what the life is building
# toward. Orrin's aspirations stay correctly unfinishable (directions); this
# organ lets him author and hold ONE believed DESTINATION on top of them.
#
# The four ingredients existed for weeks (mortality salience, narrative
# identity, evidence-weighted belief, volition); this composes them. Symbolic
# throughout, no LLM. Guardrails per the proposal §4:
#   - authored from the STARVED aspiration (a counterweight to monopoly, never
#     an amplifier), only past the maturity gate (first narrative update);
#   - done-criteria are scoreboard-checkable (completed-stage events), never
#     self-graded;
#   - the commitment bias is small (≤ +0.1 additive, commitment_value reads
#     ambition_bias()) — it biases, never dictates;
#   - at death the verdict is computed (arrived / died trying / abandoned) and
#     the next life inherits at most the QUESTION, never the ambition.
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from brain.paths import DATA_DIR
from brain.utils.json_utils import load_json, save_json
from brain.utils.failure_counter import record_failure
from brain.utils.log import log_activity

_FILE = DATA_DIR / "life_ambition.json"
_BIAS = 0.08                 # additive commit-score nudge for theme-matching goals (< cap 0.1)
_MIN_DONE = 3                # floor for the arrival count
_MAX_DONE = 20
_PER_DAY_EST = 4.0           # completed contributions/day estimate for scaling N
_THEME_MATCH_TERMS = 2       # theme terms in a goal's text to count as serving it


def _load() -> Dict[str, Any]:
    d = load_json(_FILE, default_type=dict) or {}
    return d if isinstance(d, dict) else {}


def get_ambition() -> Optional[Dict[str, Any]]:
    d = _load()
    return d if d.get("statement") and d.get("status") == "held" else None


def _first_narrative_done() -> bool:
    try:
        from brain.cognition.self_state.autobiography import load_autobiography
        auto = load_autobiography() or {}
        chapters = auto.get("chapters") or []
        return any((c.get("entries") or []) for c in chapters if isinstance(c, dict))
    except Exception as exc:
        record_failure("life_ambition.first_narrative", exc)
        return False


def _theme_terms(limit: int = 4) -> List[str]:
    """Recurring subject terms from recent long memory — the story so far."""
    try:
        from brain.paths import LONG_MEMORY_FILE
        from brain.cognition.growth_ladder import _terms
        from collections import Counter
        raw = load_json(LONG_MEMORY_FILE, default_type=list) or []
        counts: Counter = Counter()
        for e in raw[-120:]:
            if isinstance(e, dict):
                counts.update(_terms(str(e.get("content", ""))[:400]))
        return [w for w, _ in counts.most_common(limit)]
    except Exception as exc:
        record_failure("life_ambition.theme_terms", exc)
        return []


def maybe_author(context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Author the life ambition — once per life, past the maturity gate, from
    the starved aspiration. Returns the ambition when newly authored."""
    try:
        d = _load()
        if d.get("statement") and d.get("status") == "held":
            return None                       # already holding one
        if not _first_narrative_done():
            return None                       # an ambition needs a story to grow out of
        from brain.cognition.intrinsic_objectives import objective_pressure
        pressure = objective_pressure(context or {}) or {}
        if not pressure:
            return None
        serves = max(pressure, key=pressure.get)   # most starved = highest pressure
        theme = _theme_terms()
        # Scale the destination to the felt remaining time.
        days_left = 0.0
        try:
            lt = (context or {}).get("_lifetime") or {}
            days_left = float(lt.get("days_remaining_felt", 0.0) or 0.0)
        except Exception:
            days_left = 0.0
        n = int(max(_MIN_DONE, min(_MAX_DONE, round((days_left or 1.0) * _PER_DAY_EST * 0.5))))
        statement = (
            f"Before this life ends: bring {n} pieces of work all the way to completion "
            f"in service of \"{serves}\""
            + (f", growing out of what keeps recurring in my life so far ({', '.join(theme[:3])})"
               if theme else "") + "."
        )
        ambition = {
            "statement": statement,
            "serves": serves,
            "theme_terms": theme,
            "done_criteria": {"kind": "aspiration_completions", "serves": serves, "n": n},
            "confidence": 0.5, "alpha": 1.0, "beta": 1.0,
            "formed_at": round(time.time(), 1),
            "status": "held",
            "revisions": d.get("revisions", []),
        }
        save_json(_FILE, ambition)
        log_activity(f"[life_ambition] authored: {statement}")
        return ambition
    except Exception as exc:
        record_failure("life_ambition.maybe_author", exc)
        return None


def _completions_since(serves: str, since_ts: float) -> int:
    try:
        from brain.cognition.objective_scoreboard import _load as _sb_load
        events = (_sb_load() or {}).get("events", [])
        return sum(1 for e in events
                   if isinstance(e, dict) and e.get("stage") == "completed"
                   and str(e.get("asp")) == serves and float(e.get("ts", 0)) >= since_ts)
    except Exception as exc:
        record_failure("life_ambition.completions", exc)
        return 0


def progress() -> Dict[str, Any]:
    amb = get_ambition()
    if not amb:
        return {}
    crit = amb.get("done_criteria") or {}
    have = _completions_since(str(crit.get("serves")), float(amb.get("formed_at", 0)))
    return {"have": have, "n": int(crit.get("n", 0) or 0)}


def _theme_match(goal: Dict[str, Any], amb: Dict[str, Any]) -> bool:
    terms = [t.lower() for t in (amb.get("theme_terms") or [])]
    if not terms:
        return False
    text = (str(goal.get("title", "")) + " " + str(goal.get("description", ""))[:300]).lower()
    return sum(1 for t in terms if t in text) >= min(_THEME_MATCH_TERMS, len(terms))


def ambition_bias(goal: Dict[str, Any]) -> float:
    """≤ +0.1 additive commit-score nudge for goals serving the ambition —
    a pull toward the believed destination, capped so it biases, never
    dictates (proposal §4; the aspiration-share quotas stay authoritative)."""
    try:
        amb = get_ambition()
        if not amb:
            return 0.0
        try:
            from brain.cognition.intrinsic_objectives import _serves_aspiration
            goal_serves = str(goal.get("serves")
                              or _serves_aspiration(str(goal.get("driven_by", ""))))
        except Exception:
            goal_serves = str(goal.get("serves", ""))
        if goal_serves == str(amb.get("serves")) or _theme_match(goal, amb):
            return _BIAS
        return 0.0
    except Exception as exc:
        record_failure("life_ambition.bias", exc)
        return 0.0


def note_completion(goal: Dict[str, Any]) -> None:
    """On goal completion: home the will (a `will`-driven, theme-matching goal
    credits the ambition's aspiration), feed belief evidence, check arrival."""
    try:
        amb = _load()
        if not (amb.get("statement") and amb.get("status") == "held"):
            return
        if str(goal.get("driven_by", "")) == "will" and _theme_match(goal, amb) \
                and not goal.get("serves"):
            goal["serves"] = str(amb.get("serves"))   # credit path reads this (T2.3)
        p = progress()
        if not p:
            return
        amb["alpha"] = float(amb.get("alpha", 1.0)) + (1.0 if ambition_bias(goal) else 0.0)
        amb["confidence"] = round(
            float(amb["alpha"]) / max(1e-6, float(amb["alpha"]) + float(amb.get("beta", 1.0))), 3)
        if p["n"] and p["have"] >= p["n"]:
            amb["status"] = "arrived"
            amb["arrived_at"] = round(time.time(), 1)
            amb.setdefault("revisions", []).append(
                {"ts": amb["arrived_at"], "event": "arrived", "statement": amb["statement"]})
            log_activity(f"[life_ambition] ARRIVED: {amb['statement']} "
                         f"({p['have']}/{p['n']}) — a new one may now form")
        save_json(_FILE, amb)
    except Exception as exc:
        record_failure("life_ambition.note_completion", exc)


def prospective_clause() -> str:
    """One line for the mouths (autobiography / autogenerated thoughts)."""
    amb = get_ambition()
    if not amb:
        return ""
    p = progress()
    frac = f" ({p['have']}/{p['n']} of the way there)" if p.get("n") else ""
    return f"What I'm building toward: {amb['statement']}{frac}"


def ingest_lineage_seed() -> None:
    """§3d, boot side: if a lineage file survived the reset (ALWAYS_KEEP) and
    hasn't been read yet, the previous life's question becomes ONE seed memory."""
    try:
        import json
        p = DATA_DIR / "life_lineage.json"
        if not p.exists():
            return
        lineage = json.loads(p.read_text("utf-8") or "{}")
        if not (isinstance(lineage, dict) and lineage.get("seed_question")
                and not lineage.get("ingested")):
            return
        from brain.cog_memory.long_memory import update_long_memory
        update_long_memory(lineage["seed_question"],
                           event_type="lineage_seed", importance=3)
        lineage["ingested"] = True
        p.write_text(json.dumps(lineage, indent=2), "utf-8")
        log_activity(f"[life_ambition] lineage seed ingested: "
                     f"{lineage['seed_question'][:100]}")
    except Exception as exc:
        record_failure("life_ambition.ingest_lineage", exc)


def death_verdict() -> Dict[str, Any]:
    """The final-audit verdict: arrived / died_trying / abandoned / never_formed.
    The next life may inherit the QUESTION as a seed, never the ambition."""
    try:
        d = _load()
        if not d.get("statement"):
            return {"verdict": "never_formed"}
        if d.get("status") == "arrived":
            v = "arrived"
        elif d.get("status") == "held":
            v = "died_trying"
        else:
            v = "abandoned"
        p = progress() if d.get("status") == "held" else {}
        return {"verdict": v, "statement": d.get("statement"),
                "progress": p, "revisions": d.get("revisions", []),
                "seed_question": (f"The previous life aimed at: {d.get('statement')} "
                                  f"— and {v.replace('_', ' ')}.")}
    except Exception as exc:
        record_failure("life_ambition.death_verdict", exc)
        return {"verdict": "unknown"}
