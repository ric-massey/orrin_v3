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

import re
import time
from typing import Any, Dict, List, Optional

from brain.paths import DATA_DIR
from brain.utils.log import log_private
from brain.utils.failure_counter import record_failure

_STREAM_FILE = DATA_DIR / "workspace_broadcast.json"
_STREAM_MAX = 200          # persisted stream length
_HYSTERESIS_BONUS = 0.15   # continuity: the current focus is favoured to persist

_NOISE = (
    "[chunk:", "[metacog", "cpu=", "🧠", "🌓", "⏳", "🔄", "health summary",
    "[energy]", "[state_processor]", "[working_memory]", "[symbolic]",
    "spoke:", "chose:", "[done]",
)

_SUBCONSCIOUS_EVENTS = {"subconscious_pattern", "incubated_insight", "emotional_residue"}
_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_'-]{2,}")
_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "about", "have",
    "has", "had", "was", "were", "are", "but", "not", "you", "your", "orrin",
    "while", "something", "toward", "working", "notice", "connection", "memory",
}


def _f(x: Any, d: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def _is_noise(c: str) -> bool:
    cl = (c or "").strip().lower()
    return (not cl) or any(m in cl for m in _NOISE)


def _tokens(text: str) -> set:
    return {t.lower() for t in _TOKEN_RE.findall(text or "") if t.lower() not in _STOPWORDS}


def _overlap(a: str, b: str) -> float:
    aa, bb = _tokens(a), _tokens(b)
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / max(1, min(len(aa), len(bb)))


def _workspace_reference_text(context: Dict[str, Any]) -> str:
    parts: List[str] = []
    for key in ("latest_user_input", "last_function_chosen", "last_function"):
        val = context.get(key)
        if val:
            parts.append(str(val))
    gw = context.get("global_workspace") or {}
    if isinstance(gw, dict):
        parts.append(str(gw.get("content") or ""))
    cg = bound_goal(context)
    if isinstance(cg, dict):
        parts.append(str(cg.get("title") or cg.get("name") or ""))
        parts.append(str(cg.get("description") or ""))
    for sig in (context.get("top_signals") or [])[:3]:
        if isinstance(sig, dict):
            parts.append(str(sig.get("content") or sig.get("summary") or ""))
    return " ".join(p for p in parts if p)


def _subconscious_relevance(candidate: Dict[str, Any], context: Dict[str, Any]) -> Optional[float]:
    if candidate.get("event_type") not in _SUBCONSCIOUS_EVENTS and candidate.get("source") != "subconscious":
        return None
    origin = candidate.get("workspace_origin") or {}
    if not isinstance(origin, dict):
        return None
    origin_text = str(origin.get("content") or "")
    ref_text = _workspace_reference_text(context)
    if not origin_text or not ref_text:
        return None
    return max(_overlap(origin_text, ref_text), _overlap(str(candidate.get("content") or ""), ref_text) * 0.5)


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

    # The goal he is pursuing. Carry its id so the conscious moment can be bound to
    # the authoritative goal OBJECT, not just a text echo of its title (D3).
    cg = bound_goal(context)
    if isinstance(cg, dict) and (cg.get("title") or cg.get("name")):
        out.append({"source": "goal",
                    "content": f"working toward: {cg.get('title') or cg.get('name')}",
                    "salience": 0.55,
                    "goal_id": cg.get("id")})

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
            cand = {"source": "thought", "content": c[:160], "salience": 0.35}
            if isinstance(e, dict):
                if e.get("source") == "subconscious" or e.get("event_type") in _SUBCONSCIOUS_EVENTS:
                    cand["source"] = "subconscious"
                for key in ("event_type", "workspace_origin"):
                    if e.get(key) is not None:
                        cand[key] = e.get(key)
            out.append(cand)
            break

    # Contents OFFERED to consciousness by the Executive / Metacog Monitor
    # (dual_process_loop.md §6.2, I4). They compete here like any other candidate —
    # the workspace, not the offerer, decides what wins (I7: bias, never preempt).
    for off in (context.get("_workspace_offers") or []):
        if isinstance(off, dict) and off.get("content"):
            out.append(dict(off))

    # Bound situations are additive candidates: their atomic members remain in
    # the field and the ordinary workspace competition decides whether the
    # unified situation is salient enough to ignite.
    for comp in (context.get("_bound_candidates") or []):
        if isinstance(comp, dict) and comp.get("content"):
            out.append(dict(comp))

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
        # Top-down write-back: drain the salience-prior store one step before this
        # cycle's competition reads it (the store is designed to forget — decay is
        # the only persistence). Cheap; fail-safe inside.
        try:
            from brain.cognition.workspace_writeback import tick_salience_priors
            tick_salience_priors(context)
        except Exception as exc:
            record_failure("global_workspace.tick_priors", exc)

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
            try:
                from brain.cognition.goal_lens import relevance as _goal_relevance
                lens_rel = _goal_relevance(context.get("goal_lens"), c.get("content") or "")
                if lens_rel:
                    c["goal_lens_relevance"] = round(lens_rel, 3)
                    c["salience"] += min(0.18, 0.18 * lens_rel)
            except Exception as exc:
                record_failure("global_workspace.goal_lens_relevance", exc)
            try:
                from brain.cognition.workspace_writeback import salience_prior as _sp
                sp = _sp(context, c.get("content") or "")
                if sp:
                    c["salience_prior"] = round(sp, 3)
                    c["salience"] += sp
            except Exception as exc:
                record_failure("global_workspace.salience_prior", exc)
            rel = _subconscious_relevance(c, context)
            if rel is not None:
                c["subconscious_relevance"] = round(rel, 3)
                if rel >= 0.22:
                    c["salience"] += 0.16
                    c["subconscious_gate"] = "relevant"
                else:
                    c["salience"] -= 0.22
                    c["subconscious_gate"] = "stale"
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
                **({"facets": c["facets"]} if c.get("facets") else {}),
                **({"object": c["object"]} if c.get("object") else {}),
                **({"members": c["members"]} if c.get("members") else {}),
                **({"subconscious_relevance": c["subconscious_relevance"]} if c.get("subconscious_relevance") is not None else {}),
                **({"subconscious_gate": c["subconscious_gate"]} if c.get("subconscious_gate") else {}),
                **({"goal_lens_relevance": c["goal_lens_relevance"]} if c.get("goal_lens_relevance") is not None else {}),
                **({"salience_prior": c["salience_prior"]} if c.get("salience_prior") is not None else {}),
            } for c in ranked[:6]]
        except Exception as exc:
            record_failure("global_workspace.candidate_telemetry", exc)

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
        if winner.get("source") == "binding":
            for key in ("facets", "object", "members", "referent_links"):
                if winner.get(key) is not None:
                    moment[key] = winner[key]
        # D3 (Option D — one goal, many views): bind the conscious goal-moment to the
        # authoritative goal object by id, so "the goal I'm aware of" and "the goal
        # I'm pursuing" are provably the SAME thing, not two copies that can drift.
        if winner.get("goal_id"):
            moment["goal_id"] = winner["goal_id"]
        elif winner.get("source") == "binding":
            _bound_gid = (winner.get("facets") or {}).get("goal_id")
            if _bound_gid:
                moment["goal_id"] = _bound_gid
        if winner.get("subconscious_relevance") is not None:
            moment["subconscious_relevance"] = winner["subconscious_relevance"]
            moment["subconscious_gate"] = winner.get("subconscious_gate")
        # Offers are consumed once competed; the Monitor re-offers next cycle if the
        # condition persists (so escalation keeps working).
        context["_workspace_offers"] = []
        context["_bound_candidates"] = []

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
        from brain.utils.json_utils import modify_json
        with modify_json(_STREAM_FILE, list) as data:
            data.append(moment)
            if len(data) > _STREAM_MAX:
                del data[:-_STREAM_MAX]
    except Exception as exc:
        record_failure("global_workspace.append_stream", exc)


