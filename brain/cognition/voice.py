"""
brain/cognition/voice.py — THE TRANSCRIPT.

The stream of what Orrin actually SAYS, in his own words, kept apart from
everything the runtime says *about* him.

Two kinds of English come out of this codebase and only one of them is his:

  * his — felt content that won the workspace ("a strong sense of being stuck"),
    an introspection miss ("I thought that would happen and it felt true — but
    behavior disagreed"), the question a close-out just answered or failed to,
    a goal he committed to, an artifact composed through the expression door,
    his final thoughts. Every one of those exists because a real internal state
    crossed a real line.
  * the narrator's — "Orrin pruned 2 long memories", chunk-merge bookkeeping,
    bandit arithmetic. Third person, written by the machinery about the machine.

Both land in private_thoughts.txt with no marker between them, one his line per
fifty of the narrator's. This module is the separation: call sites that hold a
genuinely first-person utterance route it here, and nothing else may. What lands
here is a bounded ring (drained once per cycle into the `voice` telemetry field)
plus an append-only JSONL transcript, so the UI's Voice room and a post-mortem
read the same words.

Hard rules:
  * NEVER composes. This module filters, veils and records; it authors no
    sentence of its own. A UI-authored gloss is not his voice (that mistake is
    already made once, in the Watch page's status line).
  * The prose-stitcher (the narrative composer) is NOT a source. Its output is
    working-memory strings read back as content — the self-echo bug — and giving
    it a mouth would broadcast the bug.
  * Interoception membrane applies (felt_lexicon): a raw signal identifier never
    reaches the transcript. An utterance that still carries backend markers after
    veiling is DROPPED, not cleaned up and shipped.
"""
from __future__ import annotations

import json
import re
import threading
import time
from typing import Any, Dict, List, Optional

from brain.paths import VOICE_FILE
from brain.utils.failure_counter import record_failure

# The kinds of utterance that are genuinely his. Adding one means finding a call
# site that already holds first-person content — not inventing a phrasing here.
KINDS = (
    "felt",        # workspace affect winner: "a strong sense of being stuck"
    "prediction",  # introspection miss: felt yes / behaved no
    "intent",      # the goal he just committed to, in its own words
    "closeout",    # a question he closed: answered, or honestly not
    "speech",      # composed through the expression door (the one person-facing door)
    "final",       # last words, written once at the end of a life
)

_MAX_CHARS = 400          # an utterance is a line, not a document
_RING_MAX = 60            # utterances awaiting the next telemetry drain
_FILE_MAX_LINES = 5_000
_FILE_MAX_BYTES = 4_000_000

# A real identifier (has an underscore inside): impasse_signal, look_around,
# self_query. Natural English never matches, so veiling can be surgical instead
# of rewriting ordinary words that happen to be signal names ("confidence").
_IDENT_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+\b")

_lock = threading.Lock()
_ring: List[Dict[str, Any]] = []
_last_text: Dict[str, str] = {}   # kind -> last accepted text (suppress repeats)


def _veil(text: str) -> str:
    """Translate implementation identifiers into felt language and drop the
    conditioning scaffold. Returns "" for nothing sayable."""
    try:
        from brain.utils.felt_lexicon import felt_label, strip_scaffold
    except Exception as exc:  # membrane unavailable → say nothing rather than leak
        record_failure("voice._veil.import", exc)
        return ""
    s = strip_scaffold(str(text or "")).strip()
    if not s:
        return ""

    def _swap(m: "re.Match[str]") -> str:
        word = m.group(0)
        felt = felt_label(word.lower())
        # felt_label passes an unknown identifier straight through; de-snake it so
        # a function name reads as words rather than as code.
        return felt if felt != word.lower() else word.replace("_", " ")

    return re.sub(r"\s+", " ", _IDENT_RE.sub(_swap, s)).strip()


def utter(kind: str, text: str, *, cycle: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Record one utterance. Returns the record, or None if it was refused.

    Refused when: the kind isn't one of KINDS, the text is empty, it repeats the
    last utterance of the same kind, or it still fails the speakability
    invariant after veiling (a bracket tag, a filesystem path, a telemetry
    marker). Fail-closed by design — the transcript is the one surface that is
    only ever him, so a doubtful line is dropped, never patched into shape.
    Never raises: a transcript failure must not touch the loop.
    """
    try:
        if kind not in KINDS:
            return None
        said = _veil(text)[:_MAX_CHARS].strip()
        if not said:
            return None
        from brain.behavior.speakability import is_speakable
        if not is_speakable(said):
            return None
        with _lock:
            if _last_text.get(kind) == said:
                return None
            _last_text[kind] = said
            rec: Dict[str, Any] = {
                "kind": kind,
                "text": said,
                "cycle": int(cycle) if isinstance(cycle, (int, float)) else None,
                "ts": time.time(),
            }
            _ring.append(rec)
            del _ring[:-_RING_MAX]
        _append_transcript(rec)
        return rec
    except Exception as exc:
        record_failure("voice.utter", exc)
        return None


def drain() -> List[Dict[str, Any]]:
    """Take everything said since the last drain (the telemetry emitter's read)."""
    with _lock:
        out = list(_ring)
        _ring.clear()
    return out


def recent(limit: int = 200) -> List[Dict[str, Any]]:
    """The tail of the durable transcript — scrollback across restarts."""
    try:
        if not VOICE_FILE.exists():
            return []
        lines = VOICE_FILE.read_text("utf-8", errors="replace").splitlines()[-max(1, limit):]
        out: List[Dict[str, Any]] = []
        for line in lines:
            try:
                row = json.loads(line)
            except ValueError:  # intentional: skip a torn line, keep the rest
                continue
            if isinstance(row, dict) and row.get("text"):
                out.append(row)
        return out
    except Exception as exc:
        record_failure("voice.recent", exc)
        return []


def _append_transcript(rec: Dict[str, Any]) -> None:
    try:
        with VOICE_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
        from brain.utils.json_utils import cap_jsonl
        cap_jsonl(VOICE_FILE, max_lines=_FILE_MAX_LINES, max_bytes=_FILE_MAX_BYTES)
    except Exception as exc:  # transcript persistence best-effort — the ring still ships
        record_failure("voice._append_transcript", exc)
