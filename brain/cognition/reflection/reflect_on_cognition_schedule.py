from core.runtime_log import get_logger
import json

from cog_memory.working_memory import update_working_memory
from utils.json_utils import save_json
from utils.log import log_error, log_private
from utils.log_reflection import log_reflection
from utils.load_utils import load_all_known_json
from brain.paths import COGN_SCHEDULE_FILE
from utils.failure_counter import record_failure
_log = get_logger(__name__)


def reflect_on_cognition_schedule():
    """
    Adjust Orrin's cognitive rhythm using pure statistical analysis +
    symbolic self-model hints.  No LLM calls — data drives decisions.
    """
    try:
        data          = load_all_known_json()
        stat_schedule = dict(data.get("cognition_schedule", {}) or {})
        history       = [h for h in data.get("cognition_history", []) if isinstance(h, dict)][-50:]
        old_schedule  = dict(stat_schedule)
        protected     = {"persistent_drive_loop", "choose_next_cognition"}
        reflection_log: list = []

        # === Step 1: Pure statistical rebalancing (symbolic, no LLM) ===
        from symbolic.symbolic_cognition import rebalance_schedule as _rb
        result = _rb(stat_schedule, history)
        for fn, new_w in result["changes"].items():
            if fn not in protected:
                stat_schedule[fn] = new_w
        if result["summary"]:
            reflection_log.append(result["summary"])

        # === Step 2: Symbolic self-improvement / self-model hints ===
        try:
            from symbolic.self_improvement import get_improvement_history as _gih
            from symbolic.symbolic_reflection import symbolic_first_reflection as _sfr
            _proposals  = [p for e in _gih(n=3) for p in e.get("proposals", [])]
            _sym = _sfr("cognition_schedule", context=None,
                        data={"proposals": _proposals, "schedule": stat_schedule})
            if _sym:
                log_private(f"[symbolic] Schedule ({_sym['source']}): {_sym['text'][:80]}")
                t = _sym["text"].lower()
                if "weak" in t or "tighten" in t:
                    k = "reflect_on_self_beliefs"
                    if k not in protected:
                        stat_schedule[k] = min(stat_schedule.get(k, 4) + 1, 8)
                        reflection_log.append(f"↑ {k} (symbolic tighten hint)")
                if "improve" in t or "loosen" in t:
                    k = "dream"
                    if k not in protected:
                        stat_schedule[k] = min(stat_schedule.get(k, 6) + 1, 12)
                        reflection_log.append(f"↑ {k} (symbolic loosen hint)")
        except Exception as _e:
            record_failure("reflect_on_cognition_schedule.reflect_on_cognition_schedule", _e)

        # === Step 3: Save and log ===
        save_json(COGN_SCHEDULE_FILE, stat_schedule)
        log_private("Cognition schedule updated (symbolic).\n" + "\n".join(reflection_log))
        log_reflection(f"Cognition schedule: {' '.join(reflection_log).strip()}")

        diff = {
            k: (old_schedule.get(k), stat_schedule[k])
            for k in set(old_schedule) | set(stat_schedule)
            if old_schedule.get(k) != stat_schedule.get(k)
        }
        if diff:
            log_private(f"Schedule diff:\n{json.dumps(diff, indent=2)}")
            update_working_memory("Cognition schedule updated via symbolic rebalancing.")
        else:
            update_working_memory("No changes to cognition schedule — data supports current weights.")

    except Exception as e:
        log_error(f"reflect_on_cognition_schedule ERROR: {e}")
        update_working_memory("⚠️ Cognition schedule reflection failed.")