def current_awareness(context: Dict[str, Any]) -> str:
    """Convenience reader for other subsystems: the current conscious content."""
    gw = context.get("global_workspace") or {}
    return str(gw.get("content", ""))


def bound_goal(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The single authoritative committed goal every subsystem should read —
    "one goal, many views" (GOALS_MASTER_PLAN Part II / Option D, D3).

    It is the v1 cognitive goal object in context["committed_goal"] (authoritative
    for tier/origin/plan after Part II). When the workspace currently has a goal in
    focus, its conscious moment carries `goal_id` bound to THIS object's id — so the
    awareness view and the pursuit view can't drift into two different goals.
    Returns None when no goal is committed.

    Accepts any non-empty committed_goal dict (not only one with a title): some
    callers read control flags off an in-flight goal — `_drift_detected`,
    `_needs_deliberate_action` — before/while a title settles. This keeps the
    single accessor behaviour-equivalent to the legacy `context.get("committed_goal")`
    truthiness it replaced (an empty/absent goal is still falsy → None)."""
    cg = context.get("committed_goal")
    if isinstance(cg, dict) and cg:
        return cg
    return None


def goal_in_focus(context: Dict[str, Any]) -> bool:
    """True when the goal Orrin is consciously aware of right now is the committed
    goal (bound by id). Lets a subsystem tell "I'm attending to my goal" from "my
    goal is merely committed but something else is in the spotlight"."""
    gw = context.get("global_workspace") or {}
    gid = gw.get("goal_id")
    cg = bound_goal(context)
    return bool(gid and cg and str(gid) == str(cg.get("id")))
