"""Phase-7 module-size ratchet (the size/complexity report's enforcement spine).

Phase 4/4.5 drove every oversized module under the agreed **600-line soft limit**
(see CODEBASE_CLEANUP_PLAN 4.5C). This test locks that in so the list "cannot
silently regrow" — the condition 4.5C's exit criteria defers to Phase 7.

It is a **forward ratchet**, the same shape as ``test_package_layering.py``: the
soft limit is hard for any *new or modified* source module, and the small set of
files already over the limit when the ratchet landed is frozen in
``size_report.EXEMPT`` with a recorded reason. A new file over the limit fails
the build; an exempt file is expected to trend *down*, and the ratchet fails if
an exempt file is deleted or drops under the limit (so the exemption can't go
stale).

The scan policy (roots, exclusions, limit, exemptions) is the single source of
truth in ``brain/scripts/size_report.py`` — the human-readable report
(``make size-report``) and this gate share it so they can never disagree.

To intentionally land a module over the limit: add it to ``size_report.EXEMPT``
with a justification in the same commit (the way ``BASELINE_EDGES`` is extended).
"""

from pathlib import Path

from brain.scripts.size_report import (
    EXEMPT,
    REPO,
    SOFT_LIMIT,
    _line_count,
    module_sizes,
)


def test_no_new_module_over_soft_limit():
    offenders = [
        (rel, lines)
        for rel, lines in module_sizes()
        if lines > SOFT_LIMIT and rel not in EXEMPT
    ]
    assert not offenders, (
        f"Source module(s) exceed the {SOFT_LIMIT}-line soft limit:\n"
        + "\n".join(f"  {rel}: {lines} lines" for rel, lines in offenders)
        + "\n\nDecompose the module (bottom-up extraction, re-export the public "
        "API — see CODEBASE_CLEANUP_PLAN 4.5C), or, if the size is justified, add "
        "it to EXEMPT in brain/scripts/size_report.py with a reason."
    )


def test_exemptions_are_not_stale():
    # An exempt file that no longer exists, or has dropped under the limit, must
    # be removed from EXEMPT so the list reflects reality and keeps shrinking.
    stale = []
    for rel in EXEMPT:
        path = Path(REPO) / rel
        if not path.exists():
            stale.append(f"{rel} (no longer exists)")
        elif _line_count(path) <= SOFT_LIMIT:
            stale.append(f"{rel} (now under {SOFT_LIMIT} lines — remove the exemption)")
    assert not stale, (
        "Stale size exemption(s) in brain/scripts/size_report.py:\n"
        + "\n".join(f"  {s}" for s in stale)
        + f"\n\n(reasons on file: {EXEMPT})"
    )
