"""Phase 5.4 — round-trip migration discipline + envelope-version subsumption.

The schema spine (brain/utils/schema_migration.py) carries a SINGLE global
state_schema_version. This file enforces the two things the cleanup plan's 5.4
requires of every persisted-state envelope:

  1. SUBSUMPTION — every persisted envelope is versioned by that ONE global
     version. In particular the knowledge-graph store, which used to stamp its own
     isolated `_SCHEMA_VERSION`, now follows the global one
     (test_kg_envelope_uses_global_version). mind_archive / life_capsule already
     embed the global state_schema_version; their own *container*-format versions
     (MIND_/CAPSULE_SCHEMA_VERSION) are a separate, legitimate concern.

  2. ROUND-TRIP DISCIPLINE — every registered N→N+1 migration must have a
     round-trip test (old fixture → migrate → asserted new shape, + idempotency).
     `_ROUNDTRIP_TESTED` lists the FROM-versions covered below; the discipline lock
     asserts the registered migrations are a subset of it, so adding a migration
     to sm._MIGRATIONS without a round-trip test fails CI. A worked TEMPLATE shows
     the exact shape the next real migration copies.
"""
from __future__ import annotations

import copy
from typing import Any, Callable, Dict, Set

from brain.utils import schema_migration as sm
from brain.cognition import knowledge_graph_core as kgc


# FROM-versions that have a round-trip test in THIS file. When you register a real
# migration in sm._MIGRATIONS (and bump CURRENT_SCHEMA_VERSION), add its FROM
# version here and write the matching old→migrate→assert test below.
_ROUNDTRIP_TESTED: Set[int] = set()


def _roundtrip(old: Dict[str, Any], migrate: Callable[[Dict[str, Any]], None],
               expected: Dict[str, Any]) -> None:
    """Reusable harness: a migration must turn `old` into `expected` AND be
    idempotent (re-running it on its own output must not change the shape — boot
    can re-run migrations, and a partial-then-resumed migration must converge)."""
    got = copy.deepcopy(old)
    migrate(got)
    assert got == expected, f"migration produced {got!r}, expected {expected!r}"
    migrate(got)
    assert got == expected, "migration is not idempotent (re-running changed the shape)"


# ── 1. Subsumption ───────────────────────────────────────────────────────────

def test_kg_envelope_uses_global_version():
    # The knowledge-graph store stamps the GLOBAL schema version into its graph
    # meta — it no longer versions itself in isolation (Phase 5.4 subsumption).
    assert kgc._SCHEMA_VERSION == sm.CURRENT_SCHEMA_VERSION
    g: Dict[str, Any] = {}
    kgc._normalize_graph_inplace(g)
    assert g["meta"]["version"] == sm.CURRENT_SCHEMA_VERSION


# ── 2. Round-trip discipline lock ────────────────────────────────────────────

def test_every_registered_migration_has_a_roundtrip_test():
    untested = set(sm._MIGRATIONS) - _ROUNDTRIP_TESTED
    assert not untested, (
        "these schema migrations have no round-trip test — add each FROM-version "
        "to _ROUNDTRIP_TESTED in this file and write an old→migrate→assert test "
        f"(see test_template_roundtrip_pattern): {sorted(untested)}"
    )


def test_baseline_has_no_migrations_yet():
    # Sanity: at the shipped baseline the registry is empty and the lock is
    # vacuously satisfied. This documents the starting point so the lock above
    # is meaningful the moment the first migration lands.
    assert sm.CURRENT_SCHEMA_VERSION == sm._BASELINE_VERSION
    assert sm._MIGRATIONS == {}


def test_template_roundtrip_pattern():
    # TEMPLATE (not a registered migration): the copy-paste shape every real
    # envelope migration follows — a frozen OLD fixture, the migrate fn, the
    # asserted NEW shape, and the idempotency the harness enforces. When a real
    # graph/goals/memory format change lands, write its migration like this and
    # register it in sm._MIGRATIONS + _ROUNDTRIP_TESTED.
    def _example_migrate(g: Dict[str, Any]) -> None:
        # e.g. a v1→v2 graph change: bare-string relations become objects with a
        # default weight; idempotent because already-objects are passed through.
        if g.get("meta", {}).get("version") == 1:
            g["relations"] = [
                r if isinstance(r, dict) else {"rel": r, "weight": 1.0}
                for r in g.get("relations", [])
            ]
            g.setdefault("meta", {})["version"] = 2

    old = {"meta": {"version": 1}, "relations": ["knows"]}
    expected = {"meta": {"version": 2}, "relations": [{"rel": "knows", "weight": 1.0}]}
    _roundtrip(old, _example_migrate, expected)
