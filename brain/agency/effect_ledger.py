# brain/agency/effect_ledger.py
#
# The external-effect ledger — the *denominator* the reward function was missing
# (ORRIN_PRODUCTION_REWARD_PLAN_2026-06-18, P0 + P8).
#
# THE PROBLEM IT SOLVES
# Orrin's reward was denominated in internal events — and internal events are free
# and infinite — so the rational policy was to churn cognition forever and
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
import time
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
    "symbolic_artifact", "bookkeeping",
})

# Fix 5 (RUN6_FIX_PLAN_2026-07-08 §3): symbolic sub-kinds that are SELF-MODEL
# BOOKKEEPING, not made things. "Causal edge established" rows were 116 of the
# 152 credited effects in Run 5 (76 %) — pure self-model churn that overstated
# the making organ ~4× (S5/S7) and polluted the aspiration/commitment value
# signal. They are reclassified to the distinct `bookkeeping` kind: still
# appended (and deduped) for the record, but they earn no significance, no
# production credit, and no goal attribution — reported separately.
_BOOKKEEPING_SUB_KINDS = frozenset({"causal_edge"})

# AR1 rate cap: a rule-synthesis/crystallization storm must not farm production
# credit. At most _SYMBOLIC_CAP credited symbolic_artifact effects per rolling
# _SYMBOLIC_CAP_WINDOW_S; beyond that a row is still appended (for the record)
# but earns nothing. Time-based rather than cycle-based because the symbolic
# producers (dream cycle, crystallization) often run without a cycle context.
_SYMBOLIC_CAP = 6
_SYMBOLIC_CAP_WINDOW_S = 600.0
_symbolic_credit_times: Deque[float] = deque(maxlen=_SYMBOLIC_CAP)

# How many recent same-kind effects to compare against for near-dup detection.
_NOVELTY_WINDOW = 64

_lock = threading.RLock()

# In-memory caches, lazily hydrated from disk once per process.
_seen_hashes: set[str] = set()
_recent_by_kind: Dict[str, Deque[Tuple[str, str]]] = {}   # kind -> deque[(hash, normalized)]
_reuse_counts: Dict[str, int] = {}                          # content_hash -> times referenced again
_correction_counts: Dict[str, int] = {}                     # content_hash -> times CORRECTED (P2b, mirror of reuse)
_goal_effects: Dict[str, List[str]] = {}                    # goal_id -> [content_hash, ...]
_goal_significance: Dict[str, float] = {}                   # goal_id -> max effect significance
_tracked_progress: Dict[str, int] = {}                      # goal_id -> max completed sections
# Name → content_hash for *named* authored artifacts (tools, cognitive functions),
# so a later invocation by name (tool_runner / cognition dispatch) can be recognized
# as re-use of a specific produced artifact — the tier-3, ungameable signal.
_artifact_names: Dict[str, str] = {}                        # name -> content_hash
# A2.1 (RUN4_FIX_PLAN): normalized artifact path -> content_hash. The missing
# primitive that let mark_reused sit uncalled: read paths open FILES, and
# nothing could resolve a path back to the hash the ledger credits. Persisted
# implicitly — rebuilt at hydrate from each row's metadata.path.
_path_hash: Dict[str, str] = {}                             # normalized path -> content_hash
_hash_goal: Dict[str, str] = {}                             # content_hash -> goal_id (back-reference)
_hash_kind: Dict[str, str] = {}                             # content_hash -> effect kind (for the quality-standard proposer)
# Tier-3 re-use credits awaiting payout. Re-use is detected wherever an artifact is
# invoked (tool_runner.dispatch, cognition dispatch) — which is often outside any
# context that can persist affect changes. finalize_cycle drains this on the LIVE
# cycle context so the deferred bonus actually lands (see release_reward_signal's
# "emotional state is NOT saved here" — it must run on the cycle's own context).
_pending_reuse: List[Dict[str, Any]] = []
_PENDING_REUSE_MAX = 64
# AR4: credited symbolic artifacts pay production reward the moment they are
# recorded, not only at goal close — the symbolic producers run outside any
# context that can persist affect, so (like re-use) the credit is queued here
# and paid by finalize_cycle on the live cycle context.
_pending_production: List[Dict[str, Any]] = []
_PENDING_PRODUCTION_MAX = 64
# S7 lane bridge: every recorded row (any kind, any lane/thread) lands here so
# the production-funnel telemetry can count attempts from ALL producers, not
# just the two conscious-lane writers that hand-fed the old context list.
_recent_rows: deque = deque(maxlen=256)
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


