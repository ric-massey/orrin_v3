# brain/cognition/quality_standard/cli.py
#
# P4/P6 — the HUMAN ratify surface (a CLI; the UI calls the same ratify.py API).
# This is the human-in-the-loop entry for every loosening; cognition never reaches it.
#
#   python -m brain.cognition.quality_standard.cli list
#   python -m brain.cognition.quality_standard.cli show   <id>
#   python -m brain.cognition.quality_standard.cli approve <id>
#   python -m brain.cognition.quality_standard.cli reject  <id> [reason]
#   python -m brain.cognition.quality_standard.cli restore <id>
#   python -m brain.cognition.quality_standard.cli history       (applied audit trail)
from __future__ import annotations

import json
import sys
from typing import List

from brain.cognition.quality_standard import ratify, revisions


def _fmt(row: dict) -> str:
    ev = row.get("evidence") or {}
    ref = row.get("artifact_ref") or {}
    bits = [
        f"id={row.get('id')}",
        f"kind={row.get('kind')}",
        f"dir={row.get('direction')}",
        f"status={row.get('status')}",
    ]
    if row.get("needs_rule_review"):
        bits.append(f"needs_rule_review({row.get('failing_reason')})")
    if ref.get("artifact_path"):
        bits.append(f"path={ref['artifact_path']}")
    if ev.get("reuse_count"):
        bits.append(f"reuse={ev['reuse_count']}")
    if ev.get("memory_refs"):
        bits.append(f"memory_refs={len(ev['memory_refs'])}")
    if ev.get("signal_prior") is not None:
        bits.append(f"signal_prior={ev['signal_prior']} (ordering-only)")
    if row.get("note"):
        bits.append(f"note={row['note']!r}")
    return "  ".join(bits)


def main(argv: List[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    cmd, rest = argv[0], argv[1:]

    if cmd == "list":
        q = ratify.review_queue()
        if not q:
            print("review queue empty — nothing awaiting human ratification.")
            return 0
        print(f"{len(q)} item(s) awaiting ratification (ordered by signal_prior):")
        for r in q:
            print("  " + _fmt(r))
        return 0

    if cmd == "history":
        rows = [r for r in revisions.load() if r.get("status") == "applied"]
        print(f"{len(rows)} applied change(s):")
        for r in rows:
            print("  " + _fmt(r))
        return 0

    if cmd == "show":
        if not rest:
            print("usage: show <id>"); return 2
        row = revisions.get(rest[0])
        if row is None:
            print(f"unknown id {rest[0]}"); return 1
        print(json.dumps(row, indent=2, ensure_ascii=False))
        return 0

    if cmd == "approve":
        if not rest:
            print("usage: approve <id>"); return 2
        ok, msg = ratify.approve(rest[0])
        print(("APPLIED: " if ok else "NOT APPLIED: ") + msg)
        return 0 if ok else 1

    if cmd == "reject":
        if not rest:
            print("usage: reject <id> [reason]"); return 2
        reason = " ".join(rest[1:]) if len(rest) > 1 else ""
        row = ratify.reject(rest[0], reason=reason)
        print("rejected." if row is not None else f"unknown id {rest[0]}")
        return 0 if row is not None else 1

    if cmd == "restore":
        if not rest:
            print("usage: restore <id>"); return 2
        ok, msg = ratify.restore(rest[0])
        print(("RESTORED: " if ok else "FAILED: ") + msg)
        return 0 if ok else 1

    print(f"unknown command {cmd!r}")
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
