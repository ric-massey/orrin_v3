# brain/agency/effect_ledger.py
#
# The external-effect ledger — the *denominator* the reward function was missing
# (ORRIN_PRODUCTION_REWARD_PLAN_2026-06-18, P0 + P8).
#
# THE PROBLEM IT SOLVES
# Orrin's reward was denominated in internal events — and internal events are free
# and infinite — so the rational policy was to metabolize cognition forever and
# never produce anything. There was no record of "a durable thing that did not
# exist in the world before," so reading Wikipedia paid exactly what writing a
# file paid. This ledger is that record: an append-only, content-addressed log of
# real outward effects, written at the moment of the effect, where duplicates earn
# nothing. It lives in agency/ (the action side), not cognition/.
#
# TWO CONSUMERS, ONE LEDGER
#   - reward (P1) reads `record_effect`'s return to decide production vs intake.
#   - the Life Capsule reads the same `effect_ledger.jsonl` for observability
#     (this file is what the Capsule plan called `artifacts.jsonl`).
#
# ANTI-GAMING (P8). "Reward novel, significant artifacts" is only a fix if `novel`
# and `significant` are defined so producing junk is not easier than producing
# nothing. Three cheap, independent signals combine so a single trick can't max
# novelty:
#   - exact-dup:   sha256(normalized) already in the ledger          → novelty 0
#   - near-dup:    char-shingle Jaccard >= NEAR_DUP_SIM to a recent  → novelty <= NEAR_DUP_RESIDUAL
#   - boilerplate: < MIN_ARTIFACT_CHARS of real, stripped content    → novelty 0
# Significance is *earned*, not asserted at write time (the mean_significance=0.0
# trap came from self-asserted completion): structural (immediate) → validation /
# re-use (deferred). Re-use is the only ungameable signal — you can fabricate a
# file, you cannot fabricate your future self choosing to use it.
from __future__ import annotations

from brain.core.runtime_log import get_logger
import hashlib
import json
import re
import threading
from collections import deque
from dataclasses import dataclass, asdict
from typing import Any, Deque, Dict, List, Optional, Tuple

from brain.paths import DATA_DIR
from brain.utils.timeutils import now_iso_z
from brain.utils.failure_counter import record_failure

_log = get_logger(__name__)

EFFECT_LEDGER_FILE = DATA_DIR / "effect_ledger.jsonl"

# ── P8 constants (fixed by an ordering on a scale already in the code) ─────────
NEAR_DUP_SIM = 0.9        # standard near-dup threshold for text shingles
NEAR_DUP_RESIDUAL = 0.15  # a near-dup stays on a slope, not a hard cliff like exact-dup
MIN_ARTIFACT_CHARS = 120  # set between the failure case (~40-char affect strings) and a real finding

# kinds that correspond to a real outward act already taggable from the activity log
EFFECT_KINDS = frozenset({
    "file_write", "tool_written", "tool_run_effect", "note_novel",
    "message_answered", "code_committed", "external_post", "tracked_work",
})

# How many recent same-kind effects to compare against for near-dup detection.
_NOVELTY_WINDOW = 64

_lock = threading.RLock()

# In-memory caches, lazily hydrated from disk once per process.
_seen_hashes: set[str] = set()
_recent_by_kind: Dict[str, Deque[Tuple[str, str]]] = {}   # kind -> deque[(hash, normalized)]
_reuse_counts: Dict[str, int] = {}                          # content_hash -> times referenced again
_goal_effects: Dict[str, List[str]] = {}                    # goal_id -> [content_hash, ...]
_goal_significance: Dict[str, float] = {}                   # goal_id -> max effect significance
_tracked_progress: Dict[str, int] = {}                      # goal_id -> max completed sections
_hydrated = False


@dataclass
class EffectRow:
    ts: str
    cycle: int
    kind: str
    content_hash: str
    novelty: float
    significance: float
    goal_id: Optional[str]
    char_len: int
    dedupe: bool
    metadata: Optional[Dict[str, Any]] = None

    def to_json(self) -> Dict[str, Any]:
        return asdict(self)


# ── normalization & cheap text similarity ──────────────────────────────────────

