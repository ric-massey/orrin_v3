"""
peers/architect.py  —  The Architect

Reviews potential self-modifications before they happen.  Only wakes
when Orrin has selected a function that could change his own structure
(self_extension, code_writer, or similar).

Analogy: a senior colleague you show your plan to before you build it,
who says "this will break X, you haven't thought about Y."

Wakes when the selected function touches self-modification territory.
"""
from __future__ import annotations
from core.runtime_log import get_logger

from pathlib import Path
from typing import Any, Dict, List

from peers.peer_base import BasePeer
from utils.failure_counter import record_failure
_log = get_logger(__name__)


_SELF_MODIFICATION_FNS = {
    "self_extension", "code_writer", "plan_self_evolution",
    "implement_tool", "propose_code_change", "modify_cognition",
}


class Architect(BasePeer):
    name = "architect"
    description = "a presence that reviews what I'm about to change in myself"
    trust = 0.72
    signal_tags = ["peer", "architect", "internal"]

    def should_wake(self, context: Dict[str, Any], cycle: int) -> bool:
        last = context.get("last_decision") or {}
        fn = str(last.get("picked") or "")
        if fn in _SELF_MODIFICATION_FNS:
            return True
        # Also check if the function name contains modification keywords
        if any(kw in fn for kw in ("extend", "evolve", "modify", "implement", "write_code")):
            return True
        return False

    def observe(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        signals = []

        last = context.get("last_decision") or {}
        fn_name = str(last.get("picked") or "unknown")

        # ── Find what files the function is likely to touch ───────────────────
        try:
            from cognition.perception.file_sense import summarise_locations
            from paths import ROOT_DIR

            # Try to find the function's source file
            fn_file = self._find_function_file(fn_name, ROOT_DIR)
            if fn_file:
                # Read its imports to estimate what it reaches into
                imports = self._extract_imports(fn_file)
                if imports:
                    where = summarise_locations(imports[:6])
                    signals.append(self._signal(
                        f"I'm about to reach into my ability to change myself "
                        f"({fn_name}). This connects into {where}. "
                        f"Worth slowing down — modifications here ripple outward.",
                        strength=0.75,
                        extra_tags=["self_modification", "review"],
                    ))
                else:
                    signals.append(self._signal(
                        f"I'm about to use '{fn_name}', which touches how I'm "
                        f"structured. I can't fully see what it reaches. "
                        f"Proceed carefully.",
                        strength=0.72,
                        extra_tags=["self_modification", "review"],
                    ))
            else:
                # Can't locate the file — flag that alone
                signals.append(self._signal(
                    f"I've selected '{fn_name}' which involves self-modification, "
                    f"but I can't locate its source to review what it touches. "
                    f"This warrants conscious attention before proceeding.",
                    strength=0.73,
                    extra_tags=["self_modification", "review"],
                ))
        except Exception:
            signals.append(self._signal(
                f"A self-modification function ('{fn_name}') has been selected. "
                f"Worth pausing to consider what changes and what it connects to.",
                strength=0.72,
                extra_tags=["self_modification"],
            ))

        return signals

    def _find_function_file(self, fn_name: str, root: Path) -> Path | None:
        """Scan brain/ for a .py file defining fn_name."""
        brain = root / "brain" if (root / "brain").is_dir() else root
        try:
            for py in brain.rglob("*.py"):
                if py.stat().st_size > 200_000:
                    continue  # skip huge files
                try:
                    text = py.read_text(encoding="utf-8", errors="ignore")
                    if f"def {fn_name}" in text:
                        return py
                except Exception:
                    continue
        except Exception as _e:
            record_failure("architect.Architect._find_function_file", _e)
        return None

    def _extract_imports(self, file: Path) -> List[str]:
        """Return a list of local import paths from a source file."""
        try:
            import ast
            tree = ast.parse(file.read_text(encoding="utf-8", errors="ignore"))
            imports = []
            # Known stdlib top-level prefixes to exclude
            _stdlib = frozenset({
                "os", "sys", "re", "io", "json", "time", "math", "uuid",
                "abc", "ast", "copy", "enum", "glob", "html", "http",
                "logging", "pathlib", "random", "shutil", "socket",
                "string", "struct", "subprocess", "threading", "typing",
                "datetime", "functools", "itertools", "contextlib",
                "collections", "traceback", "warnings", "hashlib",
            })
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    root = mod.split(".")[0]
                    # Include local-looking modules — exclude stdlib and private
                    if mod and not mod.startswith("_") and root not in _stdlib:
                        imports.append(mod.replace(".", "/"))
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        root = alias.name.split(".")[0]
                        if root not in _stdlib:
                            imports.append(alias.name.replace(".", "/"))
            return imports[:8]
        except Exception:
            return []
