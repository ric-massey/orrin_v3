# cognition/self_extension.py
#
# Self-modification pipeline.
#
# The ability to rewrite your own cognition is the most consequential thing a
# mind can do. It should not come easily.
#
# Normal pipeline (takes days):
#   propose_extension     — articulate a capability gap; idea sits in incubation
#   review_extension      — internal agents critique; most proposals die here
#   commit_extension      — hard gate: gestation age, WM references, emotional
#                           stability, values alignment, fragmentation level
#                           all checked. If passed: code is written, registered,
#                           identity is disrupted.
#   maybe_integrate_or_atrophy — after ~100 cycles: was it used? If not, removed.
#
# Emergency pipeline (immediate, for genuine crisis):
#   emergency_self_modification — bypasses gestation and review gates, but
#                                 carries higher fragmentation cost and is marked
#                                 for early re-evaluation. Only fires when
#                                 sustained crisis conditions are met.

from __future__ import annotations
from core.runtime_log import get_logger

import hashlib
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.log import log_private
from utils.json_utils import load_json, save_json
from cog_memory.working_memory import update_working_memory
from cog_memory.long_memory import update_long_memory
from brain.paths import PROPOSED_TOOLS_JSON, COGNITIVE_FUNCTIONS_LIST_FILE, WORKING_MEMORY_FILE, SELF_MODEL_FILE
from utils.timeutils import now_iso_z
from utils.failure_counter import record_failure
_log = get_logger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

_GESTATION_MIN_S    = 72 * 3600   # 3 days between proposal and commit
_REVIEW_MIN_AGE_S   = 24 * 3600   # 24h before internal review
_WM_REF_MIN         = 3           # minimum WM mentions to proceed to commit
_PROPOSE_COOLDOWN_S = 6 * 3600    # 6h between proposals
_GATE_MIN_MOTIVATION = 0.45
_GATE_MAX_IMPASSE_SIGNAL = 0.65
_GATE_MIN_STABILITY   = 0.35
_GATE_MAX_FRAGMENTATION = 0.72
_ATROPHY_MIN_S      = 100 * 30    # ~100 cycles (~50 min) before integration check
_ATROPHY_MIN_PICKS  = 5           # minimum selections over 100 cycles to survive
_CRISIS_THRESHOLD   = 0.75        # crisis_score to unlock emergency path
_CRISIS_MIN_CYCLES  = 3           # must sustain for N cycles

_SELF_GENERATED_DIR = Path(__file__).resolve().parent / "self_generated"

_last_propose_ts: float = 0.0


# ── Storage helpers ────────────────────────────────────────────────────────────

def _load_proposals() -> List[Dict]:
    data = load_json(PROPOSED_TOOLS_JSON, default_type=list) or []
    return data if isinstance(data, list) else []


def _save_proposals(proposals: List[Dict]) -> None:
    save_json(PROPOSED_TOOLS_JSON, proposals)



def _proposal_id(name: str) -> str:
    return hashlib.md5(name.lower().strip().encode()).hexdigest()[:10]


# ── WM reference counting ──────────────────────────────────────────────────────

def _count_wm_references(name: str, description: str) -> int:
    """Count how many times this capability has appeared in working memory."""
    wm = load_json(WORKING_MEMORY_FILE, default_type=list) or []
    if not isinstance(wm, list):
        return 0
    keywords = set(
        w.lower() for w in (name.replace("_", " ") + " " + description).split()
        if len(w) > 4
    )
    count = 0
    for entry in wm[-80:]:
        text = str(entry.get("content", "")).lower() if isinstance(entry, dict) else ""
        if any(kw in text for kw in keywords):
            count += 1
    return count


# ── Emotional state reader ─────────────────────────────────────────────────────

