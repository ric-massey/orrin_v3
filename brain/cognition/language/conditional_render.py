"""brain/cognition/language/conditional_render.py

Phase 2C/2D (Grounded Cognition plan, THOUGHT_OBJECT_SPEC.md): the native LM as
MOUTH. The symbolic mind builds a thought object (the SEMANTIC register — what is
meant); this module renders it into words via the native organ (the SURFACE
register — how it is said), then GATES the result so his voice only flips from the
templates to the organ when the organ is actually fluent and the rendering is
faithful. Until then, the caller's template stands — authenticity over fluency.

The pieces:
  • serialize_thought()  — 2C(i): a COMPACT conditioning prefix (native_lm's
    context is _BLOCK=128 tokens, so the prefix must be short).
  • narration_pairs_corpus() — formats the accumulating (thought -> narration)
    pairs (Phase 2B) as `prefix + narration` so consolidation can train the organ
    to RENDER, not just free-run.
  • render_from_thought() — 2D: serialize -> native_lm.generate -> strip prefix ->
    VALIDATE. Returns rendered text only if it passes the gate, else None (the
    caller falls back to its template).

The 2C(ii) second-signal decision (recorded): the DEFAULT is to accept the
near-template ceiling (the project's authenticity-over-fluency value). The
self-contained supra-template signal we use is RECONSTRUCTION consistency —
round-tripping thought -> words and checking the meaning survived — because it
needs no human rating and no external model. `_reconstruction_ok` is that check in
gating form; it is also the seed of a future contrastive/reconstruction training
signal. The bright line (spec §4) is enforced here: a rendering is rejected unless
it is membrane-clean, non-degenerate, and reconstruction-consistent.
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

from brain.paths import DATA_DIR
from brain.utils.failure_counter import record_failure
from brain.utils.felt_lexicon import is_internal_identifier, strip_scaffold, has_scaffold

# Same sidecar the narrator writes (Phase 2B).
_PAIRS_FILE = DATA_DIR / "language" / "narration_pairs.jsonl"

# Fluency gate: held-out perplexity on the pair format must drop below this before
# the organ is trusted to render. exp(per-token cross-entropy); ~vocab at random,
# falling as it learns the conditioning format. Conservative + env-tunable so the
# flip is deliberate; the per-output reconstruction check is the real safety net.
_FLUENCY_MAX_PERPLEXITY = float(os.environ.get("ORRIN_RENDER_MAX_PPL", "3.0"))
_MIN_RENDER_WORDS = 3       # below this is degenerate, not speech


def serialize_thought(thought: Dict) -> str:
    """2C(i): compact conditioning prefix for native_lm. Deterministic, short.

    e.g. {intent:narrate_experience, affect:{felt:"being stuck"},
          concept_refs:[{type:act,handle:search_own_files}]}
      -> '<say narrate_experience | being stuck | search_own_files>'
    The felt SURFACE is used (never the raw signal key) so the prefix the organ
    learns to continue from is itself membrane-clean."""
    if not isinstance(thought, dict):
        return "<say>"
    intent = str(thought.get("intent") or "speak").strip()[:32]
    affect = thought.get("affect") or {}
    feel = str(affect.get("felt") or "").strip()[:48] if isinstance(affect, dict) else ""
    refs = thought.get("concept_refs") or []
    handles: List[str] = []
    if isinstance(refs, list):
        for r in refs:
            if isinstance(r, dict) and r.get("handle"):
                handles.append(str(r["handle"]).strip()[:32])
    parts = [intent]
    if feel:
        parts.append(feel)
    if handles:
        parts.append(" ".join(handles[:3]))
    return "<say " + " | ".join(parts) + ">"


def _read_pairs(limit: Optional[int] = None) -> List[Dict]:
    if not _PAIRS_FILE.exists():
        return []
    try:
        lines = _PAIRS_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception as exc:
        record_failure("conditional_render._read_pairs", exc)
        return []
    if limit:
        lines = lines[-limit:]
    out: List[Dict] = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            rec = json.loads(ln)
            if isinstance(rec, dict) and rec.get("narration"):
                out.append(rec)
        except Exception:  # intentional: skip a malformed narration-log line, keep scanning
            continue
    return out


def narration_pairs_corpus(max_chars: int = 50000) -> str:
    """Format the accumulated (thought -> narration) pairs as `prefix + narration`
    training text, so consolidation teaches the organ to render from the prefix.
    Each example: '<say ...> narration' on its own line."""
    examples: List[str] = []
    for rec in _read_pairs():
        prefix = serialize_thought(rec.get("thought") or {})
        narration = str(rec.get("narration") or "").strip()
        if narration:
            examples.append(f"{prefix} {narration}")
    return ("\n".join(examples))[-max_chars:]


# ── Validation (the bright line, spec §4) ────────────────────────────────────

def _non_degenerate(text: str) -> bool:
    words = [w for w in text.split() if w.strip()]
    if len(words) < _MIN_RENDER_WORDS:
        return False
    # Not just one token repeated (a common small-LM failure mode).
    return len(set(w.lower() for w in words)) >= max(3, len(words) // 2)


def _membrane_clean(text: str) -> bool:
    """Output is perceivable content — it must carry no internal identifier
    (invariant #2)."""
    return not is_internal_identifier(text)


def _reconstruction_ok(thought: Dict, text: str) -> bool:
    """2C(ii) reconstruction signal in gating form: the rendered words must still
    carry the thought's MEANING — its felt term and/or a referenced concept's
    words must survive the round-trip. This is what stops the organ from emitting
    fluent-but-unrelated prose (originating content, spec §4)."""
    low = text.lower()
    affect = thought.get("affect") or {}
    feel = str(affect.get("felt") or "").lower() if isinstance(affect, dict) else ""
    # A content word from the felt term, or from a concept handle, must appear.
    anchors: List[str] = []
    for token in feel.replace("-", " ").split():
        if len(token) > 3:
            anchors.append(token)
    for r in (thought.get("concept_refs") or []):
        if isinstance(r, dict) and r.get("handle"):
            for token in str(r["handle"]).replace("_", " ").split():
                if len(token) > 3:
                    anchors.append(token)
    if not anchors:
        return True   # nothing to anchor to (rare) — don't block on it
    return any(a in low for a in anchors)


# The fluency check runs a torch forward pass — cache it so it isn't recomputed
# on every single utterance (compose_from_motive is called often).
_fluent_cache: Dict[str, float] = {"ts": 0.0, "value": 0.0}
_FLUENT_TTL_S = 120.0


def organ_fluent() -> bool:
    """The fluency gate: the organ must predict the PAIR FORMAT well (held-out
    perplexity below threshold) before it is trusted to render. Today, before any
    conditional-pair training, this is False — so callers keep their templates.
    Result is cached for _FLUENT_TTL_S (the gate moves only across training bouts)."""
    import time
    now = time.time()
    if now - _fluent_cache["ts"] < _FLUENT_TTL_S:
        return bool(_fluent_cache["value"])
    result = False
    try:
        from brain.cognition.language import native_lm
        if native_lm.available():
            corpus = narration_pairs_corpus()
            if len(corpus) >= 2000:        # enough conditioning data
                ppl = native_lm.evaluate(corpus)
                result = ppl is not None and ppl <= _FLUENCY_MAX_PERPLEXITY
    except Exception as exc:
        record_failure("conditional_render.organ_fluent", exc)
        result = False
    _fluent_cache["ts"] = now
    _fluent_cache["value"] = 1.0 if result else 0.0
    return result


def render_from_thought(thought: Dict, *, length: int = 60,
                        temperature: float = 0.8) -> Optional[str]:
    """2D: render a thought object into words via the native organ, GATED. Returns
    the rendered utterance only if the organ is fluent AND the output passes the
    bright line (membrane-clean, non-degenerate, reconstruction-consistent);
    otherwise None, and the caller uses its template. Fail-safe."""
    if not isinstance(thought, dict):
        return None
    if not organ_fluent():
        return None
    try:
        from brain.cognition.language import native_lm
        prefix = serialize_thought(thought)
        raw = native_lm.generate(prompt=prefix, length=length, temperature=temperature) or ""
    except Exception as exc:
        record_failure("conditional_render.render_from_thought", exc)
        return None
    # generate() returns prefix+continuation. The exact prefix rarely survives the
    # tokenizer intact, so don't rely on startswith — strip the scaffold robustly
    # (handles the degraded "say {intent} … :" form too).
    text = raw[len(prefix):] if raw.startswith(prefix) else raw
    text = strip_scaffold(text)
    # The organ may run on past a natural stop; keep the first sentence-ish span.
    text = text.strip().split("\n", 1)[0].strip()
    if not text:
        return None
    # The bright line (spec §4) — reject anything that isn't a faithful rendering,
    # and reject outright if any conditioning scaffold still leaked through.
    if has_scaffold(text):
        return None
    if not (_non_degenerate(text) and _membrane_clean(text)
            and _reconstruction_ok(thought, text)):
        return None
    return text
