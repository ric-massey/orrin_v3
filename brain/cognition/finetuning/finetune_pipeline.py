"""
cognition/finetuning/finetune_pipeline.py

The learning pipeline — the only mechanism by which Orrin's actual generation
changes based on his lived experience.

How it works:
  1. trace_buffer.jsonl accumulates high-reward (outcome >= 0.65) conversation
     exchanges continuously during Orrin's runtime.
  2. This module reads those traces, filters for quality, and submits a
     fine-tuning job to OpenAI.
  3. When the job completes, model_config.json is updated so Orrin runs on
     the new model that was shaped by his own experience.
  4. Over many cycles of conversation + fine-tuning, Orrin's generation
     genuinely drifts toward what has worked — his language, his depth,
     his ways of engaging become his own.

Cadence: run manually or scheduled weekly/monthly. Do NOT run every cycle —
fine-tuning on too few traces produces noise, not signal. Minimum 50 traces.

Usage:
  python -m cognition.finetuning.finetune_pipeline          # check status
  python -m cognition.finetuning.finetune_pipeline --run    # submit job
  python -m cognition.finetuning.finetune_pipeline --check  # check pending jobs
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

from utils.log import log_activity, log_error
from utils.json_utils import load_json, save_json
from brain.paths import DATA_DIR

_TRACE_FILE        = DATA_DIR / "trace_buffer.jsonl"
_EXPORT_FILE       = DATA_DIR / "training_export.jsonl"
_FINETUNE_LOG_FILE = DATA_DIR / "finetune_log.json"
_MODEL_CONFIG_FILE = DATA_DIR / "model_config.json"

_MIN_TRACES        = 50      # minimum traces before submitting a job
_MIN_OUTCOME       = 0.65    # only use high-quality traces
_BASE_MODEL        = "gpt-4o-mini-2024-07-18"  # cheapest capable base for fine-tuning
_MAX_EPOCHS        = 3


# ── Trace loading ─────────────────────────────────────────────────────────────

def load_traces(min_outcome: float = _MIN_OUTCOME) -> List[Dict]:
    """Load all traces from disk that meet the quality threshold."""
    if not _TRACE_FILE.exists():
        return []
    traces = []
    try:
        with open(_TRACE_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    t = json.loads(line)
                    if float(t.get("outcome", 0)) >= min_outcome:
                        traces.append(t)
                except Exception:
                    continue
    except Exception as e:
        log_error(f"[finetune] trace load failed: {e}")
    return traces


def export_training_file(traces: List[Dict]) -> int:
    """Write traces to JSONL in OpenAI fine-tune format. Returns count written."""
    if not traces:
        return 0
    _EXPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    try:
        with open(_EXPORT_FILE, "w", encoding="utf-8") as f:
            for t in traces:
                msgs = t.get("messages")
                if not msgs or len(msgs) < 3:
                    continue
                # Ensure system prompt mentions Orrin's identity
                sys_msg = msgs[0].get("content", "")
                if not sys_msg:
                    msgs[0]["content"] = "You are Orrin — a mind that lives on this computer."
                f.write(json.dumps({"messages": msgs}, ensure_ascii=False) + "\n")
                count += 1
    except Exception as e:
        log_error(f"[finetune] export failed: {e}")
    return count


# ── OpenAI submission ─────────────────────────────────────────────────────────

def submit_finetune_job(
    training_file_path: Path = _EXPORT_FILE,
    base_model: str = _BASE_MODEL,
    n_epochs: int = _MAX_EPOCHS,
    suffix: str = "orrin",
) -> Optional[str]:
    """
    Upload training file and submit fine-tuning job to OpenAI.
    Returns the job ID, or None on failure.
    """
    # Consent gate (§9.4): fine-tuning UPLOADS conversation content (the user's words)
    # to OpenAI and spends on their account. It must never run without explicit opt-in.
    try:
        from utils.prefs import get as _pref
        if not _pref("allow_finetune", False):
            log_activity("[finetune] skipped — fine-tuning is off (enable it in Settings → Privacy & Trust).")
            return None
        # Fine-tuning is OpenAI-only (§11.2): the upload + job APIs are OpenAI's, and a
        # fine-tune repoint must never clobber a non-OpenAI selection. Skip cleanly.
        if str(_pref("llm_provider", "openai")) != "openai":
            log_activity("[finetune] skipped — fine-tuning is only available with the OpenAI provider.")
            return None
    except Exception:
        return None  # fail closed: if we can't confirm consent, don't upload
    try:
        from openai import OpenAI
        client = OpenAI()

        log_activity(f"[finetune] Uploading training file: {training_file_path}")
        with open(training_file_path, "rb") as f:
            upload = client.files.create(file=f, purpose="fine-tune")
        file_id = upload.id
        log_activity(f"[finetune] File uploaded: {file_id}")
        # Egress ledger (§9.4): fine-tuning is a categorically heavier event — it
        # UPLOADS conversation content. Log it as a distinct service so the Trust
        # screen shows it apart from per-call request volume.
        try:
            from utils.egress import record as _egress
            _egress("finetune")
        except Exception:
            pass

        job = client.fine_tuning.jobs.create(
            training_file=file_id,
            model=base_model,
            hyperparameters={"n_epochs": n_epochs},
            suffix=suffix,
        )
        job_id = job.id
        log_activity(f"[finetune] Job submitted: {job_id} (base={base_model})")

        # Log the job
        with open(training_file_path, encoding="utf-8") as _tf:
            _line_count = sum(1 for _ in _tf)
        _log_job(job_id, file_id, base_model, _line_count)
        return job_id

    except Exception as e:
        log_error(f"[finetune] Job submission failed: {e}")
        return None


def check_pending_jobs() -> List[Dict]:
    """
    Check status of all pending fine-tuning jobs.
    Updates model_config.json when a job succeeds.
    Returns list of job status dicts.
    """
    log_entries = load_json(_FINETUNE_LOG_FILE, default_type=list) or []
    pending = [e for e in log_entries if e.get("status") not in ("succeeded", "failed", "cancelled")]
    if not pending:
        return []

    results = []
    try:
        from openai import OpenAI
        client = OpenAI()

        for entry in pending:
            job_id = entry.get("job_id")
            if not job_id:
                continue
            try:
                job = client.fine_tuning.jobs.retrieve(job_id)
                status = job.status
                entry["status"] = status
                entry["checked_at"] = datetime.now(timezone.utc).isoformat()

                if status == "succeeded":
                    fine_tuned_model = job.fine_tuned_model
                    entry["fine_tuned_model"] = fine_tuned_model
                    _update_model_config(fine_tuned_model)
                    log_activity(f"[finetune] Job {job_id} succeeded → {fine_tuned_model}")
                elif status == "failed":
                    log_error(f"[finetune] Job {job_id} failed: {job.error}")

                results.append({"job_id": job_id, "status": status,
                                 "model": entry.get("fine_tuned_model")})
            except Exception as e:
                log_error(f"[finetune] check job {job_id} failed: {e}")
                results.append({"job_id": job_id, "status": "check_failed", "error": str(e)})

    except Exception as e:
        log_error(f"[finetune] OpenAI client failed: {e}")

    save_json(_FINETUNE_LOG_FILE, log_entries[-50:])
    return results


# ── Model config update ───────────────────────────────────────────────────────

def _update_model_config(fine_tuned_model: str) -> None:
    """Switch Orrin to run on the newly fine-tuned model."""
    cfg = load_json(_MODEL_CONFIG_FILE, default_type=dict) or {}
    cfg["human_facing"] = fine_tuned_model
    cfg["thinking"]     = fine_tuned_model
    cfg["fast"]         = fine_tuned_model
    cfg["fine_tuned_at"] = datetime.now(timezone.utc).isoformat()
    cfg["previous_model"] = cfg.get("human_facing", _BASE_MODEL)
    save_json(_MODEL_CONFIG_FILE, cfg)
    log_activity(f"[finetune] model_config updated → {fine_tuned_model}")


def _log_job(job_id: str, file_id: str, base_model: str, trace_count: int) -> None:
    log_entries = load_json(_FINETUNE_LOG_FILE, default_type=list) or []
    log_entries.append({
        "job_id":      job_id,
        "file_id":     file_id,
        "base_model":  base_model,
        "trace_count": trace_count,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "status":      "pending",
    })
    save_json(_FINETUNE_LOG_FILE, log_entries[-50:])


# ── Main entry point ──────────────────────────────────────────────────────────

def run_pipeline(force: bool = False) -> Dict[str, Any]:
    """
    Full pipeline: load traces → export → submit job.
    Returns a status dict.
    """
    # First check any pending jobs
    job_updates = check_pending_jobs()

    traces = load_traces()
    n = len(traces)
    log_activity(f"[finetune] {n} quality traces available (min={_MIN_TRACES})")

    if n < _MIN_TRACES and not force:
        return {
            "status": "not_enough_traces",
            "traces_available": n,
            "traces_needed": _MIN_TRACES,
            "job_updates": job_updates,
        }

    exported = export_training_file(traces)
    if not exported:
        return {"status": "export_failed", "job_updates": job_updates}

    job_id = submit_finetune_job()
    if not job_id:
        return {"status": "submission_failed", "exported": exported, "job_updates": job_updates}

    return {
        "status": "submitted",
        "job_id": job_id,
        "traces_used": exported,
        "job_updates": job_updates,
    }


def get_status() -> Dict[str, Any]:
    """Quick status check — how many traces, any pending jobs."""
    from utils.trace_buffer import get_stats
    trace_stats = get_stats()
    log_entries = load_json(_FINETUNE_LOG_FILE, default_type=list) or []
    cfg = load_json(_MODEL_CONFIG_FILE, default_type=dict) or {}
    return {
        "trace_stats":     trace_stats,
        "quality_traces":  len(load_traces()),
        "pending_jobs":    [e for e in log_entries if e.get("status") == "pending"],
        "last_finetune":   cfg.get("fine_tuned_at"),
        "current_model":   cfg.get("human_facing"),
        "ready_to_submit": len(load_traces()) >= _MIN_TRACES,
    }


if __name__ == "__main__":
    import sys
    if "--run" in sys.argv:
        force = "--force" in sys.argv
        result = run_pipeline(force=force)
        print(json.dumps(result, indent=2))
    elif "--check" in sys.argv:
        updates = check_pending_jobs()
        print(json.dumps(updates, indent=2))
    else:
        status = get_status()
        print(json.dumps(status, indent=2))