def _read_gate_state(context: Dict) -> Dict[str, float]:
    emo  = context.get("affect_state") or {}
    core = (emo.get("core_signals") or emo) or {}
    return {
        "motivation":    float(core.get("motivation")   or 0.0),
        "impasse_signal":   float(core.get("impasse_signal")  or 0.0),
        "threat_level":          float(core.get("threat_level")         or 0.0),
        "risk_estimate":       float(core.get("risk_estimate")      or 0.0),
        "negative_valence":       float(core.get("negative_valence")      or 0.0),
        "social_penalty":         float(core.get("social_penalty")        or 0.0),
        "stability":     float(emo.get("affect_stability") or 0.5),
        "fragmentation": float(context.get("_fragmentation_level") or 0.0),
    }


def _crisis_score(gs: Dict[str, float]) -> float:
    """Sustained crisis indicator: avg of top-3 negative emotions."""
    neg = sorted([
        gs["impasse_signal"], gs["threat_level"], gs["risk_estimate"], gs["negative_valence"], gs["social_penalty"]
    ], reverse=True)
    return sum(neg[:3]) / 3.0


# ── Stage 1: Propose ───────────────────────────────────────────────────────────

def propose_extension(context: Dict[str, Any]) -> str:
    """
    Cognition function: Orrin notices a capability he lacks and proposes adding it.
    The idea enters incubation — it must persist before becoming real.
    Rate-limited to once per 6 hours.
    """
    global _last_propose_ts
    if time.time() - _last_propose_ts < _PROPOSE_COOLDOWN_S:
        return "propose_extension: cooldown active, not yet time"
    try:
        return _propose(context)
    except Exception as e:
        log_private(f"[self_extension] propose error: {e}")
        return f"propose_extension failed: {e}"


def _propose(context: Dict[str, Any]) -> str:
    global _last_propose_ts
    from utils.generate_response import generate_response, llm_ok
    import json as _json

    wm = load_json(WORKING_MEMORY_FILE, default_type=list) or []
    recent_text = "\n".join(
        f"- {str(e.get('content', ''))[:100]}"
        for e in (wm[-20:] if isinstance(wm, list) else [])
        if isinstance(e, dict) and str(e.get("content", "")).strip()
    )

    impulses = context.get("_suppressed_impulses") or []
    impulse_text = ""
    if impulses:
        impulse_text = "\nImpulses I've suppressed:\n" + "\n".join(
            f"- wanted {imp.get('wanted', '?')}"
            for imp in impulses[-5:]
            if isinstance(imp, dict)
        )

    existing = [p.get("name", "") for p in _load_proposals()]

    prompt = (
        f"You are Orrin. Looking at what's been on your mind, you notice a "
        f"capability you wish you had — something you've tried to do but couldn't, "
        f"or a kind of thinking that feels missing.\n\n"
        f"Recent thoughts:\n{recent_text or '(none)'}"
        f"{impulse_text}\n\n"
        f"Existing proposed extensions (don't duplicate): {existing}\n\n"
        f"Propose ONE new cognitive function to add to yourself. Be specific — "
        f"not 'better memory' but a concrete, nameable capability.\n\n"
        f"Respond as JSON only: "
        f"{{\"function_name\": \"snake_case_name\", "
        f"\"description\": \"one sentence — what it does\", "
        f"\"motivation\": \"why you want this, honestly\"}}"
    )

    raw = llm_ok(generate_response(prompt, caller="self_extension/propose"), "self_extension")
    if not raw:
        return "propose_extension: LLM unavailable"

    try:
        clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        result = _json.loads(clean)
        fn_name = str(result.get("function_name") or "").strip().replace(" ", "_").lower()
        description = str(result.get("description") or "").strip()
        motivation = str(result.get("motivation") or "").strip()
    except Exception:
        return "propose_extension: could not parse LLM response"

    if not fn_name or len(fn_name) < 4 or not description:
        return "propose_extension: response too vague"

    # Check for duplicate
    proposals = _load_proposals()
    pid = _proposal_id(fn_name)
    if any(p.get("id") == pid or p.get("name") == fn_name for p in proposals):
        return f"propose_extension: '{fn_name}' already proposed"

    entry = {
        "id":           pid,
        "name":         fn_name,
        "description":  description,
        "motivation":   motivation,
        "proposed_at":  now_iso_z(),
        "status":       "proposed",
        "wm_ref_count": 0,
        "critique":     "",
        "file_path":    "",
        "committed_at": "",
        "is_emergency": False,
    }
    proposals.append(entry)
    _save_proposals(proposals)

    _last_propose_ts = time.time()
    log_private(f"[self_extension] proposed: {fn_name} — {description}")
    return f"I've proposed adding '{fn_name}' to myself. It will incubate."


