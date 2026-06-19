"""
embodiment/setpoint_regulation.py

Tier 1 survival daemon — unconditional background monitoring.

Runs on its own thread every 30 seconds, completely independent of the
cognitive loop. Checks operational integrity and produces a health vector
that ORRIN_loop reads at the start of each cycle.

Design contract:
  • Monitoring is unconditional — it fires regardless of what the bandit
    selected or whether the cognitive loop is busy.
  • Detection only. The daemon flags problems; ORRIN_loop decides response.
  • Zero dependency on complex brain imports — only stdlib + pathlib + json
    so this cannot cause circular imports or fail due to a broken module.

Alert severity:
  'warning'  — inject as a strong raw_signal; the signal_router/bandit factor it in
  'critical' — inject at max signal strength + set context flag; main loop
               may override the bandit's choice entirely

Checks implemented (based on operational health priorities):
  1. resource_deficit_critical     — resource_deficit > 0.92; cognitive capacity is depleted
  2. error_spike          — error_log.txt grew rapidly; something is failing
  3. long_memory_growth   — long_memory.json > 1500 entries; consolidation needed
  4. working_memory_bloat — working_memory.json > 50 entries; overflow risk
  5. self_model_hollow    — core_values empty; identity has nothing to protect
  6. data_corruption      — a critical file fails to parse; integrity at risk
"""
from __future__ import annotations
from core.runtime_log import get_logger

import json
import threading
import time
from typing import Any, Dict, List, Optional
from utils.failure_counter import record_failure
_log = get_logger(__name__)

_SAMPLE_INTERVAL   = 30    # seconds between health checks
_RESOURCE_DEFICIT_WARN      = 0.88
_RESOURCE_DEFICIT_CRITICAL  = 0.94
_LM_WARN_ENTRIES   = 1500  # long_memory entries → consolidation signal
_WM_BLOAT_ENTRIES  = 50    # working_memory entries → overflow warning
_ERROR_SIZE_WARN   = 40_000  # bytes — error_log grew this much since last check

from paths import DATA_DIR as _DATA_DIR, LOGS_DIR as _LOGS_DIR

# ── Singleton ────────────────────────────────────────────────────────────────

_daemon: Optional["HomeostasisDaemon"] = None
_daemon_lock = threading.Lock()


def start() -> "HomeostasisDaemon":
    global _daemon
    with _daemon_lock:
        if _daemon is None:
            _daemon = HomeostasisDaemon()
            _daemon.start()
    return _daemon


def get_state() -> Dict[str, Any]:
    """Return the latest health snapshot. Safe to call from any thread."""
    with _daemon_lock:
        if _daemon is None:
            return {"health_score": 1.0, "alerts": []}
    return _daemon.get_state()


# ── Daemon ───────────────────────────────────────────────────────────────────

