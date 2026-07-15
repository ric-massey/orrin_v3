# RUN8_FIX_PLAN_2026-07-14 — an absolute release for the commitment monopoly.
#
# Run 7 ended in a 90.9 % committed-goal monopoly (stale_cycles 10,291) even
# though the reward pump was gone. Every anti-monopoly lever was *relative* and
# saturated at −30, so with no rival in scoring range a stale holder just sat
# there. F1 adds the missing *absolute* release: a driver that holds the slot
# _STALE_REFRACTORY_CYCLES with ZERO credited effect (credit zeroes stale_cycles,
# so this can only trip on genuine non-production) arms its own F4 block and
# yields — no rival required. F2 admits all four enduring aspirations to the
# directional pool so that release hands the slot to another *direction*, not to
# an ordinary chore.
#
# The two §4.1 scenarios are the behavioral proof (F1 × F2 together, a driver
# slot rotating among four directional aspirations while ordinary goals compete);
# the §4.2 guards localize any failure the simulation surfaces.
import brain.cognition.planning.commitment_value as cv
import pytest

# Mirror goal_io's tier/priority ordering so the harness scores goals exactly as
# the run does: long_term → weight 1, an ordinary "growth" goal → weight 2, HIGH
# priority → rank 4. The directional CAP (not the tier weight) is what keeps a
# directional in the driver slot ahead of a higher-tier ordinary goal.
_TIER_TURNS = {"survival": 4, "existential": 3, "core": 3, "identity": 2,
               "growth": 2, "exploratory": 1, "minor": 1, "trivial": 1}


def _tier_w(t):
    return _TIER_TURNS.get(str(t or "").lower(), 1)


def _prio(p):
    return {"LOW": 1, "NORMAL": 3, "HIGH": 4, "CRITICAL": 5}.get(str(p or "").upper(), 3)


@pytest.fixture(autouse=True)
def _isolate(tmp_path):
    cv._SIGNALS_FILE = tmp_path / "commitment_signals.json"
    yield


def _mk(gid, tier, priority, directional):
    g = {"id": gid, "tier": tier, "priority": priority}
    if directional:
        # F2 keys on `_aspiration` — set on exactly the enduring directions.
        g["_aspiration"] = True
    return g


# ── §4.1 the life-simulation harness ─────────────────────────────────────────────

def _simulate_life(goals, *, pulls, credit_earner=None, credit_every=0,
                   credit_gain=0.5):
    """Drive order_committable/note_driver_selected for `pulls` cycles over a
    fixed goal population; return the occupancy trace + per-goal signal rows.

    goals: list of (gid, tier, priority, directional). Build 4 directional
        long_term aspirations + ≥2 ordinary goals so BOTH pools are populated.
    credit_earner/credit_every: optionally feed note_goal_credit to ONE goal on
        a fixed cadence, so 'persistence under progress' is exercised in-world.
    """
    found = [_mk(*g) for g in goals]
    drivers = []
    max_stale = {g[0]: 0.0 for g in goals}
    for pull in range(pulls):
        cv.order_committable(found, tier_weight_fn=_tier_w,
                             priority_rank_fn=_prio, limit=4)
        drv = str(cv._load_signals().get("driver") or "")
        drivers.append(drv)
        rows = cv.signals_snapshot()
        for gid, row in rows.items():
            if isinstance(row, dict):
                max_stale[gid] = max(max_stale.get(gid, 0.0),
                                     float(row.get("stale_cycles", 0.0)))
        if credit_earner and credit_every and (pull + 1) % credit_every == 0:
            cv.note_goal_credit(credit_earner, credit_gain,
                                content_hash=f"h{pull}")
    n = max(1, len(drivers))
    occupancy = {}
    for d in drivers:
        occupancy[d] = occupancy.get(d, 0.0) + 1.0 / n
    return {
        "occupancy": occupancy,
        "drivers": drivers,
        "refractory": cv.refractory_events(),
        "rows": cv.signals_snapshot(),
        "max_stale": max_stale,
    }


# Equal-strength aspirations (test 2): with no score gap the RELATIVE penalty
# already rotates them, so this population exercises F2's rotation + the producer
# guard, not F1's ceiling.
_FOUR = [
    ("self_understanding", "long_term", "HIGH", True),
    ("world_knowledge", "long_term", "HIGH", True),
    ("genuine_contact", "long_term", "HIGH", True),
    ("output_producing", "long_term", "HIGH", True),
]
# Dominant-incumbent population (headline): self_understanding out-scores the
# other directions by 40 (CRITICAL rank 5 vs LOW rank 1 → 10·(5−1)), more than
# the max relative penalty (stale 15 + avoid 15 = 30). This reproduces Run 7's
# actual condition — a leader NO rival is in range to displace — so the ONLY
# thing that can break the hold is F1's absolute release, not relative rotation.
_DOMINANT = [
    ("self_understanding", "long_term", "CRITICAL", True),
    ("world_knowledge", "long_term", "LOW", True),
    ("genuine_contact", "long_term", "LOW", True),
    ("output_producing", "long_term", "LOW", True),
]
_ORDINARY = [
    ("research_chore", "growth", "NORMAL", False),
    ("tidy_notes", "growth", "NORMAL", False),
]
_DIRECTIONAL_IDS = {g[0] for g in _FOUR}


