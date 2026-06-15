# manager.py
from typing import Callable, Dict

from utils.log import log_model_issue, log_private
from agency.self_code import SELF_COGNITION_DIR, ensure_tree, load_module_from

def load_custom_cognition() -> Dict[str, Callable]:
    """
    Dynamically load callable functions Orrin has written, from
    <data dir>/self_code/custom_cognition/*.py (the writable tree — §10.1; never the
    read-only program folder).

    - Honors __all__ if present.
    - Otherwise exports all top-level callables that don't start with "_".
    - Returns {function_name: callable}. Later files override earlier names (with a warning).
    """
    ensure_tree()
    directory = SELF_COGNITION_DIR
    functions: Dict[str, Callable] = {}

    if not directory.exists():
        log_model_issue(f"[load_custom_cognition] Directory not found: {directory}")
        return functions

    for path in sorted(directory.iterdir()):
        if not path.is_file() or path.suffix != ".py":
            continue
        if path.name.startswith("_") or path.name == "__init__.py":
            continue

        try:
            module = load_module_from(path, "custom_cognition")
            if module is None:
                log_model_issue(f"[load_custom_cognition] Cannot load: {path.name}")
                continue

            exported = []
            names = getattr(module, "__all__", None)
            candidates = [n for n in names if isinstance(n, str)] if isinstance(names, (list, tuple)) \
                        else [n for n in dir(module) if not n.startswith("_")]

            for name in candidates:
                obj = getattr(module, name, None)
                # If you want *only* plain functions, check types instead of callable()
                if callable(obj):
                    if name in functions and functions[name] is not obj:
                        log_model_issue(f"[load_custom_cognition] '{name}' from {path.name} overwrote previous binding.")
                    functions[name] = obj
                    exported.append(name)

            if exported:
                log_private(f"[load_custom_cognition] {path.name}: exported {', '.join(exported)}")
            else:
                log_model_issue(f"[load_custom_cognition] No callable exports found in {path.name}")

        except Exception as e:
            log_model_issue(f"[load_custom_cognition] Failed to load {path.name}: {e}")

    return functions
