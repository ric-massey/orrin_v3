# brain/cognition/quality_standard/gate.py
#
# P2 — the promotion gate.  THE ONLY AUTO-APPLY PATH in this component.
#
# WHAT THIS IS — A RATCHET-PIN, NOT BAR-DEVELOPMENT (plan §P2). Adding an exemplar
# the *current* predicate already accepts imposes NO new constraint on the predicate
# today — it passes by construction. Its only effect is to PIN that artifact as
# protected-good, so a future P4 rule loosening that would start rejecting it shows
# up as a regression. The real movement of the bar (stricter/broader rules) happens
# only in P4's human rule edits. This phase ratchets a floor under what's already
# known-good; it does not make the standard "smarter."
#
# THE SAFETY PROPERTY IS DIRECTION + PREDICATE-CONFORMANCE, NOT THE REGRESSION TEST.
# The T0.5 regression judges each fixture in ISOLATION (no prior_outputs), so the
# near-duplicate gate is unreachable there and a predicate-passing exemplar CANNOT
# turn it red. What makes this branch safe is checked BEFORE write: it only ever
# (a) ADDS an exemplar (raise-direction, never loosens), and (b) adds one the rules
# ALREADY accept (no rule change). The regression here is only a smoke check for a
# broken fixture file / IO error — relied on for nothing more.
#
# A candidate the predicate REJECTS is NOT auto-promoted: it is a "predicate too
# strict" signal routed to the human-ratify path (needs_rule_review). Editing a
# rule is the only thing that changes predicate logic, and it is never automatic.
#
# RESEARCH LINEAGE. The direction asymmetry (auto-tighten, human-only loosen) is the
# operational answer to Goodhart's law (Goodhart 1975; Strathern 1997; Manheim &
# Garrabrant 2018): the one gameable direction — loosening the grade to pass — is the
# only one denied an automatic path. Add-only auto-apply is a fail-safe monotonicity
# (ratchet) pattern: a standard engineering safety idiom, not a specific empirical
# result. See the package header (__init__.py) for the full safety lineage.
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from brain import paths
from brain.cognition.quality_predicate import assess_quality
from brain.agency import effect_artifacts
from brain.utils.log import log_activity
from brain.utils.failure_counter import record_failure
from brain.cognition.quality_standard import revisions

_IGNORE = {"README.md", "PLACEHOLDER.md"}
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]+")
_NEAR_DUP_SIM = 0.8


def _words(text: str) -> set:
    return set(w for w in _WORD_RE.findall((text or "").lower()) if len(w) > 2)


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b) if (a | b) else 0.0


def _golden_files(directory: Path) -> List[Path]:
    if not directory.is_dir():
        return []
    return [p for p in sorted(directory.iterdir())
            if p.is_file() and p.name not in _IGNORE and not p.name.startswith("_")]


def regression_smoke() -> Tuple[bool, str]:
    """The T0.5 invariant, evaluated in-process exactly as the regression test does:
    the predicate must PASS every exemplar and REJECT every anti-exemplar, each judged
    in isolation. Returns (ok, reason). On the P2 branch this is a SMOKE CHECK (a
    predicate-passing add can't fail it); it has real teeth only at P4."""
    for p in _golden_files(paths.QUALITY_EXEMPLARS_DIR):
        try:
            v = assess_quality(p.read_text(encoding="utf-8"))
        except OSError as exc:
            return False, f"unreadable_exemplar:{p.name}:{exc}"
        if not v.ok:
            return False, f"exemplar_rejected:{p.name}:{v.reason}"
    for p in _golden_files(paths.QUALITY_ANTI_EXEMPLARS_DIR):
        try:
            v = assess_quality(p.read_text(encoding="utf-8"))
        except OSError as exc:
            return False, f"unreadable_anti_exemplar:{p.name}:{exc}"
        if v.ok:
            return False, f"anti_exemplar_passed:{p.name}"
    return True, "ok"


