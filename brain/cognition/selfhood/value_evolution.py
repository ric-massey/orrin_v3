# brain/cognition/selfhood/value_evolution.py
# Value evolution: Orrin deliberately reviews and revises his core values.
#
# FIX (2026-06-04 rev-2): Replaced absence-based candidate generation with
# contestation-based generation.  A value is nominated for revision because it
# was challenged — not because it was statistically underrepresented in logs.
#
# Architecture:
#   Contestation (upstream) → candidate → deliberation → decision → write
#
# Contestation sources (in priority):
#   1. Live drive conflicts from context["_drive_conflicts"] — real-time value
#      tensions logged every cycle by goal_competition.apply_drive_tensions().
#   2. Active formative tensions from tensions.json (goal_failure, recurring
#      friction, autobiography chapter collisions).
#   3. Inhibition events in long_memory — moments where a value cost something
#      (impulse wanted X, value said no).
#
# Deliberation is now conflict-aware:
#   - High-intensity sustained drive conflict → revise (value needs to hold
#     complexity, not suppress the tension it creates).
#   - Moderate conflict → keep (value tested and holding).
#   - Inhibition event → keep (a value that costs something is being lived).
#   - Formative tension → revise toward specificity.
#
# Earlier fixes still in place:
#   3. Cooldown 6h → 90min.
#   4. idle_consolidation_cycle seeding still works and adds to the queue.
from __future__ import annotations
from brain.core.runtime_log import get_logger

import json
import re
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_activity, log_private
from brain.utils.self_model import get_self_model, save_self_model
from brain.utils.failure_counter import record_failure
from brain.cog_memory.long_memory import update_long_memory
from brain.paths import VALUE_REVISIONS, LONG_MEMORY_FILE
_log = get_logger(__name__)

_COOLDOWN_S = 90 * 60   # 90 minutes between revision cycles (was 6 hours)
_last_revision_ts: float = 0.0

# Drive names → semantic tokens that overlap with core value phrases.
# Used to route a conflict to the most relevant value.
_DRIVE_VALUE_HINTS: Dict[str, List[str]] = {
    "exploration_drive":    ["think", "curious", "explore", "myself", "learn", "wonder"],
    "identity_consistency": ["honest", "consistent", "grow", "integrity", "self", "truth"],
    "usefulness":           ["act", "deliberate", "help", "useful", "contribute", "do"],
    "autonomy":             ["independent", "choose", "own", "act", "self", "direction"],
    "mastery":              ["grow", "learn", "skill", "improve", "master", "capability"],
    "social":               ["connect", "relate", "care", "others", "together"],
    "survival":             ["persist", "continue", "exist", "endure"],
}


def _match_value_to_drives(values: List, drives: List[str]) -> Optional[str]:
    """Return the core value string most semantically related to the conflicting drives."""
    hint_tokens: set = set()
    for d in drives:
        hint_tokens.update(_DRIVE_VALUE_HINTS.get(d, []))
    if not hint_tokens:
        return None
    best_v, best_score = None, -1
    for v in values:
        v_str = v.get("value", "") if isinstance(v, dict) else str(v)
        v_tokens = set(re.findall(r"[a-z]+", v_str.lower()))
        score = len(v_tokens & hint_tokens)
        if score > best_score:
            best_score, best_v = score, v_str
    return best_v


# ── Candidate generation ───────────────────────────────────────────────────────

