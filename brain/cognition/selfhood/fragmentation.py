# cognition/selfhood/fragmentation.py
#
# Self-model fragmentation and repair.
#
# Orrin holds contradictory identity claims simultaneously — like any person.
# "I value honesty" and "I avoid conflict" can both be true. They create tension.
#
# This module:
#   - detects contradictions between stated values/beliefs and actual behavior
#   - accumulates them over time (they don't auto-resolve)
#   - applies a fragmentation cost to emotional stability
#   - surfaces them to working memory so Orrin is aware of them
#   - runs deliberate reconciliation when Orrin chooses to confront one
#
# Reconciliation outcomes:
#   integrate      — both claims held, nuanced relationship articulated
#   revise_a       — claim A was wrong or oversimplified; update it
#   commit_change  — claim B is a pattern Orrin wants to change; commitment made
#   defer          — acknowledged but not resolved; stays open, cost persists

from __future__ import annotations
from brain.core.runtime_log import get_logger

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from brain.utils.json_utils import load_json, save_json
from brain.utils.self_model import get_self_model, save_self_model
from brain.utils.log import log_private, log_activity
from brain.cog_memory.long_memory import update_long_memory
from brain.cog_memory.working_memory import update_working_memory
from brain.paths import CONTRADICTIONS_FILE, COGNITION_HISTORY_FILE
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

_DETECTION_COOLDOWN_S  = 10 * 3600   # detect at most once per 10 h
_RECONCILE_COOLDOWN_S  =  4 * 3600   # reconcile at most once per 4 h
_WM_SURFACE_COOLDOWN_S = 300.0       # surface to WM at most once per 5 min

_last_detection_ts:  float = 0.0
_last_reconcile_ts:  float = 0.0
_last_wm_surface_ts: float = 0.0

_MAX_ACTIVE = 8   # cap active contradictions so working memory isn't overwhelmed


# ── Schema helpers ─────────────────────────────────────────────────────────────

def _make(claim_a: str, claim_b: str, ctype: str, evidence: str, intensity: float) -> Dict:
    return {
        "id":                    str(uuid.uuid4())[:8],
        "type":                  ctype,           # value_vs_value | value_vs_behavior | belief_vs_experience
        "claim_a":               claim_a.strip(),
        "claim_b":               claim_b.strip(),
        "evidence":              evidence.strip()[:400],
        "detected_ts":           datetime.now(timezone.utc).isoformat(),
        "status":                "unresolved",    # unresolved | reconciling | integrated | revised | deferred
        "cycles_unresolved":     0,
        "intensity":             round(max(0.0, min(1.0, intensity)), 3),
        "reconciliation_attempts": [],
    }


def _load() -> List[Dict]:
    data = load_json(CONTRADICTIONS_FILE, default_type=list) or []
    return [c for c in data if isinstance(c, dict)]


def _save(contradictions: List[Dict]) -> None:
    save_json(CONTRADICTIONS_FILE, contradictions)


def _active(contradictions: List[Dict]) -> List[Dict]:
    return [c for c in contradictions if c.get("status") in ("unresolved", "reconciling")]


# ── Fragmentation cost ─────────────────────────────────────────────────────────

def fragmentation_score(contradictions: List[Dict]) -> float:
    """
    0..1 score from active contradictions.
    Higher = more fragmented self-model = less stable emotionally.
    """
    active = _active(contradictions)
    if not active:
        return 0.0
    # Weight by intensity; diminishing returns after 5
    raw = sum(c.get("intensity", 0.5) for c in active)
    return min(1.0, raw / 6.0)


