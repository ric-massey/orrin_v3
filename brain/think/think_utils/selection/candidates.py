"""Candidate generation + dispatch constraints for selection (Phase 4D, from
select_function.py).

Decides which function names may enter the selector pool: name-level selectability
(_is_selectable_name + its deny/allow sets), dispatchability (_is_dispatchable —
drop cognition needing args the dispatcher can't supply), and the cognition-only
candidate loaders (_load_actions / _load_action_defs, behavioral names filtered
out via _load_behavioral_names). Imports its shared inputs downward (constants),
so no cycle back to the core selector, which re-imports these names.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from brain.utils.json_utils import load_json
from brain.utils.failure_counter import record_failure
from brain.paths import BEHAVIORAL_FUNCTIONS_LIST_FILE, COGNITIVE_FUNCTIONS_LIST_FILE
from brain.think.think_utils.selection.constants import _ALWAYS_EXCLUDE, FALLBACK_ACTIONS


_NON_SELECTABLE_PREFIXES: Tuple[str, ...] = (
    "explore_",
    "apply_", "update_", "compute_", "recompute_", "decay_", "ensure_",
    "build_", "init_", "load_", "save_", "persist_", "register_", "refresh_",
    "reset_", "migrate_", "coerce_", "normalize_", "sync_", "flush_", "gc_",
    "get_", "set_", "has_", "should_",
)
_SELECTABLE_PREFIX_EXCEPTIONS: frozenset[str] = frozenset({
    "update_world_model",   # genuine cognition entry point (router-wrapped)
})
_NON_SELECTABLE_EXACT: frozenset[str] = frozenset({
    # trivial-name leaks from over-broad public-function discovery
    "available", "exists", "get", "start", "stop", "status", "report",
    "flush", "generate", "simulate", "commit", "size_chars", "vocab_size",
    "lm_ready", "poll_fs_changes",
    # internal reward/calibration calc that surfaced as "choices"
    "calibrated_reward", "calibration_observation", "check_and_reward",
    "check_and_reward_contradiction_resolution", "check_and_reward_goal_closure",
    "check_and_reward_prediction_accuracy", "train_tokenizer_on_library",
    "reflect_on_prompts", "build_system_prompt", "ensure_tokenizer",
})


def _is_selectable_name(name: str) -> bool:
    """False for plumbing/junk that must never enter the selector pool (Phase 1).

    Exact denials and curated prefix-exceptions are checked before the prefix
    sweep, so a real behavior that happens to start with a denied prefix
    (e.g. update_world_model) is kept while the plumbing it resembles is dropped.
    """
    if name in _NON_SELECTABLE_EXACT:
        return False
    if name in _SELECTABLE_PREFIX_EXCEPTIONS:
        return True
    return not name.startswith(_NON_SELECTABLE_PREFIXES)


def _load_behavioral_names() -> frozenset[str]:
    """Return the set of behavioral function names from the persisted list."""
    try:
        items: list[Any] = load_json(BEHAVIORAL_FUNCTIONS_LIST_FILE, default_type=list) or []
        names = set()
        for it in items:
            if isinstance(it, dict) and "name" in it:
                names.add(str(it["name"]))
            elif isinstance(it, str):
                names.add(it)
        return frozenset(names)
    except Exception as exc:
        record_failure("select_function.behavioral_names", exc)
        return frozenset()


_SUPPLYABLE_ARGS: frozenset[str] = frozenset({
    "context", "ctx", "self_model", "affect_state", "emotions", "relationships",
    "long_memory", "working_memory", "recent", "recent_memories",
    "retrieved_memories", "speaker",
})
_dispatchable_cache: Dict[str, bool] = {}


def _is_dispatchable(name: str) -> bool:
    """True unless the registered callable needs a required arg the dispatcher
    can't supply. Cached; fails open (keeps the candidate) if anything's unclear."""
    if name in _dispatchable_cache:
        return _dispatchable_cache[name]
    ok = True
    try:
        import inspect
        from brain.registry.cognition_registry import COGNITIVE_FUNCTIONS  # lazy: avoid import cycle
        meta = COGNITIVE_FUNCTIONS.get(name)
        fn = meta.get("function") if isinstance(meta, dict) else meta
        if callable(fn):
            for p in inspect.signature(fn).parameters.values():
                if (p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
                        and p.default is p.empty
                        and p.name not in ("self", "cls")
                        and p.name not in _SUPPLYABLE_ARGS):
                    ok = False
                    break
    except Exception:
        ok = True  # unsure → keep it; never drop a candidate by accident
    _dispatchable_cache[name] = ok
    return ok


def _load_actions() -> List[str]:
    """Load cognitive function names, excluding behavioral and bookkeeping functions."""
    items: list[Any] = load_json(COGNITIVE_FUNCTIONS_LIST_FILE, default_type=list)
    if not isinstance(items, list) or not items:
        return FALLBACK_ACTIONS
    beh_names = _load_behavioral_names()
    excluded = beh_names | _ALWAYS_EXCLUDE
    names: List[str] = []
    for it in items:
        name = str(it["name"]) if isinstance(it, dict) and "name" in it else (it if isinstance(it, str) else "")
        if name and name not in excluded and _is_selectable_name(name) and _is_dispatchable(name):
            names.append(name)
    return names or FALLBACK_ACTIONS


def _load_action_defs() -> Tuple[List[str], Dict[str, str]]:
    """
    Returns (names, defs) for COGNITIVE functions only.

    Behavioral functions (outward-facing: speak, respond_to_user, etc.)
    and bookkeeping utilities (apply_cognitive_costs, apply_drive_tensions)
    are excluded so they never compete in the same bandit pool as genuine
    cognition choices.  They enter separately via Path A in ORRIN_loop.py.

    Supports:
      - ['name', ...]
      - [{'name': 'fn', 'definition': '...'}, ...]
    Falls back to using the name as the definition.
    """
    items: list[Any] = load_json(COGNITIVE_FUNCTIONS_LIST_FILE, default_type=list)
    if not isinstance(items, list) or not items:
        return (list(FALLBACK_ACTIONS), {n: n for n in FALLBACK_ACTIONS})

    beh_names = _load_behavioral_names()
    excluded  = beh_names | _ALWAYS_EXCLUDE

    names: List[str] = []
    defs: Dict[str, str] = {}
    for it in items:
        if isinstance(it, dict) and "name" in it:
            nm = str(it["name"])
            if nm in excluded or not _is_selectable_name(nm) or not _is_dispatchable(nm):
                continue
            names.append(nm)
            defs[nm] = str(it.get("definition") or nm)
        elif isinstance(it, str):
            if it in excluded or not _is_selectable_name(it) or not _is_dispatchable(it):
                continue
            names.append(it)
            defs[it] = it

    if len(names) < 2:
        for fb in FALLBACK_ACTIONS:
            if fb not in names and fb not in excluded:
                names.append(fb)
                defs[fb] = fb
    return names, defs


def _planned_action_recruitment(context: Dict[str, Any], actions: List[str]) -> Dict[str, float]:
    """Bounded deliberate boost for an explicit Executive handoff."""
    goal = context.get("committed_goal") or {}
    need_fn = goal.get("_needs_deliberate_action") if isinstance(goal, dict) else None
    if not need_fn or need_fn not in actions:
        return {}
    impasse = float(
        ((context.get("affect_state") or {}).get("core_signals") or {}).get(
            "impasse_signal", 0.0
        ) or 0.0
    )
    return {str(need_fn): min(0.6, 0.22 + 0.5 * impasse)}