_WS_RE = re.compile(r"\s+")
# Common boilerplate/scaffold tokens that should not count as "real" content.
_TEMPLATE_RE = re.compile(
    r"\b(todo|fixme|placeholder|lorem ipsum|note to self|nothing worth noting)\b",
    re.IGNORECASE,
)


def _normalize(content: str) -> str:
    """Whitespace/case-normalize so trivial reformatting can't dodge the dedup."""
    return _WS_RE.sub(" ", str(content or "")).strip().lower()


def _real_content_len(normalized: str) -> int:
    """Length of non-template, non-whitespace content — what 'real' means for MIN_ARTIFACT_CHARS."""
    stripped = _TEMPLATE_RE.sub("", normalized)
    stripped = _WS_RE.sub("", stripped)
    return len(stripped)


def _unique_token_ratio(normalized: str) -> float:
    toks = normalized.split()
    if not toks:
        return 0.0
    return len(set(toks)) / len(toks)


def _shingles(normalized: str, k: int = 5) -> set:
    """Character k-shingles — offline-safe near-dup signal (no embedding needed)."""
    s = normalized.replace(" ", "")
    if len(s) < k:
        return {s} if s else set()
    return {s[i:i + k] for i in range(len(s) - k + 1)}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _max_similarity_to_recent(kind: str, normalized: str) -> float:
    recent = _recent_by_kind.get(kind)
    if not recent:
        return 0.0
    target = _shingles(normalized)
    if not target:
        return 0.0
    best = 0.0
    for _h, prior in recent:
        sim = _jaccard(target, _shingles(prior))
        if sim > best:
            best = sim
            if best >= 1.0:
                break
    return best


def _compute_novelty(kind: str, normalized: str, content_hash: str) -> float:
    """1 - max similarity to prior same-kind artifacts, combining three cheap signals."""
    # exact-dup → 0
    if content_hash in _seen_hashes:
        return 0.0
    # boilerplate / too-short / template-heavy → 0
    if _real_content_len(normalized) < MIN_ARTIFACT_CHARS:
        return 0.0
    if _unique_token_ratio(normalized) < 0.25:
        return 0.0
    # near-dup → clamped low, on a slope
    sim = _max_similarity_to_recent(kind, normalized)
    if sim >= NEAR_DUP_SIM:
        return round(min(NEAR_DUP_RESIDUAL, 1.0 - sim), 4)
    return round(1.0 - sim, 4)


def _structural_significance(
    kind: str,
    content: str,
    normalized: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> float:
    """Tier-1 (immediate, weak) significance: is the artifact well-formed for its kind?

    Fails structural → 0 (it's junk, no production credit at all). This is the gate;
    tier-2 (validation) and tier-3 (re-use) credit are added later via `mark_reused`
    and acceptance checks, and carry the larger, ungameable bonuses.
    """
    if _real_content_len(normalized) < MIN_ARTIFACT_CHARS:
        return 0.0
    if kind in ("tool_written", "code_committed"):
        # code must at least parse to be structurally significant
        try:
            import ast
            ast.parse(content)
        except (SyntaxError, ValueError):  # intentional: code that won't parse isn't significant
            return 0.0
        return 0.6
    if kind == "message_answered":
        # a delivered message to a real peer is structurally meaningful
        return 0.5
    if kind == "tracked_work":
        meta = metadata or {}
        # Credit cumulative work only when it names a durable path and advances
        # an identifiable section. Anti-duplication and minimum substance still
        # apply above, so appending boilerplate cannot farm progress.
        if not meta.get("path") or not meta.get("section"):
            return 0.0
        sections = max(1, int(meta.get("completed_sections") or 1))
        return min(0.9, 0.5 + 0.05 * min(sections, 8))
    # notes / file writes / posts: well-formed = enough real, varied content
    return 0.4 if _unique_token_ratio(normalized) >= 0.4 else 0.25


# ── persistence ─────────────────────────────────────────────────────────────────

def _hydrate() -> None:
    global _hydrated
    if _hydrated:
        return
    with _lock:
        if _hydrated:
            return
        try:
            if EFFECT_LEDGER_FILE.exists():
                with EFFECT_LEDGER_FILE.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            row = json.loads(line)
                        except Exception as exc:
                            record_failure("effect_ledger.hydrate_jsonl_row", exc)
                            continue
                        h = row.get("content_hash")
                        if not h:
                            continue
                        _seen_hashes.add(h)
                        gid = row.get("goal_id")
                        if gid and not row.get("dedupe"):
                            _goal_effects.setdefault(str(gid), []).append(h)
                            try:
                                sig = float(row.get("significance") or 0.0)
                                if sig > 0.0:
                                    _goal_significance[str(gid)] = max(
                                        _goal_significance.get(str(gid), 0.0), sig
                                    )
                            except Exception as exc:
                                record_failure("effect_ledger.hydrate_significance", exc)
                            meta = row.get("metadata") or {}
                            if row.get("kind") == "tracked_work" and isinstance(meta, dict):
                                try:
                                    _tracked_progress[str(gid)] = max(
                                        _tracked_progress.get(str(gid), 0),
                                        int(meta.get("completed_sections") or 0),
                                    )
                                except Exception as exc:
                                    record_failure("effect_ledger.hydrate_tracked_progress", exc)
                        # recent-by-kind window can't be reconstructed exactly
                        # (we don't persist normalized text); novelty just starts
                        # comparing fresh this process, which is safe.
        except Exception as _e:
            record_failure("effect_ledger._hydrate", _e)
        _hydrated = True


def _append_row(row: EffectRow) -> None:
    try:
        EFFECT_LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
        with EFFECT_LEDGER_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row.to_json(), ensure_ascii=False) + "\n")
    except Exception as _e:
        record_failure("effect_ledger._append_row", _e)