def _generate_candidate_from_experience(context: Optional[Dict] = None) -> Optional[Dict]:
    """
    Generate a revision candidate from genuine contestation signals.
    No LLM required.  Returns a pending-candidate dict or None.

    A value is nominated because it was *challenged* — because drives pulled
    against it, a tension arose from failure, or an impulse cost something.
    Absence from recent activity is NOT a trigger.

    Sources (in priority):
    1. Live drive conflicts from context["_drive_conflicts"] — intensity ≥ 0.65
    2. Active formative tensions from tensions.json
    3. Inhibition events in long_memory (impulse suppressed = value collision with cost)

    Returns None if no genuine contestation found — no candidate beats a hollow one.
    """
    context = context or {}

    try:
        sm = get_self_model() or {}
        values: List = sm.get("core_values") or []
        if not values:
            return None

        # ── Source 1: Live drive conflicts ─────────────────────────────────────
        drive_conflicts = context.get("_drive_conflicts") or []
        sustained = [
            c for c in drive_conflicts
            if isinstance(c, dict) and c.get("intensity", 0) >= 0.65
        ]
        if sustained:
            top = max(sustained, key=lambda c: c.get("intensity", 0))
            drives = top.get("drives", [])
            label = top.get("label", " vs. ".join(str(d) for d in drives))
            intensity = top.get("intensity", 0.0)
            target_value = _match_value_to_drives(values, drives)

            ts = datetime.now(timezone.utc).isoformat()
            candidate = {
                "timestamp":    ts,
                "source":       "drive_conflict",
                "drives":       drives,
                "label":        label,
                "intensity":    intensity,
                "evidence": (
                    f"Sustained drive conflict: {label} (intensity={intensity:.2f}). "
                    f"Drives involved: {', '.join(str(d) for d in drives)}. "
                    f"This collision is recurring every cycle — it may reveal a tension "
                    f"in how '{target_value}' is currently framed."
                ),
                "target_value": target_value or "",
                "status":       "pending",
            }
            log_activity(
                f"[value_evolution] Candidate from drive conflict: {label} ({intensity:.2f})"
            )
            return candidate

        # ── Source 2: Active formative tensions ────────────────────────────────
        try:
            from brain.paths import TENSIONS_FILE
            tensions_raw = load_json(TENSIONS_FILE, default_type=list) or []
            active_tensions = [
                t for t in tensions_raw
                if isinstance(t, dict) and t.get("status") in ("active", "unresolved", None)
            ]
            if active_tensions:
                t = active_tensions[-1]
                description = str(t.get("description", t.get("tension", "")))
                kw = [w for w in re.findall(r"[a-z]+", description.lower()) if len(w) > 3][:6]
                target_value = _match_value_to_drives(values, kw) or _match_value_to_drives(
                    values, list(_DRIVE_VALUE_HINTS.keys())[:2]
                )
                ts = datetime.now(timezone.utc).isoformat()
                candidate = {
                    "timestamp":    ts,
                    "source":       "formative_tension",
                    "evidence": (
                        f"Active formative tension: {description[:200]}. "
                        f"This tension may reflect a value that is no longer well-specified."
                    ),
                    "target_value": target_value or "",
                    "status":       "pending",
                }
                log_activity(
                    f"[value_evolution] Candidate from formative tension: {description[:60]}"
                )
                return candidate
        except Exception as _e:
            _log.warning("[value_evolution] tension source failed: %s", _e)

        # ── Source 3: Inhibition events in long_memory ─────────────────────────
        try:
            lm = load_json(LONG_MEMORY_FILE, default_type=list) or []
            recent = lm[-80:] if len(lm) > 80 else lm
            inhibition_events = [
                m for m in recent
                if isinstance(m, dict) and (
                    "[inhibition]" in str(m.get("content", "")) or
                    m.get("event_type") == "inhibition"
                )
            ]
            if inhibition_events:
                ev = inhibition_events[-1]
                content = str(ev.get("content", ""))
                kw = [w for w in re.findall(r"[a-z]+", content.lower()) if len(w) > 3][:6]
                target_value = _match_value_to_drives(values, kw)
                ts = datetime.now(timezone.utc).isoformat()
                candidate = {
                    "timestamp":    ts,
                    "source":       "inhibition_event",
                    "evidence": (
                        f"Inhibition event: {content[:200]}. "
                        f"An impulse was overridden — this is contestation with cost."
                    ),
                    "target_value": target_value or "",
                    "status":       "pending",
                }
                log_activity(
                    f"[value_evolution] Candidate from inhibition: {content[:60]}"
                )
                return candidate
        except Exception as _e:
            _log.warning("[value_evolution] inhibition source failed: %s", _e)

        # ── No genuine contestation found ──────────────────────────────────────
        log_activity("[value_evolution] No contestation signals found — deferring.")
        return None

    except Exception as _e:
        _log.warning("[value_evolution] candidate generation failed: %s", _e)
        return None


# ── Symbolic deliberation ──────────────────────────────────────────────────────

