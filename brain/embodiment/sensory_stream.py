"""
embodiment/sensory_stream.py

Continuous environment monitoring — Orrin's felt sense of his world beyond
his own process. body_sense.py already handles per-process vitals (RSS, FDs,
CPU of the Orrin process itself). This layer adds:

  • System-wide CPU + memory pressure (whole machine)
  • Home-sense: host vitals and local den/workspace file changes
  • World-sense: external/unknown file changes and network-facing texture
  • Own-code change detection (did something in brain/ change since last sample?)
  • Activity log tail (what did I just do — proprioceptive awareness)
  • Derived home/world moods that the signal_router can treat as background signal

The SensoryStream runs as a daemon thread, sampling every SAMPLE_INTERVAL
seconds. Callers get a snapshot via get_field() — a plain dict, no I/O.
"""
from __future__ import annotations
from core.runtime_log import get_logger

import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from utils.failure_counter import record_failure
_log = get_logger(__name__)

_SAMPLE_INTERVAL = 8  # seconds between sensory refreshes

# Directories to watch for file-system changes
_HOME_WATCH_DIRS: List[str] = [
    "brain/data",
    "brain/cognition/self_generated",
    "brain/logs",
    "docs",
    "goals",
    "inbox",
    "memory",
    "outbox",
]
_WORLD_WATCH_DIRS: List[str] = []

# Back-compat name for older callers/tests that may import it.
_WATCH_DIRS: List[str] = _HOME_WATCH_DIRS

# Root of repo — two levels up from this file
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# -------------------------------------------------------------------
# Singleton

_stream: Optional["SensoryStream"] = None
_stream_lock = threading.Lock()


def start() -> "SensoryStream":
    global _stream
    with _stream_lock:
        if _stream is None:
            _stream = SensoryStream()
            _stream.start()
    return _stream


def get_field() -> Dict[str, Any]:
    """Return the latest sensory snapshot. Safe to call from any thread."""
    with _stream_lock:
        if _stream is None:
            return {}
    return _stream.get_field()


# -------------------------------------------------------------------

