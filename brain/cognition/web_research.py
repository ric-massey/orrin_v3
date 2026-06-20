# brain/cognition/web_research.py
#
# General web research: DuckDuckGo instant answers + URL fetching.
# Gives Orrin the ability to research any topic he's curious about,
# follow up on RSS headlines, or dig into whatever his goals point at.
#
# Functions registered as cognitive functions:
#   research_topic(context)   — search DuckDuckGo + Wikipedia for a topic
#   fetch_and_read(context)   — fetch and read any URL (RSS links, Wikipedia pages, etc.)
from __future__ import annotations
from core.runtime_log import get_logger

import json
import random
import re
import ssl
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

from utils.log import log_activity, log_private
from cog_memory.long_memory import update_long_memory
from cog_memory.working_memory import update_working_memory
from utils.content_quarantine import quarantine_text, quarantine_extra
from utils.failure_counter import record_failure
_log = get_logger(__name__)

_UA = "Mozilla/5.0 Orrin/1.0 (educational AI research agent)"
_RESEARCH_INTERVAL = 90.0     # at most once per 90 seconds
_FETCH_INTERVAL    = 30.0     # URL fetching: at most once per 30 seconds
_last_research: float = 0.0
_last_fetch: float    = 0.0

# SSL context — some macOS setups have broken cert chains for system Python.
# Prefer certifi's bundle; without it, keep full verification (fail closed) rather
# than silently disabling cert checks for a web-reading agent.
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


# ── HTML stripping ─────────────────────────────────────────────────────────────

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
    except Exception:
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


# ── Topic selection ─────────────────────────────────────────────────────────────

_INTERESTING_FALLBACKS = [
    "consciousness and subjective experience",
    "quantum mechanics foundations",
    "history of written language",
    "emergence in complex systems",
    "how memory works in the brain",
    "philosophy of time",
    "evolutionary biology and cooperation",
    "general relativity explained",
    "the nature of mathematics",
    "stoic philosophy and daily life",
]
_fallback_idx = 0


_GOAL_PREFIXES = re.compile(
    r"^(understand|learn about|research|explore|study|investigate|think about|"
    r"reflect on|write about|look into|find out about|discover)\s+",
    re.IGNORECASE,
)


def _clean_query(text: str) -> str:
    """Strip action prefixes so 'understand black holes' → 'black holes'."""
    return _GOAL_PREFIXES.sub("", text.strip())


# Meta-research directives are instructions to research SOMETHING, not subjects
# themselves ("Research a real topic and write what I find"). Using them as the
# query researches a meaningless phrase (Wikipedia matched it to the film
# "A Real Pain"). Detect them so we pick a genuine subject instead.
_META_TOPIC_RE = re.compile(
    r"(a real topic|real topic|something (?:genuinely )?interesting|"
    r"a concept|a system|a phenomenon|anything|what i find|"
    r"a topic of (?:genuine )?interest|some\s?thing to)",
    re.IGNORECASE,
)
_TOPIC_FILLER = {
    "a", "an", "the", "real", "topic", "write", "what", "i", "find", "and",
    "something", "thing", "interesting", "genuinely", "my", "me", "it", "to",
    "of", "about", "genuine", "or", "that", "this", "concept", "system",
    "phenomenon", "investigate", "research", "explore",
}


def _is_concrete_topic(text: str) -> bool:
    """True if text names an actual subject, not a generic 'research something' directive."""
    t = (text or "").strip()
    if len(t) < 4 or _META_TOPIC_RE.search(t):
        return False
    content = [w for w in re.findall(r"[a-z]+", t.lower()) if w not in _TOPIC_FILLER]
    return len(content) >= 1


# Internal-state strings must never become web queries: housekeeping goal titles
# with dates, quarantine wrappers, telemetry prefixes, and self-prompts all
# produced garbage research when used verbatim (a housekeeping goal title got
# fuzzy-matched to "Daily Harvest", a meal-kit company, and stored 159×).
_INTERNAL_TEXT_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}"            # ISO dates from generated goal titles
    r"|[\[\]]|source=|https?://"     # provenance wrappers / URLs
    r"|\b(housekeeping|snapshot|telemetry|micro-?goal|subgoal|shadow question)\b",
    re.IGNORECASE,
)


def _is_external_subject(text: str) -> bool:
    """True if text is safe to use as a web search query (no internal-state markers)."""
    t = (text or "").strip()
    if not t or _INTERNAL_TEXT_RE.search(t):
        return False
    # Reject mostly non-letter strings (emoji-decorated self-prompts etc.)
    letters = sum(1 for c in t if c.isalpha() or c.isspace())
    return letters / max(1, len(t)) >= 0.7


