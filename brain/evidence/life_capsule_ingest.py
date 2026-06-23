# brain/evidence/life_capsule_ingest.py
# The raw -> cleaned ingest layer of the Life Capsule (Phase 4.5C, from
# life_capsule.py): capsule constants + the action-class taxonomy
# (classify_action), the small IO/hash/time helpers, and the per-stream parsers
# that turn the raw data dir into cleaned table rows (_parse_* / _derive_signals).
# This is the foundational leaf — it depends on nothing else in the capsule
# package, so the metrics, reader, and builder modules import from here.
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


# Bump when the capsule layout changes in a way tools/LLMs must reason about.
CAPSULE_SCHEMA_VERSION = 1

VALID_REASONS = {
    "normal_shutdown",
    "crash_recovery",
    "mortality_end_of_life",
    "checkpoint",
    "manual",
}

# Hard ceiling on the LLM bundle so it always fits a context window (Part VI).
_LLM_BUDGET_BYTES = 200 * 1024

# Near-duplicate / content thresholds shared with the effect ledger (P8 in the
# production-reward plan). Kept local so the capsule can stand alone.
_MIN_ARTIFACT_CHARS = 120


# ──────────────────────────────────────────────────────────────────────────────
# Action-class taxonomy (the audit lens — SIGNAL_TO_ACTION_AUDIT R1)
#
# Every choice is tagged with exactly one class so behavior is summarizable and the
# signal→action follow-through can be measured. Seeded from the `_OUTWARD_HIGH/MED/LOW`
# tiers in `select_function.py` and the activity-log tag stream.
# ──────────────────────────────────────────────────────────────────────────────
_ACTION_CLASS: Dict[str, str] = {
    # communicative — person-facing output
    "leave_note": "communicative",
    "write_desktop_note": "communicative",
    "save_note": "communicative",
    "notify_user": "communicative",
    "announce_to_dashboard": "communicative",
    "express_to_user": "communicative",
    "express_state": "communicative",
    "respond_to_user": "communicative",
    "speak": "communicative",
    # productive — durable artifacts that change the world
    "write_tool": "productive",
    "write_cognitive_function": "productive",
    "produce_code": "productive",
    "compose_section": "productive",
    "code_edit": "productive",
    # orienting — looking outward / gathering input
    "look_outward": "orienting",
    "look_around": "orienting",
    "seek_novelty": "orienting",
    "wikipedia_search": "orienting",
    "read_rss": "orienting",
    "research_topic": "orienting",
    "fetch_and_read": "orienting",
    "read_a_book": "orienting",
    "search_own_files": "orienting",
    "grep_files": "orienting",
    "search_files": "orienting",
    "survey_environment": "orienting",
    "read_clipboard": "orienting",
    "check_user_presence": "orienting",
    "run_embodied_observation": "orienting",
    # regulatory — affect/homeostasis maintenance of the self
    "attempt_regulation": "regulatory",
    "self_soothing": "regulatory",
    "reflect_on_affect": "regulatory",
    "investigate_unexplained_emotions": "regulatory",
    "reflection": "regulatory",
    # metacognitive — thinking about goals / self / plans
    "generate_intrinsic_goals": "metacognitive",
    "assess_goal_progress": "metacognitive",
    "plan_next_step": "metacognitive",
    "plan_self_evolution": "metacognitive",
    "detect_memory_contradictions": "metacognitive",
    "propose_value_revision": "metacognitive",
    "metacog_analyze": "metacognitive",
    "adapt_subgoals": "metacognitive",
    "narrative_update": "metacognitive",
    "attend_goal": "metacognitive",
    "active_commitment": "metacognitive",
    "abandon_goal": "metacognitive",
    "accrue_leave_pressure": "metacognitive",
    # maintenance — housekeeping / dreaming / snapshots
    "dream_cycle": "maintenance",
    "housekeeping": "maintenance",
    "snapshot": "maintenance",
    "pursue_committed_goal": "metacognitive",
    "pursue_goal": "metacognitive",
}


def classify_action(choice: Optional[str], *, is_action: Optional[bool] = None) -> str:
    """Map a chosen function name to one of the audit classes. Unknown names fall
    back to a coarse guess from `is_action` (the R1 lens must never crash on a new fn)."""
    if not choice:
        return "unknown"
    cls = _ACTION_CLASS.get(choice)
    if cls:
        return cls
    name = choice.lower()
    if any(k in name for k in ("note", "express", "speak", "respond", "notify", "announce")):
        return "communicative"
    if any(k in name for k in ("write", "produce", "compose", "build", "create", "code")):
        return "productive"
    if any(k in name for k in ("look", "search", "read", "fetch", "research", "survey", "explore")):
        return "orienting"
    if any(k in name for k in ("regulat", "sooth", "affect", "emotion")):
        return "regulatory"
    if any(k in name for k in ("goal", "plan", "reflect", "metacog", "narrative")):
        return "metacognitive"
    if any(k in name for k in ("dream", "housekeep", "snapshot", "maintenance")):
        return "maintenance"
    return "orienting" if is_action else "metacognitive"


