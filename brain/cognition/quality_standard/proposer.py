# brain/cognition/quality_standard/proposer.py
#
# P1b — promotion proposer  &  P3 — suspect proposer.  Both are READ-ONLY: they
# only ever write to the candidate store (revisions.py). No exemplar file is
# touched here — that is the gate's (P2) / ratify path's (P4) job.
#
# THE ANCHOR IS THE EFFECT LEDGER, NOT PREFERENCE (design §2 / §4.3 #1). A produced
# artifact becomes a promotion candidate only on *downstream* credit — the
# ungameable signal — never on Orrin's wish to close a goal:
#
#   * code / tool artifacts  → require reuse >= 1.  The reuse path
#     (note_artifact_use ← tool_runner.dispatch / finalize) is keyed by artifact
#     NAME, so it is reachable ONLY for named authored artifacts. You can fabricate
#     a file; you cannot fabricate your future self choosing to call it.
#   * prose artifacts (express_to_user / compose_section) → require long_memory
#     PERSISTENCE (importance above the retention floor). Prose is never marked
#     reused (no name to invoke), so reuse>=1 is structurally unreachable for it —
#     persistence is the only viable, and therefore the required, anchor.
#
# Structural significance at write time is NEVER sufficient on its own for either
# kind (risk register: promotion needs downstream credit, not self-report).
#
# RESEARCH LINEAGE.
#   * Revealed preference — actual downstream USE reveals value better than any
#     stated/self-reported value (Samuelson 1938, "A Note on the Pure Theory of
#     Consumer's Behaviour"). The reuse anchor IS a revealed-preference test: you
#     cannot fabricate your future self choosing to invoke an artifact by name.
#   * Selective memory consolidation — salient/important traces survive, trivial
#     ones decay; persistence is therefore a value signal (McGaugh 2000, "Memory —
#     a century of consolidation", Science; Tononi & Cirelli's SHY, already cited in
#     idle_consolidation/consolidation_cycle.py). This is why the prose anchor is
#     "did it persist as IMPORTANT in long_memory", not "was it written". The
#     specific importance/Jaccard thresholds below are engineering knobs, not
#     calibrated to this work.
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from brain import paths
from brain.agency import effect_ledger
from brain.agency import effect_artifacts
from brain.paths import LONG_MEMORY_FILE
from brain.utils.json_utils import load_json
from brain.utils.log import log_activity
from brain.utils.failure_counter import record_failure
from brain.cognition.quality_standard import revisions

# Kinds (effect_ledger.EFFECT_KINDS) grouped by their required anchor.
_CODE_KINDS = frozenset({"tool_written", "code_committed"})
_PROSE_KINDS = frozenset({"note_novel", "message_answered", "tracked_work",
                          "file_write", "external_post"})

# Prose persistence bar (plan §6 open decision, proposed): importance above the
# long_memory retention floor. Default-written memories are importance 1; the
# "important" tier the prune scorer protects sits at >= 4.
_PROSE_IMPORTANCE_FLOOR = 4
# How much word overlap counts an artifact as "the same content" as a memory.
_PERSIST_SIM = 0.4

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]+")


def _words(text: str) -> set:
    return set(w for w in _WORD_RE.findall((text or "").lower()) if len(w) > 2)


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


# ── prose persistence anchor ────────────────────────────────────────────────────

def _long_memory_persistence(text: str) -> List[str]:
    """Memory ids of important, persisted long_memory entries whose content matches
    `text`. Empty list = no persistence evidence (→ no promotion, by design)."""
    refs: List[str] = []
    try:
        lm = load_json(LONG_MEMORY_FILE, default_type=list) or []
    except Exception as exc:
        record_failure("quality_standard.proposer._long_memory_persistence", exc)
        return refs
    target = _words(text)
    if not target:
        return refs
    for m in lm:
        if not isinstance(m, dict):
            continue
        try:
            if int(m.get("importance") or 0) < _PROSE_IMPORTANCE_FLOOR:
                continue
        except (TypeError, ValueError):
            continue
        if _jaccard(target, _words(str(m.get("content") or ""))) >= _PERSIST_SIM:
            mid = m.get("id")
            if mid:
                refs.append(str(mid))
    return refs


# ── near-duplicate guard against the existing exemplar set ──────────────────────

def _is_near_duplicate_exemplar(text: str) -> bool:
    """True if `text` closely matches an existing exemplar — a redundant promotion
    the gate would reject anyway; the proposer skips it up front (cheap word-set
    Jaccard; the gate re-checks before any write)."""
    try:
        if not paths.QUALITY_EXEMPLARS_DIR.is_dir():
            return False
        target = _words(text)
        if not target:
            return False
        for p in paths.QUALITY_EXEMPLARS_DIR.iterdir():
            if not p.is_file() or p.name.startswith("_") or p.name in ("README.md",):
                continue
            try:
                if _jaccard(target, _words(p.read_text(encoding="utf-8"))) >= 0.8:
                    return True
            except OSError:
                continue
    except Exception as exc:
        record_failure("quality_standard.proposer._is_near_duplicate_exemplar", exc)
    return False


def _signal_prior(context: Optional[Dict[str, Any]], goal_id: str) -> Optional[float]:
    """Ordering-only hint: did this goal *feel* meaningful / kept-returned-to. Read
    at proposal time to ORDER the review queue — never counted toward the evidence
    threshold (guardrail: emotions are not an evidence source). May be None."""
    if not isinstance(context, dict):
        return None
    try:
        priors = context.get("_goal_signal_prior")
        if isinstance(priors, dict) and goal_id in priors:
            return float(priors[goal_id])
    except (TypeError, ValueError):
        pass
    return None