class SensoryStream:
    def __init__(self) -> None:
        self._field: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._thread = threading.Thread(
            target=self._run, name="orrin-sensory", daemon=True
        )
        # Baseline snapshots for change detection
        self._fs_baseline: Dict[str, float] = {}   # path → mtime
        self._code_baseline: Dict[str, float] = {}  # brain/*.py → mtime
        self._last_log_pos: int = 0

    def start(self) -> None:
        self._thread.start()

    def get_field(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._field)

    # ------------------------------------------------------------------
    # Background loop

    def _run(self) -> None:
        # Give the main process a moment to finish booting
        time.sleep(3)
        while True:
            try:
                field = self._sample()
                with self._lock:
                    self._field = field
            except Exception as _e:
                record_failure("sensory_stream.SensoryStream._run", _e)
            time.sleep(_SAMPLE_INTERVAL)

    def _sample(self) -> Dict[str, Any]:
        field: Dict[str, Any] = {}

        # System-wide vitals
        field["system"] = self._system_vitals()

        # File-system change detection, split by felt zone. Home is the local
        # den/workspace; world is outside/unknown. Keep fs_changes as a legacy
        # merged view while new consumers read home_sense/world_sense.
        home_changes = self._detect_fs_changes(_HOME_WATCH_DIRS, zone="home")
        world_changes = self._detect_fs_changes(_WORLD_WATCH_DIRS, zone="world")
        field["fs_changes"] = (home_changes + world_changes)[-20:]
        field["home_sense"] = {
            "system": field["system"],
            "fs_changes": home_changes,
            "own_code_modified": False,  # filled after code-change detection
            "mood": "ambient",
        }
        field["world_sense"] = {
            "fs_changes": world_changes,
            "mood": "ambient",
        }
        field["own_code_modified"] = self._detect_code_changes()
        field["home_sense"]["own_code_modified"] = field["own_code_modified"]

        # Activity log tail (proprioception — what did I just do?)
        field["log_tail"] = self._read_log_tail()
        field["home_sense"]["log_tail"] = field["log_tail"]

        # Derived moods. environment_mood remains as the legacy merged field.
        field["home_sense"]["mood"] = self._derive_home_mood(field)
        field["world_sense"]["mood"] = self._derive_world_mood(field)
        field["environment_mood"] = self._derive_mood(field)

        field["sampled_at"] = time.time()
        return field

    # ------------------------------------------------------------------
    # System vitals (whole machine, complements body_sense.py's per-process view)

    def _system_vitals(self) -> Dict[str, float]:
        vitals: Dict[str, float] = {}
        try:
            import psutil
            vitals["cpu_percent"]    = psutil.cpu_percent(interval=0.5)
            vm = psutil.virtual_memory()
            vitals["memory_percent"] = vm.percent
            vitals["memory_available_gb"] = round(vm.available / (1024**3), 2)
            try:
                disk = psutil.disk_usage(str(_REPO_ROOT))
                vitals["disk_percent"] = disk.percent
            except Exception:
                vitals["disk_percent"] = 0.0
        except Exception:
            # psutil missing or failed — use subprocess fallback
            try:
                import subprocess
                r = subprocess.run(
                    ["df", "-Pk", str(_REPO_ROOT)],
                    capture_output=True, text=True, timeout=3
                )
                lines = r.stdout.strip().splitlines()
                if len(lines) >= 2:
                    parts = lines[-1].split()
                    vitals["disk_percent"] = float(parts[4].rstrip("%"))
            except Exception as _e:
                record_failure("sensory_stream.SensoryStream._system_vitals", _e)
        return vitals

    # ------------------------------------------------------------------
    # File-system change detection

    def _detect_fs_changes(self, watch_dirs: Optional[List[str]] = None, *, zone: str = "home") -> List[Dict[str, Any]]:
        changes: List[Dict[str, Any]] = []
        for rel in (watch_dirs if watch_dirs is not None else _WATCH_DIRS):
            watch_path = _REPO_ROOT / rel
            if not watch_path.exists():
                continue
            try:
                for entry in watch_path.iterdir():
                    if not entry.is_file():
                        continue
                    try:
                        mtime = entry.stat().st_mtime
                    except Exception:
                        continue
                    key = str(entry)
                    prev = self._fs_baseline.get(key)
                    if prev is None:
                        self._fs_baseline[key] = mtime
                    elif mtime > prev + 0.5:
                        self._fs_baseline[key] = mtime
                        changes.append({
                            "path": str(entry.relative_to(_REPO_ROOT)),
                            "age_s": round(time.time() - mtime, 1),
                            "dir": rel,
                            "zone": zone,
                        })
            except Exception as _e:
                record_failure("sensory_stream.SensoryStream._detect_fs_changes", _e)
        return changes[-20:]  # cap at 20 most recent

    # ------------------------------------------------------------------
    # Own-code change detection (did brain/*.py change?)

    def _detect_code_changes(self) -> bool:
        brain_dir = _REPO_ROOT / "brain"
        changed = False
        try:
            for py in brain_dir.rglob("*.py"):
                if "__pycache__" in str(py):
                    continue
                try:
                    mtime = py.stat().st_mtime
                except Exception:
                    continue
                key = str(py)
                prev = self._code_baseline.get(key)
                if prev is None:
                    self._code_baseline[key] = mtime
                elif mtime > prev + 0.5:
                    self._code_baseline[key] = mtime
                    changed = True
        except Exception as _e:
            record_failure("sensory_stream.SensoryStream._detect_code_changes", _e)
        return changed

    # ------------------------------------------------------------------
    # Activity log tail (last 5 lines of activity_log.txt)

    def _read_log_tail(self) -> List[str]:
        try:
            from brain.paths import ACTIVITY_LOG
            log_path = Path(ACTIVITY_LOG)
            if not log_path.exists():
                return []
            size = log_path.stat().st_size
            # Read last ~1 KB to get recent lines without loading the whole file
            with log_path.open("r", encoding="utf-8", errors="replace") as f:
                f.seek(max(0, size - 1024))
                tail = f.read()
            lines = [l.strip() for l in tail.splitlines() if l.strip()]
            return lines[-5:]
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Derive moods from the sampled state

    def _derive_home_mood(self, field: Dict[str, Any]) -> str:
        sys = field.get("system", {})
        cpu = sys.get("cpu_percent", 0.0)
        mem = sys.get("memory_percent", 0.0)
        home = field.get("home_sense") or {}
        changes = len(home.get("fs_changes", []))
        own_changed = field.get("own_code_modified", False)

        if own_changed:
            return "transformed"   # own code changed — significant
        if changes > 5:
            return "active"        # the den is busy
        if cpu > 80 or mem > 85:
            return "pressured"     # machine is strained
        if cpu < 20 and mem < 50 and changes == 0:
            return "still"         # quiet, open
        return "ambient"           # baseline

    def _derive_world_mood(self, field: Dict[str, Any]) -> str:
        world = field.get("world_sense") or {}
        changes = len(world.get("fs_changes", []))
        if changes > 5:
            return "active"
        if changes:
            return "stirring"
        return "distant"

    def _derive_mood(self, field: Dict[str, Any]) -> str:
        home_mood = ((field.get("home_sense") or {}).get("mood")) or self._derive_home_mood(field)
        world_mood = ((field.get("world_sense") or {}).get("mood")) or self._derive_world_mood(field)
        if home_mood in ("transformed", "pressured", "active"):
            return home_mood
        if world_mood in ("active", "stirring"):
            return "active"
        return home_mood