class HomeostasisDaemon:
    def __init__(self) -> None:
        self._state: Dict[str, Any] = {"health_score": 1.0, "alerts": []}
        self._lock  = threading.Lock()
        self._thread = threading.Thread(
            target=self._run, name="orrin-setpoint_regulation", daemon=True
        )
        self._last_error_size: int = 0

    def start(self) -> None:
        self._thread.start()

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._state)

    # ── Background loop ──────────────────────────────────────────────────────

    def _run(self) -> None:
        time.sleep(5)  # let the main process finish booting
        while True:
            try:
                state = self._check()
                with self._lock:
                    self._state = state
            except Exception as _e:
                record_failure("setpoint_regulation.HomeostasisDaemon._run", _e)
            time.sleep(_SAMPLE_INTERVAL)

    def _check(self) -> Dict[str, Any]:
        alerts: List[Dict[str, Any]] = []
        penalty = 0.0

        # ── 1. resource_deficit ────────────────────────────────────────────────────────
        try:
            es = self._read_json("affect_state.json")
            if isinstance(es, dict):
                core = es.get("core_signals") or es
                resource_deficit = float(core.get("resource_deficit") or es.get("resource_deficit") or 0.0)
                if resource_deficit >= _RESOURCE_DEFICIT_CRITICAL:
                    alerts.append({
                        "id":          "resource_deficit_critical",
                        "severity":    "critical",
                        "description": (
                            f"resource_deficit is critical ({resource_deficit:.2f}). Cognitive capacity severely "
                            "depleted. Rest, lighter functions, or energy recovery needed."
                        ),
                        "tags":        ["resource_deficit", "rest", "recovery", "internal"],
                        "suggested_fn": "update_affect_state",
                    })
                    penalty += 0.35
                elif resource_deficit >= _RESOURCE_DEFICIT_WARN:
                    alerts.append({
                        "id":          "resource_deficit_high",
                        "severity":    "warning",
                        "description": (
                            f"resource_deficit is elevated ({resource_deficit:.2f}). Prefer lighter cognitive "
                            "functions and avoid compute-heavy operations."
                        ),
                        "tags":        ["resource_deficit", "low_energy", "internal"],
                        "suggested_fn": "update_affect_state",
                    })
                    penalty += 0.15
        except Exception as _e:
            record_failure("setpoint_regulation.HomeostasisDaemon._check", _e)

        # ── 2. Error spike ────────────────────────────────────────────────────
        try:
            err_paths = [
                _DATA_DIR / "error_log.txt",
                _LOGS_DIR / "error_log.txt",
            ]
            for err_path in err_paths:
                if err_path.exists():
                    size = err_path.stat().st_size
                    growth = size - self._last_error_size
                    if self._last_error_size > 0 and growth > _ERROR_SIZE_WARN:
                        alerts.append({
                            "id":          "error_spike",
                            "severity":    "warning",
                            "description": (
                                f"Error log grew by {growth // 1024}KB in the last 30s. "
                                "Something is failing repeatedly. Consider reflect_on_cognition_rhythm."
                            ),
                            "tags":        ["error", "repair", "instability"],
                            "suggested_fn": "reflect_on_cognition_rhythm",
                        })
                        penalty += 0.20
                    self._last_error_size = size
                    break
        except Exception as _e:
            record_failure("setpoint_regulation.HomeostasisDaemon._check.2", _e)

        # ── 3. Long-memory growth ─────────────────────────────────────────────
        try:
            lm = self._read_json("long_memory.json")
            if isinstance(lm, list) and len(lm) > _LM_WARN_ENTRIES:
                alerts.append({
                    "id":          "long_memory_growth",
                    "severity":    "warning",
                    "description": (
                        f"Long-memory has {len(lm)} entries (threshold: {_LM_WARN_ENTRIES}). "
                        "Consolidation needed — run_forgetting_cycle or run_rule_compression."
                    ),
                    "tags":        ["memory", "consolidation", "maintenance"],
                    "suggested_fn": "run_forgetting_cycle",
                })
                penalty += 0.10
        except Exception as _e:
            record_failure("setpoint_regulation.HomeostasisDaemon._check.3", _e)

        # ── 4. Working-memory bloat ───────────────────────────────────────────
        # Check both entry count AND file size. The file-size check is the
        # critical one — 30MB+ files cause REAPER kills regardless of entry count.
        try:
            wm_path = _DATA_DIR / "working_memory.json"
            wm_bytes = wm_path.stat().st_size if wm_path.exists() else 0
            if wm_bytes > 500_000:  # 500 KB — file has become unreasonably large
                alerts.append({
                    "id":          "working_memory_file_bloat",
                    "severity":    "critical",
                    "description": (
                        f"working_memory.json is {wm_bytes // 1024}KB — "
                        "large embeddings or nested chunks are bloating the file. "
                        "Cycle times will spike and REAPER may kill. metacog_flush recommended."
                    ),
                    "tags":        ["memory", "performance", "reaper_risk"],
                    "suggested_fn": "metacog_flush",
                })
                penalty += 0.30
            else:
                wm = self._read_json("working_memory.json")
                if isinstance(wm, list) and len(wm) > _WM_BLOAT_ENTRIES:
                    alerts.append({
                        "id":          "working_memory_bloat",
                        "severity":    "warning",
                        "description": (
                            f"Working memory has {len(wm)} entries (threshold: {_WM_BLOAT_ENTRIES}). "
                            "Overflow risk — metacog_flush recommended."
                        ),
                        "tags":        ["memory", "overflow", "maintenance"],
                        "suggested_fn": "metacog_flush",
                    })
                    penalty += 0.08
        except Exception as _e:
            record_failure("setpoint_regulation.HomeostasisDaemon._check.4", _e)

        # ── 5. Self-model hollow ──────────────────────────────────────────────
        try:
            sm = self._read_json("self_model.json")
            if isinstance(sm, dict):
                values = sm.get("core_values") or []
                if not values:
                    alerts.append({
                        "id":          "self_model_hollow",
                        "severity":    "warning",
                        "description": (
                            "Self-model has no core values. Identity is ungrounded — "
                            "nothing to protect or grow toward. narrative_update recommended."
                        ),
                        "tags":        ["identity", "self_model", "values", "internal"],
                        "suggested_fn": "narrative_update",
                    })
                    penalty += 0.12
        except Exception as _e:
            record_failure("setpoint_regulation.HomeostasisDaemon._check.5", _e)

        # ── 6. Data corruption ────────────────────────────────────────────────
        for fname in ("long_memory.json", "self_model.json", "cognitive_functions.json"):
            try:
                self._read_json(fname)
            except Exception:
                alerts.append({
                    "id":          f"corruption_{fname}",
                    "severity":    "critical",
                    "description": (
                        f"{fname} failed to parse — possible data corruption. "
                        "reflect_on_cognition_rhythm or manual inspection needed."
                    ),
                    "tags":        ["corruption", "repair", "critical", "integrity"],
                    "suggested_fn": "reflect_on_cognition_rhythm",
                })
                penalty += 0.40

        health_score = max(0.0, min(1.0, 1.0 - penalty))
        return {
            "health_score": round(health_score, 3),
            "alerts":       alerts,
            "sampled_at":   time.time(),
        }

    def _read_json(self, fname: str) -> Any:
        p = _DATA_DIR / fname
        with open(p, encoding="utf-8") as f:
            return json.load(f)
