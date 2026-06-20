# brain/cognition/dreaming/episode_replay.py
# Hippocampal replay: scan cognition history for high-reward sequences and
# strengthen bandit weights for those function pairs. Also extracts repeating
# high-reward pairs into function_chains.json for the chaining bonus.
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Any

from utils.json_utils import load_json, save_json
from utils.log import log_activity, log_private

try:
    from brain.paths import COGNITION_HISTORY_FILE, DATA_DIR
    _CHAINS_PATH = DATA_DIR / "function_chains.json"
except Exception:
    COGNITION_HISTORY_FILE = Path(__file__).resolve().parents[2] / "data" / "cognition_history.json"
    _CHAINS_PATH = Path(__file__).resolve().parents[2] / "data" / "function_chains.json"

_REWARD_THRESHOLD = 0.65   # minimum cycle reward to count as "good"
_WINDOW_SIZE      = 3      # consecutive cycles that form a replay episode
_MIN_PAIR_COUNT   = 2      # how many times a pair must appear to be chained
_REPLAY_LR        = 0.04   # learning rate for replay updates (softer than live)


def run_episode_replay(context: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Hippocampal-style replay during dream cycle.

    1. Load cognition_history.json (list of {choice, reward, is_agentic, timestamp}).
    2. Slide a window of _WINDOW_SIZE cycles. When mean reward > _REWARD_THRESHOLD,
       it's a high-reward episode.
    3. For each episode, call contextual_bandit.update() for each function in the
       sequence with a discounted replay reward (backward propagation: earlier
       functions get slightly less credit).
    4. Extract all consecutive pairs from all high-reward windows. Pairs that
       appear ≥ _MIN_PAIR_COUNT times are written to function_chains.json so
       select_function can apply a chain bonus.

    Returns a summary dict for dream_cycle logging.
    """
    context = context or {}

    history: List[Dict] = load_json(COGNITION_HISTORY_FILE, default_type=list) or []
    if not isinstance(history, list) or len(history) < _WINDOW_SIZE:
        return {"episodes": 0, "pairs_extracted": 0, "skipped": True, "reason": "insufficient_history"}

    # --- Find high-reward windows ---
    high_reward_windows: List[List[Dict]] = []
    for i in range(len(history) - _WINDOW_SIZE + 1):
        window = history[i: i + _WINDOW_SIZE]
        rewards = [float(c.get("reward", 0.0) or 0.0) for c in window]
        if len(rewards) >= _WINDOW_SIZE and (sum(rewards) / len(rewards)) >= _REWARD_THRESHOLD:
            high_reward_windows.append(window)

    if not high_reward_windows:
        return {"episodes": 0, "pairs_extracted": 0, "skipped": False}

    # --- Replay: strengthen bandit weights for each high-reward episode ---
    try:
        from think.bandit import contextual_bandit as _cb
        features = {"replay": 1.0, "__bias__": 1.0}
        for window in high_reward_windows:
            rewards = [float(c.get("reward", 0.0) or 0.0) for c in window]
            mean_r = sum(rewards) / len(rewards)
            for idx, cycle in enumerate(window):
                fn = str(cycle.get("choice") or "")
                if not fn:
                    continue
                # Earlier in the sequence → slightly less credit (temporal discount)
                discount = 0.9 ** (len(window) - 1 - idx)
                replay_r = mean_r * discount
                _cb.update(fn, features, reward=replay_r, lr=_REPLAY_LR)
    except Exception as e:
        log_activity(f"[episode_replay] bandit update skipped: {e}")

    # --- Extract pair frequencies from high-reward windows ---
    pair_counts: Dict[str, int] = {}
    for window in high_reward_windows:
        fns = [str(c.get("choice") or "") for c in window if c.get("choice")]
        for j in range(len(fns) - 1):
            if fns[j] and fns[j + 1]:
                key = f"{fns[j]}→{fns[j+1]}"
                pair_counts[key] = pair_counts.get(key, 0) + 1

    # --- Merge strong pairs into function_chains.json ---
    chains: Dict[str, Any] = load_json(_CHAINS_PATH, default_type=dict) or {}
    if not isinstance(chains, dict):
        chains = {}

    new_pairs = 0
    for pair_key, count in pair_counts.items():
        if count < _MIN_PAIR_COUNT:
            continue
        predecessor, successor = pair_key.split("→", 1)
        entry = chains.get(predecessor, {})
        if not isinstance(entry, dict):
            entry = {}
        existing_count = int(entry.get(successor, {}).get("count", 0) if isinstance(entry.get(successor), dict) else 0)
        entry[successor] = {
            "count": max(existing_count, count),
            "bonus": round(min(0.30, 0.05 * max(existing_count, count)), 3),
        }
        chains[predecessor] = entry
        if existing_count == 0:
            new_pairs += 1

    try:
        save_json(_CHAINS_PATH, chains)
    except Exception as e:
        log_activity(f"[episode_replay] chains save failed: {e}")

    log_activity(
        f"[episode_replay] {len(high_reward_windows)} episode(s) replayed, "
        f"{new_pairs} new chain pair(s) extracted."
    )
    log_private(f"[episode_replay] pair_counts={pair_counts}")

    return {
        "episodes": len(high_reward_windows),
        "pairs_extracted": new_pairs,
        "total_chain_keys": len(chains),
    }