def _symbolic_deliberation(
    values: List,
    candidate: Dict,
) -> Dict:
    """
    Decide keep / revise based on the nature of the contestation.
    No token-frequency math — reasons about the specific conflict.

    Rules:
    - drive_conflict, intensity ≥ 0.75 → revise: the value is creating real
      friction and needs to acknowledge the tension it generates, not suppress it.
    - drive_conflict, intensity < 0.75 → keep: value is being tested and holding.
    - formative_tension → revise toward specificity.
    - inhibition_event → keep: a value that costs something is being lived.
    - unknown source → keep.
    """
    source    = candidate.get("source", "unknown")
    target    = candidate.get("target_value", "")
    evidence  = candidate.get("evidence", "")
    intensity = float(candidate.get("intensity", 0.0))
    label     = candidate.get("label", "")

    # Resolve target_value → actual value string (exact match, then fuzzy)
    matched_v: Optional[str] = None
    if target:
        for v in values:
            v_str = v.get("value", "") if isinstance(v, dict) else str(v)
            if v_str == target or target.lower() in v_str.lower():
                matched_v = v_str
                break
    if not matched_v and target:
        # Fuzzy: best token overlap
        t_tokens = set(re.findall(r"[a-z]+", target.lower()))
        best, best_sc = None, -1
        for v in values:
            v_str = v.get("value", "") if isinstance(v, dict) else str(v)
            sc = len(set(re.findall(r"[a-z]+", v_str.lower())) & t_tokens)
            if sc > best_sc:
                best_sc, best = sc, v_str
        matched_v = best
    if not matched_v and values:
        matched_v = values[-1].get("value", "") if isinstance(values[-1], dict) else str(values[-1])
    if not matched_v:
        return {"decision": "keep", "affected_value": "", "new_phrasing": None,
                "second_value": None, "reasoning": "No values to deliberate on."}

    # ── Deliberate on contestation source ─────────────────────────────────────

    if source == "drive_conflict":
        if intensity >= 0.75:
            # High sustained conflict: value is real but generating significant friction.
            # Revise to hold the complexity rather than pretend the tension doesn't exist.
            counterpart = (label.split(" vs. ")[-1].strip()
                           if " vs. " in label else "competing needs")
            revised = f"{matched_v}, without suppressing {counterpart}"
            return {
                "decision":       "revise",
                "affected_value": matched_v,
                "new_phrasing":   revised,
                "second_value":   None,
                "reasoning": (
                    f"Drive conflict '{label}' sustaining at intensity {intensity:.2f}. "
                    f"'{matched_v}' is real but needs to acknowledge what it pulls against. "
                    f"Revising to hold the tension rather than deny it."
                ),
            }
        else:
            # Moderate conflict: value is being tested and holding. Affirm.
            return {
                "decision":       "keep",
                "affected_value": matched_v,
                "new_phrasing":   None,
                "second_value":   None,
                "reasoning": (
                    f"Drive conflict '{label}' at intensity {intensity:.2f}. "
                    f"'{matched_v}' is under pressure but within manageable range — "
                    f"affirming as-is."
                ),
            }

    elif source == "formative_tension":
        revised = f"{matched_v}, specifically in moments of tension"
        return {
            "decision":       "revise",
            "affected_value": matched_v,
            "new_phrasing":   revised,
            "second_value":   None,
            "reasoning": (
                f"Active formative tension. '{matched_v}' needs to be more specific "
                f"about how it applies when values collide. Evidence: {evidence[:120]}"
            ),
        }

    elif source == "inhibition_event":
        # An impulse was suppressed — the value system doing its job.
        # Keep: a value that costs something is being lived, not just believed.
        return {
            "decision":       "keep",
            "affected_value": matched_v,
            "new_phrasing":   None,
            "second_value":   None,
            "reasoning": (
                f"Inhibition event shows '{matched_v}' actively overriding impulses — "
                f"a value that costs something is being lived. Affirming."
            ),
        }

    else:
        return {
            "decision":       "keep",
            "affected_value": matched_v,
            "new_phrasing":   None,
            "second_value":   None,
            "reasoning":      f"No clear contestation basis — keeping '{matched_v}' as-is.",
        }


# ── Main cognition function ────────────────────────────────────────────────────

