# brain/control_signals/affect_learning.py
#
# Associative learning: maps affect signals to cognitive functions over time —
# for each dominant signal, how well each function has paid when run under it.
from brain.core.runtime_log import get_logger
from brain.paths import SIGNAL_FUNCTION_MAP_FILE
from brain.utils.json_utils import load_json, save_json
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

# F3 (learning investigation, 2026-10-17). Each entry is the running average
# reward of running that function while that signal was dominant — a value, on
# the reward's own scale, that a failure LOWERS. The old rule mixed two units:
# it decayed counts, added the reward floored at +0.1 (so a failure still
# strengthened the link), pruned every other entry under a count of 2, then
# L1-normalized to shares under 0.5 — which no entry could ever lift back over
# 2. One update left only the function just run: Run 13 died with a single
# function per signal, `impasse_signal → fetch_and_read: 0.1` among them, and
# the selector gives a singleton full weight. The A4.2 share cap
# (`_bound_coupling_shares`) went with it: it bounded counts that grew without
# limit, and an average of rewards in [-1, 1] cannot.
EMA_ALPHA = 0.2                  # weight of the newest outcome
MAX_ASSOCIATIONS_PER_EMOTION = 20  # most functions remembered per signal


def update_signal_function_map(emotion: str, function_name: str, reward_signal=None):
    """Fold one outcome into (emotion -> function): the reward the function earned
    when it ran under that dominant signal. No reward, no update — an association
    is learned from outcomes, never from having happened."""
    if not emotion or not function_name or reward_signal is None:
        return
    try:
        r = max(-1.0, min(1.0, float(reward_signal)))
    except (TypeError, ValueError) as _e:
        record_failure("affect_learning.update_signal_function_map", _e)
        return

    emotion_key = str(emotion).strip().lower()
    fn_key = str(function_name).strip()

    raw_map = load_json(SIGNAL_FUNCTION_MAP_FILE, default_type=dict)
    if not isinstance(raw_map, dict):
        raw_map = {}
    entries = raw_map.get(emotion_key)
    if not isinstance(entries, dict):
        entries = {}

    prev = entries.get(fn_key)
    if isinstance(prev, (int, float)):
        entries[fn_key] = round(float(prev) + EMA_ALPHA * (r - float(prev)), 6)
    else:
        entries[fn_key] = round(r, 6)  # first outcome is the estimate

    # Full: forget the lowest-valued other entry. Values share one scale, so the
    # least useful association is the one dropped, never the one just learned.
    while len(entries) > MAX_ASSOCIATIONS_PER_EMOTION:
        worst = min((k for k in entries if k != fn_key),
                    key=lambda k: float(entries[k]) if isinstance(entries[k], (int, float)) else -2.0)
        entries.pop(worst)

    raw_map[emotion_key] = entries
    save_json(SIGNAL_FUNCTION_MAP_FILE, raw_map)
    return entries
