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
# Source runs only: put repo root + brain/ on sys.path so bare-name brain imports
# resolve. In a FROZEN app (I3) these modules live in the PYZ and are served by
# PyInstaller's frozen importer — inserting the (partial, bundled) brain/ dir at the
# front of sys.path instead shadows that importer and breaks `from utils.paths import …`.
if not getattr(sys, "frozen", False):
    if _REPO_ROOT_STR not in sys.path:
        sys.path.insert(0, _REPO_ROOT_STR)
    if str(_BRAIN_DIR) not in sys.path:
        sys.path.insert(0, str(_BRAIN_DIR))

# --- Per-user data home (Phase 3 / Group C) ---
# A packaged app can't write into its own (read-only) program folder, so route all
# of Orrin's state to the OS app-data dir. This MUST happen before any brain module
# (paths.py, memory.config) is imported, since they read these env vars at import.
#   • ORRIN_DATA_HOME set  → use it (explicit opt-in; also how tests exercise this)
#   • frozen (PyInstaller) → the OS per-user dir
#   • running from source  → leave unset → in-repo brain/data (unchanged for devs)
import os as _os_early
from utils.paths import user_data_home as _user_data_home, apply_user_data_env as _apply_user_data_env
_data_home = _os_early.environ.get("ORRIN_DATA_HOME")
if _data_home:
    _apply_user_data_env(Path(_data_home))
elif getattr(sys, "frozen", False):
    _apply_user_data_env(_user_data_home())

# Point the ML stack at PRE-BUNDLED weights and go hard-offline (I2) — BEFORE any
# torch/sentence-transformers/spaCy import, so a frozen Orrin boots with zero network.
# No-op in a dev checkout (no bundle / no ORRIN_MODELS_DIR).
try:
    from utils.model_assets import apply_offline_env as _apply_offline_env
    if _apply_offline_env():
        print("[boot] using bundled ML weights (offline mode)")
except Exception:
    pass

from core.runtime_log import get_logger

import os
import time
import signal
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
    # Hydrate API keys the user saved in the OS keychain (Phase 4). A dev `.env`,
    # loaded just above, keeps precedence; this only fills what's absent — so a
    # packaged app with no `.env` still picks up keys pasted in Settings last session.
    try:
        from utils.secrets import load_into_env as _load_secrets_env
        _load_secrets_env()
    except Exception as _e:
        print(f"[boot] keychain load skipped ({_e})")
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
    # The lock lives WITH the mind (the resolved data dir), not in the program
    # folder — so the packaged app locks per-install in its writable dir.
    try:
        from paths import DATA_DIR as _lock_data_dir
    except Exception:
        _lock_data_dir = Path(__file__).resolve().parent / "brain" / "data"
    lock_path = _lock_data_dir / ".orrin.instance.lock"
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = open(lock_path, "w")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd.write(str(os.getpid()))
        fd.flush()
        _INSTANCE_LOCK_FD = fd  # keep alive — closing would release the lock
        print(f"[boot] single-instance lock acquired (pid {os.getpid()})")
    except BlockingIOError:
        # Another Orrin already holds the lock. The common reason for a relaunch is
        # "I closed his window and want it back" — but in Always-thinking mode he's
        # still alive in the background, and pywebview can't open a second window in a
        # new process for the SAME mind. Warn clearly (and notify on a GUI launch where
        # stderr is invisible) instead of dying with a cryptic refusal.
        holder = ""
        try:
            holder = lock_path.read_text(encoding="utf-8").strip()
        except Exception:
            pass
        always = False
        try:
            from utils import prefs as _prefs
            always = _prefs.get("existence_mode", "sleep") == "always"
        except Exception:
            pass

        who = f" (pid {holder})" if holder else ""
        if always:
            headline = "Orrin is already thinking in the background."
            detail = (
                "He's in 'Always thinking' mode, so he keeps living after his window "
                "closes. Re-opening his window from a new launch isn't supported yet "
                "(one window per process). To see him again, quit the running Orrin"
                f"{(' — e.g. kill ' + holder) if holder else ''} and start him again, "
                "or switch to 'Sleep when closed' in Settings so closing the window "
                "stops him cleanly."
            )
        else:
            headline = f"Orrin is already running{who}."
            detail = "Refusing to start a second brain — two would corrupt his shared state."

        print(f"[boot] {headline}\n[boot] {detail}\n[boot] (lock: {lock_path})", file=sys.stderr)
        # Best-effort desktop notification so a double-click launch isn't a silent exit.
        try:
            from agency.skills.notify_user import notify_user
            notify_user({"title": "Orrin is already running", "message": headline})
        except Exception:
            pass
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
# Off by default so a packaged launch opens no listening port. Enable with
# ORRIN_METRICS=1; the port is then OS-assigned (or pinned via ORRIN_METRICS_PORT)
# rather than the old fixed :9100.
from backend.server.config import metrics_enabled as _metrics_enabled
from backend.server.config import pick_free_port as _pick_free_port