# Signals we audit for follow-through (R1). Each maps to the action class we'd expect
# to rise in the cycles after the signal, if the signal→action chain is working.
_SIGNAL_EXPECTED_CLASS: Dict[str, Tuple[str, ...]] = {
    "goal_avoidance": ("productive", "communicative", "metacognitive"),
    "rut": ("orienting",),
    "oscillation": ("orienting",),
    "emotional_stagnation": ("orienting", "regulatory"),
    "reflection_imbalance": ("productive", "orienting", "communicative"),
    "stagnation": ("orienting", "productive"),
}
_FOLLOWTHROUGH_WINDOW = 25  # cycles


# ──────────────────────────────────────────────────────────────────────────────
# Low-level helpers
# ──────────────────────────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):  # intentional: missing/bad file → default
        return default


def _iter_jsonl(path: Path, *, limit: Optional[int] = None) -> Iterable[dict]:
    if not path.exists():
        return
    n = 0
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:  # intentional: skip a malformed line
                    continue
                n += 1
                if limit is not None and n >= limit:
                    return
    except OSError:  # intentional: unreadable stream → stop iterating
        return


def _sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", "replace")).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError:  # intentional: unreadable file → empty hash
        return ""
    return h.hexdigest()


def _iso_to_epoch(s: Any) -> Optional[float]:
    if not s:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    try:
        txt = str(s).replace("Z", "+00:00")
        return datetime.fromisoformat(txt).timestamp()
    except (ValueError, TypeError):  # intentional: unparseable timestamp → None
        return None


def _last_run_segment(rows: List[dict], key: str) -> List[dict]:
    """Return the tail segment of `rows` after the last point where `key` resets
    (decreases) — isolating the most recent run from a multi-run accumulating stream.
    Rows missing the key are kept with the current segment."""
    if not rows:
        return rows
    start = 0
    prev = None
    for i, r in enumerate(rows):
        v = r.get(key)
        if v is None:
            continue
        if prev is not None and isinstance(v, (int, float)) and v < prev:
            start = i
        prev = v
    return rows[start:]


def _git_sha(repo_root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=5,
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):  # intentional: git absent/timeout → no sha
        return ""


def _redact_home(text: str) -> str:
    """Scrub absolute user home paths from text (privacy — Part VI)."""
    try:
        home = str(Path.home())
        text = text.replace(home, "~")
    except RuntimeError:  # intentional: home undeterminable — regex fallback still runs
        pass
    return re.sub(r"/Users/[^/\s\"']+", "~", text)


# ──────────────────────────────────────────────────────────────────────────────
# Stream parsers → normalized rows
# Each is defensive: a malformed stream yields [] rather than raising.
# ──────────────────────────────────────────────────────────────────────────────
def _parse_decisions(data_dir: Path) -> Tuple[List[dict], List[dict], List[dict]]:
    """events.jsonl DECISION rows → (cycles, decisions, rewards) tables."""
    raw: List[dict] = []
    for ev in _iter_jsonl(data_dir / "events.jsonl"):
        if ev.get("type") != "DECISION":
            continue
        p = ev.get("payload") or {}
        dec = p.get("decision") or {}
        raw.append(
            {
                "cycle": p.get("tick"),
                "ts": ev.get("ts"),
                "choice": dec.get("picked"),
                "is_action": bool(dec.get("is_action")),
                "candidate_count": dec.get("candidate_count"),
                "top_candidates": dec.get("top_candidates") or [],
                "reason": dec.get("reason"),
                "goal_id": (p.get("goal") or {}).get("id"),
                "goal_title": (p.get("goal") or {}).get("title"),
                "reward_signal": (p.get("reward") or {}).get("reward_signal"),
                "novelty": (p.get("reward") or {}).get("novelty"),
                "acceptance_passed": (p.get("reward") or {}).get("acceptance_passed"),
                "tools_used": p.get("tools_used") or [],
            }
        )
    raw = _last_run_segment(raw, "cycle")

    cycles, decisions, rewards = [], [], []
    for r in raw:
        cls = classify_action(r["choice"], is_action=r["is_action"])
        cycles.append(
            {
                "cycle": r["cycle"],
                "ts": r["ts"],
                "choice": r["choice"],
                "action_class": cls,
                "is_action": int(bool(r["is_action"])),
                "goal_id": r["goal_id"],
            }
        )
        decisions.append(
            {
                "cycle": r["cycle"],
                "choice": r["choice"],
                "action_class": cls,
                "candidate_count": r["candidate_count"],
                "top_candidates": json.dumps(r["top_candidates"]),
                "tools_used": json.dumps(r["tools_used"]),
                "goal_title": r["goal_title"],
            }
        )
        rewards.append(
            {
                "cycle": r["cycle"],
                "reward_signal": r["reward_signal"],
                "novelty": r["novelty"],
                "acceptance_passed": int(bool(r["acceptance_passed"])),
            }
        )
    return cycles, decisions, rewards