def _slug(text: str, content_hash: str) -> str:
    """Stable, readable exemplar filename: first heading/line + short hash suffix
    (the hash keeps it unique and traceable back to the effect row)."""
    first = ""
    for line in (text or "").splitlines():
        s = re.sub(r"^#+\s*", "", line).strip()
        if s:
            first = s
            break
    base = re.sub(r"[^a-z0-9]+", "-", first.lower()).strip("-")[:48] or "exemplar"
    return f"{base}-{(content_hash or '')[:8]}"


def _is_near_duplicate(text: str) -> Optional[str]:
    """Name of an existing exemplar this text closely duplicates, else None. An
    EXPLICIT shingle/Jaccard check the gate runs (NOT something the regression does —
    the regression judges fixtures in isolation and never compares them)."""
    target = _words(text)
    if not target:
        return None
    for p in _golden_files(paths.QUALITY_EXEMPLARS_DIR):
        try:
            if _jaccard(target, _words(p.read_text(encoding="utf-8"))) >= _NEAR_DUP_SIM:
                return p.name
        except OSError:
            continue
    return None


def apply_pending_promotions() -> List[Dict[str, Any]]:
    """Process every pending `promote` candidate (plan §P2). Returns the list of
    rows whose status changed this pass (applied / rejected / needs_rule_review)."""
    changed: List[Dict[str, Any]] = []
    for cand in revisions.pending(kind="promote"):
        cid = cand.get("id")
        ref = cand.get("artifact_ref") or {}
        chash = ref.get("content_hash")
        text = effect_artifacts.load(chash) if chash else None
        if not text:
            revisions.mark(cid, "rejected", reason="artifact_text_unavailable")
            changed.append(revisions.get(cid))
            continue

        # 1) Run the CURRENT predicate in isolation — the same call the regression
        #    makes (assess_quality(text), no goal / no prior_outputs) — so a pass
        #    here guarantees the fixture passes the regression by construction.
        verdict = assess_quality(text)

        if not verdict.ok:
            # 3) Predicate rejects → "predicate too strict" signal, NOT a promotion.
            #    Hold for human rule review (P4). The only path that changes predicate
            #    logic, and it is never automatic.
            revisions.mark(
                cid, "pending",
                needs_rule_review=True,
                failing_reason=verdict.reason,
            )
            changed.append(revisions.get(cid))
            log_activity(
                f"[quality_standard] promote {cid} rejected by predicate "
                f"({verdict.reason}) → routed to human rule review (P4)."
            )
            continue

        # 2) Predicate already passes → safe to PIN. First skip redundant adds.
        dup = _is_near_duplicate(text)
        if dup:
            revisions.mark(cid, "rejected", reason=f"near_duplicate_exemplar:{dup}")
            changed.append(revisions.get(cid))
            continue

        slug = _slug(text, chash)
        dest = paths.QUALITY_EXEMPLARS_DIR / f"{slug}.md"
        try:
            paths.QUALITY_EXEMPLARS_DIR.mkdir(parents=True, exist_ok=True)
            if dest.exists():  # extremely unlikely (hash-suffixed); treat as dup
                revisions.mark(cid, "rejected", reason="exemplar_path_exists")
                changed.append(revisions.get(cid))
                continue
            dest.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
        except OSError as exc:
            record_failure("quality_standard.gate.write_exemplar", exc)
            revisions.mark(cid, "pending", apply_error=str(exc))
            continue

        # Smoke check: catches a broken fixture file / IO error only — by the §P2
        # argument it cannot go red on a predicate-passing exemplar. If it somehow
        # does, roll back the write rather than leave the golden set wedged.
        ok, reason = regression_smoke()
        if not ok:
            try:
                dest.unlink()
            except OSError:
                pass
            revisions.mark(cid, "pending", apply_error=f"smoke_failed:{reason}")
            log_activity(f"[quality_standard] promote {cid} rolled back (smoke: {reason}).")
            continue

        revisions.mark(cid, "applied", exemplar_path=str(dest))
        changed.append(revisions.get(cid))
        log_activity(f"[quality_standard] exemplar promoted: {dest.name} (candidate {cid}).")

    return changed
