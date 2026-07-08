# brain/cognition/planning/env_snapshot.py
# Environment snapshot for delta-based reward computation.
#
# Reward measures what CHANGED in the system as a result of a cognition step,
# not the text quality of the output. A step is rewarded when it causes
# observable state transitions: milestones ticked, knowledge consolidated to
# long memory, tool requests resolved, or working memory meaningfully extended.
#
# Usage (in ORRIN_loop.py around each cognition function call):
#
#   pre = take_snapshot(context)
#   fn_result = _invoke_cognition(...)
#   apply_milestone_updates(context)   # marks newly-met milestones in-place
#   post = take_snapshot(context)
#   reward = delta_reward(pre, post)
#
# Milestone checking is a keyword-overlap heuristic: a milestone is considered
# met when ≥ half its non-trivial tokens appear in any of the last 10 WM entries.
# This is intentionally approximate; the goal is a signal, not a classifier.
from __future__ import annotations
from brain.cognition.global_workspace import bound_goal

import hashlib
import time
from typing import Any, Dict, List

from brain.utils.log import log_private
from brain.utils.failure_counter import record_failure

# Stopwords excluded from keyword matching
_STOP = frozenset({
    "a", "an", "the", "is", "to", "for", "in", "of", "and", "or", "my",
    "that", "has", "have", "been", "was", "are", "will", "be", "this",
    "with", "from", "its", "by", "at", "it", "i", "me", "about", "into",
    "s", "re", "ve", "ll",
})

# Reward weights
_W_MILESTONE   = 0.35   # per newly ticked milestone (the primary signal)
_W_LM_ENTRY    = 0.10   # per new long-memory entry added (max 2 counted)
_W_TOOL_RESOLVE = 0.20  # per tool request resolved (pending count dropped)
_W_WM_GREW     = 0.05   # WM content grew (weak positive)
_W_THRASH      = -0.20  # same WM hash + no growth (repetition penalty)
_W_NO_DELTA    = -0.10  # nothing changed at all (opportunity cost)
_BASE           = 0.30   # baseline: Orrin was active


def _wm_hash(context: Dict[str, Any]) -> str:
    """SHA-256 of the last 8 WM entry content strings, truncated to 16 hex chars."""
    wm = context.get("working_memory") or []
    tail = [
        str(e.get("content", e) if isinstance(e, dict) else e)
        for e in wm[-8:]
    ]
    raw = "|".join(tail).encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()[:16]


def _milestone_tokens(text: str) -> List[str]:
    """Extract non-trivial tokens from milestone text for keyword matching."""
    tokens = [
        w.strip(".,;:!?\"'").lower()
        for w in text.split()
    ]
    return [t for t in tokens if len(t) >= 3 and t not in _STOP]


def _milestone_met(milestone: Dict[str, Any], context: Dict[str, Any]) -> bool:
    """
    Heuristic check: is this milestone observable in recent working memory?
    Returns True if already marked met, or if keyword evidence is found.
    """
    return _milestone_evidence(milestone, context) is not None


