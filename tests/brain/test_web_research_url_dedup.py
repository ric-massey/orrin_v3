# Per-URL dedup for fetch_and_read's source picker.
#
# Regression guard for the 2026-07-11 single-source re-read loop: _pick_url's
# RSS tier always returned the first item of the first feed, and nothing
# recorded that a URL had already been read, so a research aspiration re-fetched
# the same article every cycle at near-zero novelty (the effect ledger deduped
# the memo, hiding it). _pick_url must now skip already-read URLs and walk to the
# next unread feed item.

from brain.utils.json_utils import save_json
from brain.paths import RSS_CACHE_FILE
from brain.cognition import web_research as wr


def _seed_rss(*links: str) -> None:
    save_json(RSS_CACHE_FILE, {
        "Test Feed": {"items": [{"link": u} for u in links]},
    })


def _reset_url_cache() -> None:
    wr._url_cache.clear()


def test_pick_url_walks_feed_instead_of_repinning():
    _reset_url_cache()
    _seed_rss(
        "https://example.com/article-one",
        "https://example.com/article-two",
    )
    ctx = {"working_memory": []}

    first = wr._pick_url(ctx)
    assert first == "https://example.com/article-one"

    # Simulate fetch_and_read having consumed it.
    wr._record_url_read(first)

    # Next pick must advance to the unread item, not re-serve the first.
    second = wr._pick_url(ctx)
    assert second == "https://example.com/article-two"


def test_recently_read_url_is_skipped_in_working_memory_tier():
    _reset_url_cache()
    _seed_rss()  # empty feeds so tier 1 is the only source
    url = "https://example.com/read-me"
    ctx = {"working_memory": [{"content": f"saw this link {url}"}]}

    assert wr._pick_url(ctx) == url
    wr._record_url_read(url)
    # Same WM, but the URL is now marked read → tier 1 skips it.
    assert wr._pick_url(ctx) != url


def test_url_read_ttl_expiry(monkeypatch):
    _reset_url_cache()
    now = [1000.0]
    monkeypatch.setattr(wr.time, "time", lambda: now[0])
    wr._record_url_read("https://example.com/x")
    assert wr._url_recently_read("https://example.com/x") is True
    # Past the 6h success TTL it is eligible again.
    now[0] += wr._DONE_CACHE_TTL + 1
    assert wr._url_recently_read("https://example.com/x") is False
