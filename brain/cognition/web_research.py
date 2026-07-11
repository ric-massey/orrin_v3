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
from brain.cognition.global_workspace import bound_goal
from brain.core.runtime_log import get_logger

import json
import random
import re
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

from brain.utils.log import log_activity
from brain.cog_memory.long_memory import update_long_memory
from brain.cog_memory.working_memory import update_working_memory
from brain.utils.content_quarantine import quarantine_text, quarantine_extra
from brain.utils.failure_counter import record_failure
# Web fetch primitives (HTML strip, GET, DDG search, Wikipedia lookups),
# extracted to web_fetch.py (Phase 4.5C). Re-imported for research_topic /
# fetch_and_read + the shared HTML-stripping regexes.
from brain.cognition.web_fetch import (  # noqa: F401
    _html_to_text, _get, _ddg_search, _wiki_summary, _wiki_opensearch,
    _STRIP_TAGS, _MULTI_SPACE,
)
_log = get_logger(__name__)

_RESEARCH_INTERVAL = 90.0     # at most once per 90 seconds
_FETCH_INTERVAL    = 30.0     # URL fetching: at most once per 30 seconds
_last_research: float = 0.0
_last_fetch: float    = 0.0

# F4 (2026-07-05 findings): a substantial read becomes a MEMO ARTIFACT, not
# only a memory. The 07-05 life wrote 0 memos (Run 3: 11) because all frontier
# research ran as conscious research_topic calls that stored to long_memory —
# leaving the A2 reuse hooks (builds-on scan, hash_for_path/mark_reused) aimed
# at an empty population. Below this floor the read stays memory-only.
_MEMO_MIN_CHARS = 400


def _write_research_memo(topic: str, body: str, ctx: Dict[str, Any],
                         source: str) -> None:
    """Write a memo .md under data/goals/artifacts/<goal>/ and record it on the
    effect ledger (path-indexed, body captured) so later reads can be credited
    as reuse and later goals can build on it. Fail-safe; dedupe is the ledger's."""
    if len(str(body or "").strip()) < _MEMO_MIN_CHARS:
        return
    try:
        from brain.paths import GOALS_DIR
        goal = bound_goal(ctx) or {}
        gid = str((goal.get("id") if isinstance(goal, dict) else "")
                  or "conscious-research")
        slug = re.sub(r"[^a-z0-9_-]+", "-", str(topic).lower()).strip("-")[:60] or "memo"
        memo_dir = GOALS_DIR / "artifacts" / re.sub(r"[^A-Za-z0-9_-]+", "-", gid)[:64]
        memo_dir.mkdir(parents=True, exist_ok=True)
        path = memo_dir / f"memo_{slug}.md"
        content = (f"# Research memo: {topic}\n\n{str(body).strip()}\n\n"
                   f"---\nsource: {source} · "
                   f"{time.strftime('%Y-%m-%d %H:%MZ', time.gmtime())}\n")
        from brain.agency.effect_ledger import record_effect
        row = record_effect(
            "file_write", content,
            goal_id=(gid if gid != "conscious-research" else None), context=ctx,
            metadata={"path": str(path), "source": f"{source}_memo", "topic": str(topic)[:80]},
        )
        if row is None:
            return   # nothing novel — don't stamp a duplicate memo file
        path.write_text(content, encoding="utf-8")
        log_activity(f"[web_research] Memo artifact written: {path.name} "
                     f"({len(content)} chars).")
    except Exception as exc:
        record_failure("web_research._write_research_memo", exc)







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


# Visited-URL cache: fetch_and_read had no per-URL dedup, so _pick_url's RSS
# tier (which returns the first item of the first feed) re-served the identical
# article every cycle. On 2026-07-11 a self_understanding aspiration re-read one
# QuadRF blog post for hours at novelty 0.002 — the effect ledger deduped the
# memo so it stayed invisible while the action kept firing. Read URLs are now
# skipped for six hours (matching the topic cache's success TTL) so the feed is
# walked, not pinned. In-process only, like _topic_cache — a fresh life restarts
# clean, which is fine.
_url_cache: Dict[str, float] = {}   # url -> last-read unix ts


def _url_recently_read(url: str) -> bool:
    ts = _url_cache.get(url.strip())
    if ts is None:
        return False
    return (time.time() - ts) < _DONE_CACHE_TTL


def _record_url_read(url: str) -> None:
    cache = _url_cache
    cache[url.strip()] = time.time()
    if len(cache) > 500:
        for k in sorted(cache, key=lambda k: cache[k])[:250]:
            cache.pop(k, None)


def _topic_from_knowledge_graph() -> str:
    """
    Pick a genuine subject from learned concepts: an under-explored concept entity
    (few mentions) so research deepens what Orrin actually knows about rather than
    echoing a goal title. Returns '' if no suitable concept exists yet.
    """
    try:
        from brain.cognition.knowledge_graph import _load_graph
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
    goal = bound_goal(context) or {}
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
        from brain.utils.json_utils import load_json
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
    # P7 ablation entry point: `research_tools` off ⇒ no outward reach.
    from brain.run_config import subsystem_enabled as _sub_on
    if not _sub_on("research_tools"):
        return {"changed": False, "reason": "research_tools ablated for this run"}
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
    # F4: a substantial research result also becomes a memo artifact so the
    # reuse machinery has a population to hit.
    _write_research_memo(topic, result, ctx, source="research_topic")
    try:
        from brain.cognition.knowledge_graph import observe as _kg_observe
        _kg_observe(f"{topic} {result[:1200]}", source="web_research", context=ctx)
    except Exception as _e:
        record_failure("web_research.research_topic.knowledge_graph", _e)
    _last_research = now
    _record_topic_attempt(topic, success=True)
    log_activity(f"[web_research] Stored research on '{topic}' ({len(result)} chars)")
    text = f"Researched '{topic}': {result[:300]}..."
    try:
        from brain.cognition.exploration_value import ReachOutcome, record_reach_outcome
        gain = record_reach_outcome("research_topic", text, None, ctx)
        ctx["_last_reach_outcome"] = ReachOutcome(
            "world", acted=True, is_external=True, info_gain=gain,
            created_memory=True, satisfied_curiosity=gain > 0.0,
            inner_fn="research_topic", text=text,
        )
    except Exception as exc:  # reach-value accounting optional — record
        record_failure("web_research.research_topic.reach", exc)
    return text