def _norm_path(p: Any) -> Optional[str]:
    """Canonical form for the path→hash index (A2.1): absolute, resolved."""
    try:
        from pathlib import Path
        s = str(p or "").strip()
        if not s:
            return None
        return str(Path(s).expanduser().resolve())
    except (OSError, ValueError):  # intentional: unresolvable path → not indexable
        return None


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
    if kind == "bookkeeping":
        # Fix 5: self-model bookkeeping is never a production — recorded, not credited.
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
    if kind == "tool_run_effect":
        # P3 produce-and-check: a passing sandbox check is a *verified* computational
        # result — it either ran and asserted true or it didn't. Stronger evidence
        # than a note (which only has to be well-formed), so it carries code-tier
        # significance. This is the first emitter of the kind (nothing produced it
        # before P3), and it is what lets a verifiable "understand X" goal close on
        # a check-pass instead of on "stopped feeling new".
        return 0.6
    if kind == "symbolic_artifact":
        # AR1: a synthesized rule / crystallized skill / resolved experiment /
        # established causal edge is verified structure the engine itself checked
        # (compression test, establishment gate, sandbox probes) — tool-tier
        # significance, scaled by what kind of structure it is. An experiment
        # carries measured evidence, so it sits at the top of the band.
        sub = str((metadata or {}).get("kind") or "")
        return 0.6 if sub == "experiment" else 0.5
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
                        # name → hash index for authored, invocable artifacts
                        meta_top = row.get("metadata") or {}
                        if (isinstance(meta_top, dict) and meta_top.get("name")
                                and row.get("kind") in ("tool_written", "code_committed")):
                            _artifact_names[str(meta_top["name"])] = h
                        # path → hash index (A2.1): any row that names the file
                        # it wrote lets a later read resolve that file to the
                        # credited artifact.
                        if isinstance(meta_top, dict) and meta_top.get("path"):
                            np = _norm_path(meta_top["path"])
                            if np:
                                _path_hash[np] = h
                        # re-use counts are persisted as their own rows
                        if row.get("kind") == "reuse":
                            _reuse_counts[h] = _reuse_counts.get(h, 0) + 1
                        gid = row.get("goal_id")
                        # bookkeeping rows never attribute to a goal (Fix 5) —
                        # otherwise a rehydrate would hand has_qualifying_effect
                        # a self-model row as artifact evidence.
                        if gid and not row.get("dedupe") and row.get("kind") != "bookkeeping":
                            _goal_effects.setdefault(str(gid), []).append(h)
                            _hash_goal[h] = str(gid)
                            if row.get("kind"):
                                _hash_kind[h] = str(row.get("kind"))
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
    # No caller-supplied cycle: read the persisted counter so contextless
    # writers (symbolic engine, goal runner) don't all stamp cycle 0 —
    # 119/150 rows in the 2026-07-02 run were time-blind for this reason.
    try:
        from brain.utils.get_cycle_count import get_cycle_count
        return int(get_cycle_count() or 0)
    except Exception:  # intentional: counter unreadable → 0 (old behavior)
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
    # Fix 5: route self-model bookkeeping to its own ledger class before any
    # crediting logic runs (callers stay unchanged — the seam decides).
    if kind == "symbolic_artifact" and str((metadata or {}).get("kind") or "") in _BOOKKEEPING_SUB_KINDS:
        kind = "bookkeeping"
    if kind not in EFFECT_KINDS:
        # unknown kind: record nothing rather than silently miscredit
        return None
    raw = str(content or "")
    normalized = _normalize(raw)
    if not normalized:
        return None
    content_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    # A named, invocable artifact (tool / cognitive function) registers its
    # name → hash so a later invocation can be credited as re-use, regardless of
    # whether this particular write was a novel production or an identical rewrite.
    _artifact_name = (metadata or {}).get("name") if isinstance(metadata, dict) else None

    with _lock:
        if _artifact_name and kind in ("tool_written", "code_committed"):
            _artifact_names[str(_artifact_name)] = content_hash
        # A2.1: index the written file's path → hash (dedupe rows too — a
        # rewrite still leaves the file resolvable to its credited content).
        if isinstance(metadata, dict) and metadata.get("path"):
            _np = _norm_path(metadata["path"])
            if _np:
                _path_hash[_np] = content_hash
        is_dup = content_hash in _seen_hashes
        nov = _compute_novelty(kind, normalized, content_hash) if novelty is None else float(novelty)
        # An explicit caller-supplied novelty still can't beat the exact-dup gate.
        if is_dup:
            nov = 0.0
        sig = 0.0 if nov <= 0.0 else _structural_significance(kind, raw, normalized, metadata)
        # AR1 rate cap — symbolic credit beyond the rolling window earns nothing.
        if kind == "symbolic_artifact" and sig > 0.0:
            now_m = time.monotonic()
            while _symbolic_credit_times and (now_m - _symbolic_credit_times[0]) > _SYMBOLIC_CAP_WINDOW_S:
                _symbolic_credit_times.popleft()
            if len(_symbolic_credit_times) >= _SYMBOLIC_CAP:
                sig = 0.0
                metadata = dict(metadata or {})
                metadata["rate_capped"] = True
            else:
                _symbolic_credit_times.append(now_m)
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
        # S7 lane bridge: every recorded row — any kind, any thread — is visible
        # to the production-funnel telemetry via drain_rows_since_last(). The
        # 2026-07-02 run counted 0 attempts in 10k cycles because the funnel
        # read a context list only two conscious-lane writers populated.
        _recent_rows.append(row.to_json())

        # Even a dedupe row is remembered (so the next identical one also dedupes),
        # but it earns nothing and is not attributed to a goal as a production.
        _seen_hashes.add(content_hash)
        dq = _recent_by_kind.setdefault(kind, deque(maxlen=_NOVELTY_WINDOW))
        dq.append((content_hash, normalized))

        _credited = not (row.dedupe or row.significance <= 0.0)
        # F1c (2026-07-05 findings): expose this effect's VALUE to the caller's
        # lane so learning isn't conscious-lane-only — the executive lane paid a
        # flat per-step reward and compose_section's EMA sat neutral through
        # ~160 zero-value repetitions. The executive pops this after each step
        # and posts novelty×significance into the same EMA think() learns from.
        if isinstance(context, dict):
            context["_last_effect_outcome"] = {
                "kind": kind,
                "credited": _credited,
                "novelty": row.novelty,
                "significance": row.significance,
                "ts": time.time(),
            }
        # F3 (2026-07-05 findings): a credited prose effect's BODY is an
        # artifact, not a memory — capture it in the content-addressed sidecar
        # at the single record chokepoint, so memory hygiene (pruner, decay)
        # can never eat the only copy of a ledger-credited note again. capture()
        # is idempotent and floor-gated; junk below MIN_ARTIFACT_CHARS is not
        # stored.
        if _credited:
            try:
                from brain.agency.effect_artifacts import capture as _capture_artifact
                _capture_artifact(raw, content_hash=content_hash)
            except Exception as exc:
                record_failure("effect_ledger.capture_artifact", exc)

        if not _credited:
            return None

        if goal_id:
            gid = str(goal_id)
            _goal_effects.setdefault(gid, []).append(content_hash)
            _hash_goal[content_hash] = gid
            _hash_kind[content_hash] = kind
            _goal_significance[gid] = max(_goal_significance.get(gid, 0.0), row.significance)
            # Fix 2/4 (RUN6_FIX_PLAN §3): a credited effect is the "real action"
            # signal the commitment score reads — it clears the goal's staleness
            # and feeds its learned value, so pursuit that pays off keeps the
            # driver slot and pursuit that never lands loses it.
            try:
                from brain.cognition.planning.commitment_value import note_goal_credit
                note_goal_credit(gid, row.significance)
            except Exception as exc:
                record_failure("effect_ledger.note_goal_credit", exc)
            if kind == "tracked_work":
                try:
                    _tracked_progress[gid] = max(
                        _tracked_progress.get(gid, 0),
                        int((metadata or {}).get("completed_sections") or 0),
                    )
                except Exception as exc:
                    record_failure("effect_ledger.record_tracked_progress", exc)
        # AR4: queue the production credit for finalize_cycle to pay on the live
        # cycle context (symbolic producers can't persist affect themselves).
        if kind == "symbolic_artifact":
            _pending_production.append({
                "kind": kind,
                "sub_kind": str((metadata or {}).get("kind") or ""),
                "significance": row.significance,
                "goal_id": row.goal_id,
            })
            if len(_pending_production) > _PENDING_PRODUCTION_MAX:
                del _pending_production[:-_PENDING_PRODUCTION_MAX]
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


