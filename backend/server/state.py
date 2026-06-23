"""Shared runtime state + JSON read helpers for the telemetry server.

Factored out of app.py (Phase 4C) so the route handlers can be split by domain
without a circular import. `_DATA_DIR` and `_DATA_PARSE_ERRORS` are read at call
time by the helpers and by route modules (via `state._DATA_DIR`), so tests that
relocate the data root monkeypatch them HERE.
"""
from __future__ import annotations

import json as _json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from .hub import Hub

# The telemetry hub — the single in-memory snapshot/delta state every consumer
# (REST reads + the /ws stream) shares.
hub = Hub()

# The DATA root must honor ORRIN_DATA_DIR or the brain writes to the relocated dir
# while these read endpoints keep reading the stale brain/data — the UI then shows
# an empty/old mind (§13.2 split-brain). Consume the one resolver the brain uses;
# fall back to the same env logic if it can't be imported (e.g. brain/ not on the
# path). (`_REPO_ROOT` for the /source repo-jail stays program-relative in app.py.)
_REPO_ROOT = Path(__file__).resolve().parents[2]
try:
    from brain.paths import DATA_DIR as _DATA_DIR
except Exception:  # pragma: no cover - defensive
    _env_data = os.environ.get("ORRIN_DATA_DIR")
    _DATA_DIR = Path(_env_data).resolve() if _env_data else _REPO_ROOT / "brain" / "data"

# Files that failed to parse on read — surfaced by /health, cleared on a good read.
_DATA_PARSE_ERRORS: Dict[str, str] = {}


def _read_json(fname: str, default: Any) -> Any:
    try:
        text = (_DATA_DIR / fname).read_text("utf-8")
    except FileNotFoundError:
        _DATA_PARSE_ERRORS.pop(fname, None)  # missing ≠ corrupt
        return default
    except OSError:  # intentional: unreadable (permission/IO) → default
        return default
    try:
        d = _json.loads(text)
        _DATA_PARSE_ERRORS.pop(fname, None)  # parsed OK — clear any prior error
        return d if isinstance(d, type(default)) else default
    except Exception as e:
        _DATA_PARSE_ERRORS[fname] = str(e)[:160]
        return default


def _read_jsonl_tail(fname: str, n: int) -> list:
    try:
        lines = (_DATA_DIR / fname).read_text("utf-8").splitlines()
        out = []
        for ln in lines[-max(1, n):]:
            try:
                out.append(_json.loads(ln))
            except _json.JSONDecodeError:  # intentional: skip a malformed line
                continue
        return out
    except OSError:  # intentional: unreadable file → empty tail
        return []


def _float_or_none(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):  # intentional: non-numeric → None
        return None


def _belief_churn(rows: "list[Dict[str, Any]]") -> Dict[str, Dict[str, int]]:
    churn: Dict[str, Dict[str, int]] = {}
    for row in rows:
        kind = str(row.get("kind") or "unknown")
        rec = churn.setdefault(kind, {"count": 0, "strengthened": 0, "weakened": 0, "unchanged": 0})
        rec["count"] += 1
        delta = _float_or_none(row.get("confidence_delta"))
        if delta is None:
            rec["unchanged"] += 1
        elif delta > 0:
            rec["strengthened"] += 1
        elif delta < 0:
            rec["weakened"] += 1
        else:
            rec["unchanged"] += 1
    return churn