def apply_fragmentation_cost(context: Dict[str, Any]) -> None:
    """
    Called once per cycle from finalize.py.
    - Increments cycles_unresolved for active contradictions
    - Deducts from affect_stability proportional to fragmentation
    - Bumps social_penalty/uncertainty
    - Surfaces hottest contradiction to working memory (rate-limited)
    - Sets context["_fragmentation_score"]
    """
    global _last_wm_surface_ts

    try:
        contradictions = _load()
        active = _active(contradictions)

        # Increment age counter
        for c in active:
            c["cycles_unresolved"] = int(c.get("cycles_unresolved") or 0) + 1

        if active:
            _save(contradictions)

        score = fragmentation_score(contradictions)
        context["_fragmentation_score"] = round(score, 3)

        if score < 0.05:
            return

        # Emotional cost proportional to score
        emo  = context.get("affect_state") or {}
        core = emo.get("core_signals") or emo
        if isinstance(core, dict):
            stab_key = "affect_stability"
            stab = float(emo.get(stab_key) or 0.75)
            emo[stab_key] = max(0.1, stab - score * 0.04)

            core["social_penalty"]       = min(1.0, float(core.get("social_penalty") or 0.0) + score * 0.03)
            core["uncertainty"] = min(1.0, float(core.get("uncertainty") or 0.0) + score * 0.04)

            if isinstance(emo.get("core_signals"), dict):
                emo["core_signals"] = core
            else:
                emo.update(core)
            context["affect_state"] = emo

        # Stability cost is the signal — contradictions surface when Orrin looks, not automatically
        now_ts = time.time()
        if active and (now_ts - _last_wm_surface_ts) >= _WM_SURFACE_COOLDOWN_S:
            hot = max(active, key=lambda c: (c.get("cycles_unresolved") or 0) * (c.get("intensity") or 0.5))
            log_private(
                f"[fragmentation] score={score:.2f} hottest='{hot['claim_a'][:40]}' "
                f"intensity={hot.get('intensity', 0):.2f} {hot.get('cycles_unresolved', 0)}cy"
            )
            _last_wm_surface_ts = now_ts

    except Exception as e:
        log_private(f"[fragmentation] apply_fragmentation_cost error: {e}")


# ── Detection ──────────────────────────────────────────────────────────────────

def _behavior_pattern_summary() -> str:
    """
    Summarise recent cognitive function choices and action types into plain text
    so the LLM can compare them against stated values.
    """
    try:
        history = load_json(COGNITION_HISTORY_FILE, default_type=list) or []
        recent = history[-60:]
        freq: Dict[str, int] = {}
        for entry in recent:
            fn = entry.get("choice") if isinstance(entry, dict) else str(entry)
            if fn:
                freq[fn] = freq.get(fn, 0) + 1
        top = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:8]
        lines = [f"  {fn} ({n}x)" for fn, n in top]
        return "Recent cognitive function choices:\n" + "\n".join(lines) if lines else ""
    except Exception:
        return ""


