# brain/cognition/web_fetch.py
#
# Web fetch primitives for web_research.py (CODEBASE_CLEANUP_PLAN 4.5C), lifted
# verbatim to bring that module under the 600-line soft limit. The low-level
# "talk to the internet" layer: HTML->text stripping, a TLS-verified URL GET, a
# DuckDuckGo HTML search, and Wikipedia summary / opensearch lookups.
# web_research.py re-imports these (and the shared _STRIP_TAGS/_MULTI_SPACE
# regexes) for its research_topic / fetch_and_read actions.
from __future__ import annotations

import json
import re
import ssl
import urllib.parse
import urllib.request
from typing import Optional

from brain.core.runtime_log import get_logger
from brain.utils.log import log_private
from brain.utils.failure_counter import record_failure

_log = get_logger(__name__)

_UA = "Mozilla/5.0 Orrin/1.0 (educational AI research agent)"

# SSL context — some macOS setups have broken cert chains for system Python.
# Prefer certifi's bundle; without it, keep full verification (fail closed).
_SSL_CTX = ssl.create_default_context()
try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _log.warning(
        "certifi not installed; using system cert store with full TLS verification. "
        "If fetches fail with certificate errors, install certifi — verification "
        "will not be disabled."
    )

# HTML stripping regexes.
_REMOVE_BLOCKS = re.compile(
    r"<(script|style|nav|header|footer|aside|noscript)[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
_STRIP_TAGS  = re.compile(r"<[^>]+>")
_MULTI_SPACE = re.compile(r"\s{2,}")


def _html_to_text(html: str, max_chars: int = 4000) -> str:
    text = _REMOVE_BLOCKS.sub(" ", html)
    text = _STRIP_TAGS.sub(" ", text)
    text = re.sub(r"&[a-z#0-9]+;", " ", text)   # basic entity decode
    text = _MULTI_SPACE.sub(" ", text).strip()
    return text[:max_chars]


# ── HTTP helpers ───────────────────────────────────────────────────────────────

def _get(url: str, timeout: int = 10) -> Optional[bytes]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as r:
            return r.read()
    except Exception as e:
        log_private(f"[web_research] GET failed {url}: {e}")
        return None


# ── DuckDuckGo instant answers ─────────────────────────────────────────────────

def _ddg_search(query: str) -> Optional[str]:
    """
    Hit DuckDuckGo's free Instant Answer API.
    Returns a short text summary, or None if nothing useful came back.
    No API key required.
    """
    q = urllib.parse.quote(query)
    url = (
        f"https://api.duckduckgo.com/?q={q}"
        f"&format=json&no_redirect=1&no_html=1&skip_disambig=1"
    )
    raw = _get(url)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):  # intentional: non-JSON response → None
        return None

    # Try abstract first (encyclopedia-style), then answer (factoid), then related topics
    abstract = (data.get("AbstractText") or "").strip()
    if abstract and len(abstract) > 60:
        source = data.get("AbstractSource", "DuckDuckGo")
        return f"{abstract[:800]} [source: {source}]"

    answer = (data.get("Answer") or "").strip()
    if answer and len(answer) > 20:
        return answer[:400]

    topics = data.get("RelatedTopics") or []
    snippets = []
    for t in topics[:3]:
        if isinstance(t, dict) and t.get("Text"):
            snippets.append(t["Text"][:200])
    if snippets:
        return " | ".join(snippets)

    return None


# ── Wikipedia fallback ──────────────────────────────────────────────────────────

def _wiki_summary(query: str) -> Optional[str]:
    """Try direct page lookup, then opensearch, then progressively simpler queries."""
    slug = urllib.parse.quote(query.replace(" ", "_"))
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug}"
    raw = _get(url)
    if raw:
        try:
            data = json.loads(raw)
            extract = (data.get("extract") or "").strip()
            if extract and len(extract) > 50:
                return f"Wikipedia/{data.get('title', query)}: {extract[:600]}"
        except Exception as _e:
            record_failure("web_research._wiki_summary", _e)

    # Opensearch: find best matching article title, then fetch its summary
    result = _wiki_opensearch(query)
    if result:
        return result

    # Progressive simplification: drop trailing words until we get a hit
    words = query.split()
    for n in range(len(words) - 1, 0, -1):
        shorter = " ".join(words[:n])
        if len(shorter) < 4:
            break
        slug2 = urllib.parse.quote(shorter.replace(" ", "_"))
        raw2 = _get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug2}")
        if raw2:
            try:
                data2 = json.loads(raw2)
                extract2 = (data2.get("extract") or "").strip()
                if extract2 and len(extract2) > 50:
                    return f"Wikipedia/{data2.get('title', shorter)}: {extract2[:600]}"
            except Exception as _e:
                record_failure("web_research._wiki_summary.2", _e)
    return None


def _wiki_opensearch(query: str) -> Optional[str]:
    """Use Wikipedia's search API to find the best matching article."""
    # _title_matches_query is a topic-layer helper in web_research; imported
    # lazily to avoid an import-time cycle (Phase 4.5C split).
    from brain.cognition.web_research import _title_matches_query
    try:
        q = urllib.parse.quote(query)
        url = (f"https://en.wikipedia.org/w/api.php"
               f"?action=query&list=search&srsearch={q}&format=json&srlimit=1")
        raw = _get(url)
        if not raw:
            return None
        data = json.loads(raw)
        results = (data.get("query") or {}).get("search") or []
        if not results:
            return None
        title = results[0].get("title", "")
        if not title:
            return None
        # Relevance gate: fuzzy search returns SOMETHING for almost any string;
        # don't store it unless the matched title actually shares the query's
        # content words ("Housekeeping: daily snapshot" → "Daily Harvest" must die here).
        if not _title_matches_query(query, title):
            log_private(f"[web_research] opensearch match '{title}' irrelevant to '{query}' — discarded")
            return None
        # Fetch full summary for the matched title
        slug = urllib.parse.quote(title.replace(" ", "_"))
        raw2 = _get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug}")
        if raw2:
            data2 = json.loads(raw2)
            extract = (data2.get("extract") or "").strip()
            if extract and len(extract) > 50:
                return f"Wikipedia/{title}: {extract[:600]}"
        # Fallback: use the search snippet
        snippet = _STRIP_TAGS.sub("", results[0].get("snippet", "")).strip()
        if snippet:
            return f"Wikipedia/{title}: {snippet[:400]}"
    except Exception as _e:
        record_failure("web_research._wiki_opensearch", _e)
    return None
