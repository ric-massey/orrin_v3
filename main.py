# main.py
from __future__ import annotations

# --- Bootstrap sys.path BEFORE any brain-rooted import.
# First-party code is fully on the `brain.*` namespace (Phase 3), so the repo root is
# all main.py and the rest of the app need on the path. The legacy `brain/` entry —
# kept as a compatibility affordance for self-authored runtime code that emitted
# bare-name imports (`from utils.x import …`) — is gone: self-written code is now
# normalized onto `brain.*` at write time (agency/self_code.normalize_self_code_imports),
# so a generated module resolves with only the repo root present.
import sys
from pathlib import Path
_REPO_ROOT_STR = str(Path(__file__).resolve().parent)
_BRAIN_DIR = Path(__file__).resolve().parent / "brain"  # filesystem anchor (data seed, UI dist, think module) — NOT a sys.path entry
# Source runs only: in a FROZEN app (I3) these modules live in the PYZ and are served
# by PyInstaller's frozen importer — touching sys.path would shadow that importer.
if not getattr(sys, "frozen", False):
    if _REPO_ROOT_STR not in sys.path:
        sys.path.insert(0, _REPO_ROOT_STR)

# --- Per-user data home (Phase 3 / Group C) ---
# A packaged app can't write into its own (read-only) program folder, so route all
# of Orrin's state to the OS app-data dir. This MUST happen before any brain module
# (paths.py, memory.config) is imported, since they read these env vars at import.
#   • ORRIN_DATA_HOME set  → use it (explicit opt-in; also how tests exercise this)
#   • frozen (PyInstaller) → the OS per-user dir
#   • running from source  → leave unset → in-repo brain/data (unchanged for devs)
import os as _os_early
from brain.utils.paths import user_data_home as _user_data_home, apply_user_data_env as _apply_user_data_env
_data_home = _os_early.environ.get("ORRIN_DATA_HOME")
if _data_home:
    _apply_user_data_env(Path(_data_home))
elif getattr(sys, "frozen", False):
    _apply_user_data_env(_user_data_home())

# Point the ML stack at PRE-BUNDLED weights and go hard-offline (I2) — BEFORE any
# torch/sentence-transformers/spaCy import, so a frozen Orrin boots with zero network.
# No-op in a dev checkout (no bundle / no ORRIN_MODELS_DIR).
try:
    from brain.utils.model_assets import apply_offline_env as _apply_offline_env
    if _apply_offline_env():
        print("[boot] using bundled ML weights (offline mode)")
except ImportError:  # intentional: no bundle in a dev checkout — stay online
    pass

from brain.core.runtime_log import get_logger

import os
import inspect
import threading
import shutil

_log = get_logger(__name__)

# --- Crash capture nets ---
# faulthandler catches native (C-level) crashes from torch/spaCy/numpy on
# SIGSEGV/SIGABRT/SIGFPE — crashes no Python hook can see. The file handle must
# stay open for the process lifetime: closing it disarms the handler.
# Crash + uncaught-exception logging: native faulthandler to brain/logs/crash.log
# plus sys/threading excepthooks routing tracebacks to the runtime log at CRITICAL
# (a lost terminal/stderr otherwise swallows a daemon-thread death silently).
from runtime import crash_log as _crash_log
_crash_log.install()

# --- Boot config check (fast, no LLM call) ---
from runtime import preflight as _preflight
_preflight.boot_config_check()

# --- Single-instance guard ---
# Two Orrin processes writing the same brain/data files caused a corruption
# cascade (10k+ .corrupt files in hours). An exclusive advisory lock makes a
# second launch refuse to start, instead of fighting the first over the 8 GB and
# the shared JSON state. The fd is kept alive for the whole process lifetime.
from runtime import single_instance as _single_instance
_single_instance.acquire()

# --- Observability / watchdogs ---
from watchdogs import Pulse, start_watchdogs
from observability.metrics import serve_metrics

# --- Memory subsystem ---
from memory.health import snapshot as memory_snapshot  # rich snapshot

# --- Goals subsystem ---
from goals.model import Goal  # noqa: F401 (used via API/daemon)

try:
    from goals.registry import build_default_registry
    from goals.goals_daemon import GoalsDaemon
    _HAVE_GOALS_DAEMON = True
except Exception:
    _HAVE_GOALS_DAEMON = False

# --- Utils ---
from brain.utils.paths import compute_repo_root
from brain.utils.sys_events import record_event
from brain.utils.env import env_bool
from brain.utils.alive_brain import AliveBrain, start_fs_watcher
from brain.utils.memory_health import build_memory_health_provider
from brain.utils.metrics_sampling import build_fast_sampler
from brain.utils.goals_feed import init_goals

# --- Tamper guard (already existed as a util) ---
from brain.utils.tamper_guard import start_supervisor_tamper_guard

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

