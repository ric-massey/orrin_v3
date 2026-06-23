# brain/cognition/intrinsic_aspirations.py
# The aspiration subsystem of intrinsic_goals (Phase 4.5C extraction): the four
# enduring long-term aspirations, the learned driven_by -> aspiration association
# (credit_aspirations / _serves_aspiration), and the P3 fairness/recruitment
# pressure (aspiration_pressure / mark_aspiration_contribution). Self-contained:
# it reads/writes the goal + drive-credit stores and depends on no other
# intrinsic_goals helper, so intrinsic_goals re-imports the names it still uses.
from __future__ import annotations
from brain.core.runtime_log import get_logger

import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from brain.utils.log import log_activity
from brain.utils.json_utils import load_json, save_json
from brain.utils.failure_counter import record_failure
from brain.utils.env import env_bool
from brain.paths import GOALS_FILE, COMPLETED_GOALS_FILE, DATA_DIR

_log = get_logger(__name__)


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
# Phase 4 / Fix C: this is now only the COLD-START PRIOR — the link a completed
# goal actually earns is learned (see below).
_DRIVE_TO_ASPIRATION = {d: t for t, d in _ASPIRATIONS}


# ── Phase 4 / Fix C: learned driven_by → aspiration association ────────────────
# When a goal completes, credit_aspirations() works out which aspiration its
# OUTCOME actually advanced (from the goal's content + its causal effects,
# independent of the driven_by tag) and EMA-updates a weight for
# (driven_by → that aspiration). _serves_aspiration returns the argmax once there
# is evidence, falling back to the prior table until then. So the link starts as
# the prior and becomes earned. Disable with ORRIN_LEARNED_ASPIRATION=0 →
# _serves_aspiration is exactly the old static lookup.
_DRIVE_CREDIT_FILE    = DATA_DIR / "drive_aspiration_credit.json"
_DRIVE_CREDIT_ALPHA   = 0.25    # EMA learning rate for the learned link
_PRIOR_SEED_WEIGHT    = 0.50    # the prior's standing weight; an evidenced
                                # aspiration must EXCEED this to take over
_DRIVE_CREDIT_IDS_CAP = 500     # bound the per-goal idempotency ledger

# Keyword signatures used to classify which aspiration a completed goal's outcome
# advanced. Coarse on purpose — a clear keyword winner is the evidence; ties /
# no-hits yield no learning signal (the prior stands).
_ASPIRATION_KEYWORDS = {
    "Understand my own mind and how I work":
        {"self", "mind", "cognition", "cognitive", "introspect", "memory", "architecture",
         "internal", "source code", "trace", "audit", "machinery", "my own", "self-"},
    "Understand the world more deeply":
        {"world", "research", "learn", "knowledge", "fact", "history", "science",
         "topic", "concept", "wikipedia", "article", "investigate", "cause", "causes of"},
    "Be genuinely useful and connected to the people I talk to":
        {"note", "ric", "user", "message", "connect", "share", "reach", "tell",
         "conversation", "reply", "contact", "useful", "help"},
    "Make things — produce work that didn't exist before":
        {"write", "build", "create", "tool", "function", "produce", "artifact",
         "make", "html", "implement", "script", "code"},
}


def _learned_aspiration_enabled() -> bool:
    return env_bool("ORRIN_LEARNED_ASPIRATION", True)


def _load_drive_credit() -> Dict[str, Any]:
    try:
        d = load_json(_DRIVE_CREDIT_FILE, default_type=dict) or {}
        if not isinstance(d, dict):
            d = {}
    except Exception as exc:
        record_failure("intrinsic_goals.load_drive_credit", exc)
        d = {}
    d.setdefault("weights", {})        # {driven_by: {aspiration_title: weight}}
    d.setdefault("credited_ids", [])   # goal ids already folded into the EMA
    return d


def _save_drive_credit(d: Dict[str, Any]) -> None:
    try:
        save_json(_DRIVE_CREDIT_FILE, d)
    except Exception as exc:
        record_failure("intrinsic_goals.save_drive_credit", exc)


