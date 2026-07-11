# Fix: `fetch_and_read` single-source re-read loop

*Found mid-run 2026-07-11 while auditing a live instance. Fixed same day.*

## Symptom

A live instance (pid 59935, ~4,200 cycles) looked healthy on every vital —
`active` energy, motivation 0.75, signal_stability 0.99, no crashes — but the
runtime log showed the same action grinding for ~20 minutes straight:

```
[kg] fetch_and_read(spacy): rejected 14 candidate(s): '2026':noise, 'FPGA':noise,
     'RF':noise, 'CIA':noise, 'EME':noise, ...
effect recorded kind=file_write novelty=0.002 sig=0.314 goal=aspiration-self_understanding
```

The `aspiration-self_understanding` goal re-read **one** article (Jeff Geerling's
QuadRF blog post — `FPGA/RF/CIA/EME` are terms *from that page*) over and over,
each time at novelty `0.002`. It was ~21 % of recent effects. Milder than the
74–84 % ignition monopolies of Runs 2–3 (the anti-monopoly work held — 15 other
goals still got cycles), but a persistent zero-value loop.

## Why it stayed invisible

`_write_research_memo` leaves de-duplication "to the ledger" — no pile-up of
*files* appeared because each rewrite targets the same per-goal path. Health
dashboards and artifact counts looked fine.

> **Post-run correction (2026-07-11 full analysis):** the ledger did **not**
> swallow the credit. Each rewritten memo embeds a fresh
> `source: fetch_and_read · <timestamp>` footer, so every rewrite hashes new and
> the content-hash dedupe missed it: **387 of 403 rewrites were credited**
> (novelty ~0.002, significance 0.314 each), pumping the committed goal's
> `commitment_signals` value_ema to 0.8142 and locking the 92 % commitment
> monopoly. See `demo_runs/2026-07-11-run/2026-07-11_deeper_pass.md` §1. The
> URL cache fixes the re-read; the credit inflation additionally needs (a)
> volatile footers normalized out of the ledger hash, and (b) repeat-credit
> decay per artifact path.

## Root cause

`brain/cognition/web_research.py :: _pick_url()` picked the source, and it
returned the **same URL deterministically every call**:

- **Tier 2 (RSS cache)** walks feeds and returns the *first `http` link in
  `items[:5]`*. The top Hacker News item was the QuadRF post → same URL every
  cycle.
- **There was no per-URL "already read" record for `fetch_and_read`.** The only
  visited-tracking was:
  - `mark_reused_path` — gated to local `file://` paths only, never web URLs.
  - `_topic_cache` — a negative-result cache keyed by *topic string*, used by
    `research_topic`, never touched by URL-based `fetch_and_read`.
- **Habituation does not gate selection.** `brain/cognition/habituation.py` only
  scales *affective salience* and drips `stagnation_signal` (was 0.10 — nowhere
  near forcing a switch). It is keyed by WM-content-hash / goal-id, not by URL,
  so it never reaches `_pick_url`.

So: goal selects `fetch_and_read` → `_pick_url` returns the same RSS item → read
→ memo deduped → next cycle, identical.

## Fix

A per-URL visited cache mirroring the existing `_topic_cache` pattern
(`web_research.py`):

- `_url_cache: Dict[str, float]` (url → last-read ts) with `_url_recently_read()`
  / `_record_url_read()` helpers. Read URLs are skipped for 6 h (`_DONE_CACHE_TTL`,
  matching the topic cache's success TTL). In-process only, like `_topic_cache`;
  a fresh life restarts clean.
- `_pick_url` now skips recently-read URLs in **tier 1 (working memory)** and
  **tier 2 (RSS)** — tier 2 walks to the next unread feed item instead of
  re-pinning on `items[0]`.
- `fetch_and_read` calls `_record_url_read(url)` **before** fetching, so success
  *or* transient failure both prevent an immediate re-serve.

Tiers 3 (goal-derived Wikipedia) and 4 (familiar-source last resort) are left as
last resorts — the loop lived entirely in tiers 1–2.

## Tests

`tests/brain/test_web_research_url_dedup.py`:
- `_pick_url` walks the feed to the next unread item after one is consumed.
- a recently-read URL in working memory is skipped.
- the 6 h TTL expires and the URL becomes eligible again.

`make verify`: ruff + project mypy gate clean; full suite 1481 passed. (One
pre-existing, unrelated failure —
`test_selector_characterization[exploration_drive]` — fails on a clean tree too;
it tracks the already-dirty `brain/data/` selector seeds, not this change.)

## Follow-ups (not done here)

- The deeper lever is *selection*: nothing made the goal tire of `fetch_and_read`
  once its info-gain collapsed. Habituation gating action selection (not just
  affect) would generalize past this one action. Tracked as a candidate for the
  next run-fix pass, not fixed in this surgical change.
