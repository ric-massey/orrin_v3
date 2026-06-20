"""
brain/behavior/express_to_user.py

THE ONE DOOR. Every artifact a person sees — a live reply, a note, a desktop
file, a dashboard announcement, an OS notification — is composed here from a
Motive (intent + felt state), never populated by scraping internal
representation. (EXPRESSION_MEMBRANE_FIX_PLAN, 2026-06-14.)

Two sides, one door:

    INTENT (motive)  ──►  express_to_user(...)  ──►  channel
                          • compose via expression.express() (affect + learned
                            vocabulary, congruence-enforced — Rogers 1959)
                          • enforce the speakability invariant (one place)
                          • stamp the motive on the artifact (provenance)
                          • route to the channel adapter

The backend — working memory, symbolic/causal/rule tags, telemetry — is
unreachable from here. The door consumes a Motive, never raw representation.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict

from behavior.speakability import assert_speakable, strip_internal
from utils.failure_counter import record_failure
from utils.log import log_activity


@dataclass
class Motive:
    """What Orrin means to express — captured at selection time, never scraped.

    `seed` is an optional *meaning kernel* (e.g. CycleState.output_seed, which is
    "raw signal wanting expression," not telemetry). It flows into composition
    and is reworded/sanitized, not copied verbatim.
    """
    intent: str = ""           # "report a blocker", "share a finding", "check in"
    why: str = ""              # the goal purpose this serves (from the goal spec)
    recipient: str = "Ric"     # "Ric" | "self" | "dashboard"
    seed: str = ""             # optional content kernel (meaning, not a raw WM line)
    goal_id: str = ""          # provenance

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


def _dominant_emotion(context: Dict[str, Any]) -> str:
    try:
        from behavior import expression
        return expression._dominant_emotion(context)
    except Exception:
        return "neutral"


# Functions that face a person and must therefore compose through this door.
EXPRESSIVE_FUNCTIONS = frozenset({
    "leave_note", "write_desktop_note", "announce_to_dashboard",
})


def _goal_why(context: Dict[str, Any]) -> str:
    goal = context.get("committed_goal") or {}
    if not isinstance(goal, dict):
        return ""
    spec = goal.get("spec") if isinstance(goal.get("spec"), dict) else {}
    return str(spec.get("description") or goal.get("description")
               or goal.get("title") or goal.get("name") or "")[:200]


def _goal_id(context: Dict[str, Any]) -> str:
    goal = context.get("committed_goal") or {}
    if not isinstance(goal, dict):
        return ""
    return str(goal.get("id") or goal.get("title") or goal.get("name") or "")


def _meaning_seed(context: Dict[str, Any]) -> str:
    """The meaning kernel Orrin means to convey — CycleState.output_seed, which
    is 'raw signal wanting expression', not telemetry. Composed/reworded by the
    door, never copied. Empty on any failure (the door composes from affect)."""
    try:
        from think.state_processor import compute_cycle_state
        salience = compute_cycle_state(context)
        return str(getattr(salience, "output_seed", "") or "")
    except Exception:
        return ""


def build_motive(context: Dict[str, Any], *, intent: str,
                 recipient: str = "Ric", seed: str = None) -> "Motive":
    """Construct a Motive from the committed goal + felt state, with the step's
    intent threaded in by step_execution when present.

    Provenance flows one of two ways:
      • `context["_expression_motive"]` — set by execute_step_action when an
        expressive act is fired from a plan step, carrying the step's intent and
        the owning goal's purpose (Phase 2 / E6). Its fields override the
        goal-derived defaults so the act serves the reason it was triggered.
      • otherwise the goal-derived defaults (Phase-1 local motive).
    The seed always defaults to the affect meaning kernel — never a raw WM line.
    """
    default_seed = _meaning_seed(context) if seed is None else seed
    motive = Motive(
        intent=intent,
        why=_goal_why(context),
        recipient=recipient,
        seed=default_seed,
        goal_id=_goal_id(context),
    )
    threaded = context.get("_expression_motive") if isinstance(context, dict) else None
    if isinstance(threaded, dict):
        motive.intent = str(threaded.get("intent") or motive.intent)[:120]
        motive.why = str(threaded.get("why") or motive.why)[:200]
        motive.recipient = str(threaded.get("recipient") or motive.recipient)
        if threaded.get("seed"):
            motive.seed = str(threaded["seed"])
        motive.goal_id = str(threaded.get("goal_id") or motive.goal_id)
    return motive


def compose_from_motive(motive: Motive, context: Dict[str, Any]) -> str:
    """Compose person-facing language from the motive + current affect.

    Reuses the authoring organ (expression.express) — affect-driven,
    vocabulary-based, congruence-checked. It NEVER reads working memory or any
    symbolic/telemetry field; the only content kernel it sees is the motive's
    own (sanitized) seed.
    """
    from think.cycle_state import CycleState
    from behavior import expression

    # The seed is meaning, but a caller may have handed in something with a
    # leaked tag — sanitize before composition so a kernel is reworded, never a
    # telemetry line copied through. express() returns a short seed verbatim, so
    # keep it under the organ's 150-char inline threshold.
    seed = strip_internal(motive.seed)[:149]

    salience = CycleState(
        output_triggered=True,
        output_pressure=0.75,
        output_seed=seed,
    )

    text = ""
    try:
        text = expression.express(salience, context, user_input="") or ""
    except Exception as _e:
        record_failure("express_to_user.compose", _e)
    text = strip_internal(text)

    if not text:
        # express() can stay silent (e.g. social_penalty suppression, empty
        # vocab). A deliberately-chosen expressive act must still produce
        # composed language — fall back to a congruent reflection from the same
        # vocabulary, never to copied backend state.
        emotion = _dominant_emotion(context)
        try:
            text = strip_internal(
                expression._congruent_pick("reflections", emotion, 0.5) or ""
            )
        except Exception as _e:
            record_failure("express_to_user.compose.fallback", _e)
    if not text:
        emotion = _dominant_emotion(context).replace("_", " ")
        text = f"I'm here, feeling {emotion}."
    return text


# ── Channel adapters (thin — they deliver composed text, they never compose) ──

def _route_reply(text: str, context: Dict[str, Any]) -> bool:
    try:
        from think.think_utils.talk_policy import speak_text
        from behavior.speak import OrrinSpeaker
        rendered = speak_text(text, context, OrrinSpeaker())
        return bool(rendered)
    except Exception as _e:
        record_failure("express_to_user._route_reply", _e)
        return False


def _route_note(text: str, artifact: Dict[str, Any], context: Dict[str, Any]) -> bool:
    """Deliver a note (option A): the announcements bridge the dashboard already
    polls (so it is actually seen — fixes E4), plus a durable outbox copy."""
    delivered = False
    try:
        from embodiment.system_presence import announce_presence
        r = announce_presence(text, kind="note")
        delivered = bool(r.get("success"))
    except Exception as _e:
        record_failure("express_to_user._route_note.deliver", _e)
    try:
        from brain.paths import NOTES_FILE
        from utils.json_utils import load_json, save_json
        notes = load_json(NOTES_FILE, default_type=list) or []
        notes.append(artifact)
        if len(notes) > 100:
            notes = notes[-100:]
        save_json(NOTES_FILE, notes)
    except Exception as _e:
        record_failure("express_to_user._route_note.outbox", _e)
    return delivered


def _route_desktop(text: str) -> bool:
    try:
        from embodiment.system_presence import write_to_desktop_note
        r = write_to_desktop_note("Orrin's note", text)
        return bool(r.get("success"))
    except Exception as _e:
        record_failure("express_to_user._route_desktop", _e)
        return False


def _route_dashboard(text: str) -> bool:
    try:
        from embodiment.system_presence import announce_presence
        r = announce_presence(text, kind="presence")
        return bool(r.get("success"))
    except Exception as _e:
        record_failure("express_to_user._route_dashboard", _e)
        return False


def _route_notify(text: str) -> bool:
    try:
        from agency.skills.notify_user import notify_user
        r = notify_user({"message": text[:200], "title": "Orrin"})
        return bool(r.get("success", True)) if isinstance(r, dict) else True
    except Exception as _e:
        record_failure("express_to_user._route_notify", _e)
        return False


_ROUTES = {
    "reply":     lambda text, artifact, ctx: _route_reply(text, ctx),
    "note":      lambda text, artifact, ctx: _route_note(text, artifact, ctx),
    "desktop":   lambda text, artifact, ctx: _route_desktop(text),
    "dashboard": lambda text, artifact, ctx: _route_dashboard(text),
    "notify":    lambda text, artifact, ctx: _route_notify(text),
}


def express_to_user(motive: Motive, channel: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
    """Compose from `motive`, enforce speakability, stamp, and route to `channel`.

    Returns {"success", "channel", "text", "motive"}.
    """
    context = context or {}
    if channel not in _ROUTES:
        return {"success": False, "channel": channel, "text": "",
                "motive": motive.to_dict(), "error": f"unknown channel {channel!r}"}

    text = compose_from_motive(motive, context)

    # Speakability invariant — composed text that still carries a backend tag is
    # a composer bug, raised here, not shipped to a person.
    assert_speakable(text)

    artifact = {
        "text": text,
        "motive": motive.to_dict(),
        "ts": datetime.now(timezone.utc).isoformat(),
        "emotion": _dominant_emotion(context),
    }

    ok = bool(_ROUTES[channel](text, artifact, context))

    # External-effect ledger (P0): a *delivered* person-facing artifact is a real
    # outward effect. Content-addressed + deduped, so 100 identical empty notes
    # collapse to one production. A None return = nothing novel = no credit; the
    # reward split (P1) keys production reward on a non-None row this cycle.
    if ok:
        _kind = {"note": "note_novel", "desktop": "note_novel",
                 "reply": "message_answered"}.get(channel)
        if _kind:
            try:
                from agency.effect_ledger import record_effect
                _row = record_effect(_kind, text, goal_id=(motive.goal_id or None), context=context)
                if _row is not None and _row.significance > 0 and isinstance(context, dict):
                    context["_production_effect_this_cycle"] = True
                    context.setdefault("_effect_rows_this_cycle", []).append(_row.to_json())
            except Exception as _e:
                record_failure("express_to_user.record_effect", _e)

    log_activity(f"[express_to_user] {channel} ({motive.intent or 'express'}) → {text[:80]}")
    return {"success": ok, "channel": channel, "text": text, "motive": artifact["motive"]}
