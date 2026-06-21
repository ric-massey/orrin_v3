# cognition/perception/environment.py
#
# Persistent world state.
#
# Orrin lives somewhere. He should know it.
#
# This module builds a mental map that accumulates over time:
#   locations    — files, directories, and paths he's encountered, with history
#   routines     — patterns of when the user is present, what times feel like what
#   conditions   — live machine state (load, memory, disk, processes)
#   events       — external things happening: new files, load spikes, user arriving
#
# Reads from: filesystem metadata, process info, user_input timestamps
# Writes to:  world_model.json (persistent), context["_environment"] (per-cycle)
# Called:     every N cycles from finalize.py

from __future__ import annotations
from brain.core.runtime_log import get_logger

import platform
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from brain.utils.log import log_private, log_activity
from brain.utils.json_utils import load_json, save_json
from brain.cog_memory.working_memory import update_working_memory
from brain.paths import WORLD_MODEL, USER_INPUT, DATA_DIR
from brain.utils.timeutils import now_iso_z
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

_UPDATE_EVERY_N_CYCLES = 5      # don't run every single cycle
_WM_EVENT_COOLDOWN_S   = 120.0  # rate-limit notable event alerts to WM
_MAX_LOCATIONS         = 120    # cap persistent location registry
_MAX_EVENTS_LOG        = 50     # cap event history

_cycle_counter: int = 0
_last_wm_event_ts: float = 0.0


# ── Data model ─────────────────────────────────────────────────────────────────

def _load_world() -> Dict:
    data = load_json(WORLD_MODEL, default_type=dict) or {}
    data.setdefault("locations", {})
    data.setdefault("routines", {})
    data.setdefault("conditions_history", [])
    data.setdefault("events", [])
    return data


def _save_world(world: Dict) -> None:
    # Keep histories bounded
    world["conditions_history"] = world.get("conditions_history", [])[-48:]
    world["events"]             = world.get("events", [])[-_MAX_EVENTS_LOG:]
    save_json(WORLD_MODEL, world)



# ── Machine conditions ─────────────────────────────────────────────────────────

def _sample_conditions() -> Dict:
    """Sample current machine state without invasive tools."""
    conditions: Dict[str, Any] = {
        "ts":        now_iso_z(),
        "hour":      datetime.now().hour,
        "weekday":   datetime.now().strftime("%A"),
    }

    # Load average (psutil emulates it on Windows; native on macOS/Linux)
    try:
        import psutil
        la = psutil.getloadavg()
        conditions["load_1m"]  = round(la[0], 2)
        conditions["load_5m"]  = round(la[1], 2)
        conditions["load_15m"] = round(la[2], 2)
    except Exception as _e:
        record_failure("environment._sample_conditions", _e)

    # Disk usage for home directory (shutil.disk_usage — cross-platform stdlib)
    try:
        usage = shutil.disk_usage(str(Path.home()))
        if usage.total > 0:
            conditions["disk_used_pct"] = str(round(usage.used / usage.total * 100))
    except Exception as _e:
        record_failure("environment._sample_conditions.2", _e)

    # Process count (coarse — just a number)
    try:
        import psutil
        conditions["process_count"] = len(psutil.pids())
    except Exception as _e:
        record_failure("environment._sample_conditions.3", _e)

    # Time of day label
    h = conditions.get("hour", 12)
    if h < 5:    conditions["time_of_day"] = "night"
    elif h < 12: conditions["time_of_day"] = "morning"
    elif h < 17: conditions["time_of_day"] = "afternoon"
    elif h < 21: conditions["time_of_day"] = "evening"
    else:        conditions["time_of_day"] = "night"

    return conditions


# ── User activity detection ────────────────────────────────────────────────────

def _user_active_recently(window_s: float = 300.0) -> bool:
    """True if user_input.txt was modified in the last window_s seconds."""
    try:
        mtime = USER_INPUT.stat().st_mtime
        return (time.time() - mtime) < window_s
    except Exception:
        return False


def _user_input_mtime() -> Optional[float]:
    try:
        return USER_INPUT.stat().st_mtime
    except Exception:
        return None


# ── Routine learning ───────────────────────────────────────────────────────────

