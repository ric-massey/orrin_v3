# brain/cognition/planning/goal_satiety.py
#
# Fix 1 / §4.2–4.3 (explore_loop_fix_plan.md) — the *satiety* closure pathway for
# non-trivial goals. A brain doesn't close an exploration/understanding drive
# because "one action was logged" (the old process-milestone bug); it closes when
# the drive is QUENCHED — when further effort stops yielding new information
# (habituation of the novelty/info-gain response).
#
# There are two satiety proxies, chosen by what the goal actually does (§4.2):
#   • bounded-corpus exploration (search_own_files / grep_files / survey_environment
#     over the finite filesystem)  → novelty_memory exhaustion: repeated searching
#     stops surfacing anything new.
#   • open-ended understanding/research (research_topic / wikipedia / fetch_and_read
#     over the unbounded web)       → uncertainty(topic) dropping: the info-gap on
#     the topic closes. The web never runs out of novelty, so the novelty counter
#     can't be its satiety signal — the existing info-gap signal is.
#
# Guard against cycle-1 closure: satiety can only fire AFTER the goal has actually
# done some exploration work (a completed step or a recorded observation). Without
# this a topic that merely happens to be well-covered would close instantly — the
# trivial-milestone bug through a different door (A1: "not on cycle 1").
from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from brain.utils.log import log_private

# A topic is "understood enough" at/below this info-gap (uncertainty: 0=covered…1=unknown).
_UNCERTAINTY_SATED = 0.25

_SCAFFOLD_RE = re.compile(
    r"^\s*(?:understand|learn about|find out|research|explore|read more about)\b\s*:?\s*",
    re.I,
)
_TRAILING_RE = re.compile(r"\s+more deeply\b\.?\s*$", re.I)

# Filesystem/bounded-corpus exploration goals: their "topic" is a place to look,
# not a subject of knowledge, so uncertainty(title) is meaningless for them (it can
# read as "covered" by accident and close the goal on cycle 1). These use the
# novelty-exhaustion proxy ONLY. Everything else (research/understanding) is allowed
# the uncertainty info-gap proxy. (§4.2 — two proxies by goal type.)
_FILESYSTEM_MARKERS = (
    "explore the computer", "search my own", "search own files", "my own files",
    "my files", "grep", "scan the codebase", "scan my", "what's here", "what is here",
    "files exist", "look around", "survey", "clipboard", "filesystem", "my code",
    "my architecture", "my systems", "source code",
)


def _is_filesystem_exploration(goal: Dict[str, Any]) -> bool:
    blob = f"{goal.get('title') or ''} {goal.get('name') or ''} " \
           f"{(goal.get('spec') or {}).get('description', '')} {goal.get('description', '')}".lower()
    return any(m in blob for m in _FILESYSTEM_MARKERS)


def _topic_of(goal: Dict[str, Any]) -> str:
    """Reduce a goal title to a bare topic for the uncertainty() info-gap query."""
    s = str(goal.get("title") or goal.get("name") or "").strip()
    for _ in range(6):
        before = s
        s = _TRAILING_RE.sub("", s).strip()
        s = _SCAFFOLD_RE.sub("", s).strip()
        if s == before:
            break
    return s


def _did_exploration_work(goal: Dict[str, Any], goal_id: str) -> bool:
    """True once the goal has actually explored — a completed plan step or a
    recorded novel observation. Blocks premature (cycle-1) satiety closure."""
    plan = goal.get("plan") or []
    if any(isinstance(s, dict) and s.get("status") == "completed" for s in plan):
        return True
    try:
        from brain.cognition import novelty_memory
        return novelty_memory.novel_count(goal_id) > 0
    except ImportError:  # intentional: novelty_memory optional → not satiated
        return False


def is_sated(goal: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
    """Has this goal's exploration/understanding drive been quenched?
    Returns (sated, reason). Fail-safe: any error ⇒ (False, "")."""
    try:
        if not isinstance(goal, dict):
            return False, ""
        goal_id = str(goal.get("id") or goal.get("title") or goal.get("name") or "")

        # Proxy 0 (P3) — VERIFIABLE goals close on a CHECK-PASS, and on nothing else.
        # A goal in a checkable domain (math/physics/code/statistics/logic) is
        # "understood" only once produce_and_check has recorded a passing sandbox
        # check (a tool_run_effect on the ledger). It is deliberately NOT closed by
        # the uncertainty/novelty proxies below — otherwise it would satiety-close on
        # "stopped feeling new" without ever attempting the check the plan requires.
        # A passing check is itself the work, so this precedes the work-gate.
        try:
            from brain.cognition.produce_and_check import is_verifiable_goal
            if is_verifiable_goal(goal):
                from brain.agency.effect_ledger import has_effect_kind
                if goal_id and has_effect_kind(goal_id, "tool_run_effect"):
                    return True, "check_passed"
                return False, "awaiting_check"
        except Exception as _e:
            log_private(f"[goal_satiety] verifiable check-pass proxy failed: {_e}")

        # No cycle-1 closure — require real work first.
        if not _did_exploration_work(goal, goal_id):
            return False, "no_work_yet"

        # Proxy 1 — bounded-corpus exploration exhausted (filesystem search goes barren).
        try:
            from brain.cognition import novelty_memory
            exhausted, why = novelty_memory.is_exhausted(goal_id)
            if exhausted:
                return True, f"novelty_exhausted:{why}"
        except Exception as _e:
            log_private(f"[goal_satiety] novelty check failed: {_e}")

        # Proxy 2 — info-gap on the topic has closed (understanding/research goals
        # ONLY). Skip for filesystem-exploration goals, whose title is a place to
        # look rather than a knowledge subject — uncertainty(title) is noise there
        # and would wrongly close them (they rely solely on novelty exhaustion).
        if not _is_filesystem_exploration(goal):
            topic = _topic_of(goal)
            if len(topic) >= 4:
                try:
                    from brain.symbolic.intrinsic_motivation import uncertainty
                    u = float(uncertainty(topic))
                    if u <= _UNCERTAINTY_SATED:
                        return True, f"uncertainty={u:.2f}"
                except Exception as _e:
                    log_private(f"[goal_satiety] uncertainty check failed: {_e}")

        return False, ""
    except Exception as _e:
        log_private(f"[goal_satiety] error: {_e}")
        return False, ""
