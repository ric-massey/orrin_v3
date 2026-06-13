from datetime import datetime, timezone
from utils.log import log_error
from utils.json_utils import load_json, save_json
from utils.timeutils import now_iso_z
from paths import LAST_ACTIVE_FILE  # pathlib.Path

def update_last_active():
    try:
        save_json(LAST_ACTIVE_FILE, {"last": now_iso_z()})
    except Exception as e:
        log_error(f"⚠️ Failed to update last active timestamp: {e}")


def get_time_since_last_active() -> float:
    now = datetime.now(timezone.utc)

    if not LAST_ACTIVE_FILE.exists():
        return 0.0

    try:
        data = load_json(LAST_ACTIVE_FILE, default_type=dict)
        last_str = data.get("last")
        if not last_str or not isinstance(last_str, str):
            return 0.0

        # tolerate Z-suffix
        last_dt = datetime.fromisoformat(last_str.replace("Z", "+00:00"))
        # ensure tz-aware
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)

        delta = now - last_dt
        return max(0.0, float(delta.total_seconds()))
    except Exception as e:
        log_error(f"⚠️ Failed to calculate time since last active: {e}")
        return 0.0