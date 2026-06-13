# Tests for abductive fault diagnosis (cognition/planning/diagnosis.py).
#
# Peirce 1903 abduction; de Kleer & Williams 1987 model-based diagnosis;
# Heckerman et al. 1995 cheapest-promising-repair-first.
import cognition.planning.diagnosis as diag


def test_abduce_ranks_confirmed_fixable_first(monkeypatch):
    # circuit-breaker open → the transient (fixable) cause is confirmed
    monkeypatch.setattr(diag, "_llm_circuit_open", lambda ctx: True)
    monkeypatch.setattr(diag, "_llm_disabled_in_config", lambda ctx: False)
    hyps = diag.abduce("llm", {})
    assert hyps[0]["key"] == "transient_network"
    assert hyps[0]["fixable"] is True
    assert hyps[0]["confirmed"] is True


def test_abduce_unfixable_when_disabled(monkeypatch):
    monkeypatch.setattr(diag, "_llm_circuit_open", lambda ctx: False)
    monkeypatch.setattr(diag, "_llm_disabled_in_config", lambda ctx: True)
    hyps = diag.abduce("llm", {})
    top = hyps[0]
    assert top["key"] == "disabled_in_config"
    assert top["fixable"] is False
    assert top["confirmed"] is True


def test_check_and_apply_by_key(monkeypatch):
    monkeypatch.setattr(diag, "_llm_circuit_open", lambda ctx: True)
    # fixable transient cause: check True, fix takes an action
    assert diag.check_cause("llm", "transient_network", {}) is True
    assert diag.apply_fix("llm", "transient_network", {}) is True
    # unfixable cause: apply_fix is a no-op (no fix registered)
    assert diag.apply_fix("llm", "disabled_in_config", {}) is False


def test_generic_capability_models():
    hyps = diag.abduce("some_tool", {})
    keys = [h["key"] for h in hyps]
    assert "transient" in keys and "persistent" in keys
    # transient is fixable (retry), persistent is not
    assert diag.apply_fix("some_tool", "transient", {}) is True
    assert diag.apply_fix("some_tool", "persistent", {}) is False


def test_unknown_key_is_safe():
    assert diag.check_cause("llm", "nope", {}) is False
    assert diag.apply_fix("llm", "nope", {}) is False
    assert diag.check_cause("unknown_cap", "nope", {}) is False


def test_causal_augmentation_is_guarded(monkeypatch):
    # If the causal graph errors, abduction still returns the fault-model causes.
    import symbolic.causal_graph as cg
    monkeypatch.setattr(cg, "get_causes", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    hyps = diag.abduce("llm", {})
    assert len(hyps) >= 1
    assert all("key" in h and "cause" in h for h in hyps)
