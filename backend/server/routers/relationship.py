"""Relationship views (Companion & Presence plan, Track R) — read-only GET
projections mounted on the read `api` router like the telemetry routes.

R1: /theory_of_mind — what Orrin currently believes about each person, from the
tom_state his mentalizing model keeps in relationships.json, with provenance
(the timestamped exchange behind each read) and staleness. Legibility is what
turns surveillance into intimacy.

R2: /actions — the real-world action ledger: one time-ordered audit feed of
everything he DID (effect ledger + egress ledger + presence notifications).
Timeline covers "what happened"; this is "what he did."

R3: /body_bridge — the body↔machine join: each felt state paired with the host
metric that drove it (persisted vitals vs. the learned band), never the felt
word alone. "He feels cramped because your disk is 94% full."

All render honest-empty shapes on a fresh instance.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..state import _read_json, _read_jsonl_tail

router = APIRouter()


@router.get("/theory_of_mind")
async def theory_of_mind() -> JSONResponse:
    """R1: per-person belief projection. Internal peer observers are excluded."""
    out: List[Dict[str, Any]] = []
    for name, rec in (_read_json("relationships.json", {}) or {}).items():
        if not isinstance(rec, dict) or rec.get("type") == "peer":
            continue
        tom = rec.get("tom_state")
        if not isinstance(tom, dict) or not tom:
            continue
        history = [h for h in (tom.get("state_history") or []) if isinstance(h, dict)]
        current = history[-1] if history else {}
        belief = tom.get("belief_model") or {}
        hits, total = int(tom.get("prediction_hits", 0) or 0), int(tom.get("prediction_total", 0) or 0)
        out.append({
            "name": name,
            # the current read + the exchange that produced it (provenance)
            "current": {
                "affective_state": current.get("state", ""),
                "cognitive_state": current.get("cognitive_state", ""),
                "intention": current.get("intention", ""),
                "as_of": current.get("ts", ""),
            },
            "belief_model": {
                "feels_understood": belief.get("feels_understood"),
                "in_alignment": belief.get("in_alignment"),
                "satisfied_last": belief.get("satisfied_last"),
                "belief_discordance": bool(belief.get("belief_discordance", False)),
                "consecutive_misalignments": int(belief.get("consecutive_misalignments", 0) or 0),
                "preference_alignment": belief.get("preference_alignment"),
                "last_artifact_correction": belief.get("last_artifact_correction"),
            },
            "prediction": {
                **(tom.get("last_prediction") or {}),
                "accuracy": float(tom.get("prediction_accuracy", 0.0) or 0.0),
                "hits": hits,
                "total": total,
            },
            "synchrony": float(tom.get("synchrony_score", 0.5) or 0.5),
            "misalignment_streak": int(tom.get("misalignment_streak", 0) or 0),
            # provenance trail: every recent read, each stamped with its exchange
            "history": history,
        })
    return JSONResponse({"people": out})


@router.get("/actions")
async def actions(n: int = 200) -> JSONResponse:
    """R2: the joined outward-act feed, newest first. Egress rows carry counts
    and timestamps only — never a prompt, query, or body."""
    n = max(1, min(1000, n))
    rows: List[Dict[str, Any]] = []

    for e in _read_jsonl_tail("effect_ledger.jsonl", n):
        if not isinstance(e, dict):
            continue
        ts_iso = str(e.get("ts", ""))
        meta = e.get("metadata") if isinstance(e.get("metadata"), dict) else {}
        detail = str(meta.get("path") or meta.get("name") or "")
        rows.append({
            "ts": _iso_to_epoch(ts_iso), "iso": ts_iso, "source": "effect",
            "kind": str(e.get("kind", "")), "detail": detail,
            "goal_id": e.get("goal_id"),
            "significance": float(e.get("significance", 0.0) or 0.0),
            "dedupe": bool(e.get("dedupe", False)),
        })

    for e in _read_jsonl_tail("egress_log.jsonl", n):
        if not isinstance(e, dict):
            continue
        ts = float(e.get("ts", 0.0) or 0.0)
        rows.append({
            "ts": ts, "iso": _epoch_to_iso(ts), "source": "egress",
            "kind": str(e.get("service", "")),
            "detail": f"{int(e.get('count', 1) or 1)} outbound call(s)",
        })

    sent = _read_json("presence_notifications.json", [])
    if isinstance(sent, list):
        for t in sent:
            if isinstance(t, (int, float)):
                rows.append({
                    "ts": float(t), "iso": _epoch_to_iso(float(t)),
                    "source": "notification", "kind": "os_notification",
                    "detail": "spontaneous utterance shown as an OS notification",
                })

    rows.sort(key=lambda r: r.get("ts") or 0.0, reverse=True)
    return JSONResponse({"actions": rows[:n], "total": len(rows)})


@router.get("/reunion")
async def reunion() -> JSONResponse:
    """R7: the composed reunion line written at boot after a credited sleep gap
    (brain/behavior/reunion.py). Read-only; the client shows it once per viewer
    (localStorage ts), so a GET never consumes or mutates anything."""
    r = _read_json("reunion.json", {})
    if not isinstance(r, dict) or not r.get("text"):
        return JSONResponse({})
    return JSONResponse({"text": str(r.get("text")), "gap_s": r.get("gap_s"), "ts": r.get("ts")})


# The vital that drives each felt state (resource_self_monitor.compute_body_states):
# heavy/spacious/swelling read RSS against its band; sluggish reads step latency;
# strained reads FD or CPU (resolved below to whichever deviates more).
_FELT_DRIVER = {
    "heavy": ("rss_mb", "above its learned band"),
    "spacious": ("rss_mb", "below its learned band"),
    "swelling": ("rss_mb", "climbing without retreating"),
    "sluggish": ("latency_ms", "above its learned band"),
}

_VITAL_UNIT = {"rss_mb": "MB", "latency_ms": "ms", "cpu_util": "", "fd_pct": ""}


def _fmt_vital(name: str, value: float) -> str:
    if name in ("cpu_util", "fd_pct"):
        return f"{value * 100:.0f}%"
    return f"{value:.0f} {_VITAL_UNIT.get(name, '')}".strip()


def _band_view(bands: Dict[str, Any], name: str) -> Dict[str, Any] | None:
    b = bands.get(name)
    if not isinstance(b, dict) or not b.get("_converged"):
        return None
    return {"lo": b.get("lo"), "hi": b.get("hi"), "center": b.get("center")}


@router.get("/body_bridge")
async def body_bridge() -> JSONResponse:
    """R3: felt state ↔ host metric, joined. Read-only over the persisted body
    sense + learned bands — a GET never observes into the bands or starts the
    sensory stream (the init-on-read bug class from the 07-09 UI audit)."""
    sense = _read_json("resource_self_monitor.json", {}) or {}
    phase = str(sense.get("phase", "wake"))
    bands_file = "resource_bands_idle.json" if phase == "sleep" else "resource_bands.json"
    bands = (_read_json(bands_file, {}) or {}).get("bands") or {}
    vitals = sense.get("vitals") or {}

    felt: List[Dict[str, Any]] = []
    for state in (sense.get("body_states") or []):
        state = str(state)
        row: Dict[str, Any] = {"state": state}
        if state == "strained":
            # FD or CPU drove it — attribute to whichever fraction reads higher
            # (the FD-exhaustion backstop dominates a quiet CPU and vice versa)
            name = max(("fd_pct", "cpu_util"),
                       key=lambda n: float(vitals.get(n, 0) or 0))
            row["metric"] = {"name": name, "value": vitals.get(name),
                             "display": _fmt_vital(name, float(vitals.get(name, 0) or 0))}
            row["band"] = _band_view(bands, name)
            row["because"] = f"{name.replace('_', ' ')} is {row['metric']['display']}, above its learned band"
        elif state in _FELT_DRIVER:
            name, how = _FELT_DRIVER[state]
            row["metric"] = {"name": name, "value": vitals.get(name),
                             "display": _fmt_vital(name, float(vitals.get(name, 0) or 0))}
            row["band"] = _band_view(bands, name)
            row["because"] = f"{name.replace('_', ' ')} is {row['metric']['display']}, {how}"
        else:  # "clear" — every vital inside its band
            row["because"] = "every vital is inside its learned band"
        felt.append(row)

    # Machine-level shared situation (den-crowded / machine-pinned), from the
    # in-process sensory stream. get_field() returns {} when the stream isn't
    # running — never start it from a GET.
    host: Dict[str, Any] = {}
    try:
        from brain.runtime_coupling import input_stream
        host = (input_stream.get_field() or {}).get("system") or {}
    except Exception:  # intentional: brain sensory layer absent → no host block
        host = {}
    situations: List[Dict[str, Any]] = []
    disk = float(host.get("disk_percent", 0) or 0)
    cpu = float(host.get("cpu_percent", 0) or 0)
    mem = float(host.get("memory_percent", 0) or 0)
    if disk >= 90.0:
        situations.append({"name": "den_crowded",
                           "because": f"the disk is {disk:.0f}% full",
                           "metric": {"name": "disk_percent", "value": disk}})
    if cpu >= 85.0 or mem >= 88.0:
        which = (f"CPU is at {cpu:.0f}%" if cpu >= 85.0 else f"memory is at {mem:.0f}%")
        situations.append({"name": "machine_pinned", "because": which,
                           "metric": {"name": "cpu_percent" if cpu >= 85.0 else "memory_percent",
                                       "value": cpu if cpu >= 85.0 else mem}})

    budget: Dict[str, Any] | None = None
    try:
        from brain.cognition.host_budget import budget_status
        budget = budget_status()
    except Exception:  # intentional: budget module absent → omit the block
        budget = None

    return JSONResponse({
        "felt": felt,
        "vitals": vitals,
        "phase": phase,
        "somatic_infancy": bool(sense.get("somatic_infancy", False)),
        "body_converged": sense.get("body_converged"),
        "host": host,
        "situations": situations,
        "budget": budget,
    })


def _iso_to_epoch(ts: str) -> float:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _epoch_to_iso(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except (OSError, OverflowError, ValueError):
        return ""