def _evidenced_aspiration(goal: Dict[str, Any]) -> Optional[str]:
    """Which aspiration did this completed goal's OUTCOME actually advance?

    Derived from the goal's own content + the causal effects of its action — NOT
    from its driven_by tag — so the learned link can legitimately diverge from the
    prior. Returns None when there's no clear signal (the prior then stands).
    """
    valid = {t for t, _ in _ASPIRATIONS}
    explicit = str(goal.get("advanced_aspiration") or "").strip()
    if explicit in valid:
        return explicit

    spec = goal.get("spec") or {}
    parts = [
        str(goal.get("title") or goal.get("name") or ""),
        str(goal.get("description") or spec.get("description") or ""),
    ]
    parts += [str(c) for c in (goal.get("recent_contributions") or [])[:3]]
    # The causal effects of the goal's action are an outcome signal too.
    try:
        from brain.symbolic.causal_graph import get_effects
        action = str(goal.get("title") or goal.get("name") or "")
        for e in get_effects(action, min_score=0.0)[:4]:
            parts.append(str(e.get("effect", "")))
    except Exception as exc:
        record_failure("intrinsic_goals.evidenced_aspiration", exc)

    text = " ".join(parts).lower()
    if not text.strip():
        return None
    scores = {asp: sum(1 for kw in kws if kw in text) for asp, kws in _ASPIRATION_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else None


def _goal_completion_reward(goal: Dict[str, Any]) -> float:
    """Positive-evidence strength of a completion, in [0,1]. Uses the goal's own
    recorded reward/outcome if present, else the action's reward EMA, else a
    positive default (a completion is positive evidence)."""
    for k in ("reward", "outcome", "final_reward"):
        v = goal.get(k)
        if isinstance(v, (int, float)):
            return max(0.0, min(1.0, float(v)))
    try:
        ema = load_json(DATA_DIR / "action_reward_ema.json", default_type=dict) or {}
        title = str(goal.get("title") or "").lower()
        for act, r in ema.items():
            if act and isinstance(r, (int, float)) and act.lower() in title:
                return max(0.0, min(1.0, float(r)))
    except Exception as exc:
        record_failure("intrinsic_goals.goal_completion_reward", exc)
    return 0.8


def _learn_drive_aspiration(driven_by: str, evidenced_asp: str, reward: float,
                            credit: Dict[str, Any]) -> None:
    """EMA-update the learned (driven_by → aspiration) weight in-place on `credit`."""
    drive = str(driven_by or "")
    if not drive or not evidenced_asp:
        return
    row = credit["weights"].setdefault(drive, {})
    # Seed the prior the first time we touch this drive, so the learned link
    # starts AT the prior and must be earned away from it.
    if not row:
        prior = _DRIVE_TO_ASPIRATION.get(drive)
        if prior:
            row[prior] = _PRIOR_SEED_WEIGHT
    a = _DRIVE_CREDIT_ALPHA
    old = float(row.get(evidenced_asp, 0.0))
    row[evidenced_asp] = round((1.0 - a) * old + a * float(reward), 4)


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
            from brain.cog_memory.long_memory import remember_foundational
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
    """The aspiration a drive serves: the learned argmax once there's evidence,
    falling back to the static prior (cold start, or when learning is disabled)."""
    drive = str(driven_by or "")
    prior = _DRIVE_TO_ASPIRATION.get(drive, "")
    if not _learned_aspiration_enabled():
        return prior
    try:
        row = _load_drive_credit()["weights"].get(drive)
        if row:
            return max(row, key=row.get)
    except Exception as exc:
        record_failure("intrinsic_goals.aspiration_pressure_pick", exc)
    return prior


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
    except Exception as exc:
        record_failure("intrinsic_goals.proposal_priority", exc)
    # Phase 4 / Fix C: learn the driven_by → aspiration link from real completions.
    # Each completed goal folds into the EMA exactly once (idempotency ledger).
    learn = _learned_aspiration_enabled()
    credit = _load_drive_credit() if learn else None
    credited_ids: set = set(credit["credited_ids"]) if credit else set()
    credit_changed = False

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
            # Learn the link from this completion's actual outcome (once per goal).
            if credit is not None and gid and gid not in credited_ids:
                evidenced = _evidenced_aspiration(g)
                if evidenced:
                    _learn_drive_aspiration(
                        g.get("driven_by", ""), evidenced, _goal_completion_reward(g), credit)
                credited_ids.add(gid)
                credit["credited_ids"].append(gid)
                credit_changed = True
            # serves: the goal's own tag, else the (now-learned) link for its drive.
            title = str(g.get("serves") or _serves_aspiration(g.get("driven_by", "")) or "").strip()
            if title:
                contributions.setdefault(title.lower(), []).append(
                    str(g.get("title") or g.get("name") or "")[:80])

    if credit is not None and credit_changed:
        if len(credit["credited_ids"]) > _DRIVE_CREDIT_IDS_CAP:
            credit["credited_ids"] = credit["credited_ids"][-_DRIVE_CREDIT_IDS_CAP:]
        _save_drive_credit(credit)

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
        except Exception as exc:
            record_failure("intrinsic_goals.spawn_cooldown_ema", exc)
    if summary:
        log_activity("[aspirations] " + " | ".join(summary))
    return ("Aspiration progress — " + "; ".join(summary)) if summary else ""


# ── Phase 3 (P3): aspiration fairness / recruitment pressure ───────────────────
# A 0%-progress aspiration must stop being invisible to the generator. Pressure
# rises with time-since-last-contribution and with how far below the mean an
# aspiration's share sits, so "Make things" at 0% for 10k cycles → high pressure.
# It is decayed only by a real (effect-backed) contribution timestamp written in
# mark_aspiration_contribution — bookkeeping closures don't move it.
_STARVED_IDLE_FULL_S = 6 * 3600.0   # idle this long → full idle pressure component


def aspiration_pressure(context: Dict[str, Any] = None) -> Dict[str, float]:
    """Per-aspiration recruitment weight in [0,1]; higher = more starved."""
    try:
        goals = load_json(GOALS_FILE, default_type=list) or []
    except Exception:
        return {}
    asps = [g for g in goals if isinstance(g, dict)
            and (g.get("_aspiration") or g.get("kind") == "aspiration")]
    if not asps:
        return {}
    counts = {str(g.get("title", "")): int(g.get("contribution_count", 0) or 0) for g in asps}
    total = sum(counts.values())
    mean = (total / len(counts)) if counts else 0.0
    now = time.time()
    out: Dict[str, float] = {}
    for g in asps:
        title = str(g.get("title", ""))
        share_gap = max(0.0, (mean - counts[title]) / (mean + 1.0))   # below the mean share
        last = g.get("last_contribution_ts")
        if last:
            try:
                idle = now - datetime.fromisoformat(str(last).replace("Z", "+00:00")).timestamp()
            except Exception:
                idle = _STARVED_IDLE_FULL_S
        else:
            idle = _STARVED_IDLE_FULL_S       # never contributed → maximal idle pressure
        idle_norm = min(1.0, max(0.0, idle) / _STARVED_IDLE_FULL_S)
        out[title] = round(0.5 * share_gap + 0.5 * idle_norm, 4)
    return out


def _fairness_default_drive() -> str:
    """Drive of the most-starved aspiration (P3) — the new default for an untagged
    goal, so the path of least resistance stops being world_knowledge."""
    try:
        p = aspiration_pressure()
        if p:
            top = max(p, key=p.get)
            for t, d in _ASPIRATIONS:
                if t == top:
                    return d
    except Exception:
        pass
    return "world_knowledge"


def mark_aspiration_contribution(driven_by: str) -> None:
    """Stamp last_contribution_ts on the aspiration a drive serves — decays its P3
    pressure. Call ONLY on a real, effect-backed contribution (not a bookkeeping
    closure), so starved directions stay starved until something real lands."""
    asp_title = _serves_aspiration(str(driven_by or ""))
    if not asp_title:
        return
    try:
        goals = load_json(GOALS_FILE, default_type=list) or []
        if not isinstance(goals, list):
            return
        ts = datetime.now(timezone.utc).isoformat()
        changed = False
        for g in goals:
            if isinstance(g, dict) and (g.get("_aspiration") or g.get("kind") == "aspiration") \
                    and str(g.get("title", "")) == asp_title:
                g["last_contribution_ts"] = ts
                changed = True
        if changed:
            save_json(GOALS_FILE, goals)
    except Exception as _e:
        record_failure("intrinsic_goals.mark_aspiration_contribution", _e)