def _cycle_from(context: Optional[Dict[str, Any]], cycle: Optional[int]) -> int:
    if cycle is not None:
        try:
            return int(cycle)
        except (TypeError, ValueError):  # intentional: non-int cycle → 0
            return 0
    if isinstance(context, dict):
        cc = context.get("cycle_count")
        if isinstance(cc, dict):
            try:
                return int(cc.get("count", 0) or 0)
            except (TypeError, ValueError):  # intentional: non-int count → 0
                return 0
    return 0


# ── public API ───────────────────────────────────────────────────────────────

def record_effect(
    kind: str,
    content: str,
    *,
    goal_id: Optional[str] = None,
    novelty: Optional[float] = None,
    cycle: Optional[int] = None,
    context: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[EffectRow]:
    """Record a durable external effect. Returns the EffectRow on a *novel* effect,
    or None when nothing was credited (exact-dup / boilerplate / empty).

    None means "no production credit" — this is what makes 100 identical notes
    equal one production, structurally. The caller (finalize/P1) keys the
    production reward on a non-None return.
    """
    _hydrate()
    if kind not in EFFECT_KINDS:
        # unknown kind: record nothing rather than silently miscredit
        return None
    raw = str(content or "")
    normalized = _normalize(raw)
    if not normalized:
        return None
    content_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    with _lock:
        is_dup = content_hash in _seen_hashes
        nov = _compute_novelty(kind, normalized, content_hash) if novelty is None else float(novelty)
        # An explicit caller-supplied novelty still can't beat the exact-dup gate.
        if is_dup:
            nov = 0.0
        sig = 0.0 if nov <= 0.0 else _structural_significance(kind, raw, normalized, metadata)
        # The active goal's definition of done is the local standard of good.
        # For prose-like output, structural quality alone is insufficient when
        # the content has no detectable relationship to the inhabited goal.
        if sig > 0.0 and isinstance(context, dict) and kind in {
            "tracked_work", "note_novel", "file_write", "external_post", "message_answered",
        }:
            lens = context.get("goal_lens")
            if isinstance(lens, dict) and (
                not goal_id or str(lens.get("goal_id") or "") == str(goal_id)
            ):
                try:
                    from brain.cognition.goal_lens import relevance as _goal_relevance
                    alignment = _goal_relevance(lens, raw)
                    if alignment < 0.05:
                        sig = 0.0
                    else:
                        sig *= 0.75 + 0.25 * alignment
                    metadata = dict(metadata or {})
                    metadata["goal_alignment"] = round(alignment, 4)
                except Exception as exc:
                    record_failure("effect_ledger.goal_alignment", exc)

        row = EffectRow(
            ts=now_iso_z(),
            cycle=_cycle_from(context, cycle),
            kind=kind,
            content_hash=content_hash,
            novelty=round(float(nov), 4),
            significance=round(float(sig), 4),
            goal_id=str(goal_id) if goal_id else None,
            char_len=len(raw),
            dedupe=bool(is_dup or nov <= 0.0),
            metadata=dict(metadata or {}) or None,
        )
        _append_row(row)

        # Even a dedupe row is remembered (so the next identical one also dedupes),
        # but it earns nothing and is not attributed to a goal as a production.
        _seen_hashes.add(content_hash)
        dq = _recent_by_kind.setdefault(kind, deque(maxlen=_NOVELTY_WINDOW))
        dq.append((content_hash, normalized))

        if row.dedupe or row.significance <= 0.0:
            return None

        if goal_id:
            gid = str(goal_id)
            _goal_effects.setdefault(gid, []).append(content_hash)
            _goal_significance[gid] = max(_goal_significance.get(gid, 0.0), row.significance)
            if kind == "tracked_work":
                try:
                    _tracked_progress[gid] = max(
                        _tracked_progress.get(gid, 0),
                        int((metadata or {}).get("completed_sections") or 0),
                    )
                except Exception as exc:
                    record_failure("effect_ledger.record_tracked_progress", exc)
        _log.debug("effect recorded kind=%s novelty=%.3f sig=%.3f goal=%s",
                   kind, row.novelty, row.significance, goal_id)
        return row


def has_qualifying_effect(goal_id: str, goal: Optional[Dict[str, Any]] = None) -> bool:
    """True if a *novel* (non-dedupe) effect was ever recorded for this goal_id.

    This is the artifact gate for P2: an `output_producing` / `requires_artifact`
    goal completes only when this returns True, no matter what the LLM self-reports.
    """
    if not goal_id:
        return False
    _hydrate()
    with _lock:
        gid = str(goal_id)
        if not _goal_effects.get(gid):
            return False
        if isinstance(goal, dict):
            spec = goal.get("spec") if isinstance(goal.get("spec"), dict) else {}
            if bool(goal.get("tracked_work") or spec.get("tracked_work")):
                required = 1
                criteria = goal.get("definition_of_done") or spec.get("definition_of_done") or []
                for item in criteria if isinstance(criteria, list) else []:
                    if isinstance(item, dict) and str(item.get("kind") or "").lower() == "sections":
                        try:
                            required = max(required, int(item.get("target") or 1))
                        except Exception as exc:
                            record_failure("effect_ledger.required_sections", exc)
                return _tracked_progress.get(gid, 0) >= required
        return True


def effects_for_goal(goal_id: str) -> List[str]:
    if not goal_id:
        return []
    _hydrate()
    with _lock:
        return list(_goal_effects.get(str(goal_id), []))


def significance_for_goal(goal_id: str) -> float:
    """Max structural significance among a goal's recorded effects (P8). Feeds the
    completion metric so mean_significance reflects real produced work, not the
    self-asserted achievement multiplier that produced the run's 0.0."""
    if not goal_id:
        return 0.0
    _hydrate()
    with _lock:
        return float(_goal_significance.get(str(goal_id), 0.0))


def mark_reused(content_hash: str) -> int:
    """Tier-3 (deferred, strong) significance: the artifact was referenced again
    later — a tool invoked, a memo cited by a later goal, a message replied to.
    Re-use is the only ungameable significance signal. Returns the new reuse count.
    """
    if not content_hash:
        return 0
    _hydrate()
    with _lock:
        _reuse_counts[content_hash] = _reuse_counts.get(content_hash, 0) + 1
        n = _reuse_counts[content_hash]
    try:
        _append_row(EffectRow(
            ts=now_iso_z(), cycle=0, kind="reuse",
            content_hash=content_hash, novelty=0.0,
            significance=1.0, goal_id=None, char_len=0, dedupe=False,
            metadata=None,
        ))
    except Exception as exc:
        record_failure("effect_ledger.mark_reused", exc)
    return n


def reuse_count(content_hash: str) -> int:
    _hydrate()
    with _lock:
        return int(_reuse_counts.get(content_hash, 0))


def reset_for_tests() -> None:
    """Clear in-memory state — test-only helper."""
    global _hydrated
    with _lock:
        _seen_hashes.clear()
        _recent_by_kind.clear()
        _reuse_counts.clear()
        _goal_effects.clear()
        _goal_significance.clear()
        _tracked_progress.clear()
        _hydrated = False
