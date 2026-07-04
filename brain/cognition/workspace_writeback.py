# brain/cognition/workspace_writeback.py
#
# Top-down write-back — the downward half of the global workspace.
#
# The workspace has always been one-directional: the conscious winner is
# BROADCAST outward (it biases the action pick, can recruit inner_loop on
# conflict) — but nothing wrote the conscious conclusion BACK DOWN into the
# substrate's priors. Feedback never reshaped a drive or a salience prior, so
# across long runs Orrin acted on conclusions he never let change him.
#
# THE DECISION (TOPDOWN_WRITEBACK_IMPLEMENTATION_PLAN_2026-06-27):
# We build a permanent, bounded, *decaying* downward path. Conscious
# conclusions nudge priors; those nudges drain back toward the shipped-adult
# baseline. The substrate TRACKS recent conclusions (long-run coherence) but
# never BECOMES a different substrate (no ontogeny). There is no promotion path
# to a durable baseline — decay is the permanence, absence of promotion is the
# permanence. Those two properties ARE the design, not a safety dial.
#
# Two targets, one spine:
#   (a) Reappraisal → drives. The KIND of conclusion maps to a small signed
#       nudge on a cortical/relative core signal, submitted through the existing
#       single-writer affect inbox (arbiter.submit_signal: weighted, TTL-bounded,
#       decaying). We never fork a second affect writer and never touch absolute
#       reflex floors.
#   (b) Hebbian → salience priors. The content that won consciousness primes its
#       own tokens in a small bounded decaying store, so RELATED content is
#       slightly more likely to win next cycle — theme continuity across cycles,
#       which is what "coherent over long runs" concretely means.
#
# The workspace still decides; write-back only reshapes priors for the NEXT
# competition (I7: bias, never preempt). A write-back derived from this cycle's
# winner is integrated by commit_signals on the next cycle — one-cycle latency,
# gradual, decaying: the correct human-like shape.
from __future__ import annotations

from typing import Any, Dict

from brain.paths import DATA_DIR
from brain.utils.log import log_private
from brain.utils.failure_counter import record_failure
from brain.cognition.global_workspace import _tokens, _is_noise

# ── Tuning constants (conservative-first; see plan §5) ────────────────────────
_MAX_AFFECT_DELTA = 0.06    # cap on any single write-back affect nudge
_AFFECT_WEIGHT    = 0.25    # low weight: write-back is a weak voice in the sum
_AFFECT_TTL       = 4       # cycles the nudge drains over

_DECAY      = 0.85         # per-cycle multiplicative decay of every primed weight
_FLOOR      = 0.02         # weights below this are dropped
_CAP        = 0.30         # per-token weight ceiling
_PRIOR_BOOST = 0.10        # boost added to each winner token on prime
_PRIOR_CEIL = 0.12         # max total salience prior contributed to a candidate
_MAX_TOKENS = 64           # bounded store: evict lowest when exceeded

_WRITE_THRESHOLD = 0.55    # a moment must have won decisively to write back

# Sources whose winning content is a *conclusion or breakthrough* worth writing
# back — not a bare input echo (user/signal) already represented elsewhere.
_CONCLUSION_SOURCES = frozenset({"thought", "binding", "subconscious", "monitor"})

# Cortical/relative core signals write-back is allowed to nudge. Absolute reflex
# floors and scalar safety targets are deliberately absent — "refuse-to-imprint"
# by construction (plan §1 principle 5).
_ELIGIBLE_TARGETS = frozenset({"impasse_signal", "motivation", "novelty_signal"})

_PRIORS_KEY = "_workspace_priors"
_PRIORS_FILE = DATA_DIR / "workspace_priors.json"
_WRITEBACK_LOG = DATA_DIR / "workspace_writeback.jsonl"


