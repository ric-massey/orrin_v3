# brain/cognition/language_acquisition.py
#
# NOTE ON SCOPE (not a duplicate of cognition/language/):
#   This is the SYMBOLIC phrasing tier — it mines reusable discourse-marker
#   openers from what he reads and lends them to the template speech builder.
#   The NEURAL language organ (his from-scratch transformer that learns to
#   produce language) lives in the package cognition/language/ (tokenizer.py,
#   native_lm.py, acquisition.py, voice.py). The two are complementary layers,
#   not rivals: this one broadens HOW the template pipeline phrases things today;
#   the neural organ is meant to gradually take over speech (cognition/language/
#   voice.py). Keep them distinct.
#
# Tier 3 — learn language from reading (no LLM).
#
# Every article Orrin reads is language data. A developing mind picks up turns of
# phrase by exposure; this does the symbolic equivalent: it mines *content-neutral
# framing phrases* — sentence-initial discourse markers like "in fact", "over
# time", "by contrast", "more generally" — from the text he has actually read,
# and banks them with a frequency count. His speech composer then draws on this
# growing repertoire, so HOW he phrases things broadens as he reads more, while
# WHAT he says stays his own grounded content.
#
# Why framing phrases specifically: they are reusable and topic-neutral (safe to
# transplant), unlike content clauses. We deliberately avoid lifting subjects or
# full sentences — that would be parroting, not learning to phrase.
#
# Fully symbolic. Runs during the dream/consolidation pass (the "integrate what I
# read" moment). Bank is bounded and frequency-pruned.
from __future__ import annotations

import json
import re
from typing import Dict, List

from brain.paths import DATA_DIR, LONG_MEMORY_FILE
from brain.utils.json_utils import load_json
from brain.utils.log import log_activity

_BANK_FILE = DATA_DIR / "learned_phrases.json"
_MAX_BANK = 80            # cap distinct learned openers
_MIN_USES_TO_KEEP = 1
_SCAN_WINDOW = 200        # how many recent long-memory entries to scan

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")

# Words that legitimately begin a *framing* clause (prepositional / adverbial /
# discourse connective). An opener is only learned if it starts with one of these
# or is a single -ly adverb — this keeps discourse markers and rejects topic
# subjects ("black holes, …") and pronoun openers.
_FRAMING_STARTERS = {
    "in", "on", "by", "as", "over", "after", "before", "despite", "although",
    "while", "when", "since", "with", "for", "at", "from", "through", "under",
    "beyond", "unlike", "instead", "however", "therefore", "thus", "meanwhile",
    "similarly", "conversely", "interestingly", "notably", "importantly",
    "generally", "typically", "often", "sometimes", "eventually", "ultimately",
    "essentially", "basically", "historically", "originally", "recently",
    "increasingly", "surprisingly", "crucially", "fundamentally", "broadly",
    "specifically", "initially", "finally", "overall", "today",
}

# Read-sourced content only — these carry real prose worth learning phrasing from.
_READ_PREFIXES = ("[research]", "[read]")


def _candidate_openers(text: str) -> List[str]:
    """Extract content-neutral framing phrases from one block of read text."""
    out: List[str] = []
    for sent in _SENT_SPLIT.split(text or ""):
        sent = sent.strip()
        if "," not in sent:
            continue
        head, _, tail = sent.partition(",")
        head = head.strip()
        if len(tail.split()) < 4:          # must actually introduce a clause
            continue
        words = head.split()
        if not (1 <= len(words) <= 5):
            continue
        norm = head.lower()
        # Content-neutral: only lowercase letters/spaces/apostrophes (no digits,
        # no mid-phrase capitals → no proper nouns, no punctuation salad).
        if not re.fullmatch(r"[a-z][a-z ']*", norm):
            continue
        first = words[0].lower()
        if first in _FRAMING_STARTERS or (len(words) == 1 and first.endswith("ly")):
            out.append(norm)
    return out


def _load_bank() -> Dict[str, int]:
    b = load_json(_BANK_FILE, default_type=dict)
    return b if isinstance(b, dict) else {}


def _save_bank(bank: Dict[str, int]) -> None:
    # Prune to the most-frequent _MAX_BANK entries so the bank stays bounded.
    if len(bank) > _MAX_BANK:
        bank = dict(sorted(bank.items(), key=lambda kv: kv[1], reverse=True)[:_MAX_BANK])
    try:
        _BANK_FILE.write_text(json.dumps(bank, indent=2), encoding="utf-8")
    except Exception as e:
        log_activity(f"[language_acquisition] could not save phrase bank: {e}")


def learn_from_reading() -> Dict[str, int]:
    """
    Scan recent read/research memories, harvest framing phrases, and fold them
    into the learned phrase bank with frequency counts. Returns a small summary.
    Called during the dream cycle (LLM-free).
    """
    long_mem = load_json(LONG_MEMORY_FILE, default_type=list) or []
    bank = _load_bank()
    before = len(bank)
    learned = 0
    for entry in long_mem[-_SCAN_WINDOW:]:
        if not isinstance(entry, dict):
            continue
        content = str(entry.get("content", ""))
        low = content.strip().lower()
        etype = str(entry.get("event_type", "")).lower()
        if not (low.startswith(_READ_PREFIXES) or etype in ("world_perception",)):
            continue
        for opener in _candidate_openers(content):
            bank[opener] = bank.get(opener, 0) + 1
            learned += 1
    if learned:
        _save_bank(bank)
    summary = {"scanned": min(len(long_mem), _SCAN_WINDOW),
               "phrases_seen": learned, "bank_size": len(bank), "new": len(bank) - before}
    if learned:
        log_activity(
            f"[language_acquisition] learned phrasing from reading: "
            f"+{summary['new']} new, {learned} reinforced, bank={len(bank)}"
        )
    return summary


def learned_openers(n: int = 6, min_uses: int = 2) -> List[str]:
    """
    Return the most-reinforced learned framing phrases (those seen >= min_uses),
    capitalised for sentence-initial use. Empty early on; grows as he reads.
    """
    bank = _load_bank()
    ranked = sorted(
        ((p, c) for p, c in bank.items() if c >= min_uses),
        key=lambda kv: kv[1], reverse=True,
    )
    return [p[:1].upper() + p[1:] for p, _ in ranked[:n]]
