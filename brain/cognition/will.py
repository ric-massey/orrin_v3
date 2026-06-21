# brain/cognition/will.py
#
# Explicit will / commitment — the positive half of free will.
#
# Orrin already has the NEGATIVE half (veto / inhibition — the ability to NOT
# act). Will is the complement: forming an intention and HOLDING it against
# momentary impulses long enough to see it through. Without it an agent is blown
# around by whatever drive is loudest each instant (his old "wondering vs doing"
# loop was exactly this — no will to hold a course).
#
# A commitment here is "I have resolved to do X." While active it:
#   - stays present (the intention is shielded, not forgotten),
#   - lends the committed goal a modest, DECAYING follow-through bias so impulse
#     switching is resisted while fresh resolve is strong,
#   - clears when the goal is done/gone or the resolve fades.
#
# The decay + auto-clear are deliberate: willpower that never weakens would just
# be a rut. This shields follow-through without locking him in. Symbolic, no LLM.
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, Optional

from brain.paths import DATA_DIR
from brain.utils.log import log_private

_FILE = DATA_DIR / "commitments.json"
_DECAY_PER_CYCLE = 0.012     # base rate; scaled by how dearly the resolve is held
_CLEAR_BELOW = 0.15
_MAX_BIAS = 0.12             # peak follow-through boost (kept small to avoid ruts)
_MIN_STRENGTH = 0.2          # even a humbled vow must outlive the clear threshold


def _goal_title(context: Dict[str, Any]) -> str:
    cg = context.get("committed_goal")
    if isinstance(cg, dict):
        return str(cg.get("title") or cg.get("name") or "")
    return ""


def _drive_alignment(intention: str) -> float:
    """Does an active drive want this? The strongest pressure among drives
    whose name/tags share ground with the intention (master plan 4.1)."""
    try:
        from brain.embodiment import drive_engine
        from brain.cognition.selfhood.second_order_volition import _tokens
        state = drive_engine.get_state() or {}
        tags = drive_engine.get_drive_tags() or {}
        toks = _tokens(intention)
        best = 0.0
        for name, pressure in state.items():
            drive_toks = {name} | set(tags.get(name) or [])
            drive_toks = {t for tag in drive_toks for t in str(tag).split("_") if len(t) > 3}
            if toks & drive_toks:
                best = max(best, float(pressure))
        return min(1.0, best)
    except Exception:
        return 0.0


def _value_alignment(intention: str) -> float:
    """Token overlap between intention and core_values — the same _tokens
    machinery second_order_volition already uses (master plan 4.1)."""
    try:
        from brain.cognition.selfhood.second_order_volition import _tokens, _values_text
        toks = _tokens(intention)
        vals = _tokens(_values_text())
        if not toks or not vals:
            return 0.0
        return min(1.0, len(toks & vals) / 3.0)
    except Exception:
        return 0.0


def compute_commitment_strength(
    intention: str,
    stance: str,
) -> float:
    """
    Differentiated commitment strength (master plan 4.1):

        strength = clamp(0.25 + 0.30*drive_alignment + 0.25*value_alignment
                              + 0.20*affect_endorsement, 0.25, 1.0)

    then the ambivalence factor (4.2) and the failure-pattern discount (4.3) —
    a vow on ground where vows keep breaking starts appropriately humbler.
    """
    da = _drive_alignment(intention)
    va = _value_alignment(intention)
    ae = 1.0 if stance == "endorse" else 0.5
    strength = max(0.25, min(1.0, 0.25 + 0.30 * da + 0.25 * va + 0.20 * ae))
    if stance == "ambivalent":
        strength *= 0.5   # proceed, held lightly — exactly as designed
    try:
        from brain.cognition.reflection.review_failures import failure_pattern_discount
        strength -= failure_pattern_discount(intention)
    except Exception:
        pass
    return round(max(_MIN_STRENGTH, strength), 3)