# ---- Forget-on-start (stateless boot) + first-launch seeding ----
from runtime import newborn as _newborn

FORGET_FLAG = os.getenv("ORRIN_FORGET_ON_START", "").strip().lower()
if FORGET_FLAG in ("1", "true", "yes"):
    print("[forget] ORRIN_FORGET_ON_START enabled → wiping persisted state before boot")
    _newborn.forget_everything()
else:
    print("[forget] ORRIN_FORGET_ON_START not set → keeping previous state")

# First-launch seeding: a fresh/relocated data dir boots a coherent newborn.
_newborn.seed_if_newborn()

# Schema migration spine (§10.7): reconcile the on-disk state version with this build
# BEFORE any subsystem reads state. Older → auto-export then migrate forward; newer
# (a downgrade) → refuse to load rather than corrupt the mind. A newborn just gets
# stamped at the current version. Runs after seeding so a fresh dir is already coherent.
try:
    from brain.utils.schema_migration import SchemaTooNewError as _SchemaTooNewError
except Exception:
    _SchemaTooNewError = None  # don't let an import hiccup crash boot before migration runs
try:
    from brain.utils import schema_migration as _schema
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
    from brain.paths import DATA_DIR as _DD_NB
    _is_newborn = not (_DD_NB / "long_memory.json").exists() and not (_DD_NB / "autobiography.json").exists()
    from brain.utils import boot_events as _boot
    _boot.set_newborn(_is_newborn)
except Exception as _e:
    _log.warning("silent except: %s", _e)

# Existence model (§10.3): apply non-secret prefs to the runtime BEFORE the brain
# rolls a lifespan or the cognitive loop reads its cadence. Explicit env always wins
# (dev override), so these use setdefault.
try:
    from brain.utils import prefs as _prefs
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
        from brain.cognition.runtime_lifetime import credit_sleep_since_last_active as _credit_sleep
        _credited = _credit_sleep()
        if _credited > 0:
            print(f"[existence] Sleep mode — credited {_credited / 3600:.1f}h of closed time (no life lost)")
except Exception as _e:
    _log.warning("silent except: %s", _e)

# Lifecycle tag (§10.5): record whether the previous run ended cleanly (→ tell death /
# crash-stall / normal apart on the next launch), then mark THIS run in-progress.
try:
    from brain.utils import lifecycle as _lifecycle
    _lifecycle.mark_running()
except Exception as _e:
    _log.warning("silent except: %s", _e)

# ---------- Memory subsystem ----------
# Store + daemon + AR6 WAL boot replay (recall survives restart) — runtime/memory_boot.py.
from runtime.memory_boot import start_memory as _start_memory
store, daemon = _start_memory()

# Boot sequence (§9.7) — emit each milestone AFTER it actually comes up, so the
# wake-up screen reflects real readiness. Best-effort; never let it break boot.
try:
    from brain.utils import boot_events as _boot
    _boot.emit("Loading memory")
except Exception as _e:
    _log.warning("silent except: %s", _e)

# Bound provider for UIs & brain
get_memory_health = build_memory_health_provider(daemon, store, memory_snapshot)

# ---------- Goals: store/API ----------
# Goals daemon durability dir. Use the shared resolver so it honors ORRIN_GOALS_DIR
# and (failing that) ORRIN_STATE_DIR, staying co-located with the memory/media tree.
try:
    from brain.paths import GOALS_DIR as GOALS_DATA_DIR
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
from backend.server.config import ui_dev_enabled as _ui_dev_enabled, open_browser_enabled as _open_browser_enabled
from runtime.ui_launch import resolve_ui_index as _resolve_ui_index

_UI_DEV = _ui_dev_enabled()
_ui_proc = None
_urls_to_open: list = []
_webview_url: str | None = None       # loopback URL (fallback path)
_bridge_window_file: str | None = None  # file:// URL for the bridge window
_bridge = None
_BRIDGE_MODE = False
try:
    if not env_bool("ORRIN_UI", True):
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
from runtime.ui_launch import open_browsers as _open_browsers  # noqa: E402

if _urls_to_open and _open_browser_enabled():
    _browser_thread = threading.Thread(
        target=_open_browsers,
        args=(_urls_to_open,),
        name="browser-opener",
        daemon=True,
    )
    _browser_thread.start()
elif _urls_to_open:
    # ORRIN_UI_OPEN=0 — headless/server run (e.g. the Docker static image): serve the
    # UI but don't try to open a browser. Print the URL so the operator can reach it.
    for _label, _url in _urls_to_open:
        print(f"[ui] {_label} ready (browser-open disabled): {_url}")

# ---------- Watchdogs ----------
pulse = Pulse()

# Resource providers + host/resource escalation callbacks + resource-floor config,
# built outside the coupled boot core (depends only on psutil/env/telemetry).
from runtime import watchdog_setup as _wd_setup
_wd_inputs = _wd_setup.build()

