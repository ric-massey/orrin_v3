# utils/emotional_response.py
from __future__ import annotations

from typing import Any, Dict, Optional
from affect.threat_detector import process_affective_signals
from utils.generate_response import generate_response, llm_ok

def generate_emotional_response(
    prompt: str,
    model: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Run prompt through the threat_detector first; if a threat shortcut is triggered,
    return a short-circuit message; otherwise delegate to the LLM.

    Returns a string response (or an error-style string if the shortcut fired).
    """
    context: Dict[str, Any] = {
        "input_text": prompt,
        "mode": {"mode": "thinking"},
    }

    try:
        context, threat_detector_response = process_affective_signals(context)
    except Exception:
        # If the threat_detector path fails for any reason, fall back to normal generation
        return llm_ok(generate_response(prompt, model=model, config=config), "emotional_response")

    threat = bool(threat_detector_response and threat_detector_response.get("threat_detected"))
    if threat:
        shortcut = threat_detector_response.get("shortcut_function") or "safety_reflex"
        tags = threat_detector_response.get("threat_tags", [])
        return f"⚠️ threat_detector triggered a shortcut: {shortcut} due to {tags}"

    # No threat—proceed normally
    return llm_ok(generate_response(prompt, model=model, config=config), "emotional_response")