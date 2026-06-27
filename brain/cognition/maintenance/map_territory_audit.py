# brain/cognition/maintenance/map_territory_audit.py
#
# A map that notices its own drift (master plan 5.3).
#
# Problem 9's lesson: nothing inside Orrin ever compared his records of
# himself against what is actually there — dead-twin function names sat in
# selector lists, path constants pointed at files nothing writes, comments
# promised behavior the constants beside them didn't implement. This module
# checks those specific drift classes mechanically:
#
#   1. every selectable cognition function resolves to a dispatchable
#      callable in the runtime registry (catches dead-twin drift);
#   2. every paths.py constant either exists on disk or is created by some
#      writer in the source (catches "reflection routine reads a structure
#      nothing fills");
#   3. same-line doc-comment numbers cross-checked against the constants
#      they annotate, where both are machine-readable.
#
# Findings go to working memory and a RUN_ISSUES-style JSONL log — never
# silent repair. The record of the drift is itself part of the faithful
# record.
from __future__ import annotations
from brain.core.runtime_log import get_logger

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_activity, log_private
from brain.utils.failure_counter import record_failure
from brain.paths import DATA_DIR, LOGS_DIR, ROOT_DIR

_log = get_logger(__name__)

_STATE_FILE = DATA_DIR / "map_territory_audit_state.json"
_FINDINGS_LOG = LOGS_DIR / "map_territory_audit.jsonl"
_AUDIT_INTERVAL_S = 30 * 24 * 3600.0    # monthly cadence; self_review may invoke sooner

# Registry below this size means the loop hasn't registered functions yet
# (e.g. test process) — auditing it would produce mass false drift.
_REGISTRY_MIN_FOR_AUDIT = 20

_WRITE_MARKERS = (
    "save_json", "write_text", "write_bytes", "json.dump", "dump_summary",
    "append_to_json", "append_jsonl", "ensure_files", "modify_json",
    "_append_line", "mkdir", "touch", "replace(", "'w'", '"w"', "'a'", '"a"',
    "open(", "to_csv", "shutil.copy",
)


def _source_files() -> List[Path]:
    return [
        p for p in ROOT_DIR.rglob("*.py")
        if "__pycache__" not in p.parts and "site-packages" not in p.parts
    ]


def _audit_registered_functions() -> List[str]:
    """Drift class 1 (the F6 instance): a name the selector can offer that no
    registry entry dispatches is a dead twin — selectable on the map, absent
    in the territory."""
    findings: List[str] = []
    try:
        from brain.registry.cognition_registry import COGNITIVE_FUNCTIONS
    except Exception as e:
        record_failure("map_audit.registry_import", e)
        return findings

    # Registered entries must hold real callables.
    for name, meta in list(COGNITIVE_FUNCTIONS.items()):
        fn = meta.get("function") if isinstance(meta, dict) else meta
        if not callable(fn):
            findings.append(
                f"registry entry '{name}' does not resolve to a callable "
                f"(got {type(fn).__name__})"
            )

    if len(COGNITIVE_FUNCTIONS) < _REGISTRY_MIN_FOR_AUDIT:
        log_private("[map_audit] registry not populated — selectable-name check skipped")
        return findings

    # Selector candidates must be dispatchable: in the registry or behavioral.
    try:
        from brain.paths import COGNITIVE_FUNCTIONS_LIST_FILE, BEHAVIORAL_FUNCTIONS_LIST_FILE
        listed = load_json(COGNITIVE_FUNCTIONS_LIST_FILE, default_type=list) or []
        behavioral = load_json(BEHAVIORAL_FUNCTIONS_LIST_FILE, default_type=list) or []
        beh_names = {
            str(b.get("name")) if isinstance(b, dict) else str(b) for b in behavioral
        }
        for item in listed:
            name = str(item.get("name")) if isinstance(item, dict) else str(item)
            if not name:
                continue
            if name not in COGNITIVE_FUNCTIONS and name not in beh_names:
                findings.append(
                    f"selectable function '{name}' is listed but registered "
                    f"nowhere — a dead twin the selector silently filters"
                )
    except Exception as e:
        record_failure("map_audit.selectable_names", e)
    return findings


