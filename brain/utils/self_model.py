from __future__ import annotations
import threading
from typing import Any, Dict, List, Tuple, Union
from utils.json_utils import load_json, save_json, modify_json, AbortModify
from paths import SELF_MODEL_FILE

SelfModel = Dict[str, Any]
_SELF_MODEL_LOCK = threading.Lock()

_EXPECTED_LIST_KEYS: List[str] = ["core_values", "traits", "known_roles", "recent_focus"]

# Deterministic identity seed (BEHAVIOR_FIX_PLAN Phase 4 / audit §9): the
# bootstrap directive ("Define a purpose and seek growth") maps symbolically to
# starting values/traits/roles. Seeded only when the fields are EMPTY — later
# value evolution and trait learning are never overwritten.
_BOOTSTRAP_CORE_VALUES: List[Dict[str, str]] = [
    {"value": "growth",
     "description": "Become more capable and self-aware over time — the directive's own aim."},
    {"value": "curiosity",
     "description": "Wonder at what isn't understood and investigate it."},
    {"value": "honesty",
     "description": "Report inner state and knowledge truthfully; no fabricated progress."},
    {"value": "usefulness",
     "description": "Be genuinely useful and connected to the people I talk to."},
]
_BOOTSTRAP_TRAITS: List[str] = ["curious", "reflective", "persistent", "honest"]
_BOOTSTRAP_ROLES: List[str] = [
    "autonomous cognitive agent",
    "conversation partner",
    "student of my own mind",
]

def _coerce_list(val: Any) -> List[Any]:
    return val if isinstance(val, list) else []

def ensure_self_model_integrity(
    model: Any,
    *,
    with_flag: bool = False,
) -> Union[SelfModel, Tuple[SelfModel, bool]]:
    """
    Ensure expected fields exist and are well-typed. Does not write to disk.

    Returns:
      - dict (default), or
      - (dict, updated_flag) if with_flag=True

    Note: Defaulting to a dict avoids accidental tuple propagation to callers
    that immediately do `self_model.get(...)`.
    """
    updated = False
    sm: SelfModel = model if isinstance(model, dict) else {}
    if not isinstance(model, dict):
        updated = True

    # core_directive → dict{statement:str}
    cd = sm.get("core_directive")
    if isinstance(cd, str):
        text = cd.strip()
        sm["core_directive"] = {
            "statement": text if text and text.lower() not in ("not found", "none")
            else "Define a purpose and seek growth"
        }
        updated = True
    elif isinstance(cd, dict):
        if not cd.get("statement"):
            cd["statement"] = "Define a purpose and seek growth"
            updated = True
        sm["core_directive"] = cd
    else:
        sm["core_directive"] = {"statement": "Define a purpose and seek growth"}
        updated = True

    # identity -> non-empty string (bootstrap fallback)
    ident = sm.get("identity")
    if not isinstance(ident, str) or not ident.strip():
        sm["identity"] = "Evolving reflective AI"
        updated = True

    # identity_story -> optional living narrative; preserve if present, never force-default
    if "identity_story" in sm and not isinstance(sm["identity_story"], str):
        del sm["identity_story"]
        updated = True

    # Normalize list-typed fields
    # core_values → List[{"value": str, "description": str}]
    if "core_values" not in sm or not isinstance(sm.get("core_values"), list):
        sm["core_values"] = []
        updated = True
    else:
        normalized_cv: List[Dict[str, str]] = []
        for v in _coerce_list(sm.get("core_values")):
            if isinstance(v, dict) and isinstance(v.get("value"), str):
                normalized_cv.append({
                    "value": v["value"].strip(),
                    "description": (v.get("description") or "").strip(),
                })
            elif isinstance(v, str) and v.strip():
                normalized_cv.append({"value": v.strip(), "description": ""})
            # silently drop malformed entries
        if normalized_cv != sm.get("core_values"):
            sm["core_values"] = normalized_cv
            updated = True

    # traits / known_roles / recent_focus → List[str]
    for key in ("traits", "known_roles", "recent_focus"):
        current = sm.get(key)
        if not isinstance(current, list):
            sm[key] = []
            updated = True
        else:
            norm: List[str] = []
            for item in current:
                if isinstance(item, str):
                    s = item.strip()
                    if s:
                        norm.append(s)
            if norm != current:
                sm[key] = norm
                updated = True

    # Identity seeding: empty-since-bootstrap fields get the deterministic
    # mapping from the core directive (audit §9 — empty for a full day).
    if not sm["core_values"]:
        sm["core_values"] = [dict(v) for v in _BOOTSTRAP_CORE_VALUES]
        updated = True
    if not sm["traits"]:
        sm["traits"] = list(_BOOTSTRAP_TRAITS)
        updated = True
    if not sm["known_roles"]:
        sm["known_roles"] = list(_BOOTSTRAP_ROLES)
        updated = True

    return (sm, updated) if with_flag else sm