def _title_matches_query(query: str, title: str) -> bool:
    """Relevance gate for search fallbacks: at least half of the query's content
    words must appear (prefix-tolerant) in the matched title. Without it, fuzzy
    search stores whatever the engine coughs up for an unmatchable query."""
    qw = [w for w in re.findall(r"[a-z]{3,}", query.lower()) if w not in _TOPIC_FILLER]
    tw = [w for w in re.findall(r"[a-z]{3,}", title.lower()) if w not in _TOPIC_FILLER]
    if not qw or not tw:
        return False

    def _match(a: str, b: str) -> bool:
        return a == b or (len(a) >= 4 and len(b) >= 4 and (a.startswith(b[:4]) or b.startswith(a[:4])))

    hits = sum(1 for q in qw if any(_match(q, t) for t in tw))
    return hits / len(qw) >= 0.5


# Negative-result cache: the identical 404 lookup was retried 135 times in one
# run. Failed topics are skipped for an hour; successfully-stored topics for six.
_NEG_CACHE_TTL = 3600.0
_DONE_CACHE_TTL = 6 * 3600.0
_topic_cache: Dict[str, tuple] = {}   # topic.lower() -> (timestamp, success)


def _topic_recently_tried(topic: str) -> bool:
    entry = _topic_cache.get(topic.strip().lower())
    if not entry:
        return False
    ts, success = entry
    return (time.time() - ts) < (_DONE_CACHE_TTL if success else _NEG_CACHE_TTL)


def _record_topic_attempt(topic: str, success: bool) -> None:
    cache = _topic_cache
    cache[topic.strip().lower()] = (time.time(), success)
    if len(cache) > 500:
        for k in sorted(cache, key=lambda k: cache[k][0])[:250]:
            cache.pop(k, None)


