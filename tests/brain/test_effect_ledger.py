# P0/P8 contract: the external-effect ledger is the denominator the reward
# function was missing. These lock in the anti-gaming invariants
# (ORRIN_PRODUCTION_REWARD_PLAN §3 P0 + P8): a repeat earns nothing, boilerplate
# earns nothing, and only a novel+structural effect gates a production goal.
import pytest

from brain.agency import effect_ledger as el

_LONG = ("I worked out that emergence is the way large-scale order and patterns "
         "arise from many small local interactions that individually know nothing "
         "of the whole — and that this matters for how a mind can be more than its "
         "neurons.")


@pytest.fixture(autouse=True)
def _isolate(tmp_path):
    el.EFFECT_LEDGER_FILE = tmp_path / "effect_ledger.jsonl"
    el.reset_for_tests()
    yield
    el.reset_for_tests()


def test_novel_effect_is_credited():
    row = el.record_effect("note_novel", _LONG, goal_id="g1")
    assert row is not None
    assert row.novelty > 0.0
    assert row.significance > 0.0
    assert not row.dedupe


def test_exact_duplicate_earns_nothing():
    assert el.record_effect("note_novel", _LONG, goal_id="g1") is not None
    # byte-identical repeat — the 100-identical-notes case — collapses to no credit.
    assert el.record_effect("note_novel", _LONG, goal_id="g1") is None


def test_boilerplate_and_short_earn_nothing():
    assert el.record_effect("note_novel", "i feel a bit tired today", goal_id="g2") is None
    assert el.record_effect("note_novel", "TODO: placeholder note", goal_id="g2") is None
    assert not el.has_qualifying_effect("g2")


def test_artifact_gate_tracks_goal():
    assert not el.has_qualifying_effect("g3")
    el.record_effect("note_novel", _LONG, goal_id="g3")
    assert el.has_qualifying_effect("g3")


def test_unknown_kind_is_ignored():
    assert el.record_effect("not_a_real_kind", _LONG, goal_id="g4") is None
    assert not el.has_qualifying_effect("g4")


def test_unparseable_code_has_zero_significance():
    # novel but structurally junk → no production credit (P8 structural gate).
    row = el.record_effect("code_committed", "def broken(:\n  return " + ("x " * 60), goal_id="g5")
    # either rejected outright or recorded with zero significance — never a free win
    assert row is None or row.significance == 0.0


def test_tracked_work_requires_progress_metadata():
    assert el.record_effect("tracked_work", _LONG, goal_id="book") is None
    # A genuinely distinct section: under F2b (RUN7_FIX_PLAN) near-duplicate
    # content pays proportionally to its novelty, so only fresh section prose
    # carries the full section-scaled significance.
    row = el.record_effect(
        "tracked_work",
        "The thesis chapter argues something else entirely: staged verification "
        "beats stated confidence, cumulative manuscripts need durable paths, and "
        "progress only counts when the sections exist on disk as real prose.",
        goal_id="book",
        metadata={"path": "/tmp/book.md", "section": "Thesis", "completed_sections": 1},
    )
    assert row is not None
    assert row.significance >= 0.5
    assert el.has_qualifying_effect("book")


_TOOL_CODE = (
    "def my_tool(args=None):\n"
    "    numbers = [int(token) for token in str(args).split() if token.isdigit()]\n"
    "    total = sum(numbers)\n"
    "    average = total / len(numbers) if numbers else 0\n"
    "    return {'count': len(numbers), 'total': total, 'average': average}\n"
)


