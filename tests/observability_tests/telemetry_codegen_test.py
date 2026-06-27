# tests/observability_tests/telemetry_codegen_test.py
#
# The telemetry codegen + boundary-validation contract (Phase 5.2).
#
# The FE↔BE telemetry boundary crosses a process AND a language boundary, so the
# wire shape is pinned two ways:
#   1. STATIC  — frontend/src/lib/telemetry.gen.ts (zod schemas + TS types) is
#      GENERATED from backend/server/schema.py. This test re-renders it in memory
#      and fails if the committed file is stale, so the FE types can no longer be
#      hand-mirrored and silently drift from the backend.
#   2. RUNTIME — validate_frame() (backend producer, in hub.merge) and the zod
#      schema (frontend consumer) both validate frames at the boundary. The tests
#      below lock validate_frame's accept/reject behaviour.
from __future__ import annotations

from pathlib import Path

from backend.server.generate_telemetry_ts import render_ts, _OUT
from backend.server.schema import validate_frame

REPO = Path(__file__).resolve().parents[2]


def test_generated_ts_matches_schema():
    committed = _OUT.read_text(encoding="utf-8")
    rendered = render_ts()
    assert committed == rendered, (
        "frontend/src/lib/telemetry.gen.ts is stale vs backend/server/schema.py. "
        "Regenerate it with `make telemetry-types` (or "
        "`python -m backend.server.generate_telemetry_ts`) and commit the result."
    )


def test_generated_ts_is_marked_generated():
    committed = _OUT.read_text(encoding="utf-8")
    assert "AUTO-GENERATED" in committed
    assert 'import { z } from "zod";' in committed
    assert "TelemetryFrameSchema" in committed


def test_validate_frame_accepts_a_representative_frame():
    frame = {
        "active_node": "plan",
        "narrative": "Planning next step…",
        "cycle": 42,
        "affect": {"valence": 0.6, "arousal": 0.4, "homeostasis": 0.8,
                   "extra": {"motivation": 0.5}},
        "metrics": {"valence": 0.6, "arousal": 0.4},
        "logs": [{"level": "info", "source": "select_function", "message": "picked X"}],
        "memory": [{"op": "write", "store": "working", "key": "k", "summary": "s"}],
        "goals": [{"id": "g1", "title": "Understand X", "status": "in_progress",
                   "tier": "short_term", "priority": 2, "active": True}],
        "fn_recent": [{"fn": "research_topic", "cycle": 41, "lane": "deliberate"}],
        "executive": {"active_fn": "compose_section"},  # free-form block
    }
    assert validate_frame(frame) == []


def test_validate_frame_allows_unknown_keys():
    # A new producer field must NOT hard-fail the contract (extra="allow").
    assert validate_frame({"some_brand_new_block": {"a": 1}}) == []


def test_validate_frame_flags_a_type_error():
    # cycle is Optional[int]; a list can't coerce — a genuine type error the
    # validator must surface loudly.
    errs = validate_frame({"cycle": [1, 2, 3]})
    assert errs, "expected a contract violation for cycle=[1,2,3]"
    assert any("cycle" in e for e in errs)


def test_validate_frame_flags_nested_type_error():
    # affect.valence is a float; a non-numeric string is a real mismatch.
    errs = validate_frame({"affect": {"valence": "definitely-not-a-number"}})
    assert errs
    assert any("valence" in e for e in errs)
