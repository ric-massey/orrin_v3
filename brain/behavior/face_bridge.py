# brain/behavior/face_bridge.py
#
# Closes the conversation loop between the Face UI and the brain.
#
# The Face posts messages to the telemetry backend's queue (hub.inputs); the
# brain reads user_input.txt and emits replies to stdout. Nothing connected
# those two channels — so messages typed into the Face never reached Orrin's
# cognition, and his replies never reached the user. This module bridges both
# directions, using the brain's existing input file and reply path so no other
# code has to change:
#
#   Face → brain:  drain_face_inputs()  pulls queued messages and writes the
#                  latest to user_input.txt (the brain's normal input channel),
#                  remembering the message id(s) awaiting a reply.
#   brain → Face:  deliver_reply()      sends a freshly emitted reply back to
#                  every awaiting Face message via the bridge's respond().
#
# Fail-safe: if the bridge/backend is absent, every call no-ops.
from __future__ import annotations

import threading
from typing import List

from brain.utils.failure_counter import record_failure

_pending_ids: List[str] = []
_lock = threading.Lock()


def _bridge():
    try:
        from backend.telemetry_bridge import get_bridge
        return get_bridge()
    except ImportError:  # intentional: backend absent — bridge unavailable
        return None


def drain_face_inputs() -> None:
    """
    Pull any messages typed into the Face and feed them to the brain's input
    channel (user_input.txt), so the existing perception/comprehension/speech
    pipeline ingests them exactly as it would a locally-typed line. Remembers
    the message id(s) so the reply can be delivered back to the right message.
    Call once per cycle BEFORE the loop reads user input.
    """
    tb = _bridge()
    if tb is None:
        return
    try:
        items = tb.get_pending_inputs()
        if not items:
            return
        msgs = [str(it.get("message", "")).strip() for it in items]
        msgs = [m for m in msgs if m]
        if not msgs:
            return
        # get_user_input() takes the last non-empty line, so write the most
        # recent message as the active input.
        from pathlib import Path
        from brain.paths import USER_INPUT
        Path(USER_INPUT).write_text(msgs[-1], encoding="utf-8")
        with _lock:
            for it in items:
                _id = it.get("id")
                if _id:
                    _pending_ids.append(str(_id))
    except Exception as exc:  # bridge/I/O failure — record, no-op this cycle
        record_failure("face_bridge.drain_face_inputs", exc)
        return


def has_pending() -> bool:
    with _lock:
        return bool(_pending_ids)


def force_reply(context) -> None:
    """
    Backstop guarantee: if a Face message is still awaiting a reply after the
    cycle's normal cognition ran (the action gate didn't pick a speak action, or
    something suppressed it), build a reply through the symbolic speech pipeline
    and deliver it. Ensures every message the user sends gets a real answer
    rather than silence. No-ops when nothing is pending (deliver_reply clears the
    queue once the natural path has answered, so this never double-replies).
    """
    if not has_pending():
        return
    try:
        user_input = (context.get("latest_user_input") or "").strip()
        if not user_input:
            return
        from brain.behavior.speech_gate import build_speech
        emo = context.get("affect_state") or {}
        reply = (build_speech(user_input, context, emo) or "").strip()
        if not reply:
            return
        import sys
        import time as _t
        sys.stdout.write(f"REPLY: {reply}\n")
        sys.stdout.flush()
        try:
            from brain.utils.log import log_activity
            log_activity(f"REPLY: {reply[:200]}")
        except Exception as exc:  # activity-log write best-effort — record
            record_failure("face_bridge.force_reply.log", exc)
        # Log it so the evaluator scores it next turn (feeds the learning loop).
        try:
            from brain.think.speech_log import log_reply
            log_reply(user_input, reply,
                      context.get("_last_speech_plan", {}) or {},
                      context.get("_last_speech_comprehension", {}) or {})
        except Exception as exc:  # speech-log write best-effort — record
            record_failure("face_bridge.force_reply.speech_log", exc)
        context["last_ai_timestamp"] = _t.time()
        deliver_reply(reply)
    except Exception as exc:  # backstop reply failed — record, stay silent
        record_failure("face_bridge.force_reply", exc)
        return


def deliver_reply(reply_text: str) -> None:
    """
    Deliver a freshly emitted reply back to every Face message awaiting one.
    No-ops when there is nothing pending (e.g. spontaneous speech), so only
    genuine responses to the user are delivered.
    """
    if not reply_text or not reply_text.strip():
        return
    with _lock:
        ids = list(_pending_ids)
        _pending_ids.clear()
    if not ids:
        return
    tb = _bridge()
    if tb is None:
        return
    text = reply_text.strip()
    for rid in ids:
        try:
            tb.respond(rid, text)
        except Exception as exc:  # one delivery failed — record, try the rest
            record_failure("face_bridge.deliver_reply", exc)
            continue
