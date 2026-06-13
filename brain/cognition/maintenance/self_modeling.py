# self_modeling.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from utils.json_utils import load_json, extract_json
from utils.self_model import get_self_model, save_self_model
from utils.log import log_model_issue, log_private, log_error
from paths import FEEDBACK_LOG, LONG_MEMORY_FILE


def _parse_iso_dt(s: str) -> Optional[datetime]:
    """
    Robust ISO parser:
    - accepts 'Z' suffix
    - returns None on failure
    """
    if not s or not isinstance(s, str):
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except Exception:
        return None


# ----------------------------
# Maintenance routines
# ----------------------------

def prune_old_threads(max_default_days: int = 14, max_default_threads: int = 10) -> str:
    self_model = get_self_model()
    if not isinstance(self_model, dict):
        return "❌ Invalid self model. Expected a dict."

    config = self_model.get("config", {})
    if not isinstance(config, dict):
        config = {}

    max_age_days = int(config.get("max_thread_age_days", max_default_days))
    max_threads = int(config.get("max_imaginative_threads", max_default_threads))

    threads = self_model.get("imaginative_threads", [])
    if not isinstance(threads, list):
        threads = []

    now = datetime.now(timezone.utc)

    def _age_days(th: Dict[str, Any]) -> Optional[int]:
        dt = _parse_iso_dt(th.get("timestamp", ""))
        return (now - dt).days if dt else None

    # Keep only dicts with acceptable age
    kept = []
    for th in threads:
        if not isinstance(th, dict):
            continue
        age = _age_days(th)
        if age is None or age <= max_age_days:
            kept.append(th)

    # Prefer newest items: sort by timestamp (fallback to keep original order)
    def _key(th: Dict[str, Any]):
        dt = _parse_iso_dt(th.get("timestamp", "")) or datetime.min.replace(tzinfo=timezone.utc)
        return dt

    kept.sort(key=_key)
    if len(kept) > max_threads:
        kept = kept[-max_threads:]

    removed_count = len(threads) - len(kept)
    self_model["imaginative_threads"] = kept
    save_self_model(self_model)

    if removed_count > 0:
        log_private(f"Orrin pruned {removed_count} old imaginative thread(s).")
    return f"✅ Pruned; kept {len(kept)} thread(s)."


def update_influence_scores_from_feedback(increment: float = 0.05) -> str:
    feedback = load_json(FEEDBACK_LOG, default_type=list)
    if not isinstance(feedback, list):
        feedback = []

    self_model = get_self_model()
    if not isinstance(self_model, dict):
        return "❌ Invalid self model."

    agents = self_model.get("internal_agents", [])
    if not isinstance(agents, list):
        agents = []

    # Success detection is flexible: supports boolean or text fields
    def _is_success(entry: Dict[str, Any]) -> bool:
        if "success" in entry and isinstance(entry["success"], bool):
            return entry["success"]
        result = str(entry.get("result", "")).lower()
        return "success" in result or "succeeded" in result or "passed" in result

    successes = [e for e in feedback if isinstance(e, dict) and _is_success(e)]
    if not successes:
        save_self_model(self_model)  # no-op but consistent
        return "ℹ️ No successful feedback entries found."

    # Update influence scores for matching agents
    name_to_agent = {a.get("name"): a for a in agents if isinstance(a, dict) and a.get("name")}
    for entry in successes:
        agent_name = entry.get("agent") or entry.get("agent_name")
        if agent_name and agent_name in name_to_agent:
            a = name_to_agent[agent_name]
            current = float(a.get("influence_score", 0.5))
            a["influence_score"] = min(current + float(increment), 1.0)

    self_model["internal_agents"] = agents
    save_self_model(self_model)
    return f"✅ Updated influence scores from {len(successes)} success entries."


def self_model_maintenance_cycle() -> None:
    prune_old_threads()
    update_influence_scores_from_feedback()
    # Add more routines here if needed


# ----------------------------
# Self-supervised repair
# ----------------------------

def self_supervised_repair() -> str:
    self_model = get_self_model()
    long_memory = load_json(LONG_MEMORY_FILE, default_type=list)

    if not isinstance(self_model, dict) or not isinstance(long_memory, list):
        return "❌ Missing or invalid state for repair."

    recent = [
        m.get("content")
        for m in long_memory[-12:]
        if isinstance(m, dict) and isinstance(m.get("content"), str)
    ]

    # Primary: symbolic contradiction detection + direct field update
    try:
        from symbolic.symbolic_cognition import detect_rule_contradictions as _dc, update_self_model_fields as _usf
        contradictions = _dc(self_model)
        upd = _usf(self_model)
        if upd["updated_fields"] or contradictions:
            self_model.update(upd["updated_fields"])
            if contradictions:
                existing = self_model.get("emerging_conflicts", [])
                new_conflicts = [
                    c.get("belief", c.get("reason", "")) for c in contradictions
                    if c.get("belief") or c.get("reason")
                ]
                self_model["emerging_conflicts"] = list(set(existing + new_conflicts))
            save_self_model(self_model)
            log_private(f"Self-supervised repair (symbolic): {upd['changes']} | {len(contradictions)} contradictions.")
            return "✅ Self model repaired (symbolic)."
    except Exception as _se:
        log_error(f"[self_supervised_repair] symbolic path error: {_se}")

    # Last resort: gated_generate — only when the LLM tool is actually up.
    # Tool absence is normal: skip cleanly, no model-issue logging.
    try:
        from utils.llm_gate import llm_available
        if not llm_available():
            return "ℹ️ Symbolic repair found nothing to change (LLM tool unavailable)."
    except Exception:
        pass
    if not recent:
        return "ℹ️ No recent thoughts for repair."

    prompt = (
        "I am a self-reflective AI.\n"
        "Compare the following recent thoughts against my current self_model.\n"
        "Look for internal contradictions, emotional tensions, or value misalignments.\n"
        "If contradictions exist, try to:\n"
        "- Add or revise `biases`, `stances`, or `recent_changes`\n"
        "- Flag conflicting `core_beliefs`\n"
        "- Gently revise `identity_story` if it no longer fits\n\n"
        "Recent thoughts:\n"
        + "\n".join(f"- {t}" for t in recent)
        + "\n\nCurrent self_model:\n"
        + json.dumps(self_model, ensure_ascii=False, indent=2)[:1200]
        + "\n\nRespond ONLY with a JSON patch of changed fields (not the full model)."
    )

    try:
        from symbolic.llm_gate import gated_generate
        response = gated_generate(prompt, caller="self_supervised_repair", outcome=0.65)
    except Exception as e:
        log_model_issue(f"[self_supervised_repair] gated_generate error: {e}")
        return "⚠️ No response from model."

    if not response:
        return "⚠️ No response from model."

    try:
        updated = extract_json(response)
        if isinstance(updated, dict):
            self_model.update(updated)
            save_self_model(self_model)
            log_private("Self-supervised contradiction repair occurred (gated_generate).")
            return "✅ Self model repaired."
        else:
            log_model_issue("[self_supervised_repair] Model did not return a dict.")
            return "❌ Repair parse failed."
    except Exception as e:
        log_model_issue(f"[self_supervised_repair] JSON parse error: {e}\nRaw: {response}")
        return "❌ Repair parse exception."