def _store(context: Dict[str, Any]) -> Dict[str, float]:
    """The live token→weight salience-prior store, mirrored on context."""
    store = context.get(_PRIORS_KEY)
    if not isinstance(store, dict):
        # Hydrate once from disk (run-to-run is irrelevant — it's designed to
        # forget — but within a process the loop holds it on context).
        store = {}
        try:
            from brain.utils.json_utils import load_json
            loaded = load_json(_PRIORS_FILE, dict)
            if isinstance(loaded, dict):
                store = {str(k): float(v) for k, v in loaded.items()
                         if isinstance(v, (int, float))}
        except Exception as exc:
            record_failure("workspace_writeback.load_store", exc)
        context[_PRIORS_KEY] = store
    return store


def _persist(store: Dict[str, float]) -> None:
    try:
        from brain.utils.json_utils import save_json
        save_json(_PRIORS_FILE, store)
    except Exception as exc:
        record_failure("workspace_writeback.persist_store", exc)


def _prime(context: Dict[str, Any], content: str, boost: float) -> int:
    """Add/refresh token weights for the winner's content. Returns token count."""
    store = _store(context)
    toks = _tokens(content)
    if not toks:
        return 0
    for t in toks:
        store[t] = min(_CAP, store.get(t, 0.0) + boost)
    # Bound the store: evict the lowest-weight tokens beyond the cap.
    if len(store) > _MAX_TOKENS:
        for t in sorted(store, key=store.get)[: len(store) - _MAX_TOKENS]:
            store.pop(t, None)
    _persist(store)
    return len(toks)


def salience_prior(context: Dict[str, Any], content: str) -> float:
    """Read side: bounded sum of primed weights for this content's tokens.

    Used by update_workspace as one more additive prior term. Clamped to
    _PRIOR_CEIL so theme-continuity can only ever nudge a competition. Fail-safe
    (returns 0.0 on any error)."""
    try:
        store = context.get(_PRIORS_KEY)
        if not isinstance(store, dict) or not store:
            return 0.0
        toks = _tokens(content)
        if not toks:
            return 0.0
        total = sum(store.get(t, 0.0) for t in toks)
        return min(_PRIOR_CEIL, total)
    except Exception as exc:
        record_failure("workspace_writeback.salience_prior", exc)
        return 0.0


def tick_salience_priors(context: Dict[str, Any]) -> None:
    """Per-cycle decay: every primed weight drains toward zero and entries below
    the floor are dropped. This is the only persistence — the store is DESIGNED
    to forget, so a wrong conclusion is a bounded transient, never an entrenched
    prior. Fail-safe."""
    try:
        store = _store(context)
        if not store:
            return
        decayed = {t: w * _DECAY for t, w in store.items()}
        store.clear()
        store.update({t: w for t, w in decayed.items() if w >= _FLOOR})
        _persist(store)
    except Exception as exc:
        record_failure("workspace_writeback.tick", exc)


def _signal_writeback(context: Dict[str, Any], moment: Dict[str, Any]) -> Any:
    """Map the KIND of conclusion to a small signed nudge on one eligible core
    signal, submitted through the existing affect inbox. Returns (target, delta)
    on a write, or None when no recognizable kind applies (then only the
    salience half fires — conservative affect, broad theme-continuity)."""
    from brain.control_signals.arbiter import submit_signal
    from brain.cognition.global_workspace import goal_in_focus

    source = moment.get("source")
    wants = moment.get("wants")

    target = None
    delta = 0.0

    # A conclusion that the current approach is stuck (a monitor breakthrough that
    # wants to escalate) → small +impasse so the next cycle inherits the felt
    # impasse instead of rediscovering it cold.
    if source == "monitor" and wants:
        target, delta = "impasse_signal", +_MAX_AFFECT_DELTA
    # A conclusion that resolves/closes a goal step (a binding moment carrying the
    # committed goal, goal in focus) → +motivation, −impasse.
    elif source == "binding" and moment.get("goal_id") and goal_in_focus(context):
        target, delta = "motivation", +_MAX_AFFECT_DELTA
    # A salient novel insight (a subconscious insight that won) → +novelty so
    # follow-on exploration is primed.
    elif source == "subconscious":
        target, delta = "novelty_signal", +_MAX_AFFECT_DELTA

    if not target or target not in _ELIGIBLE_TARGETS:
        return None

    delta = max(-_MAX_AFFECT_DELTA, min(_MAX_AFFECT_DELTA, delta))
    submit_signal(context, target=target, delta=delta, weight=_AFFECT_WEIGHT,
                  source="workspace_writeback", ttl_cycles=_AFFECT_TTL)

    # The binding/closure case carries a paired −impasse relief alongside the
    # +motivation nudge.
    if source == "binding" and target == "motivation":
        submit_signal(context, target="impasse_signal", delta=-_MAX_AFFECT_DELTA,
                      weight=_AFFECT_WEIGHT, source="workspace_writeback",
                      ttl_cycles=_AFFECT_TTL)
    return (target, round(delta, 4))