def has_effect_kind(goal_id: str, kind: str) -> bool:
    """True if a *novel* (credited) effect of exactly `kind` was recorded for this
    goal. P3's check-pass proxy: `has_effect_kind(gid, "tool_run_effect")` lets
    `is_sated` close a verifiable goal on a passed sandbox check specifically,
    rather than on any effect (which `has_qualifying_effect` would accept)."""
    if not goal_id or not kind:
        return False
    _hydrate()
    with _lock:
        for h in _goal_effects.get(str(goal_id), []):
            if _hash_kind.get(h) == kind:
                return True
        return False


def significance_for_goal(goal_id: str) -> float:
    """Max structural significance among a goal's recorded effects (P8). Feeds the
    completion metric so mean_significance reflects real produced work, not the
    self-asserted achievement multiplier that produced the run's 0.0."""
    if not goal_id:
        return 0.0
    _hydrate()
    with _lock:
        return float(_goal_significance.get(str(goal_id), 0.0))


def kind_for_hash(content_hash: str) -> Optional[str]:
    """The effect kind recorded for a credited artifact's content_hash, or None.
    Read by the quality-standard proposer to pick the kind-aware promotion anchor
    (code/tool → reuse; prose → long-memory persistence)."""
    if not content_hash:
        return None
    _hydrate()
    with _lock:
        return _hash_kind.get(content_hash)


