# main.py
from __future__ import annotations

# --- Bootstrap sys.path BEFORE any brain-rooted import (core.*, think.*, cog_memory.*, …).
# brain/ must be importable for `from core.runtime_log import …` below to resolve when
# main.py is launched from the repo root (e.g. via run_orrin.sh). brain/ ends up first so
# v1 packages resolve there; the repo root stays on the path so v2's memory/, goals/, utils/
# remain importable too.
import sys
from pathlib import Path
_REPO_ROOT_STR = str(Path(__file__).resolve().parent)
_BRAIN_DIR = Path(__file__).resolve().parent / "brain"
if _REPO_ROOT_STR not in sys.path:
    sys.path.insert(0, _REPO_ROOT_STR)
if str(_BRAIN_DIR) not in sys.path:
    sys.path.insert(0, str(_BRAIN_DIR))

from core.runtime_log import get_logger

import os
import time
import webbrowser
import inspect
import threading
import shutil

_log = get_logger(__name__)

# --- Crash capture nets ---
# faulthandler catches native (C-level) crashes from torch/spaCy/numpy on
# SIGSEGV/SIGABRT/SIGFPE — crashes no Python hook can see. The file handle must
# stay open for the process lifetime: closing it disarms the handler.
import faulthandler
import datetime as _datetime
_CRASH_LOG_PATH = Path(__file__).resolve().parent / "brain" / "logs" / "crash.log"
_CRASH_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
_crash_fp = open(_CRASH_LOG_PATH, "a")
_crash_fp.write(f"--- session start {_datetime.datetime.now().isoformat()} pid={os.getpid()} ---\n")
_crash_fp.flush()
faulthandler.enable(file=_crash_fp, all_threads=True)

# Uncaught Python exceptions — including in the daemon thread the brain loop
# runs in — must land in orrin_runtime.log at CRITICAL, not only on a terminal
# that may be gone by morning. (The 2026-06-11 run died silently at 16:42:28
# because the default threading.excepthook printed to a lost stderr.)
import traceback as _traceback

def _log_uncaught(exc_type, exc_value, exc_tb) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    tb_text = "".join(_traceback.format_exception(exc_type, exc_value, exc_tb))
    _log.critical("UNCAUGHT EXCEPTION (main thread):\n%s", tb_text)
    sys.__excepthook__(exc_type, exc_value, exc_tb)

def _log_thread_uncaught(args) -> None:
    if args.exc_type is SystemExit:
        return
    tb_text = "".join(
        _traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)
    )
    name = args.thread.name if args.thread is not None else "<unknown>"
    _log.critical("UNCAUGHT EXCEPTION in thread %r:\n%s", name, tb_text)

sys.excepthook = _log_uncaught
threading.excepthook = _log_thread_uncaught

# --- Boot config check (fast, no LLM call) ---
def _boot_config_check() -> None:
    """Verify critical paths and config files exist before subsystems start."""
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(override=True)
    brain_dir = Path(__file__).resolve().parent / "brain"
    if not brain_dir.exists():
        print(f"[boot] FAILED: brain/ directory not found at {brain_dir}", file=sys.stderr)
        sys.exit(2)
    # Warn (don't block) if LLM key is absent — Orrin runs symbolically without it
    if not os.getenv("OPENAI_API_KEY"):
        print("[boot] WARNING: OPENAI_API_KEY not set — LLM tool calls will be skipped; symbolic-only mode")
    print("[boot] config check OK")

_boot_config_check()

# --- Single-instance guard ---
# Two Orrin processes writing the same brain/data files caused a corruption
# cascade (10k+ .corrupt files in hours). An exclusive advisory lock makes a
# second launch refuse to start, instead of fighting the first over the 8 GB and
# the shared JSON state. The fd is kept alive for the whole process lifetime.
_INSTANCE_LOCK_FD = None
def _acquire_single_instance_lock() -> None:
    global _INSTANCE_LOCK_FD
    try:
        import fcntl
    except Exception:
        return  # non-POSIX: skip the guard rather than block startup
    lock_path = Path(__file__).resolve().parent / "brain" / "data" / ".orrin.instance.lock"
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = open(lock_path, "w")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd.write(str(os.getpid()))
        fd.flush()
        _INSTANCE_LOCK_FD = fd  # keep alive — closing would release the lock
        print(f"[boot] single-instance lock acquired (pid {os.getpid()})")
    except BlockingIOError:
        print("[boot] FAILED: another Orrin instance is already running "
              f"(lock: {lock_path}). Refusing to start a second brain.", file=sys.stderr)
        sys.exit(3)
    except Exception as _e:
        print(f"[boot] single-instance lock skipped ({_e})")