def _is_conclusion(moment: Dict[str, Any]) -> bool:
    """A conscious moment worth writing back: it won decisively, it is a
    conclusion/breakthrough (not a bare input echo), and it isn't noise."""
    try:
        if float(moment.get("salience") or 0.0) < _WRITE_THRESHOLD:
            return False
    except (TypeError, ValueError):
        return False
    if moment.get("source") not in _CONCLUSION_SOURCES:
        return False
    if _is_noise(str(moment.get("content") or "")):
        return False
    return True


def write_back(context: Dict[str, Any], moment: Dict[str, Any]) -> None:
    """The spine. Runs once per cycle on the chosen conscious moment. Queues a
    decaying affect nudge (when the conclusion has a recognizable kind) and
    primes the salience-prior store with the winner's tokens. Gated so only
    genuine conclusions write — not every flicker of awareness. Wholly
    fail-safe: a write-back fault can never break a cycle."""
    try:
        if not isinstance(context, dict) or not isinstance(moment, dict):
            return
        if not _is_conclusion(moment):
            return

        affect = _signal_writeback(context, moment)
        primed = _prime(context, str(moment.get("content") or ""), _PRIOR_BOOST)

        if affect or primed:
            kind = moment.get("kind") or moment.get("source") or "?"
            if affect:
                tgt, d = affect
                log_private(f"[writeback] ({kind}) {tgt} Δ{d:+.3f}; primed {primed} tokens")
            else:
                log_private(f"[writeback] ({kind}) primed {primed} tokens")
            _emit_telemetry(context, moment, affect, primed)
    except Exception as exc:
        record_failure("workspace_writeback.write_back", exc)


def _emit_telemetry(context: Dict[str, Any], moment: Dict[str, Any],
                    affect: Any, primed: int) -> None:
    """One bounded durable line per actual write, so a run ARCHIVE can answer
    'did closing the loop change behavior?' without process memory (mirrors the
    production_loop.jsonl pattern)."""
    try:
        import json
        from brain.utils.get_cycle_count import get_cycle_count
        from brain.utils.json_utils import cap_jsonl
        record = {
            "cycle": int(get_cycle_count() or 0),
            "source": moment.get("source"),
            "kind": moment.get("kind"),
            "salience": round(float(moment.get("salience") or 0.0), 3),
            "affect_target": affect[0] if affect else None,
            "affect_delta": affect[1] if affect else None,
            "primed_tokens": primed,
        }
        _WRITEBACK_LOG.parent.mkdir(parents=True, exist_ok=True)
        with _WRITEBACK_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        cap_jsonl(_WRITEBACK_LOG, max_lines=8000)   # RUN4_FIX_PLAN §3.6 — tighter cap (~1 MB/run footprint)
    except Exception as exc:
        record_failure("workspace_writeback.telemetry", exc)
