# brain/cognition/language/voice.py
#
# The HANDOFF: lets Orrin's own native language organ take over his speech — but
# only once it's good enough, and only when the symbolic layer judges the draft
# coherent. Until then it's a no-op and his template pipeline stays in control.
#
# This is the staged, quality-gated bridge from "template mouth" → "his own
# voice." It is the neural-symbolic pattern made concrete: the organ *proposes*,
# the symbolic layer *checks and grounds*, and only a draft that passes is spoken.
# Wiring it in now is safe — the gate stays shut until schooling makes the organ
# fluent, at which point he begins speaking in his own learned voice automatically.
from __future__ import annotations

import re
import time
from typing import Dict, Optional

from utils.log import log_activity
from cognition.language import native_lm, library, tokenizer as tok

# Maturity gate — the organ may speak only past ALL of these. Conservative so a
# half-trained organ never babbles at the user; loosen as schooling progresses.
_MIN_STEPS      = 20_000
_MIN_TOKENS     = 2_000_000
_MAX_PERPLEXITY = 120.0       # held-out perplexity must be at/below this
_PPL_CACHE_S    = 600.0       # re-measure perplexity at most every 10 min

_ppl_cache: Dict = {"t": 0.0, "val": None}
_ALPHA = re.compile(r"[A-Za-z']+")


def _perplexity() -> Optional[float]:
    now = time.time()
    if _ppl_cache["val"] is not None and now - _ppl_cache["t"] < _PPL_CACHE_S:
        return _ppl_cache["val"]
    sample = library.read_text(40000)
    val = native_lm.evaluate(sample) if sample else None
    _ppl_cache.update(t=now, val=val)
    return val


def lm_ready() -> bool:
    """Is the organ mature enough to speak? Gate on training volume AND held-out
    perplexity, so it only takes over once it actually produces real language.
    Cheap short-circuits first so an immature organ adds no latency to replies."""
    if not native_lm.available() or not tok.exists():
        return False
    st = native_lm.status()
    if not st.get("device"):                       # not built / no tokenizer
        return False
    if int(st.get("train_steps", 0)) < _MIN_STEPS:
        return False
    if int(st.get("tokens_seen", 0)) < _MIN_TOKENS:
        return False
    ppl = _perplexity()
    return ppl is not None and ppl <= _MAX_PERPLEXITY


def _acceptable(draft: str, comprehension: Dict) -> bool:
    """The symbolic check on neural output — reject gibberish or off-topic drafts
    so a still-learning organ never speaks nonsense to the user."""
    s = (draft or "").strip()
    if not (12 <= len(s) <= 400):
        return False
    words = _ALPHA.findall(s)
    if len(words) < 3:
        return False
    if sum(len(w) for w in words) / max(1, len(s)) < 0.55:   # alpha density
        return False
    low = [w.lower() for w in words]
    if len(set(low)) / len(low) < 0.5:                       # repetition guard
        return False
    topics = " ".join(comprehension.get("topics", []) or []).lower()
    if topics:                                               # must stay on-topic
        toks = set(re.findall(r"[a-z']{4,}", topics))
        if toks and not (toks & set(low)):
            return False
    return True


def _prompt(comprehension: Dict, plan: Dict) -> str:
    primary = str((plan.get("primary") or plan.get("content") or "")).strip()
    if primary:
        return primary[:160] + " "
    topics = ", ".join((comprehension.get("topics") or [])[:3])
    return f"About {topics}: " if topics else ""


def lm_draft(context: Dict, plan: Dict, comprehension: Dict) -> str:
    """If the organ is ready, let it speak — checked. Returns "" otherwise, so the
    template pipeline remains the fallback (the handoff is gradual, never abrupt)."""
    try:
        if not lm_ready():
            return ""
        draft = native_lm.generate(_prompt(comprehension, plan), length=60, temperature=0.7)
        parts = re.split(r"(?<=[.!?])\s+", (draft or "").strip())
        draft = " ".join(parts[:2]).strip()
        if _acceptable(draft, comprehension):
            log_activity("[voice] native organ produced reply (gated + checked)")
            return draft
    except Exception:
        pass
    return ""