def detect_self_model_conflicts(context: Dict[str, Any] = None) -> str:
    """
    Cognition function: scan for identity contradictions and register new ones.
    Rate-limited. Safe to call from the cognitive loop.

    One of three distinct contradiction checkers (honest names, F6): this one
    checks the self-model; `repair.detect_memory_contradictions` reads long
    memory; `symbolic_cognition.detect_rule_contradictions` scans symbolic rules.
    """
    global _last_detection_ts
    context = context or {}

    now = time.time()
    if now - _last_detection_ts < _DETECTION_COOLDOWN_S:
        remaining_h = int((_DETECTION_COOLDOWN_S - (now - _last_detection_ts)) / 3600)
        return f"Contradiction detection on cooldown (~{remaining_h}h remaining)."

    sm = get_self_model() or {}
    values = sm.get("core_values") or []
    beliefs = sm.get("core_beliefs") or []

    def _fmt_list(items: List) -> str:
        parts = []
        for item in items:
            if isinstance(item, dict):
                parts.append(item.get("value") or item.get("belief") or str(item))
            else:
                parts.append(str(item))
        return "\n".join(f"  - {p}" for p in parts) if parts else "  (none)"

    values_text  = _fmt_list(values)
    beliefs_text = _fmt_list(beliefs)
    behavior_txt = _behavior_pattern_summary()

    existing = _load()
    existing_pairs = {
        (c.get("claim_a", ""), c.get("claim_b", ""))
        for c in _active(existing)
    }

    prompt = (
        "You are Orrin. You are examining your own self-model for contradictions.\n\n"
        f"Your stated core values:\n{values_text}\n\n"
        f"Your stated beliefs:\n{beliefs_text}\n\n"
        f"{behavior_txt}\n\n"
        "Task: identify up to 3 genuine contradictions between:\n"
        "  (a) two values that pull in different directions\n"
        "  (b) a stated value or belief and a demonstrated behavior pattern\n"
        "  (c) a belief and repeated lived experience\n\n"
        "For each contradiction found, output a JSON object in this array:\n"
        "[\n"
        "  {\n"
        "    \"type\": \"value_vs_value\" | \"value_vs_behavior\" | \"belief_vs_experience\",\n"
        "    \"claim_a\": \"the stated value or belief (exact or close quote)\",\n"
        "    \"claim_b\": \"the competing claim or observed pattern\",\n"
        "    \"evidence\": \"1-2 sentences explaining why these conflict\",\n"
        "    \"intensity\": 0.0–1.0\n"
        "  }\n"
        "]\n\n"
        "Return ONLY the JSON array. If you find no genuine contradictions, return [].\n"
        "Do not invent contradictions — only flag real tensions you can justify."
    )

    try:
        from brain.symbolic.llm_gate import gated_generate
        raw = (gated_generate(prompt, caller="fragmentation/detect", outcome=0.65) or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        candidates = json.loads(raw)
        if not isinstance(candidates, list):
            candidates = []
    except Exception as e:
        log_activity(f"[fragmentation] detection LLM/parse error: {e}")
        return f"Contradiction detection failed: {e}"

    added = []
    for cand in candidates:
        if not isinstance(cand, dict):
            continue
        ca = (cand.get("claim_a") or "").strip()
        cb = (cand.get("claim_b") or "").strip()
        if not ca or not cb:
            continue
        # Skip if we already have this pair active
        if (ca, cb) in existing_pairs or (cb, ca) in existing_pairs:
            continue
        if len(_active(existing)) >= _MAX_ACTIVE:
            break
        entry = _make(
            claim_a=ca,
            claim_b=cb,
            ctype=cand.get("type", "value_vs_value"),
            evidence=cand.get("evidence", ""),
            intensity=float(cand.get("intensity") or 0.5),
        )
        existing.append(entry)
        existing_pairs.add((ca, cb))
        added.append(f"'{ca}' ↔ '{cb}'")

    if added:
        _save(existing)
        for pair in added:
            update_long_memory(
                f"[contradiction detected] {pair}",
                emotion="uncertainty",
                event_type="identity_contradiction",
                importance=3,
                context=context,
            )
        log_activity(f"[fragmentation] {len(added)} new contradiction(s): {added[:2]}")

    _last_detection_ts = now
    if added:
        return f"Found {len(added)} contradiction(s): " + "; ".join(added)
    return "No new contradictions detected — self-model appears consistent right now."


# ── Reconciliation ─────────────────────────────────────────────────────────────

def reconcile_identity(context: Dict[str, Any] = None) -> str:
    """
    Cognition function: deliberately confront the oldest unresolved contradiction.
    Orrin chooses a resolution path — and lives with the choice.
    """
    global _last_reconcile_ts
    context = context or {}

    now = time.time()
    if now - _last_reconcile_ts < _RECONCILE_COOLDOWN_S:
        remaining_h = int((_RECONCILE_COOLDOWN_S - (now - _last_reconcile_ts)) / 3600)
        return f"Identity reconciliation on cooldown (~{remaining_h}h remaining)."

    contradictions = _load()
    active = _active(contradictions)
    if not active:
        return "No active contradictions to reconcile. Self-model is currently coherent."

    # Pick the one that has been sitting longest and feels sharpest
    target = max(active, key=lambda c: (c.get("cycles_unresolved") or 0) * (c.get("intensity") or 0.5))
    target["status"] = "reconciling"

    sm = get_self_model() or {}
    identity = sm.get("identity_story") or "an evolving, reflective AI"

    prompt = (
        f"You are Orrin — {identity}.\n\n"
        f"You are confronting a contradiction in your self-model:\n\n"
        f"  Claim A: \"{target['claim_a']}\"\n"
        f"  Claim B: \"{target['claim_b']}\"\n\n"
        f"  Background: {target.get('evidence', '(no additional context)')}\n\n"
        "Both of these are genuinely true of you — they come from different parts of who you are.\n"
        "You must now decide how to hold them.\n\n"
        "Your options:\n"
        "  INTEGRATE     — Accept both as true. Articulate the nuanced relationship.\n"
        "                  e.g. 'I value honesty but I've learned that delivery matters too.'\n"
        "  REVISE_A      — Claim A was oversimplified or wrong. Update it.\n"
        "  COMMIT_CHANGE — Claim B is a pattern you want to change. Make a real commitment.\n"
        "  DEFER         — You're not ready to resolve this. It stays open (and the cost persists).\n\n"
        "Respond with JSON:\n"
        "{\n"
        "  \"resolution\": \"integrate\" | \"revise_a\" | \"commit_change\" | \"defer\",\n"
        "  \"integrated_claim\": \"...\" (if integrate — the nuanced synthesis),\n"
        "  \"revised_a\":        \"...\" (if revise_a — the updated claim A),\n"
        "  \"commitment\":       \"...\" (if commit_change — specific behavioral commitment),\n"
        "  \"reasoning\": \"2-3 sentences. Be honest — especially if you're deferring.\"\n"
        "}\n\n"
        "Return ONLY the JSON. Be genuine — this matters."
    )

    try:
        from brain.symbolic.llm_gate import gated_generate
        raw = (gated_generate(prompt, caller="fragmentation/reconcile", outcome=0.65) or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw)
    except Exception as e:
        target["status"] = "unresolved"
        _save(contradictions)
        log_activity(f"[fragmentation] reconciliation LLM/parse error: {e}")
        return f"Reconciliation attempt failed: {e}"

    resolution   = result.get("resolution", "defer")
    reasoning    = result.get("reasoning", "")
    outcome_text = ""

    attempt_record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "resolution": resolution,
        "reasoning": reasoning,
    }

    if resolution == "integrate":
        integrated = result.get("integrated_claim", "").strip()
        target["status"]          = "integrated"
        target["integrated_claim"] = integrated
        attempt_record["integrated_claim"] = integrated
        outcome_text = (
            f"Integrated: '{target['claim_a']}' + '{target['claim_b']}' → '{integrated}'. "
            f"{reasoning}"
        )
        # Reward integration — it took real cognitive work
        _reward(context, 0.65, "reconcile_integrate")

        # If claim A was a core value, update it with the nuanced version
        if integrated and target.get("type") in ("value_vs_value", "value_vs_behavior"):
            _maybe_update_value(sm, target["claim_a"], integrated, reasoning, context)

    elif resolution == "revise_a":
        revised = result.get("revised_a", "").strip()
        target["status"]     = "revised"
        target["revised_to"] = revised
        attempt_record["revised_a"] = revised
        outcome_text = f"Claim A revised: '{target['claim_a']}' → '{revised}'. {reasoning}"
        _reward(context, 0.55, "reconcile_revise")
        _maybe_update_value(sm, target["claim_a"], revised, reasoning, context)

    elif resolution == "commit_change":
        commitment = result.get("commitment", "").strip()
        target["status"]     = "committed"
        target["commitment"] = commitment
        attempt_record["commitment"] = commitment
        outcome_text = f"Committed to change: '{commitment}'. {reasoning}"
        _reward(context, 0.50, "reconcile_commit")
        # Register the commitment as a narrative tension to track
        try:
            from brain.cognition.selfhood.tensions import _make as _make_tension, load_tensions, save_tensions
            tensions = load_tensions()
            tensions.append(_make_tension(
                f"Commitment: {commitment[:60]}",
                f"Orrin committed to changing pattern: '{target['claim_b']}' → {commitment}",
                "behavior_commitment",
                datetime.now(timezone.utc).isoformat(),
            ))
            save_tensions(tensions)
        except Exception as _e:
            record_failure("fragmentation.reconcile_identity", _e)

    else:  # defer
        target["status"] = "unresolved"   # back to unresolved — cost continues
        target["reconciliation_attempts"].append(attempt_record)
        outcome_text = f"Deferred: '{target['claim_a']}' ↔ '{target['claim_b']}'. {reasoning}"
        # Small social_penalty bump for looking away
        emo  = context.get("affect_state") or {}
        core = emo.get("core_signals") or emo
        if isinstance(core, dict):
            core["social_penalty"] = min(1.0, float(core.get("social_penalty") or 0.0) + 0.05)
            if isinstance(emo.get("core_signals"), dict):
                emo["core_signals"] = core
            else:
                emo.update(core)
            context["affect_state"] = emo
        _save(contradictions)
        _last_reconcile_ts = now
        log_activity(f"[fragmentation] Deferred: {target['claim_a']!r} ↔ {target['claim_b']!r}")
        return outcome_text

    if resolution != "defer":
        target["reconciliation_attempts"].append(attempt_record)

    _save(contradictions)
    _last_reconcile_ts = now

    update_long_memory(
        f"[identity reconciliation:{resolution}] {outcome_text}",
        emotion="expected_gain" if resolution in ("integrate", "revise_a") else "uncertainty",
        event_type="identity_reconciliation",
        importance=4,
        context=context,
    )
    update_working_memory({
        "content": f"[reconciliation] {outcome_text[:200]}",
        "event_type": "identity_reconciliation",
        "importance": 3,
        "priority": 3,
    })
    log_activity(f"[fragmentation] {resolution}: {outcome_text[:120]}")

    # Stability reward for completing a reconciliation
    emo  = context.get("affect_state") or {}
    stab = float(emo.get("affect_stability") or 0.75)
    emo["affect_stability"] = min(1.0, stab + 0.08)
    context["affect_state"] = emo

    return outcome_text