try:
    tup = start_watchdogs(
        pulse,
        per_key_limits={"llm_timeout": (10, 15.0)},
        get_memory_health=get_memory_health,
        memory_daemon=daemon,
        ns_sample_interval_s=0.2,
        ns_summary_interval_s=5.0,
        **_wd_inputs.kwargs,
    )
except TypeError:
    tup = start_watchdogs(
        pulse,
        per_key_limits={"llm_timeout": (10, 15.0)},
    )

(
    supervisor,
    detector,
    errors,
    liveness,
    lifespan,
    no_goals,
    mem_guard,
    host_guard,
    resource_floor_guard,
    repeat_guard,
    stop_evt,
) = tup

# --- Tamper guard: kill on any supervisor modification ---
try:
    extra_watch = []
    try:
        extra_watch.append(inspect.getfile(supervisor.__class__))
        trig = getattr(supervisor, "trigger", None)
        if callable(trig):
            func = getattr(trig, "__func__", trig)
            extra_watch.append(inspect.getfile(func))
    except Exception as _e:
        _log.warning("silent except: %s", _e)

    start_supervisor_tamper_guard(
        supervisor,
        period_s=float(os.environ.get("ORRIN_TAMPER_GUARD_PERIOD_S", "1.0")),
        extra_files=[p for p in set(extra_watch) if p],
        on_trip="exit",
    )
    print("[tamper-guard] active: supervisor integrity monitored")
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
    except Exception as exc:  # goals API unavailable — record, no goals for the brain view
        from brain.utils.failure_counter import record_failure
        record_failure("main._list_goals_for_brain", exc)
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

        # GoalsDaemon ctx hooks (runtime/goal_web_hooks.py): AR2 web hooks +
        # the emotion-state reader.
        from runtime.goal_web_hooks import goal_web_search as _goal_web_search
        from runtime.goal_web_hooks import goal_web_fetch as _goal_web_fetch
        from runtime.goal_web_hooks import get_emotional_state as _get_emotional_state

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
                # AR2 research-handler hooks. No "llm" hook on purpose: the LLM
                # is tool-only gated, and the handler's offline extractive memo
                # is the honest fallback.
                "web_search": _goal_web_search,
                "web_fetch": _goal_web_fetch,
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
            from brain.utils import boot_events as _boot
            _boot.emit("Activating goals & observers")
        except Exception as _e:
            _log.warning("silent except: %s", _e)
    except Exception as e:
        print(f"[alive] not started: {e}")
        try:
            from brain.utils import boot_events as _boot
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




# ---------- Runtime context + lifecycle stages (Phase 4B) ----------
# Boot is done. Gather the boot-produced state into the typed RuntimeContext the
# lifecycle/desktop stages run on, so they don't reach back into module globals.
from runtime.context import RuntimeContext
from runtime import lifecycle as _lifecycle_stage
from runtime import desktop as _desktop

_ctx = RuntimeContext(
    pulse=pulse,
    stop_evt=stop_evt,
    main_stop=threading.Event(),  # set by Ctrl+C/SIGTERM/window-close to unwind run()
    memory_daemon=daemon,
    goals_api=_goals_api,
    goals_daemon=_goals_daemon,
    alive=_alive,
    fs_obs=_fs_obs,
    ui_proc=_ui_proc,
    bridge=_bridge,
    bridge_mode=_BRIDGE_MODE,
    bridge_window_file=_bridge_window_file,
    wd_inputs=_wd_inputs,
    sample_metrics_fast=sample_metrics_fast,
    repo_root=REPO_ROOT,
)

# Register the UI control buttons against the context. Each is harmless if the
# app isn't importable (e.g. ORRIN_UI=0); Stop then falls back to a SIGINT.
# Stop → stop cognition only (UI stays up); Reset → wipe to newborn + re-launch;
# Mind-Restore → re-launch WITHOUT wiping.
try:
    from backend.server.app import set_stop_handler as _set_stop_handler
    _set_stop_handler(lambda: _lifecycle_stage.stop_cognition(_ctx))
except Exception as _e:
    _log.warning("could not register stop handler: %s", _e)

try:
    from backend.server.app import set_reset_handler as _set_reset_handler
    _set_reset_handler(lambda: _lifecycle_stage.reset_to_newborn(_ctx))
except Exception as _e:
    _log.warning("could not register reset handler: %s", _e)

try:
    from backend.server.app import set_restart_handler as _set_restart_handler
    _set_restart_handler(lambda: _lifecycle_stage.restart_process(_ctx))
except Exception as _e:
    _log.warning("could not register restart handler: %s", _e)


def run() -> None:
    """Foreground lifetime: cognition + the native window / headless heartbeat,
    returning into graceful shutdown on stop. The orchestration lives in
    runtime.desktop; this stays as the documented entrypoint."""
    _desktop.run(_ctx)


if __name__ == "__main__":
    run()
