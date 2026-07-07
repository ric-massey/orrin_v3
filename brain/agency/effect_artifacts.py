# brain/agency/effect_artifacts.py
#
# P1a — artifact-text capture (prerequisite for promotion to an exemplar).
#
# THE GAP THIS CLOSES. The effect ledger is content-ADDRESSED: a row stores
# `content_hash`, not the artifact text. So when an artifact later earns downstream
# credit (reuse / persistence) and the quality-standard proposer wants to promote
# it to a golden exemplar, the original text is gone. This bounded sidecar captures
# the text at production time, keyed by the SAME content_hash the ledger computes,
# so the proposer can retrieve it later.
#
# Cheap, append-only, and capped:
#   - gated by MIN_ARTIFACT_CHARS so junk/stubs are never stored (same floor the
#     ledger uses to decide novelty), and
#   - bounded to _MAX_FILES (oldest evicted) so the sidecar can't grow without limit.
#
# This is NON-COGNITION storage (lives in agency/, beside the ledger). It only ever
# RECORDS; nothing here changes the bar.
from __future__ import annotations

import hashlib
import re
import threading
from pathlib import Path
from typing import Optional

from brain.paths import EFFECT_ARTIFACTS_DIR
from brain.utils.failure_counter import record_failure

# Mirror the ledger's normalization so our hash matches its content_hash exactly.
# (effect_ledger._normalize: whitespace/case-collapse, strip.)
_WS_RE = re.compile(r"\s+")

# Same floor the ledger uses for "real content" (imported lazily to avoid a hard
# import cycle at module load; falls back to the known constant).
try:
    from brain.agency.effect_ledger import MIN_ARTIFACT_CHARS as _MIN_CHARS
except Exception:  # pragma: no cover - defensive
    _MIN_CHARS = 120

# Bounded sidecar; oldest captures evicted past this. Raised 600 → 4000 (F3,
# 2026-07-05 findings): ledger-referenced note bodies must stay resolvable for a
# whole life — the 07-05 run's only good writing survived nowhere else. At
# ~1-2 KB per capture this is still only a few MB.
_MAX_FILES = 4000
_lock = threading.Lock()


def _normalize(content: str) -> str:
    return _WS_RE.sub(" ", str(content or "")).strip().lower()


def content_hash_for(content: str) -> str:
    """The ledger-compatible content hash for `content` (sha256 of normalized text)."""
    return hashlib.sha256(_normalize(content).encode("utf-8")).hexdigest()


def _path_for(content_hash: str) -> Path:
    return EFFECT_ARTIFACTS_DIR / f"{content_hash}.txt"


def _evict_if_needed() -> None:
    """Keep the sidecar bounded: drop the oldest files past _MAX_FILES."""
    try:
        files = [p for p in EFFECT_ARTIFACTS_DIR.glob("*.txt") if p.is_file()]
        if len(files) <= _MAX_FILES:
            return
        files.sort(key=lambda p: p.stat().st_mtime)
        for p in files[: len(files) - _MAX_FILES]:
            try:
                p.unlink()
            except OSError:
                pass
    except Exception as exc:
        record_failure("effect_artifacts._evict_if_needed", exc)


def capture(content: str, *, content_hash: Optional[str] = None) -> Optional[str]:
    """Persist the artifact text keyed by content_hash. Returns the hash on capture,
    or None when the text is below the real-content floor (junk not stored).

    Idempotent: a second capture of the same content is a no-op (the file already
    exists). Safe to call at every record_effect site — including dedupe writes —
    because the hash is content-derived."""
    raw = str(content or "")
    if len(_normalize(raw).replace(" ", "")) < _MIN_CHARS:
        return None
    h = content_hash or content_hash_for(raw)
    try:
        with _lock:
            EFFECT_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
            p = _path_for(h)
            if not p.exists():
                p.write_text(raw, encoding="utf-8")
                _evict_if_needed()
        return h
    except Exception as exc:
        record_failure("effect_artifacts.capture", exc)
        return None


def load(content_hash: str) -> Optional[str]:
    """Retrieve captured artifact text for a content_hash, or None if not stored."""
    if not content_hash:
        return None
    try:
        p = _path_for(content_hash)
        if p.is_file():
            return p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        record_failure("effect_artifacts.load", exc)
    return None
