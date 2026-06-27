# utils/alive_brain.py
# Event-driven, rule-first "alive" brain and optional FS watcher

from __future__ import annotations
from pathlib import Path
import hashlib
import json
import subprocess
import time
from datetime import date
from typing import Callable, List, Dict, Any

from .sys_events import record_event, recent_events, wait_event
from .failure_counter import record_failure

class AliveBrain:
    def __init__(
        self,
        list_goals: Callable[[], List[Any]],
        create_goal: Callable[..., Any],
        get_memory_health: Callable[[], Dict[str, Any]],
        repo_root: Path,
        tick_s: int = 30,
        cooldown_s: int = 20 * 60,
        idle_s: int = 90,
        get_affect_state: Callable[[], Dict[str, Any]] | None = None,
        **_legacy_kwargs: Any,
    ):
        # NOTE: get_affect_state is accepted for compatibility with main.py,
        # which passes a reader for brain/data/emotion_state.json. The current
        # rule-set doesn't condition on emotional state, but accepting the kwarg
        # prevents AliveBrain from failing to instantiate (and thus the goals
        # daemon's housekeeping backstop from never running).
        self.list_goals = list_goals
        self.create_goal = create_goal
        self.get_memory_health = get_memory_health
        self.get_affect_state = get_affect_state
        self.repo_root = Path(repo_root)
        self.tick_s = tick_s
        self.cooldown_s = cooldown_s
        self.idle_s = idle_s
        self._stop = False
        self._last_action_ts = 0.0
        self._last_heavy: Dict[str, float] = {}
        # Dedup state is PERSISTED across restarts. It used to live only in memory,
        # so every reboot forgot it and re-spawned the same auto goals (the daily
        # snapshot churned to 200×). _last = cooldown timestamps; _created_once =
        # keys for one-shot / date-stamped goals that must never be re-created.
        self._state_file = self.repo_root / "data" / "alive_brain_state.json"
        self._last: Dict[str, float] = {}
        self._created_once: set = set()
        try:
            st = json.loads(self._state_file.read_text(encoding="utf-8"))
            self._last = {str(k): float(v) for k, v in (st.get("last") or {}).items()}
            self._created_once = set(st.get("created_once") or [])
        except (OSError, ValueError):  # intentional: missing/bad state on first run → empty
            pass

    def stop(self): self._stop = True
    def _recent(self, key: str, now: float) -> bool: return (now - self._last.get(key, 0.0)) < self.cooldown_s
    def _mark(self, key: str, now: float):
        self._last[key] = now
        self._persist_state()

    def _persist_state(self) -> None:
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            cutoff = time.time() - 86400  # bound the cooldown map to a day
            self._last = {k: v for k, v in self._last.items() if v >= cutoff}
            self._state_file.write_text(json.dumps(
                {"last": self._last, "created_once": sorted(self._created_once)[-500:]},
                indent=2), encoding="utf-8")
        except Exception as exc:  # state persist failed — record (dedup may reset on restart)
            record_failure("alive_brain._persist_state", exc)

    _INACTIVE_STATUSES = {"done", "completed", "failed", "abandoned", "cancelled", "archived"}

    def _active_titles(self) -> set:
        """Lowercased titles of goals in the store that are NOT finished — so we
        never spawn a duplicate of something already queued or in progress."""
        out: set = set()
        try:
            for g in (self.list_goals() or []):
                title = getattr(g, "title", None)
                status = getattr(g, "status", None)
                if title is None and isinstance(g, dict):
                    title = g.get("title"); status = g.get("status")
                if not title:
                    continue
                if str(status or "").lower() not in self._INACTIVE_STATUSES:
                    out.add(str(title).strip().lower())
        except Exception as exc:  # goal enumeration failed — record, no dedup titles
            record_failure("alive_brain._active_titles", exc)
        return out

    def _every(self, name: str, period_s: float, now: float) -> bool:
        t = self._last_heavy.get(name, 0.0)
        if (now - t) >= period_s:
            self._last_heavy[name] = now
            return True
        return False

    def _todo_items(self):
        p = self.repo_root / "TODO.md"
        if not p.exists(): return []
        return [ln.strip() for ln in p.read_text(errors="ignore").splitlines()
                if "- [ ]" in ln or "TODO:" in ln]

    def _lint_count(self) -> int:
        try:
            p = subprocess.run(
                ["ruff","--quiet","--select","ALL","--statistics","."],
                cwd=str(self.repo_root), capture_output=True, text=True, timeout=20
            )
            return sum(int(tok) for tok in p.stdout.split() if tok.isdigit())
        except (OSError, subprocess.SubprocessError, ValueError):  # intentional: ruff absent/timeout → 0
            return 0

    def _mypy_errors(self) -> int:
        try:
            p = subprocess.run(
                ["mypy","--hide-error-context","--no-color-output","--no-error-summary","."],
                cwd=str(self.repo_root), capture_output=True, text=True, timeout=40
            )
            return 0 if p.returncode == 0 else max(1, p.returncode)
        except (OSError, subprocess.SubprocessError):  # intentional: mypy absent/timeout → 0
            return 0

    def _outdated_deps(self) -> int:
        try:
            p = subprocess.run(["pip","list","--outdated","--format","json"],
                               cwd=str(self.repo_root), capture_output=True, text=True, timeout=20)
            return len(json.loads(p.stdout or "[]"))
        except (OSError, subprocess.SubprocessError, ValueError):  # intentional: pip absent/timeout → 0
            return 0

    def run_forever(self):
        MICRO_BATCH_S = 0.2
        last_tick = 0.0
        while not self._stop:
            ev = wait_event(timeout=0.3)
            now = time.time()
            should_tick = False
            if ev is not None:
                end = time.time() + MICRO_BATCH_S
                while time.time() < end:
                    _ = wait_event(timeout=0.05)
                should_tick = True
            elif (now - last_tick) >= self.tick_s:
                should_tick = True

            if should_tick:
                try:
                    self._tick(now)
                    last_tick = now
                except Exception as e:
                    print(f"[alive] error: {e}")

    def _tick(self, now: float):
        mem = self.get_memory_health() or {}
        evs = recent_events(40)
        goals = self.list_goals()

        def _status(g):
            s = getattr(g, "status", "")
            return getattr(s, "name", str(s)).upper()
        running = [g for g in goals if _status(g) in ("RUNNING","READY")]
        idle = (now - self._last_action_ts) > self.idle_s or not running

        candidates: List[Dict] = []
        bytes_total = int(mem.get("bytes") or 0)
        wal_lag = float(mem.get("wal_lag_s") or 0.0)

        if bytes_total > 64 * 1024 * 1024 or wal_lag > 300:
            candidates.append({
                "score": 90 if bytes_total > 64*1024*1024 else 70,
                "title": "Housekeeping: compact + snapshot (auto)",
                "kind": "housekeeping",
                "priority": "CRITICAL" if bytes_total > 64*1024*1024 else "HIGH",
                "tags": ["auto","memory"],
                "spec": {"snapshots":{"goals":True,"memory":True},"prune_wal":True,"compact_store":True},
                "key": "auto:compact+snapshot",
            })

        today = date.today().isoformat()
        candidates.append({
            "score": 40,
            "title": f"Housekeeping: daily snapshot ({today})",
            "kind": "housekeeping",
            "priority": "NORMAL",
            "tags": ["auto","snapshot"],
            "spec": {"snapshots":{"goals":True,"memory":True}},
            "key": f"auto:daily-snapshot:{today}",
        })

        if any(ev.get("type") in ("step_fail","step_exc") for ev in evs[-5:]):
            candidates.append({
                "score": 85, "title": "Investigate last step failure",
                "kind": "generic", "priority": "HIGH", "tags":["auto","recovery"],
                "spec": {"investigate": "last_step_failure"},
                "key": "auto:investigate-last-failure",
            })

        if sum(1 for ev in evs if ev.get("type")=="step_slow") >= 3:
            candidates.append({
                "score": 60, "title": "Reduce slow steps (profiling sweep)",
                "kind": "generic", "priority": "NORMAL", "tags":["auto","perf"],
                "spec": {"investigate": "slow_steps"},
                "key": "auto:perf-slow-steps",
            })

        todos = self._todo_items()
        if todos:
            digest = hashlib.sha1("\n".join(todos[:50]).encode()).hexdigest()[:8]
            candidates.append({
                "score": 55, "title": "Process TODO.md items",
                "kind": "generic", "priority": "NORMAL", "tags":["auto","todos"],
                "spec": {"process_todos": True, "limit": 5},
                "key": f"auto:process-todos:{digest}",
            })

        if self._every("ruff", 30, now):
            lint_cnt = self._lint_count()
            if lint_cnt > 100:
                candidates.append({
                    "score": 50 + min(30, lint_cnt//100),
                    "title": "Reduce lint debt (top rules)",
                    "kind": "generic", "priority": "NORMAL", "tags":["auto","lint"],
                    "spec": {"investigate": "lint_debt"},
                    "key": "auto:lint-debt",
                })

        if self._every("mypy", 120, now):
            mypy_errs = self._mypy_errors()
            if mypy_errs > 0:
                candidates.append({
                    "score": 60, "title": "Fix top mypy errors",
                    "kind": "generic", "priority": "NORMAL", "tags":["auto","typing"],
                    "spec": {"investigate": "mypy_errors"},
                    "key": "auto:mypy-errors",
                })

        if self._every("deps", 300, now):
            outdated = self._outdated_deps()
            if outdated >= 3:
                candidates.append({
                    "score": 45 + min(20, outdated),
                    "title": "Upgrade safe dependency patches",
                    "kind": "generic", "priority": "LOW", "tags":["auto","deps"],
                    "spec": {"investigate": "outdated_deps"},
                    "key": "auto:deps-outdated",
                })

        candidates.sort(key=lambda c: c.get("score", 0), reverse=True)
        active_titles = self._active_titles()
        for c in candidates:
            key = c["key"]
            if self._recent(key, now):
                continue
            # One-shot / date-stamped goals (e.g. "auto:daily-snapshot:2026-06-03")
            # must never be created twice — survives restarts via persisted state.
            dated = key.endswith(date.today().isoformat()) or ":daily-snapshot:" in key
            if dated and key in self._created_once:
                continue
            # Never duplicate a goal already queued / in progress in the store.
            if c["title"].strip().lower() in active_titles:
                self._mark(key, now)
                continue
            if idle or c["score"] >= 80:
                self.create_goal(
                    title=c["title"], kind=c["kind"], priority=c["priority"],
                    tags=c["tags"], spec=c["spec"]
                )
                if dated:
                    self._created_once.add(key)
                self._mark(key, now)
                self._last_action_ts = now
                break

def start_fs_watcher(repo_root: Path):
    """Optional: wake the brain on file edits (best-effort if watchdog is present)."""
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except Exception:
        print("[alive] watchdog filesystem module not available; FS events disabled")
        return None, None
    class _FSHandler(FileSystemEventHandler):
        def on_modified(self, event):
            if getattr(event, "is_directory", False): return
            p = str(getattr(event, "src_path", ""))
            if any(seg in p for seg in (".git",".venv","node_modules","dist","build")): return
            record_event({"type":"fs_change","path": p})
    obs = Observer()
    h = _FSHandler()
    obs.schedule(h, path=str(repo_root), recursive=True)
    obs.start()
    print("[alive] FS watcher started")
    return obs, h
