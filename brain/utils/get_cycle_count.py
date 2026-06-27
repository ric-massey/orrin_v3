from brain.paths import CYCLE_COUNT_FILE
from brain.utils.json_utils import load_json

def get_cycle_count() -> int:
    try:
        data = load_json(CYCLE_COUNT_FILE, default_type=dict)
        return int(data.get("count", 0))
    except (OSError, ValueError, TypeError, AttributeError):  # intentional: missing/malformed cycle file → 0
        return 0