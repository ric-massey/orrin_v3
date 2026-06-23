# tests/observability_tests/llm_cost_telemetry_test.py
#
# Pins the LLM-cost telemetry producer (brain.loop.telemetry._emit_llm_cost):
# the reasoning-cache stats (llm_router.cache_stats) and the symbolic-vs-LLM
# gate stats (llm_gate.gate_stats) are mapped onto the wire `llm_cost` block the
# Cognition page renders. The contract test guards the plumbing; this guards that
# the producer actually reads the two real sources and maps them by name.
from __future__ import annotations


def test_emit_llm_cost_maps_cache_and_gate_stats(monkeypatch):
    import brain.loop.telemetry as tele

    captured: dict = {}

    class _FakeBridge:
        def update(self, **kw):
            captured.update(kw)

    monkeypatch.setattr(tele, "_bridge", lambda: _FakeBridge())
    # Defeat the throttle so the single call always emits.
    monkeypatch.setattr(tele, "_LAST_LLM_COST_PUSH", 0.0)
    monkeypatch.setattr(
        "brain.utils.llm_router.cache_stats",
        lambda: {"entries": 12, "live": 9, "stale": 3, "ttl_s": 600.0},
    )
    monkeypatch.setattr(
        "brain.symbolic.llm_gate.gate_stats",
        lambda: {"llm": 4, "symbolic": 16, "total": 20, "symbolic_ratio": 0.8},
    )

    tele._emit_llm_cost({})

    lc = captured.get("llm_cost")
    assert lc is not None, "producer did not emit an llm_cost block"
    assert lc["cache_entries"] == 12 and lc["cache_live"] == 9 and lc["cache_stale"] == 3
    assert lc["cache_ttl_s"] == 600.0
    assert lc["llm_calls"] == 4 and lc["symbolic_hits"] == 16 and lc["total_calls"] == 20
    assert lc["symbolic_ratio"] == 0.8


def test_emit_llm_cost_is_fail_safe_when_sources_raise(monkeypatch):
    """A broken stats source must not crash the loop and must not emit garbage."""
    import brain.loop.telemetry as tele

    captured: dict = {}

    class _FakeBridge:
        def update(self, **kw):
            captured.update(kw)

    def _boom():
        raise RuntimeError("stats unavailable")

    monkeypatch.setattr(tele, "_bridge", lambda: _FakeBridge())
    monkeypatch.setattr(tele, "_LAST_LLM_COST_PUSH", 0.0)
    monkeypatch.setattr("brain.utils.llm_router.cache_stats", _boom)
    monkeypatch.setattr("brain.symbolic.llm_gate.gate_stats", _boom)

    tele._emit_llm_cost({})  # must not raise

    # Both sources failed → nothing meaningful to send → no llm_cost emitted.
    assert "llm_cost" not in captured