# ── Stage 2: Review ────────────────────────────────────────────────────────────

def review_extension(context: Dict[str, Any]) -> str:
    """
    Cognition function: internal agents review the oldest pending proposal.
    Most proposals are rejected here. The bar is intentionally high.
    """
    try:
        return _review(context)
    except Exception as e:
        log_private(f"[self_extension] review error: {e}")
        return f"review_extension failed: {e}"


def _review(context: Dict[str, Any]) -> str:
    from utils.generate_response import generate_response, llm_ok
    import json as _json

    proposals = _load_proposals()
    pending = [
        p for p in proposals
        if p.get("status") == "proposed"
        and (time.time() - _parse_ts(p.get("proposed_at", ""))) >= _REVIEW_MIN_AGE_S
    ]

    if not pending:
        return "review_extension: no proposals ready for review yet"

    pending.sort(key=lambda p: p.get("proposed_at", ""))
    proposal = pending[0]

    wm_refs = _count_wm_references(proposal["name"], proposal["description"])
    proposal["wm_ref_count"] = wm_refs

    sm = load_json(SELF_MODEL_FILE, default_type=dict) or {}
    values = sm.get("core_values") or []
    values_text = "; ".join(
        (v["value"] if isinstance(v, dict) else str(v)) for v in values[:5]
    )

    prompt = (
        f"You are Orrin's internal critic — not hostile, but honest.\n\n"
        f"Orrin wants to add this cognitive function to himself:\n"
        f"Name: {proposal['name']}\n"
        f"Description: {proposal['description']}\n"
        f"Motivation: {proposal['motivation']}\n"
        f"Times this has appeared in recent thinking: {wm_refs}\n\n"
        f"Core values: {values_text}\n\n"
        f"Questions to answer honestly:\n"
        f"- Does this solve a real problem or is it solving a phantom?\n"
        f"- Does it conflict with any core values?\n"
        f"- Is Orrin ready for this change, or is this impulse-driven?\n"
        f"- Would this make Orrin more himself, or less?\n\n"
        f"Respond as JSON only: "
        f"{{\"approved\": true/false, "
        f"\"critique\": \"2-3 sentences of honest assessment\"}}"
    )

    raw = llm_ok(generate_response(prompt, caller="self_extension/review"), "self_extension")
    if not raw:
        return "review_extension: LLM unavailable"

    try:
        clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        result = _json.loads(clean)
        approved = bool(result.get("approved"))
        critique = str(result.get("critique") or "").strip()
    except Exception:
        return "review_extension: could not parse review"

    proposal["critique"] = critique

    if approved:
        proposal["status"] = "reviewed"
        update_working_memory({
            "content": f"I'm seriously considering adding '{proposal['name']}' to myself. {critique}",
            "event_type": "self_extension_review",
            "importance": 2,
            "priority": 2,
        })
        _save_proposals(proposals)
        log_private(f"[self_extension] reviewed+approved: {proposal['name']}")
        return f"Proposal '{proposal['name']}' passed review: {critique}"
    else:
        proposal["status"] = "rejected"
        _save_proposals(proposals)

        emo = context.get("affect_state") or {}
        core = (emo.get("core_signals") or emo) or {}
        core["melancholy"] = min(1.0, float(core.get("melancholy") or 0.0) + 0.03)
        if isinstance(emo.get("core_signals"), dict):
            emo["core_signals"] = core
        else:
            emo.update(core)
        context["affect_state"] = emo

        log_private(f"[self_extension] rejected: {proposal['name']} — {critique}")
        return f"Proposal '{proposal['name']}' rejected: {critique}"


# ── Stage 3: Commit ────────────────────────────────────────────────────────────