def _audit_path_constants() -> List[str]:
    """Drift class 2: a paths.py constant that neither exists on disk nor is
    ever written by any source file is a structure nothing fills."""
    findings: List[str] = []
    try:
        import brain.paths as paths_mod
    except Exception as e:
        record_failure("map_audit.paths_import", e)
        return findings

    constants = {
        name: val for name, val in vars(paths_mod).items()
        if name.isupper() and isinstance(val, Path)
    }
    missing = {name: val for name, val in constants.items() if not val.exists()}
    if not missing:
        return findings

    # One pass over the source: which missing constants appear on a line that
    # also writes? (save_json(CONST..., CONST.write_text..., open(CONST,"w")…)
    # Writers commonly rebind the constant first — `from paths import X as Y`,
    # `FILE = X`, `def f(file=X)` — so each file's local aliases are resolved
    # to their root constant before the write check (the 2026-06-11 sweep
    # flagged 7 healthy constants whose writes all went through aliases).
    written: set = set()
    referenced: set = set()
    name_re = re.compile(r"\b(" + "|".join(re.escape(n) for n in missing) + r")\b")
    for src in _source_files():
        if src.name == "paths.py":
            continue
        try:
            lines = src.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:  # intentional: unreadable source → skip
            continue
        if not name_re.search("\n".join(lines)):
            continue
        # Resolve local aliases of missing constants to a fixpoint.
        local: Dict[str, str] = {n: n for n in missing}
        changed = True
        while changed:
            changed = False
            pat = re.compile(r"\b(" + "|".join(re.escape(n) for n in local) + r")\b")
            for line in lines:
                m = pat.search(line)
                if not m:
                    continue
                root = local[m.group(1)]
                # import alias / `with ... as ...`-style rebind: "X as Y"
                ma = re.search(r"\b" + re.escape(m.group(1)) + r"\s+as\s+(\w+)", line)
                if ma and ma.group(1) not in local:
                    local[ma.group(1)] = root
                    changed = True
                # assignment (incl. annotated and parameter defaults): "Y = …X…"
                mb = re.match(
                    r"\s*(\w+)\s*(?::[^=]+)?=\s*[^=].*\b" + re.escape(m.group(1)) + r"\b",
                    line,
                )
                if mb and mb.group(1) not in local:
                    local[mb.group(1)] = root
                    changed = True
        pat = re.compile(r"\b(" + "|".join(re.escape(n) for n in local) + r")\b")
        for line in lines:
            m = pat.search(line)
            if not m:
                continue
            root = local[m.group(1)]
            if m.group(1) in missing:
                referenced.add(root)
            if any(w in line for w in _WRITE_MARKERS):
                written.add(root)

    # Constants naming the same path stand or fall together (e.g. the
    # FEEDBACK_LOG / FEEDBACK_LOG_JSON alias pair): a writer for one is a
    # writer for all.
    by_path: Dict[str, set] = {}
    for name, val in missing.items():
        by_path.setdefault(str(val), set()).add(name)
    for group in by_path.values():
        if group & written:
            written |= group

    for name in sorted(missing):
        if name in written:
            continue   # created on demand by some writer — healthy
        if name in referenced:
            findings.append(
                f"paths.{name} ({missing[name].name}) is read somewhere but "
                f"missing on disk with no writer in the source — something "
                f"reads a structure nothing fills"
            )
    return findings


