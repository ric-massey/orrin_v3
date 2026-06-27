# brain/cognition/wikipedia_search.py
# Looks up Wikipedia summaries using the free REST API (no API key required).
from __future__ import annotations
from brain.core.runtime_log import get_logger

import json
import re
import ssl
import time
import urllib.parse
import urllib.request
from typing import Dict, Any, Optional

from brain.paths import THREADS_FILE
from brain.utils.json_utils import load_json
from brain.utils.log import log_activity, log_private
from brain.cog_memory.long_memory import update_long_memory
from brain.utils.content_quarantine import quarantine_text, quarantine_extra
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

_LAST_WIKI_TS: float = 0.0
_MIN_INTERVAL_S: float = 300.0  # at most every 5 minutes
_STRIP_TAGS = re.compile(r'<[^>]+>')
_UA = "Orrin/1.0 (educational AI; https://github.com)"

# Prefer certifi's bundle (macOS Python often lacks system root certs —
# DATA_FILE_AUDIT 2026-06-11 §7: every _wiki_opensearch call failed with
# CERTIFICATE_VERIFY_FAILED); without it, keep full verification (fail closed).
_SSL_CTX = ssl.create_default_context()
try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _log.warning(
        "certifi not installed; using system cert store with full TLS verification. "
        "If wiki lookups fail with certificate errors, install certifi — "
        "verification will not be disabled."
    )


def wikipedia_search(context: Dict[str, Any] = None) -> str:
    """Look up a Wikipedia article driven by current exploration_drive or active threads."""
    global _LAST_WIKI_TS
    now = time.time()
    if now - _LAST_WIKI_TS < _MIN_INTERVAL_S:
        return "Already searched Wikipedia recently — waiting before looking again."

    context = context or {}
    query = _pick_query(context)
    if not query:
        return "No query formed for Wikipedia."

    result = _wiki_summary(query)
    if not result:
        return f"Wikipedia had nothing for '{query}'."

    # Quarantine: the summary is fetched from Wikipedia and will flow into
    # prompts that drive goals and action selection (Finding 7). Wrap it
    # inline so any prompt that quotes it carries the untrusted marker.
    summary_q = quarantine_text(result['summary'][:400], source=f"wikipedia:{result['title']}")
    update_long_memory(
        f"[wikipedia] {result['title']}: {summary_q}",
        emotion="exploration_drive",
        event_type="world_perception",
        importance=3,
        context=context,
        extra=quarantine_extra({"source": "wikipedia", "query": query, "title": result["title"]}),
    )
    try:
        from brain.cognition.knowledge_graph import observe as _kg_observe
        _kg_observe(
            f"{result['title']} {result['summary'][:1200]}",
            source="wikipedia",
            context=context,
        )
    except Exception as _e:
        record_failure("wikipedia_search.knowledge_graph", _e)

    _LAST_WIKI_TS = now
    log_activity(f"[wikipedia_search] {result['title']}")
    text = f"Wikipedia on '{result['title']}': {result['summary'][:200]}"
    try:
        from brain.cognition.exploration_value import ReachOutcome, record_reach_outcome
        gain = record_reach_outcome("wikipedia_search", text, None, context)
        context["_last_reach_outcome"] = ReachOutcome(
            "world", acted=True, is_external=True, info_gain=gain,
            created_memory=True, satisfied_curiosity=gain > 0.0,
            inner_fn="wikipedia_search", text=text,
        )
    except (ImportError, TypeError, ValueError):  # best-effort reach-outcome record — never block the search
        pass
    return text


def _pick_query(context: Dict[str, Any]) -> str:
    # Internal-state strings (self-prompts like "🌓 Shadow question: …", goal
    # titles with dates, provenance wrappers) must never become lookup terms —
    # same gates as web_research (FINDINGS 2026-06-12 data sweep §3/§10).
    from brain.cognition.web_research import _is_concrete_topic, _is_external_subject

    # Active thread titles first
    try:
        threads = load_json(THREADS_FILE, default_type=list) or []
        for t in threads:
            if isinstance(t, dict) and t.get("status") == "alive":
                title = (t.get("title") or "").strip()
                if title and _is_concrete_topic(title) and _is_external_subject(title):
                    return title[:80]
    except Exception as _e:
        record_failure("wikipedia_search._pick_query", _e)

    # Questions in working memory
    wm = context.get("working_memory") or []
    for e in reversed(wm[-8:]):
        content = str(e.get("content", e) if isinstance(e, dict) else e)
        if "?" in content and 10 < len(content) < 200:
            q = content.replace("?", "").strip()
            if len(q) > 5 and _is_concrete_topic(q) and _is_external_subject(q):
                return q[:80]

    # Core values as fallback
    self_model = context.get("self_model") or {}
    for v in (self_model.get("core_values") or [])[:1]:
        val = v.get("value", v) if isinstance(v, dict) else str(v)
        val = str(val).strip()
        if val and _is_concrete_topic(val) and _is_external_subject(val):
            return val[:60]

    return ""


def _wiki_summary(query: str, timeout: int = 8) -> Optional[Dict]:
    """Try page/summary endpoint first, fall back to opensearch."""
    slug = urllib.parse.quote(query.replace(" ", "_"))
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
            data = json.loads(resp.read())
        extract = data.get("extract", "")
        if extract:
            return {"title": data.get("title", query), "summary": extract[:600]}
    except Exception as e:
        log_private(f"[wikipedia_search] direct lookup failed '{query}': {e}")

    return _wiki_opensearch(query, timeout)


def _wiki_opensearch(query: str, timeout: int = 8) -> Optional[Dict]:
    """Use Wikipedia opensearch to find the best matching article."""
    try:
        q = urllib.parse.quote(query)
        url = (
            f"https://en.wikipedia.org/w/api.php"
            f"?action=query&list=search&srsearch={q}&format=json&srlimit=1"
        )
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
            data = json.loads(resp.read())
        results = data.get("query", {}).get("search", [])
        if not results:
            return None
        title   = results[0].get("title", "")
        snippet = _STRIP_TAGS.sub("", results[0].get("snippet", ""))
        if title and snippet:
            # Relevance gate: fuzzy search matches almost anything; only store
            # results whose title shares the query's content words.
            from brain.cognition.web_research import _title_matches_query
            if not _title_matches_query(query, title):
                log_private(f"[wikipedia_search] opensearch match '{title}' irrelevant to '{query}' — discarded")
                return None
            return {"title": title, "summary": snippet[:400]}
    except Exception as _e:
        record_failure("wikipedia_search._wiki_opensearch", _e)
    return None
