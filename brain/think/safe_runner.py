from __future__ import annotations
from core.runtime_log import get_logger

import os
import shutil
import traceback
from pathlib import Path
from typing import Any, Dict, Tuple, Callable

from utils.events import emit_event, ERROR, DECISION
from utils.log import log_error, log_activity
from paths import THINK_DIR, THINK_MODULE_PY 
from utils.timeutils import now_iso_z
from utils.failure_counter import record_failure
_log = get_logger(__name__)

THINK_FILE: Path = THINK_MODULE_PY
THINK_BACKUP: Path = THINK_DIR / "think_module.py.bak"

def safe_step(context: Dict[str, Any], runner: Callable[[Dict[str, Any]], Any]) -> Tuple[bool, Dict[str, Any]]:
    """
    Run `runner(context)` safely. On exception:
      - emit an ERROR event with full traceback
      - attempt rollback of think_module.py from .bak (if present) atomically
      - emit a DECISION event indicating rollback
    Returns (ok, payload). On success, payload is the runner's dict (or {"result": val});
    on failure, payload includes {"error", "rolled_back", "needs_reload"}.
    """
    try:
        out = runner(context)
        return True, out if isinstance(out, dict) else {"result": out}
    except Exception:
        tb = traceback.format_exc()
        emit_event(ERROR, {"where": "safe_step", "err": tb, "ts": now_iso_z()})
        log_error(f"[safe_step] Crash:\n{tb}")

        rolled = False
        needs_reload = False

        try:
            THINK_FILE.parent.mkdir(parents=True, exist_ok=True)
        except Exception as _e:
            # not fatal; continue to rollback attempt
            record_failure("safe_runner.safe_step", _e)

        if THINK_BACKUP.exists():
            try:
                # Copy backup to a temp file in the same dir, then atomically replace
                tmp_target = THINK_FILE.with_suffix(".py.tmp")
                shutil.copy2(THINK_BACKUP, tmp_target)
                os.replace(tmp_target, THINK_FILE)
                rolled = True
                needs_reload = True
                log_activity("[safe_step] Rolled back think_module.py from backup.")
                emit_event(DECISION, {"rollback": True, "file": str(THINK_FILE), "ts": now_iso_z()})
            except Exception:
                rb_tb = traceback.format_exc()
                log_error(f"[safe_step] Rollback failed:\n{rb_tb}")
                emit_event(ERROR, {"where": "safe_step.rollback", "err": rb_tb, "ts": now_iso_z()})
        else:
            log_activity("[safe_step] No backup found; skipping rollback.")

        return False, {"error": tb, "rolled_back": rolled, "needs_reload": needs_reload}