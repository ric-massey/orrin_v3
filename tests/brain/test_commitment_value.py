# Run 6 Fixes 2–4 (RUN6_FIX_PLAN_2026-07-08 §3): outcomes must flow back into
# commitment. These pin the commitment score's three learned terms (value /
# staleness / avoidance), the driver-slot rotation in goal_io, the recovery
# decay for released goals, and the effect-ledger credit hook.
import pytest

import brain.goal_io as gio
import brain.cognition.planning.commitment_value as cv
from brain.agency import effect_ledger as el

_LONG = ("A real finding about how the driver slot rotates: commitment now reads "
         "learned value, staleness, and avoidance, so a monopolizing goal devalues "
         "itself the longer it holds the slot without paying off in credited work.")


@pytest.fixture(autouse=True)
def _isolate(tmp_path):
    cv._SIGNALS_FILE = tmp_path / "commitment_signals.json"
    el.EFFECT_LEDGER_FILE = tmp_path / "effect_ledger.jsonl"
    el.reset_for_tests()
    yield
    el.reset_for_tests()


def _tied_directionals():
    # Two directional aspirations, both long_term + HIGH — the exact Run-5 tie
    # the old stable-sort broke by insertion order, forever.
    return [
        {"id": "a", "name": "drive A", "title": "drive A", "tier": "long_term",
         "status": "pending", "directional": True, "priority": "HIGH"},
        {"id": "b", "name": "drive B", "title": "drive B", "tier": "long_term",
         "status": "pending", "directional": True, "priority": "HIGH"},
    ]


def _driver(monkeypatch, tree):
    monkeypatch.setattr(gio, "_load_v1_tree", lambda: tree)
    out = gio._committable_from_v1_tree(limit=3)
    directionals = [g for g in out if g.get("directional")]
    assert len(directionals) == 1
    return directionals[0]["id"]


# ── commit_score: legacy ordering holds with no signals ──────────────────────────

def test_tier_floor_and_priority_survive_cold_start():
    survival = {"id": "s", "tier": "survival", "priority": "NORMAL"}
    core_high = {"id": "c", "tier": "core", "priority": "HIGH"}
    s = cv.commit_score(survival, tier_weight=4, priority_rank=3)
    c = cv.commit_score(core_high, tier_weight=3, priority_rank=4)
    assert s > c   # tier floor: survival outranks even a HIGH lower tier


def test_adjustment_is_bounded_under_one_tier_step():
    goal = {"id": "x", "tier": "core", "priority": "HIGH"}
    for _ in range(500):
        cv.note_avoidance("x")
    cv.note_driver_selected("x", ["x"])
    worst = cv.commit_score(goal, tier_weight=3, priority_rank=4)
    best_possible_lower_tier = cv.commit_score(
        {"id": "y", "tier": "growth", "priority": "CRITICAL"}, tier_weight=2, priority_rank=5)
    assert worst > best_possible_lower_tier - 0.0  # penalties never cross a tier

# ── Fix 3: avoidance releases the commitment ─────────────────────────────────────

def test_avoidance_rotates_the_directional_driver(monkeypatch):
    tree = _tied_directionals()
    assert _driver(monkeypatch, tree) == "a"     # stable tie → A holds
    for _ in range(10):                          # a real streak, not a lone blip
        cv.note_avoidance("a")
    assert _driver(monkeypatch, tree) == "b"     # avoided goal yields the slot


def test_single_avoidance_detection_does_not_flip(monkeypatch):
    tree = _tied_directionals()
    assert _driver(monkeypatch, tree) == "a"
    cv.note_avoidance("a")                       # within the grace band
    assert _driver(monkeypatch, tree) == "a"


# ── Fix 2: staleness rotates; released goals recover ─────────────────────────────

def test_stale_holder_yields_and_recovers(monkeypatch):
    tree = _tied_directionals()
    # Grace window: the holder is stable — no per-pull thrash between tied goals.
    for _ in range(30):
        assert _driver(monkeypatch, tree) == "a"
    # Past grace + incumbency, staleness pressure hands B the slot; B then holds
    # a real dwell (hysteresis), A's penalties decay while released, and the
    # recovered A eventually rotates back in. Exactly the S10 anti-monopoly shape.
    holders = [_driver(monkeypatch, tree) for _ in range(80)]
    assert "b" in holders
    first_b = holders.index("b")
    assert set(holders[first_b:first_b + 10]) == {"b"}   # not a one-pull blip
    assert "a" in holders[first_b:]                       # released goal recovered


def test_credit_resets_staleness_and_keeps_the_slot(monkeypatch):
    tree = _tied_directionals()
    for _ in range(200):
        _driver(monkeypatch, tree)
        # pursuit that pays off: a credited effect lands every pull
        cv.note_goal_credit("a", 0.5)
    assert _driver(monkeypatch, tree) == "a"     # never went stale, never yields
    assert float(cv.signals_snapshot()["a"]["value_ema"]) > 0.5


# ── Fix 4: credited value lifts commitment rank ──────────────────────────────────

def test_learned_value_breaks_the_tie(monkeypatch):
    tree = _tied_directionals()
    for _ in range(8):
        cv.note_goal_credit("b", 0.6)            # B's pursuit demonstrably pays
    assert _driver(monkeypatch, tree) == "b"


def test_aspiration_credit_value_orders_by_credit(monkeypatch):
    """Fix 4: the credited-contribution signal ranks the well-credited aspiration
    above the starved one, so commitment and credit can converge (Run 5: the
    committed aspiration earned 1 contribution while a barely-committed one
    earned 6 — the two halves never talked)."""
    from datetime import datetime, timezone
    import brain.cognition.intrinsic_objectives as io_
    nodes = [
        {"title": "Make things — produce work that didn't exist before",
         "kind": "aspiration", "_aspiration": True, "contribution_count": 6,
         "last_contribution_ts": datetime.now(timezone.utc).isoformat()},
        {"title": "Understand my own mind and how I work",
         "kind": "aspiration", "_aspiration": True, "contribution_count": 1},
    ]
    monkeypatch.setattr(io_, "load_json", lambda *a, **k: list(nodes))
    v_make = io_.aspiration_credit_value("output_producing")
    v_self = io_.aspiration_credit_value("self_understanding")
    assert v_make is not None and v_self is not None
    assert v_make > v_self


def test_aspiration_credit_value_cold_start_is_none(monkeypatch):
    import brain.cognition.intrinsic_objectives as io_
    monkeypatch.setattr(io_, "load_json", lambda *a, **k: [
        {"title": "Understand my own mind and how I work",
         "kind": "aspiration", "_aspiration": True, "contribution_count": 0},
    ])
    assert io_.aspiration_credit_value("self_understanding") is None


# ── effect-ledger hook: a credited effect feeds the commitment signals ───────────

def test_credited_effect_updates_commitment_signals():
    cv.note_driver_selected("g1", ["g1"])
    assert float(cv.signals_snapshot()["g1"]["stale_cycles"]) == 1.0
    row = el.record_effect("note_novel", _LONG, goal_id="g1")
    assert row is not None
    sig = cv.signals_snapshot()["g1"]
    assert float(sig["stale_cycles"]) == 0.0     # credit clears staleness
    assert float(sig["value_ema"]) > 0.5         # and lifts learned value
