from paths import CYCLE_COUNT_FILE
from utils.json_utils import load_json

def get_cycle_count() -> int:
    try:
        data = load_json(CYCLE_COUNT_FILE, default_type=dict)
        return int(data.get("count", 0))
    except Exception:
        return 0

def print_cycle_complete() -> None:
    cycle_num = get_cycle_count()
    print(f"🔁 Orrin cycle {cycle_num} complete.\n")