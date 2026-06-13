# brain/cognition/global_workspace.py
#
# The unity layer — a Global Workspace (Baars 1988; Dehaene 2014).
#
# Orrin's subsystems run in parallel and each produces content: a feeling, a
# percept, the goal he's pursuing, a surfacing thought, the action he just took,
# a present user. Without a workspace these never converge into a single "what I
# am aware of right now" — he is a committee, not an experiencer.
#
# This implements the workspace bottleneck:
#
#   gather candidate contents → salience competition → ONE winner enters the
#   workspace ("conscious" content) → it is BROADCAST back into context for every
#   subsystem to read, and appended to a continuous stream of experience.
#
# Hysteresis keeps a salient content in focus across cycles, so the stream has
# continuity rather than flickering every tick — a single serial thread, the
# functional basis of a unified self. Fully symbolic, no LLM.
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from paths import DATA_DIR
from utils.log import log_private

_STREAM_FILE = DATA_DIR / "conscious_stream.json"
_STREAM_MAX = 200          # persisted stream length
_HYSTERESIS_BONUS = 0.15   # continuity: the current focus is favoured to persist

_NOISE = (
    "[chunk:", "[metacog", "cpu=", "🧠", "🌓", "⏳", "🔄", "health summary",
    "[energy]", "[state_processor]", "[working_memory]", "[symbolic]",
    "spoke:", "chose:", "[done]",
)