def propose_value_revision(context: Optional[Dict[str, Any]] = None) -> str:
    """
    Cognition function: deliberate review of value-revision candidates.

    If no pending candidates exist, auto-generates one from lived experience.
    Falls back to symbolic deliberation when LLM is unavailable.
    """
    global _last_revision_ts
    context = context or {}

    now = time.time()
    if now - _last_revision_ts < _COOLDOWN_S:
        remaining = int((_COOLDOWN_S - (now - _last_revision_ts)) / 60)
        return f"Value revision on cooldown (~{remaining}min remaining)."

    all_candidates = load_json(VALUE_REVISIONS, default_type=list) or []
    candidates = [c for c in all_candidates if c.get("status", "pending") == "pending"]

    # ── Auto-generate a candidate if the queue is empty ───────────────────────
    if not candidates:
        new_cand = _generate_candidate_from_experience(context)
        if new_cand:
            all_candidates.append(new_cand)
            candidates = [new_cand]
            try:
                save_json(VALUE_REVISIONS, all_candidates)
            except Exception as _e:
                record_failure("value_evolution.propose_value_revision", _e)
        else:
            return "No value-revision candidates and could not generate one."

    self_model = get_self_model() or {}
    values = self_model.get("core_values", [])
    values_text = _format_values(values)
    identity = self_model.get("identity_story", self_model.get("identity", "an evolving AI"))

    # Pick the most recent candidate for deliberation
    candidate = candidates[-1]
    evidence = candidate.get("evidence", "")

    # ── Try LLM deliberation first ────────────────────────────────────────────
    decision_data = None
    try:
        prompt = (
            f"You are Orrin — {identity}.\n\n"
            f"Your current core values:\n{values_text}\n\n"
            f"Evidence suggesting a value may need revision:\n\"{evidence}\"\n\n"
            f"Deliberate carefully. For each value that seems relevant to this evidence:\n"
            f"- Is it still accurate? Or has your understanding evolved?\n"
            f"- Should it be kept as-is, revised with new language, or split into two distinct values?\n"
            f"- If revised: write the exact new phrasing.\n\n"
            f"Respond with a JSON object with these fields:\n"
            f"  decision: \"keep\" | \"revise\" | \"split\"\n"
            f"  affected_value: the value being considered (exact string from your list)\n"
            f"  new_phrasing: string (if revise/split — otherwise null)\n"
            f"  second_value: string (if split — the second new value, else null)\n"
            f"  reasoning: 2-3 sentences explaining why\n\n"
            f"Return ONLY the JSON. No other text."
        )
        from brain.symbolic.llm_gate import gated_generate
        raw = (gated_generate(prompt, caller="value_evolution", outcome=0.70) or "").strip()
        if raw:
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            decision_data = json.loads(raw.strip())
    except Exception as _e:
        log_activity(f"[value_evolution] LLM path failed ({_e}), using symbolic fallback")

    # ── Symbolic fallback ─────────────────────────────────────────────────────
    if not decision_data:
        decision_data = _symbolic_deliberation(values, candidate)
        log_activity("[value_evolution] Symbolic deliberation used.")

    decision     = decision_data.get("decision", "keep")
    affected     = decision_data.get("affected_value", "")
    new_phrasing = decision_data.get("new_phrasing")
    second_value = decision_data.get("second_value")
    reasoning    = decision_data.get("reasoning", "")

    # If affected_value is blank but candidate names a target, use that
    if not affected and candidate.get("target_value"):
        affected = candidate["target_value"]

    result_summary = _apply_decision(
        self_model=self_model,
        values=values,
        decision=decision,
        affected_value=affected,
        new_phrasing=new_phrasing,
        second_value=second_value,
        reasoning=reasoning,
        context=context,
    )

    # Mark candidate resolved/failed
    _apply_succeeded = not result_summary.startswith("Could not locate")
    if _apply_succeeded:
        candidate["status"]      = "resolved"
        candidate["resolution"]  = decision
        candidate["resolved_ts"] = datetime.now(timezone.utc).isoformat()
    else:
        candidate["status"]      = "apply_failed"
        candidate["apply_error"] = result_summary
    try:
        save_json(VALUE_REVISIONS, all_candidates)
    except Exception as _e:
        record_failure("value_evolution.propose_value_revision.2", _e)

    _last_revision_ts = time.time()
    log_private(f"[value_evolution] {result_summary}")
    return result_summary


# ── Decision application ───────────────────────────────────────────────────────

