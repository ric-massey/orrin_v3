"""
agency/self_code.py — the one owner of Orrin's *self-written* code tree.

Orrin authors new cognitive functions and tools at runtime (agency/code_writer.py).
On a dev checkout those landed inside the program folder (brain/cognition/
custom_cognition, brain/agency/skills). A packaged build ships that folder
**read-only** inside an archive, so a write there fails and nothing new can be
registered (DESKTOP_APP_PLAN §10.1). The fix: treat self-written code as *state*,
not program — it lives in the writable per-user data dir alongside his memory:

    <data dir>/self_code/
      custom_cognition/   ← code_writer's new cognitive functions
      skills/             ← code_writer's new tools
      manifest.json       ← RELATIVE paths into the two dirs above

This module is the single place that:
  • resolves those dirs (from brain.paths, which honors ORRIN_DATA_DIR),
  • creates them, marks them as packages, and wires them onto the import path so a
    freshly-written module imports live exactly as before (§13.4),
  • reads/writes the manifest with paths **relative** to the self-code root, and
  • migrates the legacy in-repo manifest (absolute paths) on first launch.

Both the startup loader (core/manager.py) and the runtime writer
(agency/code_writer.py) go through here, so there is exactly one notion of "where
Orrin's own code lives" and one namespace it imports under.
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import shutil
import sys
import threading
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Optional

from paths import DATA_DIR, ROOT_DIR, SELF_CODE_DIR, SELF_COGNITION_DIR, SELF_SKILLS_DIR

# Self-written modules import under a DEDICATED top-level namespace rather than the
# bundled `cognition.custom_cognition.*` / `agency.skills.*` packages. Relocating the
# files out of those packages means the old package path no longer resolves them
# (§13.4); a separate namespace also guarantees a self-written module can never
# shadow a shipped one. Generated bodies use only absolute imports (resolved via the
# brain/ sys.path), so the namespace string is purely an identity key.
_NS = "orrin_self_code"
_PKG = {"custom_cognition": SELF_COGNITION_DIR, "skills": SELF_SKILLS_DIR}

# Manifest lives WITH the code it describes, in the writable tree.
MANIFEST_FILE = SELF_CODE_DIR / "manifest.json"
# The pre-relocation manifest (absolute paths, inside the program folder). Migrated
# once, on first launch after this change.
_LEGACY_MANIFEST = ROOT_DIR / "agency" / "manifest.json"

_LOCK = threading.RLock()
_TREE_READY = False


# ── tree creation + import wiring ────────────────────────────────────────────
def ensure_tree() -> None:
    """Create the self-code subtree, mark each subdir as a package, and make it
    importable. Idempotent and cheap to call repeatedly."""
    global _TREE_READY
    if _TREE_READY:
        return
    with _LOCK:
        if _TREE_READY:
            return
        SELF_CODE_DIR.mkdir(parents=True, exist_ok=True)
        for sub in _PKG.values():
            sub.mkdir(parents=True, exist_ok=True)
            init = sub / "__init__.py"
            if not init.exists():
                try:
                    init.write_text("# package marker for Orrin's self-written code\n", encoding="utf-8")
                except Exception:
                    pass
        # Put the self-code root on sys.path (plan §10.1) so the namespace packages
        # below — and any future cross-imports between self-written modules — resolve.
        root = str(SELF_CODE_DIR)
        if root not in sys.path:
            sys.path.append(root)
        # Register namespace packages so `orrin_self_code.<pkg>.<mod>` has a real
        # parent with a __path__ (keeps relative imports working if Orrin ever writes
        # one). Harmless if already present.
        _register_namespace_packages()
        # So bundled-skill lazy-loading (toolkit `import_module("agency.skills.<x>")`)
        # also finds self-written tools after a restart: extend the shipped package's
        # search path to include the writable skills dir. Best-effort.
        _extend_bundled_skills_path()
        _migrate_legacy_manifest()
        _TREE_READY = True


def _register_namespace_packages() -> None:
    for name, path in (
        (_NS, SELF_CODE_DIR),
        (f"{_NS}.custom_cognition", SELF_COGNITION_DIR),
        (f"{_NS}.skills", SELF_SKILLS_DIR),
    ):
        if name in sys.modules:
            continue
        mod = ModuleType(name)
        mod.__path__ = [str(path)]  # type: ignore[attr-defined]
        mod.__package__ = name
        sys.modules[name] = mod


def _extend_bundled_skills_path() -> None:
    try:
        import agency.skills as _bundled_skills  # noqa: F401
        p = str(SELF_SKILLS_DIR)
        if p not in _bundled_skills.__path__:  # type: ignore[attr-defined]
            _bundled_skills.__path__.append(p)  # type: ignore[attr-defined]
    except Exception:
        pass  # bundled package not importable in this context — non-fatal


# ── dynamic import of a self-written module ──────────────────────────────────
def load_module_from(path: Path, package: str) -> Optional[ModuleType]:
    """Import a single self-written .py under the dedicated namespace and return the
    module (or None on failure). `package` is "custom_cognition" or "skills"."""
    ensure_tree()
    module_name = f"{_NS}.{package}.{path.stem}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, str(path))
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module  # register early so relative imports resolve
        spec.loader.exec_module(module)
        return module
    except Exception:
        sys.modules.pop(module_name, None)
        return None


# ── manifest (relative paths) ────────────────────────────────────────────────
def _rel(path: Path) -> str:
    """A manifest-stored path: relative to the self-code root (POSIX), so it stays
    valid across machines and after export/restore."""
    p = Path(path).resolve()
    try:
        return p.relative_to(SELF_CODE_DIR.resolve()).as_posix()
    except ValueError:
        return p.name  # outside the tree (shouldn't happen) — store the bare name


def abs_path(entry: Dict[str, Any]) -> Path:
    """Resolve a manifest entry's stored (relative) path back to an absolute Path.
    Tolerates legacy absolute entries that predate the migration."""
    raw = str(entry.get("path", ""))
    p = Path(raw)
    return p if p.is_absolute() else (SELF_CODE_DIR / raw)


def _subdir_for_kind(kind: str) -> Path:
    return SELF_SKILLS_DIR if kind == "tool" else SELF_COGNITION_DIR


def _migrate_legacy_manifest() -> None:
    """One-time: fold the old in-repo manifest (absolute paths, files inside the
    program folder) into the writable tree. Relocate each still-existing file into
    the matching self-code subdir, rewrite the entry path to relative, and drop
    entries whose file is gone. No-op once the new manifest exists or on a fresh
    install (no legacy file).

    Scope guard: the legacy manifest + files lived in the in-repo program folder, so
    they belong to the *canonical in-repo* mind only. A relocated/packaged/test data
    dir (ORRIN_DATA_DIR pointed elsewhere) is either a newborn or an export-restore
    that already carries its own self_code — it must NOT consume the legacy manifest.
    Without this guard, whichever data dir imports first would migrate (and retire)
    the shared program-folder manifest, an order-dependent side effect on the repo."""
    if MANIFEST_FILE.exists() or not _LEGACY_MANIFEST.exists():
        return
    if DATA_DIR.resolve() != (ROOT_DIR / "data").resolve():
        return  # not the in-repo mind the legacy code belongs to — leave it alone
    try:
        legacy = json.loads(_LEGACY_MANIFEST.read_text(encoding="utf-8"))
    except Exception:
        return
    if not isinstance(legacy, list):
        return

    migrated: List[Dict[str, Any]] = []
    for entry in legacy:
        if not isinstance(entry, dict):
            continue
        src = Path(str(entry.get("path", "")))
        dst_dir = _subdir_for_kind(str(entry.get("kind", "")))
        dst = dst_dir / (src.name or f"{entry.get('name', 'unnamed')}.py")
        try:
            if src.is_absolute() and src.exists():
                dst_dir.mkdir(parents=True, exist_ok=True)
                if not dst.exists():
                    shutil.copy2(str(src), str(dst))
            elif not dst.exists():
                # File already gone (e.g. the stale test probe) — drop the entry.
                continue
        except Exception:
            continue
        entry = {**entry, "path": _rel(dst)}
        migrated.append(entry)

    try:
        MANIFEST_FILE.write_text(json.dumps(migrated, indent=2), encoding="utf-8")
        # Retire the legacy manifest so migration runs exactly once. Best-effort:
        # on a read-only program folder this fails harmlessly (no legacy file ships).
        try:
            _LEGACY_MANIFEST.rename(_LEGACY_MANIFEST.with_suffix(".json.migrated"))
        except Exception:
            pass
    except Exception:
        pass


def load_manifest() -> List[Dict[str, Any]]:
    ensure_tree()
    try:
        data = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_manifest(entries: List[Dict[str, Any]]) -> None:
    ensure_tree()
    MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_FILE.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def append_manifest(name: str, kind: str, description: str, path: Path) -> None:
    """Record a newly-written function/tool with its path stored RELATIVE to the
    self-code root."""
    try:
        from utils.timeutils import now_iso_z
        written_at = now_iso_z()
    except Exception:
        written_at = ""
    with _LOCK:
        entries = load_manifest()
        entries.append({
            "name": name,
            "kind": kind,
            "description": description,
            "path": _rel(path),
            "written_at": written_at,
        })
        save_manifest(entries)


# Wire the tree at import so both the startup loader and the writer find it ready.
ensure_tree()
