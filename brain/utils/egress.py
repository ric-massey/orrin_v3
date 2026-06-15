"""
utils/egress.py — the egress ledger (§9.4): a tiny, append-only record of every
outbound network call Orrin makes, so the Privacy & Trust screen can tell the user
*exactly* what leaves the device.

Hard privacy rule: this stores **counts and timestamps only** — `{service, ts, count,
approx_tokens?}`. NEVER a prompt, query, request body, or response. That restraint is
itself the trust signal: the ledger can be fully open because it contains nothing
private.

Recorded at the real egress points:
  • openai   — generate_response (the one cached client)
  • serper   — toolkit.web_search
  • web      — toolkit.scrape_text (arbitrary site fetches)
  • finetune — finetune_pipeline.submit_finetune_job (a heavier, data-uploading event)

Symbolic-only mode (no keys) never reaches any of these, so the ledger stays at zero —
which is what lets the screen honestly say "nothing leaves your machine."
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, List, Optional

from paths import DATA_DIR

_LOG = DATA_DIR / "egress_log.jsonl"
_LOCK = threading.Lock()
# Bound the file like the other ledgers (forgetting_log etc.) — counts age out of the
# 24h window anyway; keep a generous tail for longer rollups without unbounded growth.
_MAX_LINES = 5000


def record(service: str, *, count: int = 1, approx_tokens: Optional[int] = None) -> None:
    """Append one outbound-call record. Best-effort and never raises into the caller —
    a telemetry ledger must never break a real network call."""
    try:
        entry: Dict[str, Any] = {"service": str(service), "ts": time.time(), "count": int(count)}
        if approx_tokens is not None:
            entry["approx_tokens"] = int(approx_tokens)
        line = json.dumps(entry, ensure_ascii=False)
        with _LOCK:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with _LOG.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
            _trim_locked()
    except Exception:
        pass


def _trim_locked() -> None:
    """Keep only the last _MAX_LINES lines. Cheap, runs under _LOCK."""
    try:
        lines = _LOG.read_text(encoding="utf-8").splitlines()
        if len(lines) > _MAX_LINES:
            _LOG.write_text("\n".join(lines[-_MAX_LINES:]) + "\n", encoding="utf-8")
    except Exception:
        pass


def _read() -> List[Dict[str, Any]]:
    try:
        out: List[Dict[str, Any]] = []
        for ln in _LOG.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                rec = json.loads(ln)
                if isinstance(rec, dict):
                    out.append(rec)
            except Exception:
                continue
        return out
    except Exception:
        return []


def events(since_ts: float = 0.0) -> List[Dict[str, Any]]:
    """Raw egress records at or after `since_ts` — for the activity timeline (§9.8).
    Still counts/timestamps only; no bodies were ever stored to leak."""
    return [r for r in _read() if float(r.get("ts") or 0) >= since_ts]


def summary(window_s: float = 86400.0) -> Dict[str, Any]:
    """Per-service rollup over the last `window_s` seconds (default 24h):
    `{services: {svc: {requests, approx_tokens, last_ts}}, window_s, total_requests}`.
    """
    now = time.time()
    cutoff = now - window_s
    services: Dict[str, Dict[str, Any]] = {}
    total = 0
    for rec in _read():
        ts = float(rec.get("ts") or 0)
        if ts < cutoff:
            continue
        svc = str(rec.get("service") or "unknown")
        cnt = int(rec.get("count") or 0)
        slot = services.setdefault(svc, {"requests": 0, "approx_tokens": 0, "last_ts": 0.0})
        slot["requests"] += cnt
        if rec.get("approx_tokens") is not None:
            slot["approx_tokens"] += int(rec.get("approx_tokens") or 0)
        slot["last_ts"] = max(slot["last_ts"], ts)
        total += cnt
    return {"services": services, "window_s": window_s, "total_requests": total, "now": now}