def _f(x: Any, d: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def _is_noise(c: str) -> bool:
    cl = (c or "").strip().lower()
    return (not cl) or any(m in cl for m in _NOISE)


def _candidates(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Collect what each subsystem is currently 'offering' to consciousness."""
    out: List[Dict[str, Any]] = []

    # A present other commands attention most strongly.
    ui = (context.get("latest_user_input") or "").strip()
    if ui:
        out.append({"source": "user", "content": f'Ric said: "{ui[:160]}"', "salience": 0.95})

    # The dominant feeling.
    af = (context.get("affect_state") or {}).get("core_signals") or context.get("affect_state") or {}
    if isinstance(af, dict) and af:
        nums = {k: _f(v) for k, v in af.items() if isinstance(v, (int, float))}
        if nums:
            dom = max(nums, key=nums.get)
            val = nums[dom]
            if val >= 0.5:
                out.append({"source": "affect",
                            "content": f"a strong sense of {dom.replace('_', ' ')}",
                            "salience": 0.40 + 0.40 * val})

    # The most salient external/internal signal this cycle.
    ts = context.get("top_signals") or []
    s0 = ts[0] if isinstance(ts, list) and ts else None
    if isinstance(s0, dict):
        c = str(s0.get("content") or s0.get("summary") or "").strip()
        if c and not _is_noise(c):
            out.append({"source": "signal", "content": c[:160],
                        "salience": 0.30 + 0.50 * _f(s0.get("signal_strength"), 0.4)})

    # The goal he is pursuing.
    cg = context.get("committed_goal")
    if isinstance(cg, dict) and (cg.get("title") or cg.get("name")):
        out.append({"source": "goal",
                    "content": f"working toward: {cg.get('title') or cg.get('name')}",
                    "salience": 0.55})

    # The action he just took (sense of agency).
    lf = context.get("last_function_chosen") or context.get("last_function")
    if lf:
        out.append({"source": "action",
                    "content": f"just chose to {str(lf).replace('_', ' ')}",
                    "salience": 0.45})

    # A genuine recent thought/percept from working memory.
    for e in reversed((context.get("working_memory") or [])[-8:]):
        c = str(e.get("content", e) if isinstance(e, dict) else e)
        if len(c) >= 20 and not _is_noise(c):
            out.append({"source": "thought", "content": c[:160], "salience": 0.35})
            break

    # Contents OFFERED to consciousness by the Executive / Metacog Monitor
    # (dual_process_loop.md §6.2, I4). They compete here like any other candidate —
    # the workspace, not the offerer, decides what wins (I7: bias, never preempt).
    for off in (context.get("_workspace_offers") or []):
        if isinstance(off, dict) and off.get("content"):
            out.append(dict(off))

    return out


def offer_to_workspace(context: Dict[str, Any], candidate: Dict[str, Any]) -> None:
    """The single sanctioned way for the Executive/Monitor to push content toward
    consciousness (I4). It is queued as a candidate for the NEXT update_workspace,
    where it competes on salience — it does not flip an "is conscious" flag or
    preempt the current pick (I7). `candidate`: {content, salience, source, wants,
    kind, exempt_habituation}. Fail-safe and bounded."""
    if not isinstance(context, dict) or not isinstance(candidate, dict):
        return
    content = str(candidate.get("content") or "").strip()
    if not content:
        return
    offers = context.setdefault("_workspace_offers", [])
    if len(offers) >= 16:   # bound — a stuck offerer can't flood the workspace
        return
    offers.append({
        "source": str(candidate.get("source") or "monitor")[:48],
        "content": content[:200],
        "salience": _f(candidate.get("salience"), 0.5),
        "wants": candidate.get("wants"),
        "kind": candidate.get("kind"),
        "exempt_habituation": bool(candidate.get("exempt_habituation")),
    })


def update_workspace(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Run one workspace cycle: compete, select the single conscious content,
    broadcast it into context, and extend the continuous stream. Returns the
    conscious moment, or None when nothing is salient. Fail-safe.
    """
    try:
        cands = _candidates(context)
        if not cands:
            return None

        prev = context.get("global_workspace") or {}
        prev_key = str(prev.get("content", "")).strip().lower()[:40]
        # Recent conscious contents — used for habituation (you stop noticing a
        # constant feeling; the spotlight moves on). Without this the stream
        # sticks forever on the strongest standing affect.
        recent = context.get("_gw_recent") or []

        for c in cands:
            # I14 (habituation override): a persistent STRUCTURAL breakthrough
            # (stuck step / unmet objective) must NOT fade by repetition — silence
            # -by-habituation on a real problem is a defect. It is exempt from decay;
            # the Monitor escalates its salience with unresolved duration instead.
            if c.get("exempt_habituation"):
                continue
            key = str(c["content"]).strip().lower()[:40]
            rcount = recent.count(key)
            # Habituation: each recent appearance saps salience (cap -0.5), so
            # constants fade from awareness and other contents get their turn.
            c["salience"] -= min(0.5, rcount * 0.20)
            # Light hysteresis: hold the immediate focus briefly — but only while
            # it hasn't already habituated (rcount<=1), so it doesn't lock in.
            if prev_key and key == prev_key and rcount <= 1:
                c["salience"] += _HYSTERESIS_BONUS

        winner = max(cands, key=lambda c: c["salience"])

        # Surface the full competition (UI_FIXES Fix 4): the ranked candidates —
        # what ALMOST became conscious — used to be computed then discarded.
        # Stash a bounded, post-habituation ranking on context; the loop's
        # existing workspace mirror emit forwards it (no new emit path here —
        # this module never talks to the bridge).
        try:
            ranked = sorted(cands, key=lambda c: _f(c.get("salience")), reverse=True)
            context["_workspace_candidates"] = [{
                "source": str(c.get("source", ""))[:48],
                "content": str(c.get("content", ""))[:160],
                "salience": round(_f(c.get("salience")), 3),
                **({"kind": c["kind"]} if c.get("kind") else {}),
                **({"wants": c["wants"]} if c.get("wants") else {}),
            } for c in ranked[:6]]
        except Exception:
            pass

        # Record for habituation (bounded window).
        context["_gw_recent"] = (recent + [str(winner["content"]).strip().lower()[:40]])[-6:]
        moment = {
            "content": winner["content"],
            "source": winner["source"],
            "salience": round(float(winner["salience"]), 3),
            "ts": time.time(),
        }
        # Carry the Monitor's requested route so select_function can act on a
        # breakthrough that won consciousness (dual_process_loop.md §6.2 → §11 P3).
        if winner.get("wants"):
            moment["wants"] = winner["wants"]
        if winner.get("kind"):
            moment["kind"] = winner["kind"]
        # Offers are consumed once competed; the Monitor re-offers next cycle if the
        # condition persists (so escalation keeps working).
        context["_workspace_offers"] = []

        # ── Broadcast: every subsystem can now read "what I'm aware of". ──
        context["global_workspace"] = moment

        # ── Stream: a new conscious moment only when the content changes. ──
        stream = context.get("_conscious_stream") or []
        if not stream or stream[-1].get("content") != moment["content"]:
            stream.append(moment)
            context["_conscious_stream"] = stream[-30:]
            _append_stream(moment)
            log_private(f"[aware] ({winner['source']}) {winner['content'][:120]}")
        return moment
    except Exception as e:
        log_private(f"[global_workspace] error: {e}")
        return None


def _append_stream(moment: Dict[str, Any]) -> None:
    try:
        data: List[Dict[str, Any]] = []
        if _STREAM_FILE.exists():
            data = json.loads(_STREAM_FILE.read_text(encoding="utf-8")) or []
        data.append(moment)
        _STREAM_FILE.write_text(json.dumps(data[-_STREAM_MAX:], indent=1), encoding="utf-8")
    except Exception:
        pass


def current_awareness(context: Dict[str, Any]) -> str:
    """Convenience reader for other subsystems: the current conscious content."""
    gw = context.get("global_workspace") or {}
    return str(gw.get("content", ""))