def _milestone_evidence(milestone: Dict[str, Any], context: Dict[str, Any]) -> "str | None":
    """The evidence source-type that satisfies this milestone, or None if unmet.

    F11 (2026-07-08 addendum): each met milestone is stamped with WHERE the
    evidence came from, so downstream pruning/completion can refuse a milestone
    that only instrumentation "proved". Values: prior_met, production_wm,
    note_wm, goal_effect, research_lm_growth, research_wm, keyword_overlap,
    tool_use_wm, speech_wm.
    """
    if milestone.get("met"):
        return str(milestone.get("evidence_source") or "prior_met")

    text = milestone.get("text", "")
    if not text:
        return None

    text_lower = text.lower()
    wm = context.get("working_memory") or []

    # Production milestones ("a function/tool was written and registered", etc.)
    # are gated FIRST and strictly, then return — they must never fall through to
    # the looser checks below. This was the root cause of hollow output-producing
    # goal completions: the old secondary check tripped on the bare word "tool"
    # and then accepted ANY "action" event as proof, so a single search_own_files
    # pick marked "A new function or tool was written and registered" as met. That
    # false tick satisfied mark_goal_completed()'s all-milestones-met guard,
    # completing+rewarding the goal without a line of code written — which starved
    # the goal-shielding / progress-gated-reward supervisor (no active goal left to
    # supervise) and left him looping on pure exploration. Real production leaves a
    # distinctive WM trace (code_writer: "Wrote new cognitive function: ...",
    # "wrote and registered ..."); nothing short of that genuine evidence counts.
    _PRODUCTION_WORDS = ("written", "wrote", "registered", "created", "built",
                         "produced", "implemented")
    _ARTIFACT_WORDS = ("function", "tool", "capability", "module", "code")
    if (any(w in text_lower for w in _PRODUCTION_WORDS)
            and any(w in text_lower for w in _ARTIFACT_WORDS)):
        for entry in wm[-10:]:
            es = str(entry.get("content", entry) if isinstance(entry, dict) else entry).lower()
            if (("wrote new" in es and ("function" in es or "tool" in es))
                    or "wrote and registered" in es
                    or "synthesized and registered" in es):
                return "production_wm"
        return None  # production milestone with no real artifact evidence → unmet

    # NOTE milestones ("the note was written / left / delivered", "wrote a note to
    # Ric"). leave_note/write_desktop_note write the note to the outbox and drop a
    # 'note_written' marker into WM. Verify by that REAL artifact, not by whether the
    # note's prose echoes the milestone's own words — it never does (the note is about
    # its subject, e.g. the obstacle, not about "a readable note"). This is what let
    # note goals stall forever despite the note genuinely being written.
    _NOTE_ACTIONS = ("written", "wrote", "write", "left", "deliver", "compos", "record")
    if "note" in text_lower and any(w in text_lower for w in _NOTE_ACTIONS):
        for entry in wm[-12:]:
            if isinstance(entry, dict):
                et = str(entry.get("event_type", "")).lower()
                es = str(entry.get("content", "")).lower()
            else:
                et, es = "", str(entry).lower()
            if et in ("note_written", "leave_note", "desktop_note") \
                    or "[note_written]" in es or es.startswith("left a note"):
                return "note_wm"
        return None  # note milestone, no real note artifact yet → unmet

    # RESEARCH / FINDING milestones ("a finding/summary was written to long memory",
    # "a search was performed", "results were retrieved"). research_topic/wikipedia/
    # fetch_and_read store the finding and drop a '[research]'/'[wikipedia]' marker in
    # WM. Verify by that real-retrieval evidence rather than token overlap.
    _RESEARCH_HINTS = ("finding", "research", "summary of findings", "search was performed",
                       "results were retrieved", "written to long memory", "stored in long memory")
    if any(h in text_lower for h in _RESEARCH_HINTS):
        # AR7/G3: a real ledger effect for THIS goal is the strongest evidence a
        # finding was produced — honest work that recorded a credited artifact
        # (research memo, symbolic artifact, note) must not fail the milestone
        # gate because its prose doesn't echo the milestone's keywords.
        if context.get("_goal_has_effect"):
            return "goal_effect"
        # Real RESEARCH-typed long-memory growth since the goal committed = a
        # finding was genuinely stored (set by apply_milestone_updates; robust to
        # WM pruning). F11: this flag now counts only research-like event types,
        # never goal_progress/metacog_pattern/chunk instrumentation.
        if context.get("_research_progressed"):
            return "research_lm_growth"
        for entry in wm[-12:]:
            if isinstance(entry, dict):
                et = str(entry.get("event_type", "")).lower()
                es = str(entry.get("content", "")).lower()
            else:
                et, es = "", str(entry).lower()
            # Specific research-action markers only — NOT the broad "world_perception"
            # type, which look_around/environment perceptions also use (would false-tick).
            if es.startswith(("[research]", "[wikipedia]", "[fetch", "[llm_research]")) \
                    or "[research]" in es or et == "llm_tool_research":
                return "research_wm"
        return None  # research milestone, no real retrieval yet → unmet

    key_tokens = _milestone_tokens(text)
    if len(key_tokens) < 2:
        return None

    threshold = max(2, len(key_tokens) // 2)

    for entry in wm[-10:]:
        entry_str = str(entry.get("content", entry) if isinstance(entry, dict) else entry).lower()
        hits = sum(1 for t in key_tokens if t in entry_str)
        if hits >= threshold:
            return "keyword_overlap"

    # Tool-USE / request milestones (a tool was queued/used/requested — NOT
    # produced). "action" is deliberately excluded here: an ordinary cognition pick
    # is not tool use, and accepting it is precisely the hollow-completion bug
    # described above. Production is handled by the strict gate higher up.
    if any(w in text_lower for w in ("queued", "requested", "tool request", "used a tool")):
        for entry in wm[-5:]:
            etype = (entry.get("event_type", "") if isinstance(entry, dict) else "").lower()
            if etype in ("tool_use", "tool_request", "tool_result"):
                return "tool_use_wm"

    if any(w in text_lower for w in ("sent", "message", "said", "reply", "spoke")):
        for entry in wm[-5:]:
            etype = (entry.get("event_type", "") if isinstance(entry, dict) else "").lower()
            if etype in ("speech", "reply", "social_deficit"):
                return "speech_wm"

    return None


def apply_milestone_updates(context: Dict[str, Any]) -> int:
    """
    Check each milestone on the committed goal against current WM state.
    Marks newly-met milestones in-place with met=True and met_at timestamp.
    Returns count of newly ticked milestones.
    """
    goal = bound_goal(context)
    if not isinstance(goal, dict):
        return 0

    milestones = goal.get("milestones")
    if not isinstance(milestones, list):
        return 0

    # Long-memory progress signal for research/finding milestones. research_topic /
    # wikipedia_search / fetch_and_read reliably store findings in LONG memory (not
    # WM), so "a finding was written to long memory" is verified by real long-memory
    # GROWTH since this goal was committed — robust to the WM pruning/timing that left
    # the transient "[research]" marker invisible. Baseline lazily on first sight.
    # AR7/G3: effect-ledger grounding for the milestone check — the durable,
    # ungameable record of whether this goal produced anything real.
    try:
        from brain.agency.effect_ledger import has_qualifying_effect
        gid = str(goal.get("id") or "")
        context["_goal_has_effect"] = bool(gid) and has_qualifying_effect(gid, goal)
    except Exception as exc:
        record_failure("env_snapshot.goal_has_effect", exc)
        context["_goal_has_effect"] = False

    # F11 (2026-07-08 addendum): "research progressed" counts only research-like
    # long-memory growth. The old total-count proxy ticked on the goal_progress
    # entry record_goal_progress wrote every 5 cycles, so routine instrumentation
    # satisfied "a finding was written" and frontier children closed in ~90 s.
    try:
        _lm_now = _lm_research_total(context)
        if goal.get("_lm_research_baseline") is None:
            goal["_lm_research_baseline"] = _lm_now
        context["_research_progressed"] = _lm_now > int(goal.get("_lm_research_baseline") or 0)
    except Exception:
        context["_research_progressed"] = False

    now = time.time()
    ticked = 0
    for ms in milestones:
        if not isinstance(ms, dict) or ms.get("met"):
            continue
        source = _milestone_evidence(ms, context)
        if source is not None:
            ms["met"] = True
            ms["met_at"] = now
            ms["evidence_source"] = source   # F11: provenance for downstream gates
            ticked += 1
            log_private(f"[env_snapshot] milestone ticked ({source}): "
                        f"{ms.get('text','')[:80]}")

    return ticked


def _lm_total(context: Dict[str, Any]) -> int:
    """Read long-memory total count from file (cheap: just len of JSON list)."""
    try:
        from brain.paths import LONG_MEMORY_FILE
        import json as _json
        raw = LONG_MEMORY_FILE.read_bytes()
        # Count top-level array entries without full parse
        data = _json.loads(raw)
        return len(data) if isinstance(data, list) else 0
    except Exception as e:
        record_failure("env_snapshot._lm_total", e)
        return 0


# F11: event types that count as research/finding evidence. Instrumentation
# types (goal_progress, metacog_pattern, chunk, goal_pursuit, …) never qualify —
# they record that pursuit HAPPENED, not that anything was learned.
_RESEARCH_EVENT_TYPES = frozenset({
    "world_perception", "research", "finding", "llm_tool_research",
    "web_research", "wikipedia", "dream_insight",
})


def _lm_research_total(context: Dict[str, Any]) -> int:
    """Count long-memory entries whose event_type is research-like."""
    try:
        from brain.paths import LONG_MEMORY_FILE
        import json as _json
        data = _json.loads(LONG_MEMORY_FILE.read_bytes())
        if not isinstance(data, list):
            return 0
        return sum(
            1 for e in data
            if isinstance(e, dict)
            and str(e.get("event_type") or "") in _RESEARCH_EVENT_TYPES
        )
    except Exception as e:
        record_failure("env_snapshot._lm_research_total", e)
        return 0


def _tool_pending(context: Dict[str, Any]) -> int:
    """Count pending (unresolved) tool requests from context or file."""
    # Check context first (cheaper)
    reqs = context.get("tool_requests")
    if isinstance(reqs, list):
        return sum(1 for r in reqs if isinstance(r, dict) and not r.get("executed"))
    try:
        from brain.paths import TOOL_REQUESTS_FILE
        import json as _json
        data = _json.loads(TOOL_REQUESTS_FILE.read_bytes())
        if isinstance(data, list):
            return sum(1 for r in data if isinstance(r, dict) and not r.get("executed"))
    except Exception as e:
        record_failure("env_snapshot._tool_pending", e)
    return 0


def take_snapshot(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Capture a lightweight state bundle before or after a cognition step.
    """
    wm = context.get("working_memory") or []
    goal = bound_goal(context) or {}
    milestones = goal.get("milestones") or []

    return {
        "ts":             time.time(),
        "wm_len":         len(wm),
        "wm_hash":        _wm_hash(context),
        "lm_total":       _lm_total(context),
        "tool_pending":   _tool_pending(context),
        "milestone_met":  [bool(ms.get("met")) for ms in milestones if isinstance(ms, dict)],
    }


def delta_reward(pre: Dict[str, Any], post: Dict[str, Any]) -> float:
    """
    Compute reward from the observable change between two snapshots.
    Returns a float in [0.0, 1.0].

    Reward components (in priority order):
      +0.35 per milestone newly ticked     (strongest signal)
      +0.20 per tool request resolved
      +0.10 per new long-memory entry (capped at 2)
      +0.05 if working memory grew
      -0.20 if WM hash unchanged AND WM didn't grow (thrash)
      -0.10 if absolutely nothing changed (opportunity cost)
      +0.30 baseline for being active
    """
    if not pre or not post:
        return 0.40  # neutral when no snapshot data

    # Milestones
    pre_met  = pre.get("milestone_met", [])
    post_met = post.get("milestone_met", [])
    new_ticks = sum(
        1 for i in range(len(post_met))
        if post_met[i] and (i >= len(pre_met) or not pre_met[i])
    )

    # Long-memory growth
    lm_delta = max(0, post.get("lm_total", 0) - pre.get("lm_total", 0))

    # Tool requests resolved
    tool_resolved = max(0, pre.get("tool_pending", 0) - post.get("tool_pending", 0))

    # WM growth
    wm_grew  = post.get("wm_len", 0) > pre.get("wm_len", 0)
    wm_thrash = (
        post.get("wm_hash") is not None
        and post.get("wm_hash") == pre.get("wm_hash")
        and not wm_grew
    )

    score = _BASE
    score += new_ticks           * _W_MILESTONE
    score += min(lm_delta, 2)    * _W_LM_ENTRY
    score += min(tool_resolved, 2) * _W_TOOL_RESOLVE
    score += _W_WM_GREW if wm_grew else 0.0

    if wm_thrash:
        score += _W_THRASH

    total_delta = new_ticks + lm_delta + tool_resolved + (1 if wm_grew else 0)
    if total_delta == 0:
        score += _W_NO_DELTA

    result = float(max(0.0, min(1.0, score)))
    log_private(
        f"[env_snapshot] delta_reward={result:.3f} "
        f"milestones+{new_ticks} lm+{lm_delta} tool+{tool_resolved} "
        f"wm_grew={wm_grew} thrash={wm_thrash}"
    )
    return result