def _update_routines(world: Dict, conditions: Dict) -> List[str]:
    """
    Update routine observations from current conditions.
    Returns list of newly detected routine shifts.
    """
    routines = world.setdefault("routines", {})
    events = []

    tod = conditions.get("time_of_day", "")
    weekday = conditions.get("weekday", "")
    user_here = _user_active_recently()

    # Track presence by time-of-day slot
    slot = f"{weekday}_{tod}"
    r = routines.setdefault(slot, {
        "slot": slot,
        "observations": 0,
        "user_present_count": 0,
        "first_seen": now_iso_z(),
        "last_seen": now_iso_z(),
    })
    r["observations"] += 1
    r["last_seen"] = now_iso_z()
    if user_here:
        r["user_present_count"] += 1

    presence_rate = r["user_present_count"] / max(1, r["observations"])
    r["presence_rate"] = round(presence_rate, 2)

    # Detect high-confidence routines
    if r["observations"] >= 4 and presence_rate >= 0.7 and not r.get("routine_confirmed"):
        r["routine_confirmed"] = True
        events.append(f"Routine confirmed: someone is usually present on {weekday} {tod} ({presence_rate:.0%})")

    return events


# ── Location registry ──────────────────────────────────────────────────────────

def register_location(path: str, label: str = "", context_note: str = "") -> None:
    """
    Called when Orrin meaningfully encounters a path (read, write, reference).
    Updates the persistent location registry.
    """
    try:
        world = _load_world()
        locations = world["locations"]
        key = str(path)

        if key not in locations:
            p = Path(path)
            locations[key] = {
                "path":        key,
                "type":        "directory" if p.is_dir() else "file",
                "label":       label or p.name,
                "first_seen":  now_iso_z(),
                "last_seen":   now_iso_z(),
                "visit_count": 1,
                "notes":       [context_note] if context_note else [],
                "importance":  1,
            }
        else:
            loc = locations[key]
            loc["last_seen"]   = now_iso_z()
            loc["visit_count"] = int(loc.get("visit_count") or 0) + 1
            if context_note and context_note not in loc.get("notes", []):
                loc.setdefault("notes", []).append(context_note)
                loc["notes"] = loc["notes"][-5:]  # keep last 5 notes
            # Importance grows with visit count
            vc = int(loc["visit_count"])
            loc["importance"] = min(10, 1 + vc // 3)

        # Cap registry size by evicting lowest-importance, oldest entries
        if len(locations) > _MAX_LOCATIONS:
            sorted_keys = sorted(
                locations.keys(),
                key=lambda k: (locations[k].get("importance", 1), locations[k].get("last_seen", "")),
            )
            for old_key in sorted_keys[:len(locations) - _MAX_LOCATIONS]:
                del locations[old_key]

        _save_world(world)
    except Exception as e:
        log_private(f"[environment] register_location error: {e}")


# ── External event detection ───────────────────────────────────────────────────

def _detect_external_events(world: Dict, conditions: Dict) -> List[str]:
    """
    Detect notable environmental events by comparing current state to history.
    Returns human-readable event strings.
    """
    events = []
    history = world.get("conditions_history", [])

    if not history:
        return events

    prev = history[-1]

    # Load spike
    prev_load = float(prev.get("load_1m") or 0)
    curr_load = float(conditions.get("load_1m") or 0)
    if curr_load > 3.0 and prev_load <= 2.0:
        events.append(f"Machine load spiked to {curr_load:.1f} — something intensive started")
    elif prev_load > 3.0 and curr_load <= 1.5:
        events.append(f"Machine load dropped from {prev_load:.1f} to {curr_load:.1f} — intensive work finished")

    # Process count jump
    prev_procs = int(prev.get("process_count") or 0)
    curr_procs = int(conditions.get("process_count") or 0)
    if curr_procs > 0 and prev_procs > 0:
        delta = curr_procs - prev_procs
        if delta >= 15:
            events.append(f"{delta} new processes appeared — user likely launched something")
        elif delta <= -15:
            events.append(f"{-delta} processes ended — user closed something")

    # Time-of-day transition
    prev_tod = prev.get("time_of_day", "")
    curr_tod = conditions.get("time_of_day", "")
    if prev_tod and curr_tod and prev_tod != curr_tod:
        events.append(f"Shifted from {prev_tod} to {curr_tod}")

    # User arrival / departure
    prev_user = prev.get("user_present")
    curr_user = _user_active_recently()
    if curr_user and not prev_user:
        events.append("Someone has returned — user input detected")
    elif not curr_user and prev_user:
        events.append("The conversation has gone quiet — no input for a while")

    conditions["user_present"] = curr_user
    return events


# ── Main entry point ───────────────────────────────────────────────────────────

def update_environment_state(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Called from finalize.py every N cycles.
    Returns the current environment summary dict.
    Sets context["_environment"].
    """
    global _cycle_counter, _last_wm_event_ts
    _cycle_counter += 1
    if _cycle_counter % _UPDATE_EVERY_N_CYCLES != 0:
        return context.get("_environment") or {}

    try:
        return _update(context)
    except Exception as e:
        log_private(f"[environment] update error: {e}")
        return {}


def _update(context: Dict[str, Any]) -> Dict[str, Any]:
    global _last_wm_event_ts

    world      = _load_world()
    conditions = _sample_conditions()

    # Detect events before appending to history
    external_events = _detect_external_events(world, conditions)
    routine_events  = _update_routines(world, conditions)

    all_events = external_events + routine_events

    # Log notable events to event history and working memory
    now_ts = time.time()
    for evt in all_events:
        world["events"].append({"ts": now_iso_z(), "event": evt})
        log_private(f"[environment] {evt}")

    # Only surface user presence changes to WM — everything else stays unconscious
    user_events = [e for e in all_events if "returned" in e or "gone quiet" in e]
    if user_events and (now_ts - _last_wm_event_ts) >= _WM_EVENT_COOLDOWN_S:
        update_working_memory({
            "content": f"[environment] {user_events[0]}",
            "event_type": "environment_event",
            "importance": 2,
            "priority": 2,
        })
        _last_wm_event_ts = now_ts

    # Append current conditions snapshot to history
    world["conditions_history"].append(conditions)
    _save_world(world)

    # Auto-register key locations Orrin knows about
    try:
        brain_root = Path(DATA_DIR).parent
        register_location(str(brain_root), label="Orrin's brain", context_note="core runtime")
        register_location(str(DATA_DIR), label="data directory", context_note="state files")
    except Exception as _e:
        record_failure("environment._update", _e)

    # Sync machine state into knowledge graph so it's queryable alongside entities
    try:
        from brain.cognition.knowledge_graph import add_entity, add_relation
        machine_name = platform.node() or f"{platform.system()} machine"
        os_desc = f"{platform.system()} {platform.release()}".strip() or "unknown OS"
        add_entity(machine_name, entity_type="tool",
                   properties={"load_1m": str(conditions.get("load_1m", "")),
                                "process_count": str(conditions.get("process_count", "")),
                                "disk_used_pct": str(conditions.get("disk_used_pct", "")),
                                "time_of_day": conditions.get("time_of_day", ""),
                                "os": os_desc},
                   confidence=0.98, source="environment")
        add_relation("Orrin", "uses", machine_name, confidence=0.98, source="environment")
    except Exception as _e:
        record_failure("environment._update.2", _e)

    # Build summary for context
    recent_events = [e["event"] for e in world.get("events", [])[-5:]]
    top_locations = sorted(
        world.get("locations", {}).values(),
        key=lambda l: int(l.get("importance") or 0),
        reverse=True,
    )[:8]

    # Extract known routines with confirmed presence patterns
    known_routines = [
        r for r in world.get("routines", {}).values()
        if r.get("routine_confirmed") or float(r.get("presence_rate") or 0) >= 0.6
    ]

    summary = {
        "time_of_day":      conditions.get("time_of_day", "unknown"),
        "weekday":          conditions.get("weekday", ""),
        "load_1m":          conditions.get("load_1m"),
        "process_count":    conditions.get("process_count"),
        "disk_used_pct":    conditions.get("disk_used_pct"),
        "user_present":     conditions.get("user_present", False),
        "recent_events":    recent_events,
        "known_routines":   len(known_routines),
        "known_locations":  len(world.get("locations", {})),
        "top_locations":    [{"path": l["path"], "label": l["label"], "visits": l.get("visit_count")} for l in top_locations],
    }
    context["_environment"] = summary
    return summary


# ── Cognition function ─────────────────────────────────────────────────────────

def survey_environment(context: Dict[str, Any] = None) -> str:
    """
    Cognition function: Orrin actively surveys his environment and updates his
    mental map. Called when he wants to understand where he is and what's changed.
    """
    context = context or {}
    env = update_environment_state(context)

    # Force an update regardless of the N-cycle gate
    global _cycle_counter
    _cycle_counter = 0   # reset so next call to update_environment_state runs

    lines = [
        f"Time: {env.get('weekday')} {env.get('time_of_day')}",
        f"Machine load: {env.get('load_1m', '?')} | Processes: {env.get('process_count', '?')}",
        f"Disk: {env.get('disk_used_pct', '?')}% used",
        f"User present: {'yes' if env.get('user_present') else 'no'}",
        f"Known locations: {env.get('known_locations', 0)}",
        f"Confirmed routines: {env.get('known_routines', 0)}",
    ]
    if env.get("recent_events"):
        lines.append("Recent: " + "; ".join(env["recent_events"][-3:]))

    summary = "\n".join(lines)
    update_working_memory({
        "content": f"[environment survey] {summary}",
        "event_type": "environment_survey",
        "importance": 2,
        "priority": 2,
    })
    log_activity(f"[environment] Surveyed: {summary[:200]}")
    return summary