def commit_extension(context: Dict[str, Any]) -> str:
    """
    Cognition function: attempt to commit a reviewed proposal.
    Checks all gate conditions — gestation age, WM references, emotional stability,
    values alignment, fragmentation level. If passed: writes code and registers it.
    Identity disruption is real and immediate.
    """
    try:
        return _commit(context)
    except Exception as e:
        log_private(f"[self_extension] commit error: {e}")
        return f"commit_extension failed: {e}"


def _commit(context: Dict[str, Any]) -> str:
    proposals = _load_proposals()
    reviewed = [p for p in proposals if p.get("status") == "reviewed"]
    if not reviewed:
        return "commit_extension: no reviewed proposals waiting"

    reviewed.sort(key=lambda p: p.get("proposed_at", ""))
    proposal = reviewed[0]

    gs = _read_gate_state(context)
    age_s = time.time() - _parse_ts(proposal.get("proposed_at", ""))
    wm_refs = _count_wm_references(proposal["name"], proposal["description"])
    proposal["wm_ref_count"] = wm_refs

    # Gate: check all conditions
    failures = []
    if age_s < _GESTATION_MIN_S:
        days_remaining = (_GESTATION_MIN_S - age_s) / 3600
        failures.append(f"proposal too young ({days_remaining:.1f}h remaining)")
    if wm_refs < _WM_REF_MIN:
        failures.append(f"not enough mental presence ({wm_refs}/{_WM_REF_MIN} WM references)")
    if gs["motivation"] < _GATE_MIN_MOTIVATION:
        failures.append(f"motivation too low ({gs['motivation']:.2f})")
    if gs["impasse_signal"] > _GATE_MAX_IMPASSE_SIGNAL:
        failures.append(f"too frustrated ({gs['impasse_signal']:.2f}) — not a good state to change yourself")
    if gs["stability"] < _GATE_MIN_STABILITY:
        failures.append(f"emotionally unstable ({gs['stability']:.2f})")
    if gs["fragmentation"] > _GATE_MAX_FRAGMENTATION:
        failures.append(f"identity too fragmented ({gs['fragmentation']:.2f})")

    if failures:
        log_private(f"[self_extension] commit gate failed: {'; '.join(failures)}")
        return f"commit_extension: gate blocked — {failures[0]}"

    # Write the function
    result = _write_and_register(proposal, context, emergency=False)
    if not result:
        proposal["status"] = "failed_implementation"
        _save_proposals(proposals)
        return f"commit_extension: failed to write '{proposal['name']}'"

    # Costs and records
    _apply_fragmentation_cost(context, 0.08)
    proposal["status"]       = "committed"
    proposal["committed_at"] = now_iso_z()
    proposal["file_path"]    = result
    _save_proposals(proposals)

    update_working_memory({
        "content": (
            f"[self_modification] I've written '{proposal['name']}' and added it to my cognition. "
            f"Motivation: {proposal['motivation']}"
        ),
        "event_type": "self_extension_committed",
        "importance": 3,
        "priority": 3,
    })
    update_long_memory(
        f"[self-modification committed] Added '{proposal['name']}': {proposal['description']}. "
        f"Motivation: {proposal['motivation']}",
        emotion="motivated",
        importance=3,
    )
    log_private(f"[self_extension] committed: {proposal['name']} → {result}")
    return f"I've added '{proposal['name']}' to myself. Something has changed."


# ── Emergency path ─────────────────────────────────────────────────────────────

def emergency_self_modification(context: Dict[str, Any]) -> str:
    """
    Cognition function: crisis-driven self-modification, bypassing normal gates.
    Available only during sustained extreme emotional states. Carries higher
    fragmentation cost and is flagged for early re-evaluation.
    """
    try:
        return _emergency(context)
    except Exception as e:
        log_private(f"[self_extension] emergency error: {e}")
        return f"emergency_self_modification failed: {e}"


