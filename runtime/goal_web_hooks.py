# runtime/goal_web_hooks.py
#
# GoalsDaemon ctx hooks, wired in by main.py. The web hooks are AR2: the
# 2026-07-02 run's three research goals all crashed with "ctx.web_search hook
# not provided" — the pipeline was connected end-to-end except this last inch.
from __future__ import annotations

import logging
from pathlib import Path

_log = logging.getLogger(__name__)

_EMOTION_STATE_PATH = Path(__file__).resolve().parent.parent / "brain" / "data" / "emotion_state.json"


def get_emotional_state() -> dict:
    """Read Orrin's current emotional state from v1's persisted file."""
    try:
        import json as _json
        raw = _EMOTION_STATE_PATH.read_text(encoding="utf-8")
        data = _json.loads(raw)
        # Flatten: prefer core_emotions block if present, fall back to top-level
        core = data.get("core_emotions")
        if isinstance(core, dict):
            merged = dict(data)
            merged.update(core)
            return merged
        return data
    except (OSError, ValueError, AttributeError):  # intentional: missing/bad state → empty
        return {}


def goal_web_search(query: str, k: int = 5) -> list:
    """web_search(query, k) -> [{"title","url","snippet"}].
    Serper when a key is configured; otherwise Wikipedia article search — the
    same capability the conscious lane already uses."""
    results: list = []
    try:
        from brain.behavior.tools.toolkit import web_search as _serper
        raw = _serper(str(query))
        for r in (raw.get("organic") or [])[: max(1, int(k))]:
            if isinstance(r, dict) and r.get("link"):
                results.append({
                    "title": str(r.get("title") or ""),
                    "url": str(r.get("link")),
                    "snippet": str(r.get("snippet") or ""),
                })
    except Exception as _e:
        _log.warning("goal web_search (serper) failed: %s", _e)
    if results:
        return results
    try:
        import json as _json
        import urllib.parse as _up
        from brain.cognition.web_fetch import _get
        q = _up.quote(str(query))
        raw = _get(
            "https://en.wikipedia.org/w/api.php"
            f"?action=query&list=search&srsearch={q}&format=json"
            f"&srlimit={max(1, int(k))}"
        )
        if raw:
            for r in (_json.loads(raw).get("query") or {}).get("search") or []:
                title = str(r.get("title") or "").strip()
                if title:
                    results.append({
                        "title": title,
                        "url": "https://en.wikipedia.org/wiki/"
                               + _up.quote(title.replace(" ", "_")),
                        "snippet": str(r.get("snippet") or ""),
                    })
    except Exception as _e:
        _log.warning("goal web_search (wikipedia) failed: %s", _e)
    return results


def goal_web_fetch(url: str, timeout: int | None = None) -> str:
    """Fetch a URL to plaintext for the research memo synthesizer (source
    material — the ledger's gates decide credit)."""
    from brain.cognition.web_fetch import _get, _html_to_text
    raw = _get(str(url), timeout=int(timeout or 12))
    if not raw:
        return ""
    try:
        html = raw.decode("utf-8", errors="ignore")
    except Exception:  # intentional: undecodable payload → empty text
        return ""
    return _html_to_text(html, max_chars=20000)