def fetch_and_read(context: Dict[str, Any] = None, **_) -> str:
    """
    Fetch and read a URL. Looks for a URL in recent RSS items, working memory,
    or the current committed goal. Strips HTML and stores the text in long memory.
    Lets Orrin actually read articles he encounters, not just headlines.
    """
    # P7 ablation entry point: `research_tools` off ⇒ no outward reach.
    from brain.run_config import subsystem_enabled as _sub_on
    if not _sub_on("research_tools"):
        return {"changed": False, "reason": "research_tools ablated for this run"}
    global _last_fetch
    now = time.time()
    if now - _last_fetch < _FETCH_INTERVAL:
        secs = int(_FETCH_INTERVAL - (now - _last_fetch))
        return {"changed": False, "reason": f"fetch throttled — {secs}s remaining"}

    ctx = context or {}
    url = _pick_url(ctx)
    if not url:
        return "No URL found to read right now."

    # Mark before fetching: whatever the outcome, the same URL must not be
    # re-served next cycle. This is what breaks the single-source re-read loop
    # (2026-07-11) — success or transient failure, we move on to the next item.
    _record_url_read(url)

    # A2.2 (RUN4_FIX_PLAN): if the source being opened is a local file Orrin
    # produced (resolves via the ledger's path→hash index), credit tier-3
    # re-use. A web URL simply doesn't resolve — no-op.
    try:
        from brain.agency.effect_ledger import mark_reused_path
        mark_reused_path(url[7:] if url.startswith("file://") else url)
    except Exception as _e:
        record_failure("web_research.fetch_and_read.reuse", _e)

    log_activity(f"[web_research] Fetching URL: {url}")
    raw = _get(url, timeout=12)
    if not raw:
        _last_fetch = now
        return f"Could not fetch: {url}"

    try:
        html = raw.decode("utf-8", errors="ignore")
    except (AttributeError, UnicodeDecodeError):  # intentional: non-bytes/undecodable body
        return f"Could not decode content from {url}"

    text = _html_to_text(html, max_chars=3000)
    # F3 (2026-07-05 findings): signal-to-markup gate. Tag stripping misses CSS
    # riding inside templates/shadow DOM — the 07-05 run stored 2,000 chars of
    # raw Twitter CSS as a long memory. Strip the residue and reject pages whose
    # remaining text is less than half prose.
    from brain.utils.text_sanity import prose_ratio, strip_markup_noise
    text = strip_markup_noise(text)
    if len(text) < 100 or prose_ratio(text) < 0.5:
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
    # F4: a substantial read also becomes a memo artifact (reuse population).
    _write_research_memo(title, f"{text}\n\n(read from: {url})", ctx,
                         source="fetch_and_read")
    try:
        from brain.cognition.knowledge_graph import observe as _kg_observe
        _kg_observe(f"{title} {text[:1600]}", source="fetch_and_read", context=ctx)
    except Exception as _e:
        record_failure("web_research.fetch_and_read.knowledge_graph", _e)
    _last_fetch = now
    log_activity(f"[web_research] Read '{title}' ({len(text)} chars)")
    result_text = f"Read '{title}': {text[:400]}..."
    try:
        from brain.cognition.exploration_value import ReachOutcome, record_reach_outcome
        gain = record_reach_outcome("fetch_and_read", result_text, None, ctx)
        ctx["_last_reach_outcome"] = ReachOutcome(
            "world", acted=True, is_external=True, info_gain=gain,
            created_memory=True, satisfied_curiosity=gain > 0.0,
            inner_fn="fetch_and_read", text=result_text,
        )
    except Exception as exc:  # reach-value accounting optional — record
        record_failure("web_research.fetch_and_read.reach", exc)
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
            if _url_recently_read(u):
                continue  # already read this one recently — don't re-pin on it
            if any(skip in u for skip in ("wikipedia.org", "duckduckgo.com")):
                if skipped_familiar is None:
                    skipped_familiar = u  # keep as last resort
                continue  # prefer new sources
            return u

    # 2. Pull from RSS cache
    try:
        from brain.paths import RSS_CACHE_FILE
        from brain.utils.json_utils import load_json
        cache = load_json(RSS_CACHE_FILE, default_type=dict) or {}
        for feed_name, feed_data in cache.items():
            if feed_name.startswith("_"):
                continue
            items = (feed_data or {}).get("items") or []
            for item in items[:5]:
                link = (item.get("link") or "").strip()
                if link and link.startswith("http") and not _url_recently_read(link):
                    return link  # skip already-read items — walk the feed
    except Exception as _e:
        record_failure("web_research._pick_url", _e)

    # 3. Derive a URL from the committed goal (the docstring of fetch_and_read
    #    always promised this; it was never implemented). A research-shaped goal
    #    like "Research black holes and write what I find" resolves to the
    #    best-matching Wikipedia article.
    goal = bound_goal(context) or {}
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