def _parse_affect(data_dir: Path) -> List[dict]:
    """telemetry_archive.jsonl → the full affect time series (this run only)."""
    rows = [
        {
            "cycle": r.get("cycle"),
            "ts": r.get("t"),
            "valence": r.get("valence"),
            "arousal": r.get("arousal"),
            "homeostasis": r.get("homeostasis"),
            "energy": r.get("energy"),
            "fatigue": r.get("fatigue"),
            "motivation": r.get("motivation"),
            "confidence": r.get("confidence"),
            "curiosity": r.get("curiosity"),
            "distress": r.get("distress"),
            "stability": r.get("stability"),
            "allostatic_load": r.get("allostatic_load"),
            "impasse_raw": r.get("impasse_raw"),
            "learning": r.get("learning"),
        }
        for r in _iter_jsonl(data_dir / "telemetry_archive.jsonl")
    ]
    return _last_run_segment(rows, "cycle")


def _parse_behavior_changes(data_dir: Path) -> List[dict]:
    data = _read_json(data_dir / "behavior_changes.json", []) or []
    out = []
    for r in data if isinstance(data, list) else []:
        out.append(
            {
                "when": r.get("when"),
                "pattern": r.get("pattern"),
                "situation": r.get("situation"),
                "old_action": r.get("old_action"),
                "new_action": r.get("new_action"),
                "reason": r.get("reason"),
                "outcome": r.get("outcome"),  # filled by Part X.3 if present; else null
            }
        )
    return out


def _parse_goals(data_dir: Path, state_dir: Path) -> List[dict]:
    """v2 daemon goal rows (data/goals/state.jsonl) — last status per goal id."""
    by_id: Dict[str, dict] = {}
    for rec in _iter_jsonl(state_dir / "goals" / "state.jsonl"):
        g = rec.get("goal")
        if not isinstance(g, dict) or not g.get("id"):
            continue
        by_id[g["id"]] = {
            "goal_id": g.get("id"),
            "title": g.get("title"),
            "kind": g.get("kind"),
            "status": g.get("status"),
            "driven_by": (g.get("spec") or {}).get("driven_by"),
            "created_at": g.get("created_at"),
            "updated_at": g.get("updated_at"),
            "deadline": g.get("deadline"),
            "tags": json.dumps(g.get("tags") or []),
            "progress": (g.get("progress") or {}).get("percent"),
        }
    return list(by_id.values())


def _parse_artifacts(data_dir: Path) -> List[dict]:
    """The effect ledger is the authoritative 'what did he make' record (it subsumes
    the old activity-tag parse — P0 of the production-reward plan)."""
    rows = []
    for r in _iter_jsonl(data_dir / "effect_ledger.jsonl"):
        rows.append(
            {
                "ts": r.get("ts"),
                "cycle": r.get("cycle"),
                "kind": r.get("kind"),
                "content_hash": r.get("content_hash"),
                "novelty": r.get("novelty"),
                "significance": r.get("significance"),
                "goal_id": r.get("goal_id"),
                "char_len": r.get("char_len"),
                "dedupe": int(bool(r.get("dedupe"))),
            }
        )
    return rows


def _parse_memory_events(state_dir: Path) -> List[dict]:
    rows = []
    for r in _iter_jsonl(state_dir / "memory" / "wal" / "events.jsonl"):
        rows.append(
            {
                "id": r.get("id"),
                "ts": r.get("ts"),
                "kind": r.get("kind"),
                "content": (r.get("content") or "")[:500],
            }
        )
    return rows


def _parse_peers(data_dir: Path) -> List[dict]:
    rel = _read_json(data_dir / "relationships.json", {}) or {}
    rows = []
    for name, info in (rel.items() if isinstance(rel, dict) else []):
        if not isinstance(info, dict):
            continue
        hist = info.get("interaction_history") or []
        rows.append(
            {
                "name": name,
                "type": info.get("type"),
                "trust": info.get("trust"),
                "influence_score": info.get("influence_score"),
                "depth": info.get("depth"),
                "interactions": len(hist) if isinstance(hist, list) else 0,
                "last_interaction_time": info.get("last_interaction_time"),
            }
        )
    return rows


def _derive_signals(behavior_changes: List[dict]) -> List[dict]:
    """Derived: each detected corrective pattern with its onset cycle is unknown
    (behavior_changes are time-stamped, not cycle-stamped), so we key on `when` and
    carry the pattern. The follow-through audit (metrics) joins these to cycles by ts."""
    rows = []
    for bc in behavior_changes:
        if not bc.get("pattern"):
            continue
        rows.append(
            {
                "kind": bc.get("pattern"),
                "when": bc.get("when"),
                "situation": (bc.get("situation") or "")[:300],
            }
        )
    return rows


