"""
utils/trace_buffer.py

High-value interaction trace collector — the first step toward real learning.

Collects traces that are candidates for fine-tuning, RLHF, or LoRA adaptation.
A trace is a (prompt, response, outcome) triple where outcome is measured by
reward signals, not LLM self-evaluation.

Quality gates (trace is only buffered when ALL pass):
  - outcome_score >= _MIN_OUTCOME  (reward signal confirms this was good)
  - response length >= _MIN_RESPONSE_LEN  (not a trivial output)
  - not a pure introspection cycle  (no user was involved = weak ground truth)

The buffer is written to data/trace_buffer.jsonl, capped at _MAX_TRACES entries.
Periodically flushed by ORRIN_loop. Format is compatible with OpenAI fine-tune
JSONL (messages array) and with HuggingFace TRL's SFTTrainer.

To use for fine-tuning:
  python -c "from utils.trace_buffer import export_for_training; export_for_training()"
  → writes data/training_export.jsonl in chat-completion format
"""
from __future__ import annotations
from brain.core.runtime_log import get_logger

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

_LOCK = threading.Lock()
_MIN_OUTCOME = 0.55       # minimum normalized reward to buffer a trace
_MIN_RESPONSE_LEN = 40    # minimum response characters
_MAX_TRACES = 2000        # rolling cap — oldest are evicted when exceeded
_FLUSH_EVERY_N = 10       # write to disk every N buffered traces

_buffer: List[Dict[str, Any]] = []
_unflushed: int = 0


def _data_dir() -> Path:
    try:
        from brain.paths import DATA_DIR
        return DATA_DIR
    except Exception:
        return Path(__file__).resolve().parent.parent / "data"


def _trace_file() -> Path:
    return _data_dir() / "trace_buffer.jsonl"


def _export_file() -> Path:
    return _data_dir() / "training_export.jsonl"


# ── Quality gates ─────────────────────────────────────────────────────────────

def _passes_quality_gate(
    user_input: str,
    response: str,
    outcome_score: float,
) -> bool:
    if outcome_score < _MIN_OUTCOME:
        return False
    if len(response.strip()) < _MIN_RESPONSE_LEN:
        return False
    if not user_input or not user_input.strip():
        return False
    return True


# ── Public API ────────────────────────────────────────────────────────────────

def record_trace(
    user_input: str,
    system_prompt: str,
    response: str,
    outcome_score: float,
    context_snapshot: Optional[Dict[str, Any]] = None,
    fn_name: str = "",
) -> bool:
    """
    Attempt to buffer a high-value trace.
    Returns True if the trace passed quality gates and was buffered.

    outcome_score: normalized reward in [0, 1]. Use the reward_trace
    actual_reward value from the most recent finalize_cycle call.
    """
    global _unflushed

    if not _passes_quality_gate(user_input, response, outcome_score):
        return False

    # Extract minimal context snapshot to keep traces compact
    ctx = context_snapshot or {}
    emo = ctx.get("affect_state") or {}
    core = emo.get("core_signals") or emo
    dominant_emotion = ""
    try:
        dominant_emotion = max(
            {k: float(v) for k, v in core.items() if isinstance(v, (int, float))},
            key=lambda k: core[k],
            default="",
        )
    except Exception as _e:
        record_failure("trace_buffer.record_trace", _e)

    goal = ctx.get("committed_goal") or {}
    goal_title = goal.get("title", "") if isinstance(goal, dict) else ""

    trace = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "fn": fn_name,
        "outcome": round(float(outcome_score), 4),
        "dominant_affect": dominant_emotion,
        "goal": goal_title[:60],
        "messages": [
            {"role": "system",    "content": system_prompt[:800] if system_prompt else "You are Orrin."},
            {"role": "user",      "content": user_input[:600]},
            {"role": "assistant", "content": response[:800]},
        ],
    }

    with _LOCK:
        _buffer.append(trace)
        _unflushed += 1
        if len(_buffer) > _MAX_TRACES:
            _buffer.pop(0)

        if _unflushed >= _FLUSH_EVERY_N:
            _flush_to_disk()
            _unflushed = 0

    return True


def _flush_to_disk() -> None:
    """Append buffered traces to JSONL file. Must be called under _LOCK."""
    if not _buffer:
        return
    try:
        path = _trace_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            for trace in _buffer[-_FLUSH_EVERY_N:]:
                f.write(json.dumps(trace, ensure_ascii=False) + "\n")
    except Exception as _e:
        record_failure("trace_buffer._flush_to_disk", _e)


def flush_all() -> int:
    """Force-flush all buffered traces to disk. Returns count written."""
    with _LOCK:
        if not _buffer:
            return 0
        try:
            path = _trace_file()
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                for trace in _buffer:
                    f.write(json.dumps(trace, ensure_ascii=False) + "\n")
            count = len(_buffer)
            _buffer.clear()
            return count
        except Exception:
            return 0


def get_stats() -> Dict[str, Any]:
    """Return current buffer statistics."""
    with _LOCK:
        try:
            path = _trace_file()
            disk_count = sum(1 for _ in open(path, encoding="utf-8")) if path.exists() else 0
        except Exception:
            disk_count = 0
        return {
            "buffer_size": len(_buffer),
            "disk_traces": disk_count,
            "total": len(_buffer) + disk_count,
        }


def export_for_training(min_outcome: float = _MIN_OUTCOME) -> int:
    """
    Export traces from disk buffer to training_export.jsonl in OpenAI
    fine-tune format. Returns the number of traces exported.

    Only includes traces with outcome >= min_outcome (default: _MIN_OUTCOME).
    """
    flush_all()
    count = 0
    try:
        src = _trace_file()
        dst = _export_file()
        if not src.exists():
            return 0
        dst.parent.mkdir(parents=True, exist_ok=True)
        with open(src, encoding="utf-8") as fin, \
             open(dst, "w", encoding="utf-8") as fout:
            for line in fin:
                line = line.strip()
                if not line:
                    continue
                try:
                    trace = json.loads(line)
                    if float(trace.get("outcome", 0)) >= min_outcome:
                        # Write in OpenAI SFT format
                        fout.write(json.dumps({"messages": trace["messages"]},
                                              ensure_ascii=False) + "\n")
                        count += 1
                except Exception:
                    continue
    except Exception as _e:
        record_failure("trace_buffer.export_for_training", _e)
    return count