def credited_goal_ids() -> List[str]:
    """Goal ids that have at least one credited (non-dedupe) effect. The candidate
    set the promotion proposer walks (read-only)."""
    _hydrate()
    with _lock:
        return list(_goal_effects.keys())


def hash_for_path(path: Any) -> Optional[str]:
    """Resolve a file path back to the content_hash of the ledger row that wrote
    it, or None for a file the ledger never produced (A2.1 — the primitive every
    read-path reuse credit needs). Accepts any path form; normalizes the same way
    the write-side index does."""
    np = _norm_path(path)
    if not np:
        return None
    _hydrate()
    with _lock:
        return _path_hash.get(np)


def mark_reused_path(path: Any) -> Optional[int]:
    """Convenience for read paths (A2.2): if `path` resolves to a produced
    artifact, credit tier-3 re-use and return the new reuse count; else None.
    Never raises — reading must not break because crediting did."""
    try:
        h = hash_for_path(path)
        if not h:
            return None
        return mark_reused(h)
    except Exception as exc:
        record_failure("effect_ledger.mark_reused_path", exc)
        return None


def mark_reused(content_hash: str) -> int:
    """Tier-3 (deferred, strong) significance: the artifact was referenced again
    later — a tool invoked, a memo cited by a later goal, a message replied to.
    Re-use is the only ungameable significance signal. Returns the new reuse count.

    Re-use also lifts the owning goal's recorded significance toward the ceiling,
    so `significance_for_goal` (the headline mean_significance metric) reflects work
    that actually got used, not just work that got written.
    """
    if not content_hash:
        return 0
    _hydrate()
    with _lock:
        _reuse_counts[content_hash] = _reuse_counts.get(content_hash, 0) + 1
        n = _reuse_counts[content_hash]
        gid = _hash_goal.get(content_hash)
        if gid:
            prior = _goal_significance.get(gid, 0.0)
            _goal_significance[gid] = min(1.0, max(prior, 0.6) + 0.1)
    try:
        _append_row(EffectRow(
            ts=now_iso_z(), cycle=0, kind="reuse",
            content_hash=content_hash, novelty=0.0,
            significance=1.0, goal_id=gid, char_len=0, dedupe=False,
            metadata=None,
        ))
    except Exception as exc:
        record_failure("effect_ledger.mark_reused", exc)
    return n


