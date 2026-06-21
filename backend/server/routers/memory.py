"""Memory-store browsing routes: the store, not the live stream (Fix 8).

Split out of app.py (Phase 4C). Reads the real store files via the shared data
root (`server_state._DATA_DIR`, monkeypatchable) and is mounted on the read API
router by app.py.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .. import state as server_state

router = APIRouter()

# ── Memory store browsing: the store, not the stream (Fix 8) ─────────────────
_MEMORY_STORES = {
    "long": "long_memory.json",
    "working": "working_memory.json",
    "knowledge": "knowledge_graph.json",
    "semantic": "semantic_facts.json",
}


@router.get("/memory")
async def memory_store(store: str = "long", q: str = "", n: int = 50, offset: int = 0,
                      order: str = "recency") -> JSONResponse:
    """Paged browse of a REAL memory store file — what he actually remembers, as
    opposed to the live op ring the WS streams. `order=recency` (default, newest
    first) or `order=importance` (by importance/salience) powers the Memory
    Explorer's Recent vs Important lenses (§9.5)."""
    import json as _json
    fname = _MEMORY_STORES.get((store or "").lower())
    if not fname:
        return JSONResponse({"entries": [], "total": 0,
                             "error": f"unknown store; one of {sorted(_MEMORY_STORES)}"}, status_code=400)
    try:
        raw = _json.loads((server_state._DATA_DIR / fname).read_text("utf-8"))
        # knowledge_graph.json is {entities, relations, meta} — browse the entities.
        if isinstance(raw, dict):
            ents = raw.get("entities")
            if isinstance(ents, dict):
                raw = [{"id": k, **v} if isinstance(v, dict) else {"id": k, "content": str(v)}
                       for k, v in ents.items()]
            elif isinstance(ents, list):
                raw = ents
            else:
                raw = []
        if not isinstance(raw, list):
            raw = []
        total = len(raw)
        entries = [e for e in raw if isinstance(e, dict)]
        needle = (q or "").strip().lower()
        if needle:
            entries = [e for e in entries if needle in _json.dumps(e, ensure_ascii=False).lower()]
        matched = len(entries)
        if (order or "").lower() == "importance":
            def _imp(e: Dict[str, Any]) -> float:
                for k in ("importance", "salience", "weight", "score"):
                    v = e.get(k)
                    if isinstance(v, (int, float)):
                        return float(v)
                return 0.0
            entries = sorted(entries, key=_imp, reverse=True)
        else:
            entries = list(reversed(entries))  # recency: newest-first (stores append)
        lo = max(0, int(offset))
        hi = lo + max(1, min(200, int(n)))
        page = []
        for e in entries[lo:hi]:
            slim = dict(e)
            c = slim.get("content")
            if isinstance(c, str) and len(c) > 2000:
                slim["content"] = c[:2000] + "…"
            page.append(slim)
        return JSONResponse({"entries": page, "total": total, "matched": matched,
                             "store": store, "offset": lo})
    except FileNotFoundError:
        return JSONResponse({"entries": [], "total": 0, "matched": 0, "store": store, "offset": 0})
    except Exception as e:
        return JSONResponse({"entries": [], "total": 0, "error": str(e)})


@router.get("/memory_counts")
async def memory_counts() -> JSONResponse:
    """True store sizes for the Inspector's chips (live-op counts are NOT sizes)."""
    import json as _json
    out: Dict[str, int] = {}
    for key, fname in _MEMORY_STORES.items():
        try:
            raw = _json.loads((server_state._DATA_DIR / fname).read_text("utf-8"))
            if isinstance(raw, dict):
                ents = raw.get("entities")
                out[key] = len(ents) if isinstance(ents, (list, dict)) else 0
            else:
                out[key] = len(raw) if isinstance(raw, list) else 0
        except Exception:
            out[key] = 0
    return JSONResponse({"counts": out})
