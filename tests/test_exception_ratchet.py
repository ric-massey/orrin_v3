"""Forward ratchet for silent broad exception handlers (STRUCTURAL_DEBT_PLAN §9).

The 2026-06-18 engineering audit's finding §9: ``except Exception:`` blocks whose
only body is ``pass``/``continue``/``return`` with no logging make *dead paths and
partial failures look healthy* — a swallowed I/O error or schema mismatch is
indistinguishable from success. The audit counted 603 such handlers across 247
files.

Big-bang reclassification of 603 sites is unsafe and unreviewable, so — mirroring
``test_module_size.py`` and ``test_package_layering.py`` — this is a **forward
ratchet**: it freezes the count at ``CEILING`` and fails the build if it rises.
New silent handlers can no longer be added; the number can only go down. As worst
files are reclassified (log / narrow / re-raise / annotate the genuinely-intentional
ones) the real count drops, and ``CEILING`` is lowered in the same commit — the
ceiling at convergence is the permanent floor.

The scan policy and the ceiling are the single source of truth in
``brain/scripts/audit_exception_handlers.py`` — the human-readable report
(``make audit-exceptions``) and this gate share them so they can never disagree.

To intentionally change the count: reclassify handlers and lower ``CEILING`` in the
same commit (never raise it).
"""

from brain.scripts.audit_exception_handlers import (
    CEILING,
    find_silent_broad_handlers,
    repo_root,
)


def test_silent_handler_count_at_or_below_ceiling():
    findings = find_silent_broad_handlers(repo_root())
    count = len(findings)
    assert count <= CEILING, (
        f"Silent broad exception handlers rose to {count} (ceiling {CEILING}).\n"
        "New `except Exception:` blocks whose only body is pass/continue/return "
        "with no logging are forbidden — they hide failures.\n"
        "Log via record_failure/get_logger, narrow the exception type, re-raise, "
        "or (if genuinely intentional) annotate with `# intentional: <category>` "
        "and a real handler body. See STRUCTURAL_DEBT_PLAN_2026-06-23.md §9."
    )


def test_ceiling_is_not_stale():
    # If the real count has dropped below the ceiling, lower CEILING to match so it
    # keeps ratcheting down (the same anti-staleness guard as the size ratchet).
    count = len(find_silent_broad_handlers(repo_root()))
    assert count == CEILING, (
        f"Silent handler count is {count} but CEILING is {CEILING}. Lower CEILING "
        f"to {count} in brain/scripts/audit_exception_handlers.py — the ratchet "
        "must track the real floor so it can't go stale."
    )