def form_commitment(
    context: Dict[str, Any],
    intention: str,
    strength: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """
    Resolve to pursue something — the act of will. Records and shields it.

    The will stands at the door (master plan 4.2): the endorsement faculty is
    consulted at the binding moment. A disowned intention forms NO commitment
    (the goal may still exist, but gets no will shield). When `strength` is
    given explicitly the gate is bypassed (caller has already judged).
    Returns the commitment, or None when the intention was disowned.
    """
    # Re-commitment gate (DATA_FILE_AUDIT 2026-06-11 §4): the respawn loop
    # formed 91 identical commitments in one afternoon (one every ~90 s).
    # An identical recent commitment means the resolve already exists —
    # return it instead of vowing again.
    existing = _recent_identical_commitment(intention)
    if existing is not None:
        log_private(f"[will] already committed (recent, identical): {str(intention)[:80]}")
        context["_commitment"] = existing
        return existing

    stance, gloss = "endorse", "I stand behind this."
    if strength is None:
        try:
            from brain.cognition.selfhood.second_order_volition import endorse_intention
            stance, gloss = endorse_intention(intention, context)
        except Exception as _e:
            log_private(f"[will] endorsement gate unavailable, proceeding plain: {_e}")
        if stance == "disown":
            log_private(f"[will] declined to commit (disowned): {str(intention)[:80]}")
            return None
        strength = compute_commitment_strength(intention, stance)

    wm_id = str(uuid.uuid4())
    c = {
        "id": str(uuid.uuid4()),
        "intention": str(intention)[:160],
        "strength": float(strength),
        "initial_strength": float(strength),
        "stance": stance,
        "wm_id": wm_id,
        "formed_ts": time.time(),
    }
    context["_commitment"] = c
    try:
        from brain.cog_memory.working_memory import update_working_memory
        if stance == "ambivalent":
            content = (f"[will] I resolve (held lightly, strength {strength:.2f}) to: "
                       f"{c['intention']} — {gloss}")
        else:
            content = (f"[will] I resolve to: {c['intention']} — {gloss} "
                       f"(strength {strength:.2f})")
        update_working_memory({
            "id": wm_id,
            "content": content,
            "event_type": "commitment", "importance": 3, "priority": 3,
        })
    except Exception:
        pass
    try:
        log = []
        if _FILE.exists():
            log = json.loads(_FILE.read_text(encoding="utf-8")) or []
        log.append(c)
        _FILE.write_text(json.dumps(log[-100:], indent=1), encoding="utf-8")
    except Exception:
        pass
    # A commitment without a goal is unfalsifiable (BEHAVIOR_FIX_PLAN 2.2):
    # assert a corresponding active goal exists, or create one.
    try:
        _link_commitment_to_goal(c["intention"])
    except Exception as _e:
        log_private(f"[will] could not link commitment to a goal: {_e}")
    log_private(f"[will] resolved ({stance}, strength {strength:.2f}): {c['intention'][:100]}")
    return c


_RECOMMIT_COOLDOWN_S = 6 * 3600.0   # identical intention within this window → no new vow


def _recent_identical_commitment(intention: str) -> Optional[Dict[str, Any]]:
    """The most recent stored commitment with this exact intention, if it was
    formed within the re-commitment cooldown window."""
    key = str(intention)[:160].strip().lower()
    if not key:
        return None
    try:
        log = json.loads(_FILE.read_text(encoding="utf-8")) if _FILE.exists() else []
    except Exception:
        return None
    if not isinstance(log, list):
        return None
    cutoff = time.time() - _RECOMMIT_COOLDOWN_S
    for c in reversed(log):
        if (isinstance(c, dict)
                and str(c.get("intention", "")).strip().lower() == key
                and float(c.get("formed_ts") or 0.0) >= cutoff):
            return c
    return None


def _bare_intention(intention: str) -> str:
    s = str(intention or "").strip()
    if s.lower().startswith("pursue:"):
        s = s[len("pursue:"):].strip()
    return s


def _iter_goals(nodes):
    for n in nodes or []:
        if isinstance(n, dict):
            yield n
            yield from _iter_goals(n.get("subgoals"))


def _link_commitment_to_goal(intention: str) -> None:
    """Ensure an active goal exists for this commitment; create one if missing."""
    from brain.cognition.planning.goals import load_goals, add_goal
    bare = _bare_intention(intention)
    if not bare:
        return
    key = " ".join(bare.lower().split())
    for g in _iter_goals(load_goals()):
        title = " ".join(str(g.get("title") or g.get("name") or "").lower().split())
        if title == key and str(g.get("status", "")).lower() not in (
                "completed", "failed", "abandoned", "cancelled"):
            return  # already covered
    add_goal({
        "title": bare[:160],
        "name": bare[:160],
        "status": "pending",
        "source": "commitment",
        "driven_by": "will",
    })
    log_private(f"[will] created goal for commitment: {bare[:80]}")


def check_orphaned_commitments() -> int:
    """Consistency check: log commitments with no matching active goal.
    Returns the orphan count. Intended for the nightly/maintenance pass."""
    try:
        log = json.loads(_FILE.read_text(encoding="utf-8")) if _FILE.exists() else []
    except Exception:
        return 0
    if not isinstance(log, list):
        return 0
    try:
        from brain.cognition.planning.goals import load_goals
        titles = {
            " ".join(str(g.get("title") or g.get("name") or "").lower().split())
            for g in _iter_goals(load_goals())
            if str(g.get("status", "")).lower() not in ("completed", "failed", "abandoned", "cancelled")
        }
    except Exception:
        return 0
    orphans = 0
    seen: set = set()
    for c in log[-30:]:
        bare = " ".join(_bare_intention((c or {}).get("intention", "")).lower().split())
        if bare and bare not in titles and bare not in seen:
            seen.add(bare)
            orphans += 1
            log_private(f"[will] orphaned commitment (no active goal): {bare[:80]}")
    return orphans


def tick_commitment(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Decay the active commitment and expose its follow-through bias. Clears it when
    the goal is gone/done or resolve has faded. Called once per cycle.
    """
    c = context.get("_commitment")
    if not isinstance(c, dict):
        context.pop("_commitment_bias", None)
        return None

    # No active committed goal → the resolve has nothing to hold; release it.
    if not _goal_title(context):
        context.pop("_commitment", None)
        context.pop("_commitment_bias", None)
        return None

    # Decay inversely scaled by how dearly the resolve was held (master plan
    # 4.1): a 1.0-strength vow fades ~0.6x base rate, a 0.25 vow ~1.35x.
    _init = float(c.get("initial_strength", c.get("strength", 0.0)) or 0.0)
    _rate = _DECAY_PER_CYCLE * (1.6 - _init)
    c["strength"] = max(0.0, float(c.get("strength", 0.0)) - _rate)
    if c["strength"] <= _CLEAR_BELOW:
        context.pop("_commitment", None)
        context.pop("_commitment_bias", None)
        log_private("[will] commitment spent — resolve released")
        return None

    context["_commitment"] = c
    context["_commitment_bias"] = round(_MAX_BIAS * c["strength"], 3)
    return c


def active_commitment(context: Dict[str, Any]) -> Optional[str]:
    c = context.get("_commitment")
    return c.get("intention") if isinstance(c, dict) else None


def find_commitment_for_goal(
    goal_title: str,
    context: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    The commitment (if any) bound to this goal — used by mark_goal_failed
    (master plan 4.3) so a failed vow can cost in proportion to its strength
    and the failure memory can point back at the moment of resolve.
    Checks the live in-context commitment first, then the durable log.
    """
    key = " ".join(str(goal_title or "").lower().split())
    if not key:
        return None
    if isinstance(context, dict):
        c = context.get("_commitment")
        if isinstance(c, dict) and \
                " ".join(_bare_intention(c.get("intention", "")).lower().split()) == key:
            return c
    try:
        log = json.loads(_FILE.read_text(encoding="utf-8")) if _FILE.exists() else []
    except Exception:
        return None
    if not isinstance(log, list):
        return None
    for c in reversed(log[-50:]):
        if isinstance(c, dict) and \
                " ".join(_bare_intention(c.get("intention", "")).lower().split()) == key:
            return c
    return None