def mark_corrected(content_hash: str) -> int:
    """The mirror of `mark_reused` (P2b): the person CORRECTED this produced artifact,
    so it was wrong/unwanted — write its significance DOWN, and pull the owning goal's
    recorded significance down with it. Re-use is the ungameable *positive* signal; a
    human correction of produced work is the ungameable *negative* one. Returns the new
    correction count for the hash."""
    if not content_hash:
        return 0
    _hydrate()
    gid = None
    with _lock:
        _correction_counts[content_hash] = _correction_counts.get(content_hash, 0) + 1
        n = _correction_counts[content_hash]
        gid = _hash_goal.get(content_hash)
        if gid:
            prior = _goal_significance.get(gid, 0.0)
            # halve, then a floor penalty — a corrected artifact should not keep a
            # high headline significance (it did not land).
            _goal_significance[gid] = round(max(0.0, prior * 0.5 - 0.1), 4)
    try:
        _append_row(EffectRow(
            ts=now_iso_z(), cycle=0, kind="correction",
            content_hash=content_hash, novelty=0.0,
            significance=0.0, goal_id=gid, char_len=0, dedupe=False,
            metadata=None,
        ))
    except Exception as exc:
        record_failure("effect_ledger.mark_corrected", exc)
    return n


def correction_count(content_hash: str) -> int:
    """How many times this artifact has been corrected (0 if never). Read-only."""
    if not content_hash:
        return 0
    _hydrate()
    with _lock:
        return int(_correction_counts.get(content_hash, 0))


def note_artifact_use(name: str) -> Optional[int]:
    """Record that an Orrin-authored, named artifact (a tool / cognitive function)
    was invoked by name — the canonical tier-3 re-use event. Returns the new re-use
    count, or None when `name` is not a known authored artifact (a built-in or any
    function Orrin did not write → not re-use, no credit).

    The caller (a dispatch chokepoint) usually has no context that can persist
    affect, so the reward is *queued* here and paid by finalize_cycle on the live
    cycle context via `drain_pending_reuse`.
    """
    if not name:
        return None
    _hydrate()
    with _lock:
        h = _artifact_names.get(str(name))
    if not h:
        return None
    n = mark_reused(h)
    with _lock:
        gid = _hash_goal.get(h)
        _pending_reuse.append({"name": str(name), "hash": h, "goal_id": gid, "count": n})
        if len(_pending_reuse) > _PENDING_REUSE_MAX:
            del _pending_reuse[:-_PENDING_REUSE_MAX]
    return n


def drain_pending_reuse() -> List[Dict[str, Any]]:
    """Hand the queued tier-3 re-use credits to the reward layer and clear them.
    Each entry: {name, hash, goal_id, count}. finalize_cycle pays a diminishing
    bonus per entry so re-invoking the same artifact can't be farmed."""
    _hydrate()
    with _lock:
        if not _pending_reuse:
            return []
        out = list(_pending_reuse)
        _pending_reuse.clear()
        return out


def drain_pending_production(limit: int = 4) -> List[Dict[str, Any]]:
    """AR4: hand queued symbolic production credits to the reward layer.
    Each entry: {kind, sub_kind, significance, goal_id}. Capped per drain so a
    burst can't dump unbounded reward into one cycle (the rest pay next cycle);
    the record-time rate cap already bounds total volume."""
    _hydrate()
    with _lock:
        if not _pending_production:
            return []
        out = _pending_production[:max(1, int(limit))]
        del _pending_production[:len(out)]
        return out


def drain_recent_rows() -> List[Dict[str, Any]]:
    """S7 lane bridge: hand every effect row recorded since the last drain to the
    production-funnel telemetry (finalize). Rows come from ALL lanes — conscious
    writers, the symbolic engine, the goals-daemon runner — so the funnel's
    attempt/success counters can no longer be blind to a whole lane."""
    with _lock:
        out = list(_recent_rows)
        _recent_rows.clear()
        return out


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
        _correction_counts.clear()
        _goal_effects.clear()
        _goal_significance.clear()
        _tracked_progress.clear()
        _artifact_names.clear()
        _path_hash.clear()
        _hash_goal.clear()
        _hash_kind.clear()
        _pending_reuse.clear()
        _pending_production.clear()
        _recent_rows.clear()
        _symbolic_credit_times.clear()
        _hydrated = False