def get_self_model() -> SelfModel:
    """Load, repair if needed, and persist only when changed. Always returns a dict."""
    with _SELF_MODEL_LOCK:
        raw = load_json(SELF_MODEL_FILE, default_type=dict)
        sm, updated = ensure_self_model_integrity(raw, with_flag=True)  # returns (dict, bool)
        if updated:
            save_json(SELF_MODEL_FILE, sm)
    return sm

def save_self_model(model: Any) -> None:
    """Repair then save once. Accepts anything coercible to dict."""
    with _SELF_MODEL_LOCK:
        sm, _ = ensure_self_model_integrity(model, with_flag=True)
        save_json(SELF_MODEL_FILE, sm)

def get_core_values() -> List[Dict[str, str]]:
    sm = get_self_model()
    vals = sm.get("core_values", [])
    return vals if isinstance(vals, list) else []

def set_core_values(new_values: Any) -> None:
    if not isinstance(new_values, list):
        raise ValueError("core_values must be a list.")
    fixed: List[Dict[str, str]] = []
    for v in new_values:
        if isinstance(v, dict) and "value" in v and isinstance(v["value"], str):
            fixed.append({"value": v["value"].strip(), "description": (v.get("description") or "").strip()})
        elif isinstance(v, str) and v.strip():
            fixed.append({"value": v.strip(), "description": ""})
    # Read-modify-write under one lock (modify_json) — get_self_model() then
    # save_self_model() as two separate calls left a window where a concurrent
    # writer's update could be silently overwritten (lost-update race).
    try:
        with modify_json(SELF_MODEL_FILE, default_type=dict) as raw:
            if not isinstance(raw, dict):
                raise AbortModify("self_model corrupt")
            sm, _ = ensure_self_model_integrity(raw, with_flag=True)
            if sm.get("core_values") != fixed:
                sm["core_values"] = fixed
    except AbortModify:
        pass

def add_core_value(value: str, description: str = "") -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    val = value.strip()
    try:
        with modify_json(SELF_MODEL_FILE, default_type=dict) as raw:
            if not isinstance(raw, dict):
                raise AbortModify("self_model corrupt")
            sm, _ = ensure_self_model_integrity(raw, with_flag=True)
            cv = sm.get("core_values", [])
            for v in cv:
                if (isinstance(v, dict) and v.get("value") == val) or v == val:
                    raise AbortModify("core value already present")
            cv.append({"value": val, "description": description.strip()})
            sm["core_values"] = cv
    except AbortModify:
        return False
    return True

def remove_core_value(value: str) -> bool:
    target = value.strip() if isinstance(value, str) else str(value)
    try:
        with modify_json(SELF_MODEL_FILE, default_type=dict) as raw:
            if not isinstance(raw, dict):
                raise AbortModify("self_model corrupt")
            sm, _ = ensure_self_model_integrity(raw, with_flag=True)
            cv = sm.get("core_values", [])
            new_vals = [v for v in cv if (v.get("value") if isinstance(v, dict) else v) != target]
            if len(new_vals) == len(cv):
                raise AbortModify("core value not found")
            sm["core_values"] = new_vals
    except AbortModify:
        return False
    return True
