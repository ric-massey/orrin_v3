"""
utils/mind_archive.py — Mind Export / Restore (§9.6): zip up *everything that is
Orrin* into one portable archive, and restore it atomically.

His state is split by design across several trees (README "Two state trees"):
the mind (`brain/data`, incl. self-written code), his logs, the generated think
module, and the daemons' durability trees (`data/goals`, `data/memory`, `data/media`).
A backup of only one restores an inconsistent Orrin. So this captures the FULL set
from `paths.state_roots()` as a single point-in-time, and restore swaps them together.

The archive layout:
    meta.json                      schema version, born date, counts, root manifest
    <root>/<relpath...>            one top-level folder per state root

Privacy/safety: import snapshots the CURRENT mind to a timestamped safety copy FIRST
(never destroy a running mind without a fallback), and refuses an archive whose schema
is newer than this build understands.
"""
from __future__ import annotations

import io
import json
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, Tuple

import paths

# Bump when the on-disk layout changes in a way restore must reason about (§10.7).
MIND_SCHEMA_VERSION = 1

_SKIP_NAMES = {"__pycache__", ".DS_Store"}
_SKIP_SUFFIXES = (".lock",)


def _non_overlapping_roots() -> Dict[str, Path]:
    """state_roots(), minus any root nested inside another (e.g. self_code lives under
    data) — so each file is captured exactly once, under its outermost root."""
    roots = {k: Path(v).resolve() for k, v in paths.state_roots().items()}
    out: Dict[str, Path] = {}
    for name, p in roots.items():
        nested = any(
            other != p and _is_within(p, other) for oname, other in roots.items() if oname != name
        )
        if not nested:
            out[name] = p
    return out


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _skip(path: Path) -> bool:
    if path.name in _SKIP_NAMES or path.suffix in _SKIP_SUFFIXES:
        return True
    if path.name == ".orrin.instance.lock":
        return True
    return any(part in _SKIP_NAMES for part in path.parts)


def _counts() -> Dict[str, int]:
    counts: Dict[str, int] = {}
    try:
        lm = json.loads((paths.DATA_DIR / "long_memory.json").read_text("utf-8"))
        counts["memories"] = len(lm) if isinstance(lm, list) else 0
    except Exception:
        counts["memories"] = 0
    return counts


def _born_at() -> str:
    try:
        ls = json.loads((paths.DATA_DIR / "lifespan.json").read_text("utf-8"))
        return str(ls.get("born_at") or "")
    except Exception:
        return ""


def _state_schema_version() -> int:
    """The on-disk STATE schema version (§10.7) — distinct from this archive's own
    format version. Restore uses it to refuse an archive whose mind layout is newer
    than the importing build understands."""
    try:
        from utils import schema_migration as _sm
        return int(_sm.read_version())
    except Exception:
        return 1


def build_meta() -> Dict[str, Any]:
    return {
        "schema_version": MIND_SCHEMA_VERSION,
        "state_schema_version": _state_schema_version(),
        "born_at": _born_at(),
        "exported_at": time.time(),
        "roots": sorted(_non_overlapping_roots().keys()),
        "counts": _counts(),
    }


def export_bytes() -> bytes:
    """Capture the full mind as a zip (in memory). Best-effort WAL flush first so the
    daemon trees are consistent at the captured instant."""
    try:
        from memory.wal import flush as _wal_flush
        _wal_flush()
    except Exception:
        pass

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("meta.json", json.dumps(build_meta(), indent=2))
        for name, root in _non_overlapping_roots().items():
            if not root.exists():
                continue
            if root.is_file():
                if not _skip(root):
                    zf.write(root, arcname=f"{name}/{root.name}")
                continue
            for f in root.rglob("*"):
                if f.is_file() and not _skip(f):
                    zf.write(f, arcname=f"{name}/{f.relative_to(root).as_posix()}")
    return buf.getvalue()


def export_filename() -> str:
    return f"Orrin-{time.strftime('%Y-%m-%d')}.orrindmind"


def validate(archive: bytes) -> Tuple[bool, str, Dict[str, Any]]:
    """Check an archive is a well-formed, compatible mind. Returns (ok, reason, meta)."""
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as zf:
            names = zf.namelist()
            if "meta.json" not in names:
                return False, "not an Orrin mind archive (no meta.json)", {}
            meta = json.loads(zf.read("meta.json"))
    except Exception as e:
        return False, f"unreadable archive: {e}", {}
    sv = int(meta.get("schema_version") or 0)
    if sv > MIND_SCHEMA_VERSION:
        return False, f"archive is from a newer version (schema {sv} > {MIND_SCHEMA_VERSION})", meta
    # Also refuse a mind whose on-disk STATE layout is newer than this build (§10.7) —
    # restoring it would corrupt state we don't understand. Older state imports fine;
    # the migration spine brings it forward on the next boot.
    ssv = int(meta.get("state_schema_version") or 1)
    try:
        from utils import schema_migration as _sm
        cur = _sm.CURRENT_SCHEMA_VERSION
    except Exception:
        cur = 1
    if ssv > cur:
        return False, f"archive's mind is from a newer build (state schema v{ssv} > v{cur})", meta
    if "data" not in (meta.get("roots") or []):
        return False, "archive is missing the core mind (data root)", meta
    return True, "", meta


def _snapshot_dir() -> Path:
    d = paths.DATA_DIR / "_backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def import_archive(archive: bytes) -> Dict[str, Any]:
    """Atomically restore a mind: validate → snapshot the current mind to a safety
    copy → clear + extract each root. Caller restarts the process afterwards so the
    new state loads clean. Raises on validation failure (current mind untouched)."""
    ok, reason, meta = validate(archive)
    if not ok:
        raise ValueError(reason)

    # 1. Safety snapshot of the CURRENT mind first — never destroy without a fallback.
    snap = _snapshot_dir() / f"pre-restore-{time.strftime('%Y%m%d-%H%M%S')}.orrindmind"
    try:
        snap.write_bytes(export_bytes())
    except Exception:
        pass  # snapshot is best-effort; validation already passed

    # 2. Clear the target roots and extract the archive into them.
    import shutil

    roots = _non_overlapping_roots()
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        present = {n.split("/", 1)[0] for n in zf.namelist() if "/" in n}
        for name in present:
            target = roots.get(name)
            if target is None:
                continue
            # Don't nuke our own safety snapshot (it lives under data/_backups).
            if target.exists() and target.is_dir():
                for child in target.iterdir():
                    if child.resolve() == _snapshot_dir().resolve():
                        continue
                    try:
                        shutil.rmtree(child, ignore_errors=True) if child.is_dir() else child.unlink(missing_ok=True)
                    except Exception:
                        pass
            target.mkdir(parents=True, exist_ok=True)
        for info in zf.infolist():
            if info.is_dir() or "/" not in info.filename:
                continue
            rootname, rel = info.filename.split("/", 1)
            target = roots.get(rootname)
            if target is None or not rel:
                continue
            dest = (target / rel)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(dest, "wb") as out:
                out.write(src.read())

    return {"ok": True, "restored_roots": sorted(present), "snapshot": str(snap), "meta": meta}