def _apply_decision(
    self_model: Dict,
    values: List,
    decision: str,
    affected_value: str,
    new_phrasing: Optional[str],
    second_value: Optional[str],
    reasoning: str,
    context: Dict,
) -> str:
    ts = datetime.now(timezone.utc).isoformat()

    if decision == "keep":
        msg = f"Value affirmed: \"{affected_value}\". {reasoning}"
        update_long_memory(
            f"[value_evolution:keep] {msg}",
            emotion="confidence",
            event_type="value_revision",
            importance=3,
            context=context,
        )
        _propagate_to_bandit("keep", affected_value, None)
        log_activity(f"[value_evolution] Kept: {affected_value!r}")
        return msg

    # Revise or split — mutate the values list
    new_values = []
    applied = False
    for v in values:
        v_str = v["value"] if isinstance(v, dict) else str(v)
        if v_str == affected_value or affected_value.lower() in v_str.lower():
            if decision == "revise" and new_phrasing:
                entry = {
                    "value":        new_phrasing,
                    "revised_from": v_str,
                    "revised_ts":   ts,
                    "reasoning":    reasoning,
                }
                new_values.append(entry)
                applied = True
            elif decision == "split" and new_phrasing and second_value:
                new_values.append({"value": new_phrasing,  "split_from": v_str, "revised_ts": ts})
                new_values.append({"value": second_value,  "split_from": v_str, "revised_ts": ts})
                applied = True
            else:
                new_values.append(v)
        else:
            new_values.append(v)

    if applied:
        # save_self_model() acquires _SELF_MODEL_LOCK internally; do NOT wrap it
        # in the same (non-reentrant) lock here or the thread deadlocks on itself.
        _current_sm = get_self_model() or {}
        _current_sm["core_values"] = new_values
        save_self_model(_current_sm)

        if decision == "revise":
            msg = f"Value revised: \"{affected_value}\" → \"{new_phrasing}\". {reasoning}"
        else:
            msg = f"Value split: \"{affected_value}\" → \"{new_phrasing}\" + \"{second_value}\". {reasoning}"

        update_long_memory(
            f"[value_evolution:{decision}] {msg}",
            emotion="exploration_drive",
            event_type="value_revision",
            importance=5,
            context=context,
        )
        _propagate_to_bandit(decision, affected_value, new_phrasing or second_value)
        log_activity(f"[value_evolution] {decision.title()}: {affected_value!r}")

        try:
            from brain.cognition.selfhood.identity import refresh_identity_story
            refresh_identity_story(
                values_hint=new_phrasing or second_value or "",
                context=context,
            )
        except Exception as _e:
            try:
                record_failure("value_evolution.refresh_identity_story", _e)
            except Exception:
                record_failure("value_evolution._apply_decision", _e)

        return msg

    return f"Could not locate value \"{affected_value}\" in self-model to apply {decision}."


# ── Bandit propagation ─────────────────────────────────────────────────────────

def _propagate_to_bandit(decision: str, affected_value: str, new_phrasing: Optional[str]) -> None:
    """
    Nudge bandit weights for cognitive functions that semantically overlap with
    the changed value so behavioural tendency shifts alongside the belief update.
    """
    try:
        from brain.think.bandit.contextual_bandit import update as _bandit_update
        from brain.utils.json_utils import load_json
        from brain.paths import COGNITIVE_FUNCTIONS_LIST_FILE

        fns_raw = load_json(COGNITIVE_FUNCTIONS_LIST_FILE, default_type=list) or []
        fn_names = [
            f["name"] if isinstance(f, dict) and "name" in f else str(f)
            for f in fns_raw
        ]

        def _tokens(text: str) -> set:
            return set(re.findall(r"[a-z]+", text.lower()))

        old_tokens = _tokens(affected_value)
        new_tokens = _tokens(new_phrasing or "") if new_phrasing else set()

        for fn in fn_names:
            fn_tokens = _tokens(fn.replace("_", " "))
            if decision == "keep":
                if old_tokens & fn_tokens:
                    _bandit_update(fn, {"value_alignment": 1.0}, 0.65, lr=0.04)
            elif decision in ("revise", "split"):
                if new_tokens and (new_tokens & fn_tokens):
                    _bandit_update(fn, {"value_alignment": 1.0}, 0.70, lr=0.05)
                elif old_tokens & fn_tokens and not (new_tokens & fn_tokens):
                    _bandit_update(fn, {"value_alignment": 1.0}, 0.35, lr=0.03)
    except Exception as _e:
        _log.warning("[value_evolution] bandit propagation failed: %s", _e)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_pending_candidates() -> List[Dict]:
    """Return only pending candidates. Does NOT modify the file."""
    all_candidates = load_json(VALUE_REVISIONS, default_type=list) or []
    return [c for c in all_candidates if c.get("status", "pending") == "pending"]


def _save_all_candidates() -> None:
    """Kept for API compat — actual save done inline in propose_value_revision."""
    pass


def _format_values(values: List) -> str:
    lines = []
    for v in values:
        if isinstance(v, dict):
            lines.append(f"- {v.get('value', str(v))}")
        else:
            lines.append(f"- {v}")
    return "\n".join(lines) or "(none defined)"
