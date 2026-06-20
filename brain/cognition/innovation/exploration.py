# exploration.py
from __future__ import annotations
from core.runtime_log import get_logger

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from utils.core_utils import extract_questions, rate_satisfaction
from utils.generate_response import generate_response, get_thinking_model, llm_ok
from utils.json_utils import extract_json, load_json, save_json
from utils.append import append_to_json
from cog_memory.working_memory import update_working_memory
from utils.log import log_error, log_activity

from brain.paths import (
    CURIOUS_GEORGE,
    CORE_MEMORY_FILE,
    WORLD_MODEL,
    CASUAL_RULES,            # note: txt in your paths
    PRIVATE_THOUGHTS_FILE,
    ensure_files,
)
from utils.timeutils import now_iso_z
from utils.llm_gate import llm_callable_by
from utils.failure_counter import record_failure
_log = get_logger(__name__)


def _age_seconds(iso: str) -> float:
    try:
        dt = datetime.fromisoformat((iso or "").replace("Z", "+00:00"))
    except Exception:
        dt = datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds()

def _priority(q: Dict[str, Any]) -> float:
    """Bigger = higher priority: low satisfaction, older, fewer attempts."""
    sat = float(q.get("satisfaction", 0.0))
    age = _age_seconds(q.get("last_thought", "1970-01-01T00:00:00Z"))
    tries = int(q.get("attempts", 0))
    # weights are tunable
    return (1.0 - sat) * 0.6 + (age / 3600.0) * 0.3 + (1.0 / (1 + tries)) * 0.1

def exploration_drive_loop() -> str | None:
    if not llm_callable_by("exploration"):
        log_activity("[exploration] exploration_drive_loop skipped — LLM unavailable")
        return None
    exploration_drive = load_json(CURIOUS_GEORGE, default_type=list)
    if not isinstance(exploration_drive, list):
        log_error("⚠️ CURIOUS_GEORGE is not a list. Resetting to empty list.")
        exploration_drive = []

    # Seed questions if none exist
    if not exploration_drive:
        prompt = "What am I currently curious about? What questions do I have about myself, the user, or the world?"
        new_qs = llm_ok(generate_response(prompt, config={"model": get_thinking_model()}), "exploration")
        if new_qs:
            for q in extract_questions(new_qs):
                exploration_drive.append({
                    "question": q,
                    "status": "open",
                    "attempts": 0,
                    "satisfaction": 0.0,
                    "last_thought": now_iso_z(),
                })
            save_json(CURIOUS_GEORGE, exploration_drive)

    open_qs = [q for q in exploration_drive if isinstance(q, dict) and q.get("status") == "open"]
    if not open_qs:
        return None

    # Pick least-satisfied first, refined by age and attempts
    top_q = max(open_qs, key=_priority)

    thought = llm_ok(generate_response(
        f"Think deeply about this question:\n{top_q.get('question','(missing)')}",
        config={"model": get_thinking_model()},
    ), "exploration") or ""

    update_working_memory({
        "content": f"exploration_drive: {top_q.get('question','(missing)')} → {thought}",
        "event_type": "exploration_drive",
        "importance": 1,
        "priority": 1,
    })

    top_q["attempts"] = int(top_q.get("attempts", 0)) + 1
    top_q["last_thought"] = now_iso_z()
    top_q["satisfaction"] = float(rate_satisfaction(thought))

    if top_q["satisfaction"] >= 0.95:
        top_q["status"] = "resolved"
        update_working_memory({
            "content": f"✅ Resolved exploration_drive: {top_q.get('question','(missing)')} → {thought}",
            "event_type": "exploration_drive_resolved",
            "importance": 2,
            "priority": 2,
        })

        # Append a structured JSON entry to CORE_MEMORY_FILE (don’t corrupt it with raw text)
        append_to_json(CORE_MEMORY_FILE, {
            "event": "resolved_exploration_drive",
            "question": top_q.get("question"),
            "answer": (thought or "").strip()[:300],
            "timestamp": now_iso_z(),
        })

    save_json(CURIOUS_GEORGE, exploration_drive)
    return top_q.get("status")

def _load_causal_rules_text() -> str:
    """CASUAL_RULES is a .txt in your paths; read as text."""
    try:
        p = Path(CASUAL_RULES)
        if p.exists():
            return p.read_text(encoding="utf-8")
    except Exception as _e:
        record_failure("exploration._load_causal_rules_text", _e)
    return "(no causal rules text available)"

def simulate_world_state_change(change_description: str) -> Dict[str, Any] | None:
    if not llm_callable_by("exploration"):
        log_activity("[exploration] simulate_world_state_change skipped — LLM unavailable")
        return None
    world_model = load_json(WORLD_MODEL, default_type=dict)
    if not isinstance(world_model, dict):
        log_error("⚠️ WORLD_MODEL is not a dict. Resetting to empty dict.")
        world_model = {}

    causal_rules_text = _load_causal_rules_text()

    prompt = (
        "I am Orrin, simulating a world model update.\n"
        f"Change description: '{change_description}'\n\n"
        "Here is my current internal world model:\n"
        f"{json.dumps(world_model, ensure_ascii=False, indent=2)}\n\n"
        "Here are my known causal rules (text):\n"
        f"{causal_rules_text}\n\n"
        "Predict the impact of this change using any applicable rules.\n"
        "Respond in JSON:\n"
        "{\n"
        '  "entities_changed": [""],\n'
        '  "new_events": [""],\n'
        '  "belief_impacts": [""],\n'
        '  "rules_used": [""]\n'
        "}"
    )

    # Bias toward valid JSON so extract_json succeeds
    response = llm_ok(generate_response(prompt, config={"model": get_thinking_model(), "expect_json": True}), "exploration")
    result = extract_json(response or "")

    if not result:
        update_working_memory({
            "content": f"Failed to simulate world change for: {change_description}",
            "event_type": "world_model",
            "importance": 1,
            "priority": 1,
        })
        return None

    now = now_iso_z()
    updated = False

    # Add new events
    if isinstance(result.get("new_events"), list):
        world_model.setdefault("events", [])
        for e in result["new_events"]:
            if not isinstance(e, str):
                continue
            world_model["events"].append({"description": e, "timestamp": now})
            updated = True

    # Track entity changes
    if isinstance(result.get("entities_changed"), list):
        world_model.setdefault("entities", {})
        for ent in result["entities_changed"]:
            if not isinstance(ent, str):
                continue
            world_model["entities"].setdefault(ent, {}).setdefault("history", []).append(
                {"change": change_description, "timestamp": now}
            )
            updated = True

    if updated:
        save_json(WORLD_MODEL, world_model)

    update_working_memory({
        "content": f"Simulated world change: {change_description}\nResult: {json.dumps(result, ensure_ascii=False, indent=2)}",
        "event_type": "world_model",
        "importance": 1,
        "priority": 1,
    })

    # Write a single-line entry to PRIVATE_THOUGHTS_FILE (so your line parser stays happy)
    ensure_files([Path(PRIVATE_THOUGHTS_FILE)])
    with open(PRIVATE_THOUGHTS_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{now}] World change: {change_description} | {json.dumps(result, ensure_ascii=False)}\n")

    return result