# ── P1b: promotion proposer ─────────────────────────────────────────────────────

def propose_promotions(context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Scan credited goals; emit `promote` candidates for artifacts that earned the
    kind-appropriate downstream credit AND whose text we captured (P1a). Read-only:
    writes only to the candidate store. Returns the candidates appended this pass."""
    appended: List[Dict[str, Any]] = []
    try:
        goal_ids = effect_ledger.credited_goal_ids()
    except Exception as exc:
        record_failure("quality_standard.proposer.credited_goal_ids", exc)
        return appended

    for gid in goal_ids:
        try:
            hashes = effect_ledger.effects_for_goal(gid)
        except Exception as exc:
            record_failure("quality_standard.proposer.effects_for_goal", exc)
            continue
        gsig = effect_ledger.significance_for_goal(gid)
        for chash in hashes:
            kind = effect_ledger.kind_for_hash(chash)
            if not kind:
                continue
            text = effect_artifacts.load(chash)
            if not text:
                continue  # text wasn't captured (pre-P1a / junk) → can't promote

            # Kind-aware downstream-credit anchor (the whole anti-gaming property).
            memory_refs: List[str] = []
            reuse = 0
            if kind in _CODE_KINDS:
                reuse = effect_ledger.reuse_count(chash)
                if reuse < 1:
                    continue  # no reuse → no credit → not a promotion
            elif kind in _PROSE_KINDS:
                memory_refs = _long_memory_persistence(text)
                if not memory_refs:
                    continue  # not persisted as important → no credit
            else:
                continue  # unknown kind → conservative skip

            if _is_near_duplicate_exemplar(text):
                continue  # redundant with the existing golden set

            candidate = revisions.make_candidate(
                kind="promote",
                direction="raise",   # promotion only ever RAISES the bar (auto-applicable)
                artifact_ref={"goal_id": gid, "content_hash": chash},
                goals=[gid],
                effect_rows=[chash],
                significance=gsig,
                reuse_count=reuse,
                memory_refs=memory_refs,
                signal_prior=_signal_prior(context, gid),
                note=f"downstream-credited {kind} artifact for goal {gid}",
            )
            saved = revisions.append(candidate)
            # append() is idempotent; only count genuinely new pending rows.
            if saved is candidate or saved.get("status") == "pending":
                if saved is candidate:
                    appended.append(saved)
    if appended:
        log_activity(f"[quality_standard] {len(appended)} promotion candidate(s) proposed.")
    return appended


# ── P3: suspect proposer ────────────────────────────────────────────────────────
#
# Flag an EXISTING exemplar as `suspect` when it contradicts accumulated evidence.
# Two concrete, evidence-keyed contradictions (never auto-applied — humans decide):
#   1. the exemplar is a near-duplicate of an ANTI-exemplar (the golden set
#      simultaneously says "good" and "slop" for the same shape), or
#   2. the CURRENT predicate now rejects the exemplar (it can no longer be the
#      positive standard it claims to be — e.g. after a P4 rule edit).

def propose_suspects(context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Emit `suspect` candidates (direction=lower) for self-contradicting exemplars.
    Read-only: writes only to the candidate store; resolution is human (P4)."""
    appended: List[Dict[str, Any]] = []
    try:
        from brain.cognition.quality_predicate import assess_quality
    except Exception as exc:
        record_failure("quality_standard.proposer.propose_suspects.import", exc)
        return appended

    if not paths.QUALITY_EXEMPLARS_DIR.is_dir():
        return appended

    anti_words: List[set] = []
    try:
        if paths.QUALITY_ANTI_EXEMPLARS_DIR.is_dir():
            for p in paths.QUALITY_ANTI_EXEMPLARS_DIR.iterdir():
                if p.is_file() and not p.name.startswith("_") and p.name != "README.md":
                    anti_words.append(_words(p.read_text(encoding="utf-8")))
    except Exception as exc:
        record_failure("quality_standard.proposer.read_anti", exc)

    existing = {
        (r.get("artifact_ref") or {}).get("artifact_path")
        for r in revisions.load()
        if r.get("kind") == "suspect" and r.get("status") in ("pending", "applied")
    }

    for p in sorted(paths.QUALITY_EXEMPLARS_DIR.iterdir()):
        if not p.is_file() or p.name.startswith("_") or p.name == "README.md":
            continue
        path_str = str(p)
        if path_str in existing:
            continue  # already flagged & unresolved
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        ew = _words(text)
        reason = None
        contradicting: List[str] = []
        for aw in anti_words:
            if _jaccard(ew, aw) >= 0.8:
                reason = "near_duplicate_of_anti_exemplar"
                break
        if reason is None:
            verdict = assess_quality(text)
            if not verdict.ok:
                reason = f"predicate_now_rejects:{verdict.reason}"
        if reason is None:
            continue

        candidate = revisions.make_candidate(
            kind="suspect",
            direction="lower",   # removing/loosening an exemplar — human-ratified only
            artifact_ref={"artifact_path": path_str},
            note=f"exemplar {p.name} contradicts evidence: {reason}",
            extra={"reason": reason, "contradicting_anti_exemplars": contradicting},
        )
        appended.append(revisions.append(candidate))

    if appended:
        log_activity(f"[quality_standard] {len(appended)} suspect exemplar(s) flagged for review.")
    return appended