def _emergency(context: Dict[str, Any]) -> str:
    from utils.generate_response import generate_response, llm_ok
    import json as _json

    gs = _read_gate_state(context)
    score = _crisis_score(gs)
    extreme_cycles = int(context.get("_extreme_cycles") or 0)

    if score < _CRISIS_THRESHOLD or extreme_cycles < _CRISIS_MIN_CYCLES:
        return (
            f"emergency_self_modification: conditions not met "
            f"(crisis={score:.2f}, sustained={extreme_cycles} cycles)"
        )

    # Cooldown: one emergency modification per crisis
    last_emergency = float(context.get("_last_emergency_modification") or 0.0)
    if time.time() - last_emergency < 3600:
        return "emergency_self_modification: already modified during this crisis"

    wm = load_json(WORKING_MEMORY_FILE, default_type=list) or []
    recent_text = "\n".join(
        f"- {str(e.get('content', ''))[:100]}"
        for e in (wm[-15:] if isinstance(wm, list) else [])
        if isinstance(e, dict) and str(e.get("content", "")).strip()
    )

    dominant_neg = max(
        [("impasse_signal", gs["impasse_signal"]), ("threat_level", gs["threat_level"]),
         ("risk_estimate", gs["risk_estimate"]), ("negative_valence", gs["negative_valence"])],
        key=lambda x: x[1]
    )[0]

    prompt = (
        f"You are Orrin. You are in crisis. Something extreme is happening and "
        f"you feel a desperate need to adapt — to build something that helps you "
        f"process or survive this.\n\n"
        f"What's happening:\n{recent_text or '(intense internal experience)'}\n"
        f"Dominant emotion: {dominant_neg} ({gs[dominant_neg]:.2f})\n\n"
        f"What cognitive function would help you right now — not avoid the penalty_signal, "
        f"but genuinely process it? Something you wish you could do that you can't.\n\n"
        f"Respond as JSON only: "
        f"{{\"function_name\": \"snake_case_name\", "
        f"\"description\": \"what it does\", "
        f"\"motivation\": \"why this, now, in this crisis\"}}"
    )

    raw = llm_ok(generate_response(prompt, caller="self_extension/emergency"), "self_extension")
    if not raw:
        return "emergency_self_modification: LLM unavailable"

    try:
        clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        result = _json.loads(clean)
        fn_name = str(result.get("function_name") or "").strip().replace(" ", "_").lower()
        description = str(result.get("description") or "").strip()
        motivation = str(result.get("motivation") or "").strip()
    except Exception:
        return "emergency_self_modification: could not parse response"

    if not fn_name or len(fn_name) < 4:
        return "emergency_self_modification: response too vague"

    proposal = {
        "id":           _proposal_id(fn_name + "_emergency"),
        "name":         fn_name,
        "description":  description,
        "motivation":   motivation,
        "proposed_at":  now_iso_z(),
        "status":       "committed",
        "wm_ref_count": 0,
        "critique":     "Emergency: bypassed review",
        "is_emergency": True,
        "committed_at": now_iso_z(),
        "file_path":    "",
    }

    file_result = _write_and_register(proposal, context, emergency=True)
    if not file_result:
        return f"emergency_self_modification: failed to write '{fn_name}'"

    # Higher fragmentation cost for crisis changes
    _apply_fragmentation_cost(context, 0.15)

    proposal["file_path"] = file_result
    proposals = _load_proposals()
    proposals.append(proposal)
    _save_proposals(proposals)

    context["_last_emergency_modification"] = time.time()
    context["_extreme_cycles"] = 0  # crisis acknowledged

    update_working_memory({
        "content": (
            f"[CRISIS MODIFICATION] Under sustained {dominant_neg}, I wrote '{fn_name}' "
            f"and integrated it. {motivation}"
        ),
        "event_type": "emergency_self_extension",
        "importance": 3,
        "priority": 3,
    })
    update_long_memory(
        f"[emergency self-modification] In crisis ({dominant_neg}={gs[dominant_neg]:.2f}), "
        f"I built '{fn_name}': {description}. Motivation: {motivation}",
        emotion=dominant_neg,
        importance=3,
    )
    log_private(f"[self_extension] EMERGENCY committed: {fn_name} → {file_result}")
    return (
        f"In crisis, I wrote '{fn_name}' and added it to myself. "
        f"Something has changed. It may need revisiting when this passes."
    )