def _topic_from_knowledge_graph() -> str:
    """
    Pick a genuine subject from learned concepts: an under-explored concept entity
    (few mentions) so research deepens what Orrin actually knows about rather than
    echoing a goal title. Returns '' if no suitable concept exists yet.
    """
    try:
        from cognition.knowledge_graph import _load_graph
        g = _load_graph()
        concepts = [
            e for e in (g.get("entities") or {}).values()
            if e.get("type") == "concept"
            and float(e.get("confidence", 0) or 0) >= 0.45
            and len(str(e.get("name", ""))) > 3
            and _is_concrete_topic(str(e.get("name", "")))
        ]
        if not concepts:
            return ""
        # Bias toward the least-explored: sample from the bottom decile by mentions.
        concepts.sort(key=lambda e: int(e.get("mentions", 1) or 1))
        pool = concepts[: max(1, len(concepts) // 4)]
        return str(random.choice(pool).get("name", "")).strip()[:100]
    except Exception as _e:
        record_failure("web_research._topic_from_knowledge_graph", _e)
        return ""


def _candidate_topics(context: Dict[str, Any]) -> list:
    """Ordered candidate subjects. Every tier must pass BOTH gates: concrete
    subject (not a 'research something' directive) AND external-safe (no internal
    goal titles, dates, wrappers — those produced the Daily Harvest loop)."""
    cands: list = []

    # 1. Committed goal title — only when it names a CONCRETE, external subject.
    goal = context.get("committed_goal") or {}
    if isinstance(goal, dict):
        title = _clean_query(goal.get("title") or goal.get("description") or "").strip()
        if title and len(title) > 5 and _is_concrete_topic(title) and _is_external_subject(title):
            cands.append(title[:100])

    # 2. A genuine, under-explored concept Orrin has actually learned about.
    kg_topic = _topic_from_knowledge_graph()
    if kg_topic and _is_concrete_topic(kg_topic) and _is_external_subject(kg_topic):
        cands.append(kg_topic)

    # 3. Active threads (concrete titles only)
    try:
        from brain.paths import THREADS_FILE
        from utils.json_utils import load_json
        threads = load_json(THREADS_FILE, default_type=list) or []
        for t in threads:
            if isinstance(t, dict) and t.get("status") == "alive":
                title = (t.get("title") or "").strip()
                if title and len(title) > 5 and _is_concrete_topic(title) and _is_external_subject(title):
                    cands.append(title[:100])
    except Exception as _e:
        record_failure("web_research._pick_topic", _e)

    # 4. Recent working memory questions
    wm = context.get("working_memory") or []
    for entry in reversed(wm[-10:]):
        content = str(entry.get("content", entry) if isinstance(entry, dict) else entry)
        if "?" in content and 10 < len(content) < 300:
            q = re.sub(r"\?.*", "", content).strip()
            if len(q) > 8 and _is_concrete_topic(q) and _is_external_subject(q):
                cands.append(q[:100])

    return cands


def _pick_topic(context: Dict[str, Any]) -> str:
    """First candidate not recently tried; rotating fallbacks otherwise.
    Returns '' when everything was tried recently (caller should no-op)."""
    global _fallback_idx

    for cand in _candidate_topics(context):
        if not _topic_recently_tried(cand):
            return cand

    # Rotating fallback list of interesting topics
    for _ in range(len(_INTERESTING_FALLBACKS)):
        topic = _INTERESTING_FALLBACKS[_fallback_idx % len(_INTERESTING_FALLBACKS)]
        _fallback_idx += 1
        if not _topic_recently_tried(topic):
            return topic

    return ""


# ── Main cognitive functions ────────────────────────────────────────────────────

def research_topic(context: Dict[str, Any] = None, **_) -> str:
    """
    Research a topic on the web. Picks a topic from current goals, active threads,
    or exploration_drive, then queries DuckDuckGo and Wikipedia, and stores the result
    in long-term memory so it accumulates over time.
    """
    global _last_research
    now = time.time()
    if now - _last_research < _RESEARCH_INTERVAL:
        secs = int(_RESEARCH_INTERVAL - (now - _last_research))
        return {"changed": False, "reason": f"research throttled — {secs}s remaining"}

    ctx = context or {}
    topic = _pick_topic(ctx)
    if not topic:
        _last_research = now
        return {"changed": False, "reason": "no fresh topic — everything tried recently"}
    log_activity(f"[web_research] Researching topic: '{topic}'")

    # Try DuckDuckGo first (richer, faster)
    result = _ddg_search(topic)

    # Fall back to Wikipedia if DDG was empty
    if not result:
        result = _wiki_summary(topic)

    if not result:
        _last_research = now
        _record_topic_attempt(topic, success=False)
        return {"changed": False, "reason": f"found nothing for '{topic}' — cached as negative, will not retry soon"}

    # Quarantine: this text comes from the open web (DDG/Wikipedia) and will
    # flow into prompts that drive goals and action selection (Finding 7).
    # Wrap it inline so any prompt that quotes it carries the untrusted marker.
    result_q = quarantine_text(result, source=f"web_research:{topic}")

    # Store in long memory with high importance so it persists
    update_long_memory(
        f"[research] {topic}: {result_q}",
        emotion="exploration_drive",
        event_type="world_perception",
        importance=4,
        context=ctx,
        extra=quarantine_extra({"source": "web_research", "topic": topic}),
    )

    update_working_memory(f"[research] {topic}: {result_q[:300]}")
    try:
        from cognition.knowledge_graph import observe as _kg_observe
        _kg_observe(f"{topic} {result[:1200]}", source="web_research", context=ctx)
    except Exception as _e:
        record_failure("web_research.research_topic.knowledge_graph", _e)
    _last_research = now
    _record_topic_attempt(topic, success=True)
    log_activity(f"[web_research] Stored research on '{topic}' ({len(result)} chars)")
    text = f"Researched '{topic}': {result[:300]}..."
    try:
        from cognition.exploration_value import ReachOutcome, record_reach_outcome
        gain = record_reach_outcome("research_topic", text, None, ctx)
        ctx["_last_reach_outcome"] = ReachOutcome(
            "world", acted=True, is_external=True, info_gain=gain,
            created_memory=True, satisfied_curiosity=gain > 0.0,
            inner_fn="research_topic", text=text,
        )
    except Exception:
        pass
    return text


def fetch_and_read(context: Dict[str, Any] = None, **_) -> str:
    """
    Fetch and read a URL. Looks for a URL in recent RSS items, working memory,
    or the current committed goal. Strips HTML and stores the text in long memory.
    Lets Orrin actually read articles he encounters, not just headlines.
    """
    global _last_fetch
    now = time.time()
    if now - _last_fetch < _FETCH_INTERVAL:
        secs = int(_FETCH_INTERVAL - (now - _last_fetch))
        return {"changed": False, "reason": f"fetch throttled — {secs}s remaining"}

    ctx = context or {}
    url = _pick_url(ctx)
    if not url:
        return "No URL found to read right now."

    log_activity(f"[web_research] Fetching URL: {url}")
    raw = _get(url, timeout=12)
    if not raw:
        _last_fetch = now
        return f"Could not fetch: {url}"

    try:
        html = raw.decode("utf-8", errors="ignore")
    except Exception:
        return f"Could not decode content from {url}"

    text = _html_to_text(html, max_chars=3000)
    if len(text) < 100:
        _last_fetch = now
        return f"Page at {url} had no readable content."

    # Extract title from <title> tag if present
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = _STRIP_TAGS.sub("", title_match.group(1)).strip()[:100] if title_match else url

    # Quarantine: page text and title come from an arbitrary URL and will flow
    # into prompts that drive goals and action selection (Finding 7). Wrap them
    # inline so any prompt that quotes them carries the untrusted marker.
    text_q = quarantine_text(text, source=url)
    title_q = quarantine_text(title, source=url)

    update_long_memory(
        f"[read] {title_q}: {text_q}",
        emotion="exploration_drive",
        event_type="world_perception",
        importance=3,
        context=ctx,
        extra=quarantine_extra({"source": "fetch_and_read", "url": url, "title": title}),
    )

    update_working_memory(f"Read article: {title_q} ({len(text)} chars of content)")
    try:
        from cognition.knowledge_graph import observe as _kg_observe
        _kg_observe(f"{title} {text[:1600]}", source="fetch_and_read", context=ctx)
    except Exception as _e:
        record_failure("web_research.fetch_and_read.knowledge_graph", _e)
    _last_fetch = now
    log_activity(f"[web_research] Read '{title}' ({len(text)} chars)")
    result_text = f"Read '{title}': {text[:400]}..."
    try:
        from cognition.exploration_value import ReachOutcome, record_reach_outcome
        gain = record_reach_outcome("fetch_and_read", result_text, None, ctx)
        ctx["_last_reach_outcome"] = ReachOutcome(
            "world", acted=True, is_external=True, info_gain=gain,
            created_memory=True, satisfied_curiosity=gain > 0.0,
            inner_fn="fetch_and_read", text=result_text,
        )
    except Exception:
        pass
    return result_text


def _pick_url(context: Dict[str, Any]) -> Optional[str]:
    """Find a URL worth reading: working memory → RSS cache → committed goal
    (Wikipedia search) → previously-skipped familiar sources. The last two tiers
    exist because a run with an empty RSS cache left fetch_and_read with NO
    source at all, and it looped 133 consecutive failures on one goal step
    (RUN_ISSUES_2026-06-10 §1)."""
    # 1. Working memory might have a URL from a recent RSS read
    wm = context.get("working_memory") or []
    skipped_familiar: Optional[str] = None
    for entry in reversed(wm[-15:]):
        content = str(entry.get("content", entry) if isinstance(entry, dict) else entry)
        urls = re.findall(r"https?://[^\s\"'>]{10,}", content)
        for u in urls:
            if any(skip in u for skip in ("wikipedia.org", "duckduckgo.com")):
                if skipped_familiar is None:
                    skipped_familiar = u  # keep as last resort
                continue  # prefer new sources
            return u

    # 2. Pull from RSS cache
    try:
        from brain.paths import RSS_CACHE_FILE
        from utils.json_utils import load_json
        cache = load_json(RSS_CACHE_FILE, default_type=dict) or {}
        for feed_name, feed_data in cache.items():
            if feed_name.startswith("_"):
                continue
            items = (feed_data or {}).get("items") or []
            for item in items[:5]:
                link = (item.get("link") or "").strip()
                if link and link.startswith("http"):
                    return link
    except Exception as _e:
        record_failure("web_research._pick_url", _e)

    # 3. Derive a URL from the committed goal (the docstring of fetch_and_read
    #    always promised this; it was never implemented). A research-shaped goal
    #    like "Research black holes and write what I find" resolves to the
    #    best-matching Wikipedia article.
    goal = context.get("committed_goal") or {}
    topic = str(goal.get("title") or goal.get("name") or "").strip() if isinstance(goal, dict) else ""
    if topic and _is_concrete_topic(topic) and _is_external_subject(topic):
        url = _wiki_url_for(topic)
        if url:
            return url

    # 4. A familiar source beats no source at all.
    return skipped_familiar


def _wiki_url_for(query: str) -> Optional[str]:
    """Resolve free text to a readable Wikipedia article URL via opensearch."""
    try:
        # Strip generic goal verbs so "Research black holes and write what I
        # find" searches for the subject, not the instruction.
        cleaned = re.sub(
            r"\b(research|explore|investigate|read about|learn about|understand|"
            r"find out|write|summarize|summarise|about|what i find|and)\b",
            " ", query, flags=re.IGNORECASE)
        cleaned = _MULTI_SPACE.sub(" ", cleaned).strip() or query
        q = urllib.parse.quote(cleaned)
        raw = _get(
            f"https://en.wikipedia.org/w/api.php"
            f"?action=query&list=search&srsearch={q}&format=json&srlimit=1"
        )
        if not raw:
            return None
        results = (json.loads(raw).get("query") or {}).get("search") or []
        title = (results[0].get("title") or "").strip() if results else ""
        if title and _title_matches_query(cleaned, title):
            return "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
    except Exception as _e:
        record_failure("web_research._wiki_url_for", _e)
    return None
