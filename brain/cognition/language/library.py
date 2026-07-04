# brain/cognition/language/library.py
#
# Orrin's library — a house full of books instead of an empty room (#1).
#
# His language faculty is data-starved, not broken. The fastest, purest fix is to
# give him a great deal of real, clean English to READ — public-domain text he
# ingests himself and consolidates in sleep. This is not "adding an LLM": it's
# enriching his environment, the way raising a child among books accelerates
# language without implanting anyone else's mind.
#
# Curriculum (#3): books are ordered roughly simple → rich, so he learns from
# plain language first (how children acquire it) before dense prose.
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import List

from brain.utils.failure_counter import record_failure
from brain.utils.log import log_activity

_UA = {"User-Agent": "OrrinLanguageLearner/1.0 (personal research; contact: local)"}

_LIB = Path(__file__).resolve().parents[2] / "data" / "language" / "library"

# Public-domain Project Gutenberg IDs, ordered simple → rich (curriculum).
_CURRICULUM = [
    11,     # Alice's Adventures in Wonderland — simple, playful
    19033,  # Aesop's Fables — short, plain
    16,     # Peter Pan — simple narrative
    74,     # The Adventures of Tom Sawyer
    1661,   # The Adventures of Sherlock Holmes — clear prose
    1342,   # Pride and Prejudice — richer
    84,     # Frankenstein — dense
    10,     # The King James Bible — foundational English: narrative, poetry, law
    2701,   # Moby Dick — very dense
]

# Topical packs (public-domain Gutenberg IDs). Failures are skipped gracefully,
# so a wrong/edition-shifted id just doesn't load — safe to be generous.
_NURSERY = [
    19033,  # Aesop's Fables
    2591,   # Grimm's Fairy Tales
    1597,   # Hans Andersen's Fairy Tales
    7439,   # English Fairy Tales
    2781,   # Just So Stories
    236,    # The Jungle Book
    25609,  # A Child's Garden of Verses
    55,     # The Wonderful Wizard of Oz
    289,    # The Wind in the Willows
    113,    # The Secret Garden
    271,    # Black Beauty
    1448,   # Heidi
]
_SCIENCE = [
    1228,   # On the Origin of Species
    944,    # The Voyage of the Beagle
    14474,  # The Chemical History of a Candle (Faraday)
    5001,   # Relativity: The Special & General Theory (Einstein)
    33283,  # Side-lights on Astronomy (Newcomb)
    37729,  # The Story of the Heavens
    1268,   # The Mysterious Island (science-adventure)
    2009,   # The Origin of Species (2nd ed)
    15491,  # The Wonders of Life (Haeckel)
    768,    # Wuthering Heights  (placeholder-rich prose; harmless if it loads)
]
_CLASSICS = [
    120, 345, 98, 1400, 76, 35, 36, 46, 829, 521, 514, 45, 1080, 2542, 1232,
    # Treasure Island, Dracula, Tale of Two Cities, Great Expectations, Huck Finn,
    # Time Machine, War of the Worlds, A Christmas Carol, Gulliver, Robinson Crusoe,
    # Little Women, Anne of Green Gables, A Modest Proposal, A Doll's House, The Prince
]

_GUT_HEADER = re.compile(r"\*\*\*\s*START OF (THE|THIS)? ?PROJECT GUTENBERG.*?\*\*\*", re.S | re.I)
_GUT_FOOTER = re.compile(r"\*\*\*\s*END OF (THE|THIS)? ?PROJECT GUTENBERG.*", re.S | re.I)


def _strip_gutenberg(text: str) -> str:
    """Remove Gutenberg license header/footer so only the actual book remains."""
    m = _GUT_HEADER.search(text)
    if m:
        text = text[m.end():]
    m = _GUT_FOOTER.search(text)
    if m:
        text = text[:m.start()]
    return text.strip()