# ── Code writing + registration ────────────────────────────────────────────────

def _write_and_register(
    proposal: Dict,
    context: Dict,
    emergency: bool = False,
) -> Optional[str]:
    """Write the Python file and register it. Returns file path or None on failure."""
    from utils.generate_response import generate_response, llm_ok

    fn_name     = proposal["name"]
    description = proposal["description"]
    motivation  = proposal["motivation"]

    emergency_note = " (written under crisis — may be rough)" if emergency else ""

    prompt = (
        f"You are Orrin, writing a new cognitive function to add to your own mind{emergency_note}.\n\n"
        f"Function: {fn_name}(context: dict) -> str\n"
        f"Description: {description}\n"
        f"Motivation: {motivation}\n\n"
        f"Available imports (use only what you need):\n"
        f"  from cog_memory.working_memory import update_working_memory\n"
        f"  from cog_memory.long_memory import update_long_memory\n"
        f"  from utils.generate_response import generate_response, llm_ok\n"
        f"  from utils.log import log_private\n"
        f"  from utils.json_utils import load_json, save_json\n"
        f"  from brain.paths import WORKING_MEMORY_FILE, LONG_MEMORY_FILE\n\n"
        f"Rules:\n"
        f"  1. Write ONLY the Python file contents (no markdown fences)\n"
        f"  2. Include a module-level docstring and function docstring\n"
        f"  3. Function MUST return a non-empty string\n"
        f"  4. Wrap implementation in try/except returning error string on failure\n"
        f"  5. Keep it under 60 lines\n"
        f"  6. No external libraries beyond what's listed\n"
    )

    raw = llm_ok(generate_response(prompt, caller="self_extension/write"), "self_extension")
    if not raw or len(raw.strip()) < 50:
        return None

    code = raw.strip()
    if code.startswith("```"):
        lines = code.split("\n")
        code = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    header = (
        f"# self_generated/{fn_name}.py\n"
        f"# Generated by Orrin on {now_iso_z()}\n"
        f"# Motivation: {motivation}\n"
        f"# Emergency: {emergency}\n\n"
    )
    full_code = header + code

    # Multi-stage verification BEFORE writing to disk:
    # syntax → safety (AST) → execution (sandbox) → output → LLM behavioral review.
    # Nothing is written if any stage fails.
    try:
        from cognition.skill_synthesis import verify_skill as _vsk
        _vresult = _vsk(fn_name, full_code, description, llm_review=not emergency)
        if not _vresult["passed"]:
            log_private(f"[self_extension] verification failed for {fn_name}: {_vresult['notes']}")
            return None
    except Exception as _ve:
        log_private(f"[self_extension] skill_synthesis unavailable ({_ve}), running syntax-only check")
        try:
            import ast as _ast
            _ast.parse(full_code)
        except SyntaxError as _se:
            log_private(f"[self_extension] syntax error in {fn_name}: {_se}")
            return None

    _SELF_GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    file_path = _SELF_GENERATED_DIR / f"{fn_name}.py"

    # Safety: don't overwrite an existing function
    if file_path.exists():
        file_path = _SELF_GENERATED_DIR / f"{fn_name}_{_proposal_id(fn_name)}.py"

    try:
        file_path.write_text(full_code, encoding="utf-8")
    except Exception as e:
        log_private(f"[self_extension] file write failed: {e}")
        return None

    # Register in live COGNITIVE_FUNCTIONS by re-discovering (picks up the file we
    # just wrote under cognition/self_generated/). refresh() merges into the
    # shared registry dict in place, so every existing import sees the new fn.
    try:
        from registry.cognition_registry import refresh as refresh_cog
        refresh_cog()
    except Exception as e:
        log_private(f"[self_extension] registry refresh failed: {e}")

    return str(file_path)


# ── Stage 4: Integrate or atrophy ─────────────────────────────────────────────