def test_monopoly_breaks_and_rotates():
    """F1 × F2, the headline. A dominant incumbent (self_understanding) that no
    rival can displace relatively — the Run 7 condition — + three lower
    directions + two ordinary goals, NO goal earns credit. Only F1's absolute
    release can break the hold, and F2 must hand the slot to another *direction*."""
    sim = _simulate_life(_DOMINANT + _ORDINARY, pulls=1600)

    # G1 — no single goal exceeds ~60 % of the driver slot (Run 7 was 90.9 %).
    top_gid, top_share = max(sim["occupancy"].items(), key=lambda kv: kv[1])
    assert top_share < 0.60, f"{top_gid} held {top_share:.1%} of the slot"

    # F1 fired on the dominant incumbent: no relative penalty could have moved it,
    # so a non-empty refractory naming self_understanding proves the absolute
    # release is what broke the hold.
    assert sim["refractory"], "F1 never armed — the absolute release did nothing"
    released = {str(e.get("goal")) for e in sim["refractory"]}
    assert "self_understanding" in released

    # F2 handoff is to a *direction*: every driver in the trace is one of the four
    # aspirations, never an ordinary goal. Without F2 the released incumbent's
    # block would fall through to an ordinary goal in the driver slot.
    assert set(sim["drivers"]) <= _DIRECTIONAL_IDS, (
        f"an ordinary goal reached the driver slot: "
        f"{set(sim['drivers']) - _DIRECTIONAL_IDS}")

    # Bounded staleness: hundreds, not thousands (Run 7 = 10,291).
    ceiling = cv._STALE_REFRACTORY_CYCLES + cv._RECOMMIT_BLOCK_PULLS
    assert max(sim["max_stale"].values()) < ceiling

    # Re-entry: the released incumbent drives AGAIN later (block decayed, not
    # permanent suppression).
    release_pull = sim["drivers"].index("self_understanding")
    assert "self_understanding" in sim["drivers"][release_pull + 1:], (
        "released aspiration never re-entered the driver slot")


def test_producer_holds_without_thrash():
    """G4 anti-thrash, in the same world. One aspiration earns credit on a
    cadence; F1 must never force-release it, and it must legitimately hold MORE
    of the slot than any non-producer — while the non-producers still rotate."""
    producer = "self_understanding"
    sim = _simulate_life(_FOUR + _ORDINARY, pulls=1200,
                         credit_earner=producer, credit_every=150, credit_gain=0.5)

    # No release ever fires on the credit-earner (credit zeroes stale_cycles, so
    # a producer can never reach the ceiling).
    released = {str(e.get("goal")) for e in sim["refractory"]}
    assert producer not in released
    assert sim["max_stale"][producer] < cv._STALE_REFRACTORY_CYCLES

    # It legitimately holds MORE of the slot than any non-producer — contribution
    # buys the hold; it is not starved by the rotation machinery.
    prod_share = sim["occupancy"].get(producer, 0.0)
    for gid, share in sim["occupancy"].items():
        if gid != producer:
            assert prod_share > share, f"{gid} ({share:.1%}) held ≥ producer"

    # ...but the protection is not a total lockout: the producer briefly goes
    # stale between credits and yields, so the slot still moves to another
    # direction — rotation is not frozen (breaking a monopoly by idling would be
    # a failure, but so would re-freezing on the producer forever).
    assert prod_share < 1.0
    non_producers = {d for d in sim["drivers"]
                     if d in _DIRECTIONAL_IDS and d != producer}
    assert len(non_producers) >= 1


# ── §4.2 focused guards (one condition each, for fast triage) ─────────────────────

def test_arms_on_absolute_staleness():
    """Guard 3 — held _STALE_REFRACTORY_CYCLES with no credit → own block armed,
    one refractory entry logged."""
    for _ in range(cv._STALE_REFRACTORY_CYCLES):
        cv.note_driver_selected("g", ["g"])
    row = cv.signals_snapshot()["g"]
    assert row["recommit_block_pulls"] == cv._RECOMMIT_BLOCK_PULLS
    ev = cv.refractory_events()
    assert len(ev) == 1 and ev[0]["goal"] == "g"


def test_yields_the_slot_even_when_it_outscores():
    """Guard 4 — a blocked directional is ineligible even when it out-scores the
    rival; the next-best directional drives."""
    for _ in range(cv._STALE_REFRACTORY_CYCLES):
        cv.note_driver_selected("g", ["g"])
    assert cv.signals_snapshot()["g"]["recommit_block_pulls"] > 0
    # g out-scores g2 (higher learned value) but is blocked.
    cv.note_goal_credit("g", 0.9, content_hash="x")
    found = [
        {"id": "g", "tier": "long_term", "_aspiration": True, "priority": "HIGH"},
        {"id": "g2", "tier": "long_term", "_aspiration": True, "priority": "HIGH"},
    ]
    out = cv.order_committable(found, tier_weight_fn=_tier_w,
                              priority_rank_fn=_prio, limit=3)
    ids = [g["id"] for g in out]
    assert "g" not in ids
    assert "g2" in ids


def test_ablation_no_block_when_disabled(monkeypatch):
    """Guard 5 — with the master switch off, Run-7 behaviour is reproducible: the
    holder rides staleness with no absolute release, isolating F1 as the cause."""
    monkeypatch.setattr(cv, "_STALE_REFRACTORY_ENABLED", False)
    for _ in range(cv._STALE_REFRACTORY_CYCLES + 50):
        cv.note_driver_selected("g", ["g"])
    row = cv.signals_snapshot()["g"]
    assert float(row.get("recommit_block_pulls", 0.0) or 0.0) == 0.0
    assert cv.refractory_events() == []
    assert row["stale_cycles"] >= cv._STALE_REFRACTORY_CYCLES