if _metrics_enabled():
    METRICS_PORT = int(os.environ.get("ORRIN_METRICS_PORT") or _pick_free_port())
    serve_metrics(port=METRICS_PORT)
    print(f"[metrics] Prometheus exporter on http://127.0.0.1:{METRICS_PORT}/metrics")
else:
    print("[metrics] disabled (set ORRIN_METRICS=1 to enable)")

# ---------- Repo root ----------
REPO_ROOT = compute_repo_root(__file__)

# ---- Forget-on-start (stateless boot) ----
def _is_subpath(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False

def _forget_everything() -> None:
    """
    DANGER: Deletes Orrin's daemon-durability state (the resolved state tree) so he
    boots fresh. Controlled by ORRIN_FORGET_ON_START=1|true|yes. Targets only the
    known state subtrees, which relocate with ORRIN_STATE_DIR.
    """
    try:
        from paths import STATE_DIR, MEMORY_DIR, GOALS_DIR
    except Exception:
        STATE_DIR = REPO_ROOT / "data"
        MEMORY_DIR, GOALS_DIR = STATE_DIR / "memory", STATE_DIR / "goals"
    for p in (MEMORY_DIR, GOALS_DIR, STATE_DIR / "logs", REPO_ROOT / "tmp"):
        try:
            if p.exists():
                print(f"[forget] removing {p}")
                shutil.rmtree(p, ignore_errors=True)
        except Exception as e:
            print(f"[forget] could not remove {p}: {e}")
    for p in (STATE_DIR, STATE_DIR / "logs", REPO_ROOT / "tmp"):
        try:
            p.mkdir(parents=True, exist_ok=True)
        except Exception as _e:
            _log.warning("silent except: %s", _e)


# Bundled config seeds — the minimum a newborn needs to boot coherently. Shipped in
# the program folder's brain/data; copied into a fresh (relocated) data dir on first
# launch so the brain doesn't error on missing model_config / vocabulary / etc.
_SEED_FILES = (
    "affect_model.json", "behavioral_functions_list.json",
    "capability_descriptions.json", "cognitive_functions.json",
    "meta_rules.json", "model_config.json", "vocab_weights.json", "vocabulary.json",
)


def _seed_if_newborn() -> None:
    """If the resolved data dir is a fresh/empty install (no model_config.json yet),
    seed the bundled config files so a newborn boots. No-op when running in-repo on
    the seed dir itself, or when state already exists (relaunch reuses it)."""
    try:
        from paths import DATA_DIR
    except Exception:
        return
    seed_src = _BRAIN_DIR / "data"
    if DATA_DIR.resolve() == seed_src.resolve():
        return  # in-repo: the data dir IS the seed source
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if (DATA_DIR / "model_config.json").exists():
        return  # already a living mind here — reuse it
    copied = 0
    for name in _SEED_FILES:
        src, dst = seed_src / name, DATA_DIR / name
        try:
            if src.exists() and not dst.exists():
                shutil.copy2(src, dst)
                copied += 1
        except Exception as e:
            print(f"[seed] could not seed {name}: {e}")
    print(f"[seed] newborn data dir → seeded {copied} config file(s) into {DATA_DIR}")


FORGET_FLAG = os.getenv("ORRIN_FORGET_ON_START", "").strip().lower()
if FORGET_FLAG in ("1", "true", "yes"):
    print("[forget] ORRIN_FORGET_ON_START enabled → wiping persisted state before boot")
    _forget_everything()
else:
    print("[forget] ORRIN_FORGET_ON_START not set → keeping previous state")

# First-launch seeding: a fresh/relocated data dir boots a coherent newborn.
_seed_if_newborn()

# Schema migration spine (§10.7): reconcile the on-disk state version with this build
# BEFORE any subsystem reads state. Older → auto-export then migrate forward; newer
# (a downgrade) → refuse to load rather than corrupt the mind. A newborn just gets
# stamped at the current version. Runs after seeding so a fresh dir is already coherent.
try:
    from utils.schema_migration import SchemaTooNewError as _SchemaTooNewError
except Exception:
    _SchemaTooNewError = None  # don't let an import hiccup crash boot before migration runs
try:
    from utils import schema_migration as _schema
    _mig = _schema.check_and_migrate()
    if _mig.get("action") == "migrated":
        print(
            f"[schema] migrated mind v{_mig['from']} → v{_mig['to']} "
            f"(backed up first: {_mig.get('backup') or 'snapshot failed'})"
        )
except Exception as _e:
    # A genuinely-newer on-disk schema must HALT boot (refuse to corrupt the mind);
    # any other failure here is best-effort and must not block boot.
    if _SchemaTooNewError is not None and isinstance(_e, _SchemaTooNewError):
        print(f"[schema] REFUSING TO BOOT — {_e}")
        raise SystemExit(1)
    _log.warning("silent except: %s", _e)

# Flag a fresh mind so the UI can show First Wake (§9.2). A newborn has no
# autobiography / long-term memory yet (seeds are config only, not lived experience).
try:
    from paths import DATA_DIR as _DD_NB
    _is_newborn = not (_DD_NB / "long_memory.json").exists() and not (_DD_NB / "autobiography.json").exists()
    from utils import boot_events as _boot
    _boot.set_newborn(_is_newborn)
except Exception as _e:
    _log.warning("silent except: %s", _e)

# Existence model (§10.3): apply non-secret prefs to the runtime BEFORE the brain
# rolls a lifespan or the cognitive loop reads its cadence. Explicit env always wins
# (dev override), so these use setdefault.
try:
    from utils import prefs as _prefs
    _band = _prefs.get("lifespan_band", [365, 730])
    if isinstance(_band, (list, tuple)) and len(_band) == 2:
        # The lifespan band sets the ODDS; mortality still rolls at random inside it.
        # Consumed only when a lifespan is first rolled (birth/Reset).
        os.environ.setdefault("ORRIN_LIFESPAN_MIN_DAYS", str(_band[0]))
        os.environ.setdefault("ORRIN_LIFESPAN_MAX_DAYS", str(_band[1]))
    if _prefs.get("game_mode", False):
        # Throttle to near-zero CPU — he stays alive (ages), just thinks rarely.
        os.environ.setdefault("ORRIN_CYCLE_SLEEP", "30")
        os.environ.setdefault("ORRIN_EXECUTIVE_DAEMON_INTERVAL", "60")
        print("[existence] Game Mode ON — cognition throttled so other apps run smoothly")
    _disk_ceiling = _prefs.get("disk_ceiling_gb", 5)
    if _disk_ceiling:
        # The target his forgetting sweeps trim toward (§10.3).
        os.environ.setdefault("ORRIN_DISK_CEILING_GB", str(_disk_ceiling))
    _mem_ceiling = _prefs.get("memory_ceiling_gb", 4)
    if _mem_ceiling:
        # The target above which the dream cycle evicts in-process caches (§10.3).
        os.environ.setdefault("ORRIN_MEMORY_CEILING_GB", str(_mem_ceiling))
    if _prefs.get("existence_mode", "sleep") == "sleep":
        # Closed time costs no life: credit the interval since he was last active.
        from cognition.mortality import credit_sleep_since_last_active as _credit_sleep
        _credited = _credit_sleep()
        if _credited > 0:
            print(f"[existence] Sleep mode — credited {_credited / 3600:.1f}h of closed time (no life lost)")
except Exception as _e:
    _log.warning("silent except: %s", _e)

# Lifecycle tag (§10.5): record whether the previous run ended cleanly (→ tell death /
# crash-stall / normal apart on the next launch), then mark THIS run in-progress.
try:
    from utils import lifecycle as _lifecycle
    _lifecycle.mark_running()
except Exception as _e:
    _log.warning("silent except: %s", _e)

# ---------- Memory subsystem ----------
store = InMemoryStore()
daemon = MemoryDaemon(store)
daemon.start()
print("[memory] MemoryDaemon started with InMemoryStore")

# Boot sequence (§9.7) — emit each milestone AFTER it actually comes up, so the
# wake-up screen reflects real readiness. Best-effort; never let it break boot.
try:
    from utils import boot_events as _boot
    _boot.emit("Loading memory")
except Exception as _e:
    _log.warning("silent except: %s", _e)

# Bound provider for UIs & brain
get_memory_health = build_memory_health_provider(daemon, store, memory_snapshot)

# ---------- Goals: store/API ----------
# Goals daemon durability dir. Use the shared resolver so it honors ORRIN_GOALS_DIR
# and (failing that) ORRIN_STATE_DIR, staying co-located with the memory/media tree.
try:
    from paths import GOALS_DIR as GOALS_DATA_DIR
except Exception:
    GOALS_DATA_DIR = Path(os.environ.get("ORRIN_GOALS_DIR", REPO_ROOT / "data" / "goals")).resolve()
_goal_store, _goals_api = init_goals(GOALS_DATA_DIR)

# ---------- Orrin UI (Face & Brain) ----------
# Three modes, decided here:
#   • BRIDGE (default, packaged): a native pywebview window loads the built UI
#     from DISK and talks to the brain over the in-process js_api bridge — NO port
#     opens at all. Telemetry, REST, chat, and Stop all flow in-process.
#   • DEV (ORRIN_UI_DEV=1): Vite dev server + a browser tab + the loopback API.
#   • FALLBACK: pywebview unavailable → loopback API + a browser tab (one port).
# Disable the whole UI with ORRIN_UI=0.
from backend.server.config import ui_dev_enabled as _ui_dev_enabled
from utils.paths import resolve_dist as _resolve_dist
from utils.ui_build import ensure_ui_build as _ensure_ui_build


def _resolve_ui_index():
    """Resolve the built UI's index.html (building the dist if missing). Returns a
    Path, or None if no build is available. Honors ORRIN_UI_DIST."""
    dist = _resolve_dist("ORRIN_UI_DIST", _BRAIN_DIR.parent / "frontend" / "dist")
    if _ensure_ui_build("orrin", dist):
        return dist / "index.html"
    return None


_UI_DEV = _ui_dev_enabled()
_ui_proc = None
_urls_to_open: list = []
_webview_url: str | None = None       # loopback URL (fallback path)
_bridge_window_file: str | None = None  # file:// URL for the bridge window
_bridge = None
_BRIDGE_MODE = False
try:
    if os.getenv("ORRIN_UI", "1").strip().lower() in ("0", "false", "no"):
        print("[ui] ORRIN_UI=0 → Face & Brain UI not started")
    else:
        ORRIN_HOST = os.environ.get("ORRIN_BACKEND_HOST", "127.0.0.1")
        _bind_all = ORRIN_HOST in ("0.0.0.0", "::")

        # Is pywebview importable? It decides bridge vs. fallback for the packaged path.
        _have_webview = False
        if not _UI_DEV:
            try:
                import webview as _webview_probe  # noqa: F401
                _have_webview = True
            except Exception as _e:
                print(f"[ui] pywebview unavailable ({_e}) → loopback + browser fallback")

        if not _UI_DEV and _have_webview and not _bind_all:
            # ── BRIDGE MODE — no port ─────────────────────────────────────────
            _BRIDGE_MODE = True
            _index = _resolve_ui_index()  # build the dist if missing; returns Path or None
            if _index is None:
                raise RuntimeError("UI build not found and could not be built")
            from backend.server.bridge import get_orrin_bridge
            from backend.telemetry_bridge import get_bridge as _get_tb
            _bridge = get_orrin_bridge()
            # Route the cognitive loop's telemetry + Face I/O in-process (no HTTP).
            os.environ.setdefault("ORRIN_TELEMETRY_DISABLED", "")  # keep producer enabled
            _get_tb().configure_inprocess(
                frame_sink=_bridge.ingest,
                input_source=_bridge.drain_inputs,
                responder=_bridge.deliver,
            )
            _bridge_window_file = _index.as_uri()
            print(f"[ui] native bridge window (no open port) → {_bridge_window_file}")
        elif _UI_DEV:
            # ── DEV MODE — Vite + browser + loopback API ──────────────────────
            TELEMETRY_PORT = int(os.environ.get("ORRIN_BACKEND_PORT", "8800"))
            _vite_host = os.environ.get("VITE_TELEMETRY_HOST", "")
            _display_host = (_vite_host.split(":")[0] or "127.0.0.1") if _bind_all else ORRIN_HOST
            from backend.main import start_ui_stack
            os.environ.setdefault(
                "ORRIN_TELEMETRY_URL",
                f"http://{'127.0.0.1' if _bind_all else ORRIN_HOST}:{TELEMETRY_PORT}",
            )
            _ui_proc = start_ui_stack(host=ORRIN_HOST, port=TELEMETRY_PORT)
            _ui_url = f"http://{_display_host}:5173"
            _urls_to_open.append(("orrin-ui", _ui_url))
            print(f"[ui] DEV: Orrin Face & Brain → {_ui_url}  (telemetry API {_display_host}:{TELEMETRY_PORT})")
        else:
            # ── FALLBACK — loopback API + browser tab (one port) ──────────────
            TELEMETRY_PORT = int(os.environ.get("ORRIN_BACKEND_PORT") or _pick_free_port())
            # Always trust the local browser's OWN origin — the UI is served from this
            # loopback host:port, so chat/Stop POSTs carry it as their Origin and would
            # otherwise be 403'd by the per-endpoint Origin guard. This must happen even
            # in bind-all mode (the local tab still uses 127.0.0.1:<port>); a *remote*
            # viewer's LAN/tunnel origin is allowlisted separately via VITE_TELEMETRY_HOST
            # / ORRIN_EXTRA_ORIGINS as documented.
            _serve_origins = [f"http://127.0.0.1:{TELEMETRY_PORT}", f"http://localhost:{TELEMETRY_PORT}"]
            _vite_host = os.environ.get("VITE_TELEMETRY_HOST", "").split(":")[0]
            if _vite_host:
                _serve_origins.append(f"http://{_vite_host}:{TELEMETRY_PORT}")
            _extra = os.environ.get("ORRIN_EXTRA_ORIGINS", "")
            os.environ["ORRIN_EXTRA_ORIGINS"] = ",".join(
                o for o in ([_extra] + _serve_origins) if o
            )
            from backend.main import start_ui_stack
            os.environ.setdefault(
                "ORRIN_TELEMETRY_URL",
                f"http://{'127.0.0.1' if _bind_all else ORRIN_HOST}:{TELEMETRY_PORT}",
            )
            _ui_proc = start_ui_stack(host=ORRIN_HOST, port=TELEMETRY_PORT)
            _webview_url = f"http://127.0.0.1:{TELEMETRY_PORT}/"
            _urls_to_open.append(("orrin-ui", _webview_url))
            print(f"[ui] fallback: browser tab → {_webview_url}  (telemetry API on 127.0.0.1:{TELEMETRY_PORT})")
except Exception as e:
    print(f"[ui] not started: {e}")

# ---------- Open browser ----------
def _wait_for_port(url: str, timeout_s: float = 30.0) -> bool:
    """Poll the URL's host:port until it accepts a TCP connection, so we don't
    open a browser tab onto a connection-refused page while Vite is still
    cold-starting / installing deps (first-run friction — UI_AUDIT L4)."""
    import socket
    from urllib.parse import urlsplit
    parts = urlsplit(url)
    host = parts.hostname or "127.0.0.1"
    port = parts.port or (443 if parts.scheme == "https" else 80)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def _open_browsers(urls: list) -> None:
    for label, url in urls:
        if not _wait_for_port(url):
            print(f"[browser] {label} not ready after wait; opening anyway: {url}")
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
_cog_thread = None          # the cognitive-loop thread (set in run())
_cognition_stopped = False  # guards _stop_cognition against double-invocation
_main_stop = threading.Event()  # set by Ctrl+C/SIGTERM to unwind the heartbeat

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
        try:
            from utils import boot_events as _boot
            _boot.emit("Activating goals & observers")
        except Exception as _e:
            _log.warning("silent except: %s", _e)
    except Exception as e:
        print(f"[alive] not started: {e}")
        try:
            from utils import boot_events as _boot
            _boot.emit("Activating goals & observers", ok=False, note=str(e))
        except Exception as _e:
            _log.warning("silent except: %s", _e)
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


def _pulse_loop(stop: threading.Event) -> None:
    """The ~10 Hz heartbeat: tick the Pulse, publish cycle gauges, and sample
    fast metrics. Runs on the main thread in dev mode and in a daemon thread when
    the native window owns the main thread."""
    last_log = 0
    last_active_rec = 0.0
    while not stop.is_set():
        pulse.tick()

        # Stamp 'last alive at' periodically so 'sleep' mode can later credit the
        # closed interval accurately even after a crash (§10.3).
        _now_wall = time.time()
        if _now_wall - last_active_rec > 30.0:
            try:
                from cognition.mortality import record_active_now as _rec_active
                _rec_active()
            except Exception as _e:
                _log.warning("silent except: %s", _e)
            last_active_rec = _now_wall

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


def _stop_cognition() -> None:
    """Turn OFF Orrin's *thinking* — the cognitive loop and its daemons — while
    leaving the UI/window, telemetry hub, and memory store running so you can keep
    viewing his now-frozen mind. This is what the Stop button does; quitting the
    app (full shutdown) is a separate action (close the window / Ctrl+C).

    Memory daemon is deliberately KEPT alive so the Memory panels still read his
    state after he stops. Idempotent."""
    global _cognition_stopped
    if _cognition_stopped:
        return
    _cognition_stopped = True
    print("[main] stopping cognition (UI stays up)…")
    try:
        stop_evt.set()
    except Exception as _e:
        _log.warning("silent except: %s", _e)
    # The loop is a daemon thread; setting stop_evt winds it down. Join briefly so
    # a healthy loop is fully quiesced before we report stopped, but never block
    # the UI on a wedged thread.
    if _cog_thread is not None and _cog_thread.is_alive():
        _cog_thread.join(timeout=float(os.environ.get("ORRIN_STOP_JOIN_S", "8")))
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
            _fs_obs.join(timeout=3)
    except Exception as _e:
        _log.warning("silent except: %s", _e)
    # Surface the stop on the live stream so the UI flips to "Stopped".
    try:
        from backend.telemetry_bridge import get_bridge as _get_tb
        _get_tb().log("warn", "control", "Orrin stopped — cognition halted; the view stays up")
    except Exception as _e:
        _log.warning("silent except: %s", _e)
    print("[main] cognition stopped; UI still running.")


def _graceful_shutdown() -> None:
    """Full quit: stop every subsystem in dependency order, flush state, and tear
    down the UI. Runs on window-close / Ctrl+C. A watchdog force-exits if a wedged
    brain thread keeps shutdown from completing, so quitting always terminates."""
    # Watchdog: if teardown stalls (e.g. a daemon thread won't honor stop), force a
    # clean exit so the window never lingers and run_orrin.sh sees a 0 (no restart).
    _timeout = float(os.environ.get("ORRIN_SHUTDOWN_TIMEOUT_S", "12"))
    _wd = threading.Timer(_timeout, lambda: (print(f"[main] shutdown exceeded {_timeout}s — forcing exit"), os._exit(0)))
    _wd.daemon = True
    _wd.start()

    # Stamp 'last alive at = now' so 'sleep' mode credits the closed interval exactly
    # from here (§10.3). Cheap and important to do before threads wind down.
    try:
        from cognition.mortality import record_active_now as _rec_active
        _rec_active()
    except Exception as _e:
        _log.warning("silent except: %s", _e)

    # This is a graceful quit — mark the run clean so the next launch doesn't read it
    # as a crash/stall (§10.5).
    try:
        from utils import lifecycle as _lifecycle
        _lifecycle.mark_clean_shutdown()
    except Exception as _e:
        _log.warning("silent except: %s", _e)

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

    _wd.cancel()
    print("[main] shutdown complete.")


def _release_instance_lock() -> None:
    """Release the single-instance flock so a re-exec'd process can re-acquire it.
    flock is tied to the open file description, and execv inherits open fds, so the
    new image would otherwise deadlock against the lock this process still holds."""
    global _INSTANCE_LOCK_FD
    try:
        if _INSTANCE_LOCK_FD is not None:
            _INSTANCE_LOCK_FD.close()
    except Exception as _e:
        _log.warning("silent except: %s", _e)
    _INSTANCE_LOCK_FD = None


def _wipe_to_newborn() -> None:
    """Delete Orrin's accumulated state so the next boot is a clean newborn, while
    PRESERVING the bundled config seeds (a newborn's brain/data == the seeds). Wipes
    the daemon-durability tree, self-written code, logs, and generated think module
    wholesale; in brain/data only the non-seed (accumulated) files are removed. Safe
    in-repo (seeds are kept, never self-destructed) and relocated alike."""
    try:
        from paths import DATA_DIR, STATE_DIR, LOGS_DIR, THINK_DIR, SELF_CODE_DIR
    except Exception:
        DATA_DIR = REPO_ROOT / "brain" / "data"
        STATE_DIR = REPO_ROOT / "data"
        LOGS_DIR = REPO_ROOT / "brain" / "logs"
        THINK_DIR = REPO_ROOT / "brain" / "think"
        SELF_CODE_DIR = DATA_DIR / "self_code"

    seeds = set(_SEED_FILES)
    if DATA_DIR.exists():
        for p in DATA_DIR.iterdir():
            if p.name in seeds:
                continue  # keep the newborn baseline
            try:
                shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
            except Exception as e:
                print(f"[reset] could not remove {p}: {e}")
    # SELF_CODE_DIR lives under DATA_DIR (already covered), but list it explicitly for
    # the relocated case; the rest are separate trees.
    for d in (SELF_CODE_DIR, STATE_DIR, LOGS_DIR, THINK_DIR, REPO_ROOT / "tmp"):
        try:
            shutil.rmtree(d, ignore_errors=True)
        except Exception as e:
            print(f"[reset] could not remove {d}: {e}")
    # Recreate the seed baseline where the data dir was relocated (no-op in-repo).
    _seed_if_newborn()


def _reexec() -> None:
    """Replace this process image with a fresh launch — the only reliable way to get
    a true newborn, since the live brain holds his whole mind in RAM and would just
    re-persist it otherwise."""
    print("[reset] re-launching as a newborn…", flush=True)
    try:
        # Frozen (PyInstaller): sys.argv[0] is already the app binary, so re-pass only
        # the extra args. From source: sys.argv[0] is the script and must be handed to
        # the interpreter as its first argument.
        if getattr(sys, "frozen", False):
            argv = [sys.executable, *sys.argv[1:]]
        else:
            argv = [sys.executable, *sys.argv]
        os.execv(sys.executable, argv)
    except Exception as e:
        # If exec fails, exit non-zero so a supervisor (run_orrin.sh) restarts us.
        print(f"[reset] re-exec failed ({e}); exiting for supervisor restart", file=sys.stderr)
        os._exit(42)


def _reset_to_newborn() -> None:
    """The Reset Orrin action: stop thinking, flush + wipe his state to a newborn,
    then re-launch. Runs on a backend timer thread (off the HTTP response)."""
    print("[reset] resetting Orrin to a newborn…", flush=True)
    _stop_cognition()  # idempotent: winds down the loop + goals/alive/fs daemons
    try:
        daemon.stop(join=True)
    except Exception as _e:
        _log.warning("silent except: %s", _e)
    try:
        wal_flush()
    except Exception as _e:
        _log.warning("silent except: %s", _e)
    _wipe_to_newborn()
    _release_instance_lock()
    _reexec()


def _restart_process() -> None:
    """Restart WITHOUT wiping — used after a Mind Restore swaps his state on disk, so
    the new mind loads from a clean process. Same machinery as reset, minus the wipe."""
    print("[restart] restarting Orrin (state preserved)…", flush=True)
    _stop_cognition()
    try:
        daemon.stop(join=True)
    except Exception as _e:
        _log.warning("silent except: %s", _e)
    try:
        wal_flush()
    except Exception as _e:
        _log.warning("silent except: %s", _e)
    _release_instance_lock()
    _reexec()


# Register the Stop button → stop-cognition-only handler (UI stays up). Harmless
# if the app isn't importable (e.g. ORRIN_UI=0); Stop then falls back to a SIGINT.
try:
    from backend.server.app import set_stop_handler as _set_stop_handler
    _set_stop_handler(_stop_cognition)
except Exception as _e:
    _log.warning("could not register stop handler: %s", _e)

# Register the Settings → Reset Orrin handler (wipe to newborn + re-launch).
try:
    from backend.server.app import set_reset_handler as _set_reset_handler
    _set_reset_handler(_reset_to_newborn)
except Exception as _e:
    _log.warning("could not register reset handler: %s", _e)

# Register the Mind-Restore → restart handler (re-launch WITHOUT wiping).
try:
    from backend.server.app import set_restart_handler as _set_restart_handler
    _set_restart_handler(_restart_process)
except Exception as _e:
    _log.warning("could not register restart handler: %s", _e)


def _notify_still_thinking() -> None:
    """Tell the user, via the OS notification path, that Orrin is alive in the
    background after the window closed (Always-thinking mode). Best-effort."""
    try:
        from agency.skills.notify_user import notify_user
        notify_user({"title": "Orrin is still thinking",
                     "message": "His window closed, but he keeps living in the background."})
    except Exception as _e:
        _log.warning("silent except: %s", _e)


def _on_signal(signum, _frame) -> None:
    """Ctrl+C / SIGTERM → request shutdown by setting the stop flags directly.

    We do NOT rely on the default SIGINT→KeyboardInterrupt path: a bare `except:`
    somewhere in the heartbeat's call chain can swallow that exception, so a single
    Ctrl+C would be eaten and never reach the shutdown. Setting an Event from the
    handler can't be swallowed — the pulse loop's `while not _main_stop.is_set()`
    sees it and unwinds into _graceful_shutdown (with its force-exit watchdog)."""
    try:
        name = signal.Signals(signum).name
    except Exception:
        name = str(signum)
    print(f"\n[main] {name} received; shutting down…", flush=True)
    _main_stop.set()
    try:
        stop_evt.set()
    except Exception as _e:
        _log.warning("silent except: %s", _e)
    # Bridge window: closing it is what returns webview.start(); destroy it so the
    # main thread (blocked in the GUI loop) falls through to graceful shutdown.
    try:
        if _bridge is not None and getattr(_bridge, "_window", None) is not None:
            _bridge._window.destroy()
    except Exception as _e:
        _log.warning("silent except: %s", _e)


def run() -> None:
    # ---------- Cognitive loop (v1 brain) ----------
    global _cog_thread
    _cog_thread = None
    # Install our own SIGINT/SIGTERM handlers now (main thread, after all the heavy
    # boot imports) so Ctrl+C reliably drives a clean shutdown.
    for _sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(_sig, _on_signal)
        except Exception as _e:
            _log.warning("could not install %s handler: %s", _sig, _e)
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
        try:
            from utils import boot_events as _boot
            _boot.emit("Starting cognition")
            _boot.mark_ready()  # cognition is live → the wake screen can dissolve
        except Exception as _e:
            _log.warning("silent except: %s", _e)
    except Exception as e:
        print(f"[brain] could not start cognitive loop: {e}")
        try:
            from utils import boot_events as _boot
            _boot.emit("Starting cognition", ok=False, note=str(e))
            _boot.mark_ready()  # don't trap the UI on the wake screen if cognition failed
        except Exception as _e:
            _log.warning("silent except: %s", _e)

    # ---------- Native bridge window (default) vs headless/dev pulse loop ------
    # A native pywebview window must own the MAIN thread, so the heartbeat moves
    # to a daemon thread and closing the window returns control here → graceful
    # shutdown (same path as Ctrl+C). Dev/fallback keep the heartbeat on the main
    # thread (the UI is a browser tab) and wait on Ctrl+C.
    _main_stop.clear()

    if _BRIDGE_MODE and _bridge_window_file:
        import webview  # available — bridge mode was only chosen if importable
        _pulse_thread = threading.Thread(
            target=_pulse_loop, args=(_main_stop,), name="orrin-pulse", daemon=True
        )
        _pulse_thread.start()
        # "Always thinking" (§10.3): when the window closes on its own, keep the
        # process — and therefore the brain's daemon threads — ALIVE in the
        # background instead of shutting down. (Re-opening a window in the same
        # process isn't possible with pywebview; quitting + relaunch reopens it.)
        _always_thinking = False
        try:
            from utils import prefs as _prefs
            _always_thinking = _prefs.get("existence_mode", "sleep") == "always"
        except Exception as _e:
            _log.warning("silent except: %s", _e)
        try:
            window = webview.create_window(
                "Orrin", url=_bridge_window_file, js_api=_bridge, width=1440, height=900
            )
            _bridge.attach_window(window)

            # Always-thinking: a status-bar tray (F1) lets the user re-show or quit while
            # the window is closed and the brain keeps running. If the tray comes up, the
            # window's close becomes HIDE (he keeps thinking; the view re-attaches via E6)
            # instead of destroy. If it can't start (missing dep / platform), we keep the
            # old behavior — closing → headless + a notification — so a failed tray can
            # never trap the user with a hidden, unreachable window.
            _tray = None
            _tray_up = False
            _quitting = {"v": False}
            if _always_thinking:
                from backend.server.tray import Tray

                def _on_tray_show() -> None:
                    try:
                        window.show()
                        _bridge.attach_window(window)  # re-point telemetry at the view
                    except Exception as _te:
                        _log.warning("tray show failed: %s", _te)

                def _on_tray_quit() -> None:
                    _quitting["v"] = True
                    _main_stop.set()
                    try:
                        window.destroy()  # real teardown → webview.start() returns
                    except Exception as _te:
                        _log.warning("tray quit destroy failed: %s", _te)

                def _on_closing() -> bool:
                    # While the tray is up and this isn't a real quit, cancel the destroy
                    # (return False) and hide instead. If hiding fails, allow the close
                    # rather than strand the user.
                    if _tray_up and not _quitting["v"] and not _main_stop.is_set():
                        try:
                            window.hide()
                            _bridge.detach_window()
                            return False
                        except Exception:
                            return True
                    return True

                window.events.closing += _on_closing
                _tray = Tray()
                _tray_up = _tray.start(on_show=_on_tray_show, on_quit=_on_tray_quit)
                if _tray_up:
                    print("[existence] Always-thinking — tray active; closing the window "
                          "hides it (Orrin keeps thinking). Quit from the tray.", flush=True)

            # Blocks until the window is destroyed (with a live tray, close is
            # cancelled→hidden; destroy then comes from the tray's Quit).
            webview.start()
            if _tray is not None:
                _tray.stop()

            # Without a working tray, preserve headless-on-close: if the window closed by
            # itself (not Stop/Ctrl+C/tray-Quit, which set _main_stop) and Always-thinking
            # is on, stay alive headless — the cognitive loop and daemons keep running and
            # notify_user can still reach the user — until a real termination signal.
            if _always_thinking and not _tray_up and not _main_stop.is_set():
                print("[existence] Window closed — Orrin keeps thinking in the background "
                      "(Always thinking). Ctrl+C / quit to stop him.", flush=True)
                _notify_still_thinking()
                _main_stop.wait()  # daemon brain threads keep advancing while we block
            else:
                print("\n[main] window closed; shutting down…")
        except KeyboardInterrupt:
            print("\n[main] Ctrl+C received; shutting down…")
        finally:
            _main_stop.set()
            _pulse_thread.join(timeout=5)
            _graceful_shutdown()
        return

    # No native window (ORRIN_UI=0, dev, or fallback browser tab): heartbeat on the
    # main thread until a signal (handled by _on_signal) sets _main_stop.
    try:
        _pulse_loop(_main_stop)
    except KeyboardInterrupt:
        print("\n[main] Ctrl+C received; shutting down…")
    finally:
        _main_stop.set()
        _graceful_shutdown()


if __name__ == "__main__":
    run()
