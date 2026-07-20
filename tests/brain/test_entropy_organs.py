# Run 11 §6.1b — the general instruments: C8 distribution-entropy monitor and
# C9 global entropy budget (with E1's measured-compression readout).

from brain.cognition import entropy_monitor as em
from brain.cognition import entropy_budget as eb


def test_entropy_is_undefined_until_warm_then_reads_the_distribution():
    ch = "test_warmup"
    for i in range(em._MIN_SAMPLES - 1):
        em.observe(ch, f"sym{i}")
    assert em.entropy(ch) is None, "no verdict on a cold distribution"
    em.observe(ch, "symX")
    e = em.entropy(ch)
    assert e is not None and e > 0.9, f"fully diverse window must read high, got {e}"


def test_monoculture_reads_as_collapse():
    ch = "test_monoculture"
    for _ in range(em._MIN_SAMPLES + 10):
        em.observe(ch, "the_same_goal_every_pull")
    assert em.entropy(ch) == 0.0
    assert ch in em.collapsed_channels()


def test_collapse_routes_felt_pressure_once_per_cooldown():
    ch = "test_pressure"
    for _ in range(em._MIN_SAMPLES + 5):
        em.observe(ch, "pinned")
    em._last_pressure_ts.pop(ch, None)
    ctx: dict = {}
    fired = em.route_collapse_pressure(ctx)
    assert ch in fired, "a collapsed channel must push into the felt layer"
    # Within the cooldown the pressure does not re-fire (a push, not a siren).
    assert ch not in em.route_collapse_pressure(ctx)


def test_snapshot_history_persists_for_the_gate():
    ch = "test_history"
    for i in range(em._MIN_SAMPLES + em._SNAPSHOT_EVERY + 5):
        em.observe(ch, f"s{i % 3}")
    snap = em.snapshot()
    assert snap["current"].get(ch) is not None
    assert snap["history"].get(ch), "the gate reads the persisted entropy series"


def test_budget_ledger_counts_grew_compressed_forgotten():
    eb.note("grew", "long_memory", 3)
    eb.note("forgotten", "long_memory", 2)
    eb.note("compressed", "memory_store", 1)
    eb.flush()
    snap = eb.snapshot()
    q = next(v for k, v in snap.items() if k.startswith("q"))
    assert q["grew"]["long_memory"] >= 3
    assert q["forgotten"]["long_memory"] >= 2
    assert eb.compression_events() >= 1, "E1's gate readout: compression is measured"
