# brain/cognition/rss_reader.py
# Reads configurable RSS feeds and stores new items in long memory.
from __future__ import annotations

import re
import ssl
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Dict, Any, List

from brain.paths import RSS_CACHE_FILE, RSS_FEEDS_FILE
from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_activity, log_private
from brain.cog_memory.long_memory import update_long_memory
from brain.utils.content_quarantine import quarantine_text, quarantine_extra

_LAST_RSS_TS: float = 0.0
_MIN_INTERVAL_S: float = 1800.0  # at most every 30 minutes

_DEFAULT_FEEDS: List[Dict] = [
    {"name": "Hacker News", "url": "https://news.ycombinator.com/rss"},
    {"name": "MIT News", "url": "https://news.mit.edu/rss/research"},
    {"name": "Quanta Magazine", "url": "https://www.quantamagazine.org/feed/"},
]

_STRIP_TAGS = re.compile(r'<[^>]+>')

# SSL context — same pattern as web_research.py. System Python on some macOS
# setups has a broken cert chain; a bare urlopen() then fails EVERY https feed
# with CERTIFICATE_VERIFY_FAILED, which is why rss_cache.json never held a
# single item (RUN_ISSUES_2026-06-10 §1: fetch_and_read had no URL source).
_SSL_CTX = ssl.create_default_context()
try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX.check_hostname = False
    _SSL_CTX.verify_mode = ssl.CERT_NONE


def read_rss(context: Dict[str, Any] = None) -> str:
    """Fetch one RSS feed (rotating) and store new items in long memory."""
    global _LAST_RSS_TS
    now = time.time()
    if now - _LAST_RSS_TS < _MIN_INTERVAL_S:
        return "Already checked RSS recently — waiting before looking again."

    feeds = load_json(RSS_FEEDS_FILE, default_type=list) or _DEFAULT_FEEDS
    if not feeds:
        return "No RSS feeds configured."

    cache = load_json(RSS_CACHE_FILE, default_type=dict) or {}
    last_idx = cache.get("_last_feed_idx", -1)
    idx = (last_idx + 1) % len(feeds)
    feed = feeds[idx]

    items = _fetch_feed(feed["url"])
    if not items:
        cache["_last_feed_idx"] = idx
        save_json(RSS_CACHE_FILE, cache)
        # Visible (activity-log) failure: this branch failed silently for weeks
        # while the cache stayed empty — log_private alone hid the breakage.
        log_activity(f"[rss_reader] Could not fetch {feed['name']} ({feed['url']})")
        return f"Could not fetch {feed['name']}."

    seen = set(cache.get("_seen_guids", []))
    new_items = [i for i in items if i.get("guid") not in seen][:3]

    for item in new_items:
        # Quarantine: feed title/summary come from an external publisher and
        # will flow into prompts that drive goals and action selection
        # (Finding 7). Wrap them inline with the untrusted-content marker.
        title_q = quarantine_text(item['title'], source=f"rss:{feed['name']}")
        summary_q = quarantine_text(item['summary'][:200], source=f"rss:{feed['name']}")
        update_long_memory(
            f"[rss:{feed['name']}] {title_q}: {summary_q}",
            emotion="exploration_drive",
            event_type="world_perception",
            importance=2,
            context=context or {},
            extra=quarantine_extra({"source": "rss", "feed": feed["name"], "link": item.get("link", "")}),
        )
        seen.add(item.get("guid") or item["title"])

    cache["_last_feed_idx"] = idx
    cache["_seen_guids"] = list(seen)[-500:]
    cache[feed["name"]] = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "items": items[:10],
    }
    save_json(RSS_CACHE_FILE, cache)
    _LAST_RSS_TS = now

    result = f"Read {len(new_items)} new items from {feed['name']}"
    log_activity(f"[rss_reader] {result}")
    return result


def _fetch_feed(url: str, timeout: int = 12) -> List[Dict]:
    """Fetch and parse an RSS 2.0 or Atom feed."""
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 Orrin/1.0 RSS Reader"}
        )
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
    except Exception as e:
        log_private(f"[rss_reader] fetch failed for {url}: {e}")
        return []

    items: List[Dict] = []

    # RSS 2.0
    for item in root.findall(".//item"):
        title   = (item.findtext("title") or "").strip()
        desc    = _STRIP_TAGS.sub("", (item.findtext("description") or "")).strip()[:300]
        link    = (item.findtext("link") or "").strip()
        guid    = (item.findtext("guid") or link or title)
        if title:
            items.append({"title": title, "summary": desc, "link": link, "guid": guid})

    # Atom
    if not items:
        _NS = {"a": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("a:entry", _NS):
            title   = (entry.findtext("a:title", namespaces=_NS) or "").strip()
            summary = _STRIP_TAGS.sub("", (entry.findtext("a:summary", namespaces=_NS) or "")).strip()[:300]
            link_el = entry.find("a:link", _NS)
            link    = link_el.get("href", "") if link_el is not None else ""
            guid    = (entry.findtext("a:id", namespaces=_NS) or link or title)
            if title:
                items.append({"title": title, "summary": summary, "link": link, "guid": guid})

    return items[:20]