# Constant-name suffix → the comment units it can be compared against.
_UNIT_SUFFIXES = {
    "_S": ("s", "sec", "secs", "second", "seconds"),
    "_SEC": ("s", "sec", "secs", "second", "seconds"),
    "_SECONDS": ("s", "sec", "secs", "second", "seconds"),
    "_MIN": ("min", "mins", "minute", "minutes"),
    "_MINUTES": ("min", "mins", "minute", "minutes"),
    "_H": ("h", "hr", "hrs", "hour", "hours"),
    "_HOURS": ("h", "hr", "hrs", "hour", "hours"),
    "_CYCLES": ("cycle", "cycles"),
}

_CONST_LINE_RE = re.compile(
    r"^\s*(_?[A-Z][A-Z0-9_]+)\s*=\s*(\d+(?:\.\d+)?)\s*#(.*)$"
)
_COMMENT_NUM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*([a-zA-Z]+)\b")


def _audit_comment_constants() -> List[str]:
    """Drift class 3 (the F8 instance): a same-line comment stating a number
    in the same units as the constant's own suffix, disagreeing with it.
    Deliberately narrow — only flags when units provably match."""
    findings: List[str] = []
    for src in _source_files():
        try:
            text = src.read_text(encoding="utf-8", errors="ignore")
        except OSError:  # intentional: unreadable source → skip
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            m = _CONST_LINE_RE.match(line)
            if not m:
                continue
            name, value_s, comment = m.groups()
            units: Optional[tuple] = None
            for suffix, unit_words in _UNIT_SUFFIXES.items():
                if name.endswith(suffix):
                    units = unit_words
                    break
            if units is None:
                continue
            value = float(value_s)
            for num_s, word in _COMMENT_NUM_RE.findall(comment):
                if word.lower() in units and float(num_s) != value:
                    findings.append(
                        f"{src.relative_to(ROOT_DIR)}:{lineno} — {name}={value_s} "
                        f"but its comment says {num_s} {word}: the comment "
                        f"promises behavior the constant doesn't implement"
                    )
                    break
    return findings


def audit_map_territory(context: Optional[Dict[str, Any]] = None) -> str:
    """
    Run the full map-vs-territory audit. Findings are written to working
    memory (event_type="map_drift") and appended to the audit JSONL — the
    drift record is itself part of the faithful record. Returns a summary.
    """
    started = time.time()
    findings: List[str] = []
    for check in (_audit_registered_functions, _audit_path_constants,
                  _audit_comment_constants):
        try:
            findings.extend(check())
        except Exception as e:
            record_failure(f"map_audit.{check.__name__}", e)

    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        _FINDINGS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(_FINDINGS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": now_iso,
                "findings": findings,
                "duration_s": round(time.time() - started, 2),
            }, ensure_ascii=False) + "\n")
    except Exception as e:
        record_failure("map_audit.log", e)

    if findings:
        try:
            from brain.cog_memory.working_memory import update_working_memory
            for finding in findings[:6]:   # surface the worst; the log holds all
                update_working_memory({
                    "content": f"[map drift] {finding}",
                    "event_type": "map_drift",
                    "importance": 4,
                    "priority": 3,
                    "emotion": "risk_estimate",
                })
        except Exception as e:
            record_failure("map_audit.wm", e)

    state = load_json(_STATE_FILE, default_type=dict) or {}
    state["last_run_ts"] = time.time()
    state["last_run_iso"] = now_iso
    state["last_findings_count"] = len(findings)
    try:
        save_json(_STATE_FILE, state)
    except Exception as e:
        record_failure("map_audit.state", e)

    msg = (f"Map-territory audit: {len(findings)} drift finding(s)."
           if findings else "Map-territory audit: map and territory agree.")
    log_activity(f"[map_audit] {msg}")
    return msg


def audit_if_due(context: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Monthly-cadence wrapper for self_review: runs the audit only when
    _AUDIT_INTERVAL_S has passed since the last run."""
    state = load_json(_STATE_FILE, default_type=dict) or {}
    last = float(state.get("last_run_ts") or 0.0)
    if time.time() - last < _AUDIT_INTERVAL_S:
        return None
    return audit_map_territory(context)