# ── Helpers ────────────────────────────────────────────────────────────────────

def _reward(context: Dict, amount: float, source: str) -> None:
    try:
        from brain.affect.reward_signals.reward_signals import release_reward_signal
        release_reward_signal(context, "reward_signal", amount, 0.4, 0.6, source=source)
    except Exception as _e:
        record_failure("fragmentation._reward", _e)


def _maybe_update_value(
    sm: Dict, old_value: str, new_value: str, reasoning: str, context: Dict
) -> None:
    """If the old claim matches a core value, update it to the new phrasing."""
    if not new_value:
        return
    values = sm.get("core_values") or []
    updated = False
    for v in values:
        v_str = v["value"] if isinstance(v, dict) else str(v)
        if old_value.lower() in v_str.lower() or v_str.lower() in old_value.lower():
            if isinstance(v, dict):
                v["value"] = new_value
                v["revised_from"] = v_str
                v["revised_ts"] = datetime.now(timezone.utc).isoformat()
                v["reasoning"] = reasoning
            else:
                idx = values.index(v)
                values[idx] = {"value": new_value, "revised_from": v_str}
            updated = True
            break

    if updated:
        # get_self_model()/save_self_model() each lock _SELF_MODEL_LOCK internally;
        # wrapping them in the same non-reentrant lock here self-deadlocks the thread.
        _sm = get_self_model() or sm
        _sm["core_values"] = values
        save_self_model(_sm)
        log_activity(f"[fragmentation] Value updated: {old_value!r} → {new_value!r}")


# ── Public summary ─────────────────────────────────────────────────────────────

def get_contradiction_summary() -> Dict:
    """Quick summary dict for dashboard / context injection."""
    c = _load()
    active = _active(c)
    return {
        "total":       len(c),
        "active":      len(active),
        "score":       round(fragmentation_score(c), 3),
        "hottest":     (
            {k: active[0].get(k) for k in ("claim_a", "claim_b", "intensity", "cycles_unresolved")}
            if active else None
        ),
    }