def test_named_artifact_reuse_closes_the_loop():
    # Authoring a tool indexes it by name; invoking it by name is tier-3 re-use.
    row = el.record_effect("tool_written", _TOOL_CODE,
                           goal_id="gtool", metadata={"name": "my_tool"})
    assert row is not None
    base_sig = el.significance_for_goal("gtool")

    # first use → credited, and the owning goal's significance rises (re-use is the
    # ungameable signal, so it lifts mean_significance).
    assert el.note_artifact_use("my_tool") == 1
    assert el.significance_for_goal("gtool") > base_sig
    # a name Orrin never authored is not re-use → no credit.
    assert el.note_artifact_use("builtin_search") is None

    # the credit is queued for finalize to pay, with a diminishing count.
    assert el.note_artifact_use("my_tool") == 2
    pending = el.drain_pending_reuse()
    assert [p["count"] for p in pending] == [1, 2]
    assert all(p["name"] == "my_tool" and p["goal_id"] == "gtool" for p in pending)
    # draining clears the queue.
    assert el.drain_pending_reuse() == []


def test_reuse_index_survives_rehydration():
    code = _TOOL_CODE.replace("my_tool", "reload_tool")
    el.record_effect("tool_written", code, goal_id="gh", metadata={"name": "reload_tool"})
    el.note_artifact_use("reload_tool")
    # simulate a fresh process: drop caches, re-read the jsonl.
    el._hydrated = False
    el._artifact_names.clear()
    el._hash_goal.clear()
    el._reuse_counts.clear()
    el._pending_reuse.clear()
    el._goal_significance.clear()
    el._goal_effects.clear()
    el._seen_hashes.clear()
    # next use must still resolve the name and continue the count from disk.
    assert el.note_artifact_use("reload_tool") == 2


def test_tracked_work_goal_waits_for_required_sections():
    goal = {
        "tracked_work": True,
        "definition_of_done": [{"criterion": "three sections", "kind": "sections", "target": 3}],
    }
    texts = [
        _LONG + " The first section establishes a concrete thesis about local interactions.",
        _LONG + " The second section distinguishes coordination from centralized control.",
        _LONG + " The third section integrates the implications for cognition and agency.",
    ]
    for count, text in enumerate(texts, 1):
        row = el.record_effect(
            "tracked_work",
            text,
            goal_id="book-3",
            metadata={"path": "/tmp/book.md", "section": f"S{count}", "completed_sections": count},
        )
        assert row is not None
        assert el.has_qualifying_effect("book-3", goal) is (count == 3)


# ── Fix 5 (RUN6_FIX_PLAN_2026-07-08 §3): causal-edge rows are bookkeeping ─────────

_EDGE = ("[causal edge established] cause: sustained reflection without action; "
         "effect: rising action debt and goal avoidance pressure; strength=0.82 "
         "causal_score=0.77; evidence: 9 confirmations, 3 interventions, "
         "1 counterfactuals; layer L2; domain self")


def test_causal_edge_is_bookkeeping_not_production():
    """A 'causal edge established' row is self-model bookkeeping (76 % of Run 5's
    credited effects) — recorded under its own ledger class, never credited."""
    out = el.record_effect(
        "symbolic_artifact", _EDGE, goal_id="g-edge",
        metadata={"kind": "causal_edge", "edge_id": "e1"},
    )
    assert out is None                              # no production credit
    assert not el.has_qualifying_effect("g-edge")   # no artifact evidence
    assert el.significance_for_goal("g-edge") == 0.0
    assert el.drain_pending_production() == []      # no queued reward
    rows = el.drain_recent_rows()
    assert len(rows) == 1
    assert rows[0]["kind"] == "bookkeeping"         # reported separately
    assert rows[0]["significance"] == 0.0


def test_other_symbolic_sub_kinds_still_credit():
    row = el.record_effect(
        "symbolic_artifact", _LONG, goal_id="g-rule", metadata={"kind": "rule"},
    )
    assert row is not None and row.significance > 0.0
    assert el.has_qualifying_effect("g-rule")


def test_bookkeeping_rows_never_rehydrate_as_goal_evidence():
    el.record_effect(
        "symbolic_artifact", _EDGE, goal_id="g-edge2",
        metadata={"kind": "causal_edge"},
    )
    # simulate a fresh process: hydrate goal attribution from the jsonl.
    el._hydrated = False
    el._goal_effects.clear()
    el._seen_hashes.clear()
    assert not el.has_qualifying_effect("g-edge2")