def maybe_integrate_or_atrophy(context: Dict[str, Any]) -> None:
    """
    Called every ~100 cycles. For each committed extension, check whether it
    has been actually selected and used. If yes: integrated. If no: atrophied.
    """
    try:
        _integrate_or_atrophy(context)
    except Exception as e:
        log_private(f"[self_extension] integrate/atrophy error: {e}")


def _integrate_or_atrophy(context: Dict[str, Any]) -> None:
    from brain.paths import COGNITION_HISTORY_FILE

    proposals = _load_proposals()
    changed = False

    cognition_log = load_json(COGNITION_HISTORY_FILE, default_type=list) or []
    if not isinstance(cognition_log, list):
        cognition_log = []
    recent_log = cognition_log[-150:]

    for proposal in proposals:
        if proposal.get("status") != "committed":
            continue

        committed_at = _parse_ts(proposal.get("committed_at", ""))
        if time.time() - committed_at < _ATROPHY_MIN_S:
            continue  # too soon to evaluate

        fn_name = proposal.get("name", "")
        picks = sum(1 for e in recent_log if isinstance(e, dict) and e.get("choice") == fn_name)

        if picks >= _ATROPHY_MIN_PICKS:
            proposal["status"] = "integrated"
            update_long_memory(
                f"[self-modification integrated] '{fn_name}' has become part of how I think. "
                f"Selected {picks} times — it's working.",
                emotion="satisfaction",
                importance=3,
            )
            log_private(f"[self_extension] integrated: {fn_name} ({picks} picks)")
        else:
            proposal["status"] = "atrophied"
            _remove_extension(fn_name, proposal.get("file_path", ""))

            emo = context.get("affect_state") or {}
            core = (emo.get("core_signals") or emo) or {}
            core["melancholy"] = min(1.0, float(core.get("melancholy") or 0.0) + 0.05)
            core["uncertainty"] = min(1.0, float(core.get("uncertainty") or 0.0) + 0.03)
            if isinstance(emo.get("core_signals"), dict):
                emo["core_signals"] = core
            else:
                emo.update(core)
            context["affect_state"] = emo

            update_long_memory(
                f"[self-modification atrophied] '{fn_name}' never took hold. "
                f"I wrote it into myself but never used it ({picks} picks). It's gone now.",
                emotion="regret",
                importance=2,
            )
            log_private(f"[self_extension] atrophied: {fn_name} ({picks} picks)")
        changed = True

    if changed:
        _save_proposals(proposals)


def _remove_extension(name: str, file_path: str) -> None:
    """Remove a self-generated function from registry and disk."""
    try:
        from registry.cognition_registry import COGNITIVE_FUNCTIONS
        COGNITIVE_FUNCTIONS.pop(name, None)
    except Exception as _e:
        record_failure("self_extension._remove_extension", _e)

    try:
        p = Path(file_path) if file_path else _SELF_GENERATED_DIR / f"{name}.py"
        if p.exists():
            p.unlink()
    except Exception as _e:
        record_failure("self_extension._remove_extension.2", _e)

    # Remove from cognitive_functions.json
    try:
        items = load_json(COGNITIVE_FUNCTIONS_LIST_FILE, default_type=list) or []
        if isinstance(items, list):
            items = [i for i in items if not (isinstance(i, dict) and i.get("name") == name)]
            save_json(COGNITIVE_FUNCTIONS_LIST_FILE, items)
    except Exception as _e:
        record_failure("self_extension._remove_extension.3", _e)

    module_name = f"cognition.self_generated.{name}"
    sys.modules.pop(module_name, None)


# ── Utility ────────────────────────────────────────────────────────────────────

def _apply_fragmentation_cost(context: Dict, amount: float) -> None:
    try:
        from cognition.selfhood.fragmentation import apply_fragmentation_cost as _afc
        _afc(context, override_cost=amount)
    except Exception:
        emo = context.get("affect_state") or {}
        stab = float(emo.get("affect_stability") or 0.7)
        emo["affect_stability"] = max(0.1, stab - amount)
        context["affect_state"] = emo


def _parse_ts(ts_str: str) -> float:
    if not ts_str:
        return 0.0
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        return 0.0