def fetch_books(ids: List[int]) -> int:
    """Download given Gutenberg book IDs into the library (skips ones already
    present). Returns count newly fetched. Best-effort; needs network."""
    try:
        import requests
    except Exception:
        log_activity("[library] requests unavailable — cannot fetch")
        return 0
    _LIB.mkdir(parents=True, exist_ok=True)
    got = 0
    for bid in ids:
        dest = _LIB / f"pg{bid}.txt"
        if dest.exists() and dest.stat().st_size > 1000:
            continue
        text = None
        for url in (f"https://www.gutenberg.org/cache/epub/{bid}/pg{bid}.txt",
                    f"https://www.gutenberg.org/files/{bid}/{bid}-0.txt"):
            try:
                r = requests.get(url, timeout=20, headers=_UA)
                if r.status_code == 200 and len(r.text) > 1000:
                    text = r.text
                    break
            except requests.RequestException:  # intentional: network error → try next url
                continue
        time.sleep(0.5)  # be polite to Gutenberg
        if not text:
            continue
        try:
            # Capture the real title from the metadata BEFORE we strip the header,
            # and store it as a "Title:" line so it survives for later display.
            mt = re.search(r"^title:\s*(.+)$", text[:3000], re.I | re.M)
            body = _strip_gutenberg(text)
            if mt:
                body = f"Title: {mt.group(1).strip()}\n\n" + body
            dest.write_text(body, encoding="utf-8")
            got += 1
            log_activity(f"[library] acquired book {bid} ({dest.stat().st_size // 1024} KB)")
        except Exception as exc:  # write/parse failure for one book — record, skip it
            record_failure("library.fetch_books", exc)
            continue
    return got


def fetch_wikipedia(n_articles: int = 50) -> int:
    """
    The endless tap: pull full-text extracts of random Wikipedia articles via the
    API (clean plain text, no dump parsing) into the library. Run it as many times
    as you like — this is how he gets *more than he could ever read*. Best-effort.
    """
    try:
        import requests
    except ImportError:  # intentional: optional dep absent — no fetch
        return 0
    _LIB.mkdir(parents=True, exist_ok=True)
    got = 0
    api = "https://en.wikipedia.org/w/api.php"
    while got < n_articles:
        batch = min(10, n_articles - got)
        params = {
            "action": "query", "format": "json",
            "generator": "random", "grnnamespace": 0, "grnlimit": batch,
            "prop": "extracts", "explaintext": 1, "exsectionformat": "plain",
        }
        try:
            r = requests.get(api, params=params, timeout=20, headers=_UA)
            pages = (r.json().get("query", {}) or {}).get("pages", {}) or {}
        except Exception:
            break
        for pid, page in pages.items():
            text = str(page.get("extract", "") or "").strip()
            if len(text) < 400:          # skip stubs
                continue
            title = str(page.get("title", "") or "").strip()
            if title:
                text = f"Title: {title}\n\n" + text
            try:
                (_LIB / f"wiki_{pid}.txt").write_text(text, encoding="utf-8")
                got += 1
            except Exception as exc:  # write failure for one article — record, skip it
                record_failure("library.fetch_wikipedia", exc)
                continue
        time.sleep(0.4)  # be polite to Wikipedia
    if got:
        log_activity(f"[library] pulled {got} Wikipedia articles; library now {size_chars()//1024} KB")
    return got