_acquire_single_instance_lock()

# --- Observability / watchdogs ---
from watchdogs import Pulse, start_watchdogs
from observability.metrics import serve_metrics
from observability import metrics  # Gauge: lifespan_cycles

# --- Memory subsystem ---
from memory.store.inmem import InMemoryStore
from memory.memory_daemon import MemoryDaemon
from memory.health import snapshot as memory_snapshot  # rich snapshot
from memory.wal import flush as wal_flush

# --- Goals subsystem ---
from goals.model import Goal  # noqa: F401 (used via API/daemon)

try:
    from goals.registry import build_default_registry
    from goals.goals_daemon import GoalsDaemon
    _HAVE_GOALS_DAEMON = True
except Exception:
    _HAVE_GOALS_DAEMON = False

# --- Utils ---
from utils.paths import compute_repo_root
from utils.sys_events import record_event
from utils.alive_brain import AliveBrain, start_fs_watcher
from utils.memory_health import build_memory_health_provider
from utils.metrics_sampling import build_fast_sampler
from utils.goals_feed import init_goals
from brain.utils.get_cycle_count import get_cycle_count

# --- Tamper guard (already existed as a util) ---
from utils.tamper_guard import start_reaper_tamper_guard

# ---------- Metrics endpoint (Prometheus) ----------
METRICS_PORT = 9100  # http://127.0.0.1:9100/metrics
serve_metrics(port=METRICS_PORT)
print(f"[metrics] Prometheus exporter on http://127.0.0.1:{METRICS_PORT}/metrics")

# ---------- Repo root ----------
REPO_ROOT = compute_repo_root(__file__)

