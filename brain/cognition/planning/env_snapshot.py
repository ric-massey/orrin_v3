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

import hashlib
import time
from typing import Any, Dict, List

from utils.log import log_private
from utils.failure_counter import record_failure

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
    if milestone.get("met"):
        return True

    text = milestone.get("text", "")
    if not text:
        return False

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
                return True
        return False  # production milestone with no real artifact evidence → unmet

    key_tokens = _milestone_tokens(text)
    if len(key_tokens) < 2:
        return False

    threshold = max(2, len(key_tokens) // 2)

    for entry in wm[-10:]:
        entry_str = str(entry.get("content", entry) if isinstance(entry, dict) else entry).lower()
        hits = sum(1 for t in key_tokens if t in entry_str)
        if hits >= threshold:
            return True

    # Tool-USE / request milestones (a tool was queued/used/requested — NOT
    # produced). "action" is deliberately excluded here: an ordinary cognition pick
    # is not tool use, and accepting it is precisely the hollow-completion bug
    # described above. Production is handled by the strict gate higher up.
    if any(w in text_lower for w in ("queued", "requested", "tool request", "used a tool")):
        for entry in wm[-5:]:
            etype = (entry.get("event_type", "") if isinstance(entry, dict) else "").lower()
            if etype in ("tool_use", "tool_request", "tool_result"):
                return True

    if any(w in text_lower for w in ("sent", "message", "said", "reply", "spoke")):
        for entry in wm[-5:]:
            etype = (entry.get("event_type", "") if isinstance(entry, dict) else "").lower()
            if etype in ("speech", "reply", "social_deficit"):
                return True

    return False


def apply_milestone_updates(context: Dict[str, Any]) -> int:
    """
    Check each milestone on the committed goal against current WM state.
    Marks newly-met milestones in-place with met=True and met_at timestamp.
    Returns count of newly ticked milestones.
    """
    goal = context.get("committed_goal")
    if not isinstance(goal, dict):
        return 0

    milestones = goal.get("milestones")
    if not isinstance(milestones, list):
        return 0

    now = time.time()
    ticked = 0
    for ms in milestones:
        if not isinstance(ms, dict) or ms.get("met"):
            continue
        if _milestone_met(ms, context):
            ms["met"] = True
            ms["met_at"] = now
            ticked += 1
            log_private(f"[env_snapshot] milestone ticked: {ms.get('text','')[:80]}")

    return ticked


def _lm_total(context: Dict[str, Any]) -> int:
    """Read long-memory total count from file (cheap: just len of JSON list)."""
    try:
        from paths import LONG_MEMORY_FILE
        import json as _json
        raw = LONG_MEMORY_FILE.read_bytes()
        # Count top-level array entries without full parse
        data = _json.loads(raw)
        return len(data) if isinstance(data, list) else 0
    except Exception as e:
        record_failure("env_snapshot._lm_total", e)
        return 0


def _tool_pending(context: Dict[str, Any]) -> int:
    """Count pending (unresolved) tool requests from context or file."""
    # Check context first (cheaper)
    reqs = context.get("tool_requests")
    if isinstance(reqs, list):
        return sum(1 for r in reqs if isinstance(r, dict) and not r.get("executed"))
    try:
        from paths import TOOL_REQUESTS_FILE
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
    goal = context.get("committed_goal") or {}
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

    result = max(0.0, min(1.0, score))
    log_private(
        f"[env_snapshot] delta_reward={result:.3f} "
        f"milestones+{new_ticks} lm+{lm_delta} tool+{tool_resolved} "
        f"wm_grew={wm_grew} thrash={wm_thrash}"
    )
    return result