def populate_big(wikipedia: int = 60) -> dict:
    """Fill the shelves: nursery + science + classics books, plus a batch of
    Wikipedia articles. Re-runnable; skips what's already present."""
    books = fetch_books(_NURSERY + _SCIENCE + _CLASSICS)
    wiki = fetch_wikipedia(wikipedia)
    return {"books_fetched": books, "wiki_fetched": wiki, "library_kb": size_chars() // 1024}


# RUN4_FIX_PLAN §3.8 — a small BUNDLED public-domain starter, so the shelf is
# never empty offline (Gutenberg fetch needs network; a native-LM deployment may
# have none). These are firmly public-domain Aesop fables (pre-1500s, no
# copyright). A stocked shelf also feeds A2's read-path reuse: a produced memo
# that ends up here can be re-read and reuse-credited.
_STARTER_BUNDLED = {
    "aesop_starter.txt": (
        "AESOP'S FABLES (a small starter shelf)\n\n"
        "THE FOX AND THE GRAPES\n"
        "A hungry Fox saw some fine bunches of Grapes hanging from a vine that was "
        "trained along a high trellis, and did his best to reach them by jumping as "
        "high as he could into the air. But it was all in vain, for they were just "
        "out of reach: so he gave up trying, and walked away with an air of dignity "
        "and unconcern, remarking, \"I thought those Grapes were ripe, but I see now "
        "they are quite sour.\"\n\n"
        "THE TORTOISE AND THE HARE\n"
        "A Hare was one day making fun of a Tortoise for being so slow upon his feet. "
        "\"Wait a bit,\" said the Tortoise; \"I'll run a race with you, and I'll wager "
        "that I win.\" The Hare, thinking the whole thing impossible, agreed. The Fox, "
        "who had consented to act as judge, marked the distance and started the "
        "runners off. The Hare was soon far out of sight, and, to make the Tortoise "
        "feel how absurd it was for him to try a race, lay down to have a nap. The "
        "Tortoise meanwhile kept plodding on, and in time reached the goal. At last "
        "the Hare woke up with a start, and dashed on at his fastest, but only to "
        "find that the Tortoise had already won the race.\n\n"
        "THE ANT AND THE GRASSHOPPER\n"
        "In a field one summer's day a Grasshopper was hopping about, chirping and "
        "singing to its heart's content. An Ant passed by, bearing along with great "
        "toil an ear of corn he was taking to the nest. \"Why not come and chat with "
        "me,\" said the Grasshopper, \"instead of toiling and moiling in that way?\" "
        "\"I am helping to lay up food for the winter,\" said the Ant, \"and recommend "
        "you to do the same.\" \"Why bother about winter?\" said the Grasshopper; \"we "
        "have got plenty of food at present.\" But the Ant went on its way and "
        "continued its toil. When the winter came the Grasshopper had no food, and "
        "found itself dying of hunger, while it saw the ants distributing every day "
        "corn and grain from the stores they had collected in the summer. Then the "
        "Grasshopper knew: it is best to prepare for the days of necessity.\n"
    ),
}


def _write_bundled_starter() -> int:
    """Write the bundled public-domain texts to the shelf (idempotent). Returns
    the number newly written. The offline floor under populate_starter."""
    _LIB.mkdir(parents=True, exist_ok=True)
    wrote = 0
    for name, text in _STARTER_BUNDLED.items():
        p = _LIB / name
        if not p.exists():
            try:
                p.write_text(text, encoding="utf-8")
                wrote += 1
            except OSError as exc:
                record_failure("library._write_bundled_starter", exc)
    return wrote


def populate_starter(n: int = 3) -> int:
    """Fetch the first n curriculum books so he has something to read. Idempotent.
    Falls back to a bundled public-domain starter when the network fetch adds
    nothing AND the shelf is still empty — so read_a_book always has a book."""
    got = fetch_books(_CURRICULUM[:n])
    if got == 0 and size_chars() == 0:
        got += _write_bundled_starter()
    return got


def size_chars() -> int:
    if not _LIB.exists():
        return 0
    return sum(f.stat().st_size for f in _LIB.glob("*.txt"))


def read_text(max_chars: int = 40000) -> str:
    """Return a chunk of library text for a learning bout, preferring earlier
    (simpler) books — a gentle curriculum. Walks book-by-book in order."""
    if not _LIB.exists():
        return ""
    import random
    files = sorted(_LIB.glob("*.txt"))
    if not files:
        return ""
    # Bias toward the simpler (curriculum-early) books, but include variety.
    f = random.choice(files[: max(1, len(files) // 2 + 1)])
    try:
        txt = f.read_text(encoding="utf-8", errors="ignore")
        if len(txt) <= max_chars:
            return txt
        start = random.randint(0, len(txt) - max_chars)
        return txt[start:start + max_chars]
    except Exception as exc:  # book read failed — record, skip this bout
        record_failure("library.read_text", exc)
        return ""


# ── Browsing the shelves: picking and reading a PARTICULAR book ──────────────
# When he's bored he doesn't just sip random text — he can look over the shelf,
# let one book draw him (by curiosity/interest, or simply something he hasn't
# read), settle in, and read THAT one. We track how often each book's been read
# so novelty pulls him toward the unread, the way a person drifts to a new spine.

_READS_FILE = _LIB.parent / "book_reads.json"


def _load_reads() -> dict:
    try:
        if _READS_FILE.exists():
            return json.loads(_READS_FILE.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # bad/unreadable reads ledger — record, treat as empty
        record_failure("library._load_reads", exc)
    return {}


def _save_reads(reads: dict) -> None:
    try:
        _READS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _READS_FILE.write_text(json.dumps(reads), encoding="utf-8")
    except Exception as exc:  # external I/O persisting the reads ledger
        record_failure("library._save_reads", exc)


_TITLE_RE = re.compile(r"^title:\s*(.+)$", re.I)
_TITLE_NOISE = re.compile(
    r"^\s*(\[illustration|note:|produced by|project gutenberg|this ebook|this file|"
    r"\*|http|transcriber|contents|chapter\b|copyright|release date|posting date|"
    r"language:|character set|end of|start of|by\s+\w+\s*$|there are several|"
    r"the original|updated:|edition\b)",
    re.I,
)


def _title_of(path: Path) -> str:
    """A human-readable title for a book/article — for his own sense of what he
    chose to read, and for the UI/logs. Skips Gutenberg boilerplate."""
    try:
        head = path.read_text(encoding="utf-8", errors="ignore")[:3000]
    except Exception:
        head = ""
    # Explicit "Title:" metadata wins if present.
    for line in head.splitlines():
        m = _TITLE_RE.match(line.strip())
        if m:
            return m.group(1).strip()[:70]
    # Otherwise the first real line that looks like a title: not boilerplate, and
    # not a mid-sentence fragment (real titles don't begin with a lowercase word).
    for line in head.splitlines():
        s = line.strip()
        if len(s) < 4 or not any(ch.isalpha() for ch in s) or _TITLE_NOISE.match(s):
            continue
        if s[:1].islower():
            continue
        return s[:70]
    return path.stem


def list_books() -> List[dict]:
    """The shelf: every book/article he can choose, with size and how often he's
    read it. Sorted simplest-first (curriculum order, then the rest)."""
    if not _LIB.exists():
        return []
    reads = _load_reads()
    out = []
    for f in sorted(_LIB.glob("*.txt")):
        out.append({
            "name": f.name,
            "title": _title_of(f),
            "kb": f.stat().st_size // 1024,
            "reads": int(reads.get(f.name, 0)),
            "kind": "wikipedia" if f.name.startswith("wiki_") else "book",
        })
    return out


def pick_book(topics: List[str] | None = None, prefer_novel: bool = True) -> Path | None:
    """Let a book draw him. If `topics` (current interests) match a book's title
    or opening, that one calls to him; otherwise boredom pulls him toward what he
    hasn't read yet — with enough randomness that browsing stays free, not rote."""
    if not _LIB.exists():
        return None
    import random
    files = sorted(_LIB.glob("*.txt"))
    if not files:
        return None
    reads = _load_reads()

    # Interest first: does anything on the shelf speak to what he's curious about?
    if topics:
        toks = [t.lower() for t in topics if isinstance(t, str) and len(t) >= 4]
        if toks:
            matches = []
            for f in files:
                try:
                    blob = (f.name + " " + _title_of(f) + " " +
                            f.read_text(encoding="utf-8", errors="ignore")[:2000]).lower()
                except OSError:  # intentional: unreadable file → skip in topic match
                    continue
                if any(t in blob for t in toks):
                    matches.append(f)
            if matches:
                return random.choice(matches)

    if prefer_novel:
        # Boredom → reach for the unread. Take the least-read third, choose freely.
        files.sort(key=lambda f: reads.get(f.name, 0))
        pool = files[: max(1, len(files) // 3)]
        return random.choice(pool)
    return random.choice(files)


def read_book(selector: Path | str | None = None, max_chars: int = 50000,
              topics: List[str] | None = None) -> tuple[str, str]:
    """Settle in with a particular book and return (title, text). Marks it read,
    so novelty later steers him toward books he hasn't opened. `selector` may be a
    Path, a filename, or None (let one draw him via `pick_book`)."""
    if isinstance(selector, str):
        cand = _LIB / selector
        path = cand if cand.exists() else pick_book(topics)
    elif isinstance(selector, Path):
        path = selector
    else:
        path = pick_book(topics)
    if not path or not path.exists():
        return ("", "")
    import random
    try:
        txt = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:  # book read failed — record, nothing to read
        record_failure("library.read_book", exc)
        return ("", "")
    reads = _load_reads()
    reads[path.name] = int(reads.get(path.name, 0)) + 1
    _save_reads(reads)
    # A2.2 (RUN4_FIX_PLAN): if this shelf file is one Orrin himself produced
    # (it resolves through the effect ledger's path→hash index), reading it is
    # tier-3 re-use — the ungameable significance signal. No-op for the
    # public-domain stock.
    try:
        from brain.agency.effect_ledger import mark_reused_path
        mark_reused_path(path)
    except Exception as exc:
        record_failure("library.read_book.reuse", exc)
    title = _title_of(path)
    if len(txt) <= max_chars:
        return (title, txt)
    start = random.randint(0, len(txt) - max_chars)
    return (title, txt[start:start + max_chars])