# ---- Forget-on-start (stateless boot) ----
def _is_subpath(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False

def _forget_everything(repo_root: Path) -> None:
    """
    DANGER: Deletes local persisted state so Orrin boots fresh.
    Controlled by ORRIN_FORGET_ON_START=1|true|yes.
    Only deletes paths inside repo_root for safety.
    """
    candidates = [
        repo_root / "data" / "memory",
        repo_root / "data" / "goals",
        repo_root / "data" / "logs",
        repo_root / "tmp",
    ]
    for p in candidates:
        try:
            if _is_subpath(p, repo_root) and p.exists():
                print(f"[forget] removing {p}")
                shutil.rmtree(p, ignore_errors=True)
        except Exception as e:
            print(f"[forget] could not remove {p}: {e}")
    # Re-create minimal structure some code expects
    for p in (repo_root / "data", repo_root / "data" / "logs", repo_root / "tmp"):
        try:
            p.mkdir(parents=True, exist_ok=True)
        except Exception as _e:
            _log.warning("silent except: %s", _e)

FORGET_FLAG = os.getenv("ORRIN_FORGET_ON_START", "").strip().lower()
if FORGET_FLAG in ("1", "true", "yes"):
    print("[forget] ORRIN_FORGET_ON_START enabled → wiping persisted state before boot")
    _forget_everything(REPO_ROOT)
else:
    print("[forget] ORRIN_FORGET_ON_START not set → keeping previous state")

# ---------- Memory subsystem ----------
store = InMemoryStore()
daemon = MemoryDaemon(store)
daemon.start()
print("[memory] MemoryDaemon started with InMemoryStore")

# Bound provider for UIs & brain
get_memory_health = build_memory_health_provider(daemon, store, memory_snapshot)

# ---------- Goals: store/API ----------
GOALS_DATA_DIR = Path(os.environ.get("ORRIN_GOALS_DIR", REPO_ROOT / "data" / "goals")).resolve()
_goal_store, _goals_api = init_goals(GOALS_DATA_DIR)

# ---------- Orrin UI (Face & Brain) ----------
# Replaces the old dashboard/ UI. Starts the FastAPI telemetry backend in-process
# and the Vite UI as a child process. Guarded so the brain still boots if the UI
# stack (fastapi / node) isn't installed. Disable with ORRIN_UI=0.
_ui_proc = None
_urls_to_open: list = []
try:
    if os.getenv("ORRIN_UI", "1").strip().lower() in ("0", "false", "no"):
        print("[ui] ORRIN_UI=0 → Face & Brain UI not started")
    else:
        from backend.main import start_ui_stack
        TELEMETRY_PORT = int(os.environ.get("ORRIN_BACKEND_PORT", "8800"))
        # Host the telemetry backend + UI bind to. Defaults to localhost; set
        # ORRIN_BACKEND_HOST to a LAN/Tailscale IP to serve the UI over the network.
        # The launcher derives the browser's VITE_TELEMETRY_HOST from this same
        # value, so the page and its telemetry/API both resolve to one host.
        ORRIN_HOST = os.environ.get("ORRIN_BACKEND_HOST", "127.0.0.1")
        # When binding all interfaces (0.0.0.0/::), the in-process bridge talks to
        # localhost, and the URL shown to users comes from the browser-facing
        # VITE_TELEMETRY_HOST (a reachable LAN/Tailscale IP). Otherwise everything
        # uses the explicit host.
        _bind_all = ORRIN_HOST in ("0.0.0.0", "::")
        _vite_host = os.environ.get("VITE_TELEMETRY_HOST", "")
        _display_host = (_vite_host.split(":")[0] or "127.0.0.1") if _bind_all else ORRIN_HOST
        # Point the cognitive loop's TelemetryBridge at this backend.
        os.environ.setdefault(
            "ORRIN_TELEMETRY_URL",
            f"http://{'127.0.0.1' if _bind_all else ORRIN_HOST}:{TELEMETRY_PORT}",
        )
        _ui_proc = start_ui_stack(host=ORRIN_HOST, port=TELEMETRY_PORT)
        _ui_url = f"http://{_display_host}:5173"
        _urls_to_open.append(("orrin-ui", _ui_url))
        print(f"[ui] Orrin Face & Brain → {_ui_url}  (telemetry API {_display_host}:{TELEMETRY_PORT})")
except Exception as e:
    print(f"[ui] not started: {e}")

# ---------- Open browser ----------
def _open_browsers(urls: list) -> None:
    for label, url in urls:
        try:
            webbrowser.open(url)
            print(f"[browser] opened {label}: {url}")
        except Exception as e:
            print(f"[browser] could not open {label}: {e}")
        time.sleep(0.6)

if _urls_to_open:
    _browser_thread = threading.Thread(
        target=_open_browsers,
        args=(_urls_to_open,),
        name="browser-opener",
        daemon=True,
    )
    _browser_thread.start()

# ---------- Watchdogs ----------
pulse = Pulse()

# psutil-based resource providers (gracefully absent if psutil not installed)
try:
    import psutil as _psutil
    _proc = _psutil.Process()
    # `resource` is POSIX-only; absent on Windows. Keep psutil monitoring either way.
    try:
        import resource as _resource
    except Exception:
        _resource = None  # type: ignore
    def _get_rss_mb() -> float:
        return _proc.memory_info().rss / 1024 / 1024
    def _get_fd_open() -> int:
        # num_fds() on POSIX, num_handles() on Windows
        if hasattr(_proc, "num_fds"):
            return _proc.num_fds()
        return _proc.num_handles()
    def _get_fd_limit() -> int:
        try:
            if _resource is not None:
                return min(_resource.getrlimit(_resource.RLIMIT_NOFILE)[0], 1024)
        except Exception:
            pass
        return 1024
    def _get_sock_open() -> int:
        try:
            return len(_proc.net_connections())
        except Exception:
            return 0
    def _get_sock_limit() -> int:
        return 1024
    def _get_cpu_util() -> float:
        return _proc.cpu_percent(interval=None) / 100.0
except ImportError:
    _get_rss_mb = _get_fd_open = _get_fd_limit = None  # type: ignore[assignment]
    _get_sock_open = _get_sock_limit = _get_cpu_util = None  # type: ignore[assignment]

try:
    tup = start_watchdogs(
        pulse,
        per_key_limits={"llm_timeout": (10, 15.0)},
        get_memory_health=get_memory_health,
        memory_daemon=daemon,
        ns_sample_interval_s=0.2,
        ns_summary_interval_s=5.0,
        get_rss_mb=_get_rss_mb,
        get_fd_open=_get_fd_open,
        get_fd_limit=_get_fd_limit,
        get_sock_open=_get_sock_open,
        get_sock_limit=_get_sock_limit,
        get_cpu_util=_get_cpu_util,
    )
except TypeError:
    tup = start_watchdogs(
        pulse,
        per_key_limits={"llm_timeout": (10, 15.0)},
    )

(
    reaper,
    detector,
    errors,
    liveness,
    lifespan,
    no_goals,
    mem_guard,
    repeat_guard,
    stop_evt,
) = tup

# --- Tamper guard: kill on any reaper modification ---
try:
    extra_watch = []
    try:
        extra_watch.append(inspect.getfile(reaper.__class__))
        trig = getattr(reaper, "trigger", None)
        if callable(trig):
            func = getattr(trig, "__func__", trig)
            extra_watch.append(inspect.getfile(func))
    except Exception as _e:
        _log.warning("silent except: %s", _e)

    start_reaper_tamper_guard(
        reaper,
        period_s=float(os.environ.get("ORRIN_TAMPER_GUARD_PERIOD_S", "1.0")),
        extra_files=[p for p in set(extra_watch) if p],
        on_trip="exit",
    )
    print("[tamper-guard] active: reaper integrity monitored")
except Exception as e:
    print(f"[tamper-guard] not started: {e}")

# ---------- Goals daemon + Alive brain + FS watcher ----------
_goals_daemon = None
_alive = None
_alive_thr = None
_fs_obs = None

def _list_goals_for_brain():
    try:
        return _goals_api.list_goals()
    except Exception:
        return []

if _HAVE_GOALS_DAEMON:
    try:
        _registry = build_default_registry()
        def _goal_memory_writer(kind: str, text: str, meta: dict) -> None:
            """Write goal lifecycle events into v2 MemoryDaemon so they're semantically searchable."""
            try:
                from memory.models import Event
                daemon.ingest(Event(kind=kind, content=text, meta=meta or {}))
            except Exception as _e:
                _log.warning("silent except: %s", _e)

        def _goals_reaper_sink(event: dict) -> None:
            """Fan goal daemon events out to: (1) AliveBrain event bus, (2) the new UI's Live Console."""
            record_event(event)
            try:
                from backend.telemetry_bridge import get_bridge
                get_bridge().log("info", "goals", str(event.get("kind", "goal_event")))
            except Exception as _e:
                _log.warning("silent except: %s", _e)

        _EMOTION_STATE_PATH = REPO_ROOT / "brain" / "data" / "emotion_state.json"

        def _get_emotional_state() -> dict:
            """Read Orrin's current emotional state from v1's persisted file."""
            try:
                import json as _json
                raw = _EMOTION_STATE_PATH.read_text(encoding="utf-8")
                data = _json.loads(raw)
                # Flatten: prefer core_emotions block if present, fall back to top-level
                core = data.get("core_emotions")
                if isinstance(core, dict):
                    merged = dict(data)
                    merged.update(core)
                    return merged
                return data
            except Exception:
                return {}

        _goals_daemon = GoalsDaemon(
            store=_goal_store,
            registry=_registry,
            workers=2,
            tick_seconds=0.5,
            ctx={
                "repo_root": str(REPO_ROOT),
                "get_memory_health": get_memory_health,
                "api": _goals_api,
                "get_emotional_state": _get_emotional_state,
            },
            reaper_sink=_goals_reaper_sink,
            memory_writer=_goal_memory_writer,
        )
        _goals_daemon.start()
        try:
            _goals_api.daemon = _goals_daemon
        except Exception as _e:
            _log.warning("silent except: %s", _e)

        _alive = AliveBrain(
            list_goals=_list_goals_for_brain,
            create_goal=_goals_api.create_goal,
            get_memory_health=get_memory_health,
            get_emotional_state=_get_emotional_state,
            repo_root=REPO_ROOT,
            tick_s=30, cooldown_s=20*60, idle_s=90,
        )
        _alive_thr = threading.Thread(target=_alive.run_forever, name="alive-brain", daemon=True)
        _alive_thr.start()

        _fs_obs, _fs_handler = start_fs_watcher(REPO_ROOT)
        print("[alive] goals daemon + brain started")
    except Exception as e:
        print(f"[alive] not started: {e}")
else:
    print("[alive] goals daemon modules not available; alive brain disabled")

# ---------- Fast metric sampler (wake the brain on changes) ----------
sample_metrics_fast = build_fast_sampler(get_memory_health)

def _validate_think_module() -> None:
    """
    Compile-check think_module.py before the cognitive import chain loads it.
    If it has a SyntaxError (from a bad auto-revision), roll back to backup so
    ORRIN_loop can import successfully.
    """
    think_path = _BRAIN_DIR / "think" / "think_module.py"
    backup_path = _BRAIN_DIR / "think" / "think_module_backup.py"

    if not think_path.exists():
        return

    try:
        source = think_path.read_text(encoding="utf-8")
        compile(source, str(think_path), "exec")
        print("[boot] think_module.py syntax OK")
    except SyntaxError as e:
        print(f"[boot] think_module.py has SyntaxError: {e}")
        if backup_path.exists():
            shutil.copy2(str(backup_path), str(think_path))
            print("[boot] think_module.py rolled back from backup")
        else:
            print("[boot] WARNING: no backup found — cognitive loop may fail to import")


_validate_think_module()


def run() -> None:
    # ---------- Cognitive loop (v1 brain) ----------
    _cog_thread = None
    try:
        from brain.ORRIN_loop import run_cognitive_loop
        _cog_thread = threading.Thread(
            target=run_cognitive_loop,
            kwargs={
                "pulse": pulse,
                "goals_api": _goals_api,
                "memory_daemon": daemon,
                "stop_event": stop_evt,
                "cycle_sleep": float(os.environ.get("ORRIN_CYCLE_SLEEP", "10")),
            },
            name="orrin-brain",
            daemon=True,
        )
        _cog_thread.start()
        print("[brain] cognitive loop thread started")
    except Exception as e:
        print(f"[brain] could not start cognitive loop: {e}")

    last_log = 0
    try:
        while True:
            pulse.tick()

            n = pulse.read()
            try:
                metrics.cycle_gauge.set(float(n))
            except Exception as _e:
                _log.warning("silent except: %s", _e)

            if (n % 5) == 0:  # ~10Hz loop → fire ~2Hz
                sample_metrics_fast()
                try:
                    cog_n = get_cycle_count()
                    metrics.lifespan_cycles.set(float(cog_n))
                except Exception as _e:
                    _log.warning("silent except: %s", _e)

            time.sleep(0.02)

            last_log += 1
            if last_log >= 100:
                try:
                    print(f"[main] pulse={n} cog_cycles={get_cycle_count()}")
                except Exception:
                    print(f"[main] pulse={n}")
                last_log = 0

    except KeyboardInterrupt:
        print("\n[main] Ctrl+C received; shutting down…")
    finally:
        try:
            stop_evt.set()
        except Exception as _e:
            _log.warning("silent except: %s", _e)

        if _cog_thread is not None and _cog_thread.is_alive():
            _cog_thread.join(timeout=15)

        try:
            if _alive: _alive.stop()
        except Exception as _e:
            _log.warning("silent except: %s", _e)
        try:
            if _goals_daemon: _goals_daemon.stop()
        except Exception as _e:
            _log.warning("silent except: %s", _e)

        try:
            if _fs_obs:
                _fs_obs.stop()
                _fs_obs.join()
        except Exception as _e:
            _log.warning("silent except: %s", _e)

        try:
            daemon.stop(join=True)
        except Exception as _e:
            _log.warning("silent except: %s", _e)
        try:
            wal_flush()
        except Exception as _e:
            _log.warning("silent except: %s", _e)

        if _ui_proc is not None:
            try:
                from backend.server.launcher import stop_ui
                stop_ui(_ui_proc)
            except Exception:
                _log.warning("silent except")

        print("[main] shutdown complete.")

if __name__ == "__main__":
    run()
