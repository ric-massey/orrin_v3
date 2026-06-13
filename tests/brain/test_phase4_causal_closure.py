# Phase 4: confirmed beliefs → causal-graph edges that planning/diagnosis READ.
#
# Closes the loop: trial-and-error (experiments) and repairs (problem_refocus)
# write causal edges; abductive diagnosis and goal planning read them back.
# Pearl levels of evidence; Newell & Simon (1972) means-ends analysis.
import cognition.experimentation as exp
import cognition.planning.pursue_goal as pg
import cognition.planning.diagnosis as diag
import cognition.planning.problem_refocus as pr
import symbolic.causal_graph as cg


# ── WRITE: confirmed experiments → causal edges ─────────────────────────────────

def test_extract_cause_effect_from_hypothesis():
    assert exp._extract_cause_effect("when I reflect too long, action_debt rises") == (
        "I reflect too long", "action_debt rises")
    assert exp._extract_cause_effect("deep research leads to better answers") == (
        "deep research", "better answers")
    assert exp._extract_cause_effect("reflection is generally good") is None


def test_confirmed_experiment_writes_edge(monkeypatch):
    seen = {}
    monkeypatch.setattr(cg, "update_edge",
                        lambda cause, effect, **k: seen.update(cause=cause, effect=effect, **k) or {})
    out = exp._write_causal_edge_from_experiment(
        {"hypothesis": "when uncertainty is high, I stall"}, "confirmed")
    assert out is not None
    assert seen["cause"] == "uncertainty is high" and seen["effect"] == "I stall"
    assert seen["confirmed"] is True and seen["source"] == "experiment"


def test_inconclusive_experiment_writes_nothing(monkeypatch):
    monkeypatch.setattr(cg, "update_edge",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not write")))
    assert exp._write_causal_edge_from_experiment(
        {"hypothesis": "when X, Y"}, "inconclusive") is None


# ── WRITE: successful repairs → causal edges ────────────────────────────────────

def test_repair_records_cause_of_failure(monkeypatch):
    seen = {}
    monkeypatch.setattr(cg, "update_edge",
                        lambda cause, effect, **k: seen.update(cause=cause, effect=effect, **k) or {})
    ap = {
        "capability": "llm",
        "hypotheses": [{"key": "transient_network",
                        "cause": "a transient network problem", "fixable": True}],
        "hyp_idx": 0,
    }
    pr._record_repair_belief(ap, "llm", workaround=False)
    assert seen["effect"] == diag.failure_node("llm") == "llm failure"
    assert "transient network" in seen["cause"]
    assert seen["intervention"] is True          # a successful fix is do(x) evidence


# ── READ: abductive diagnosis surfaces learned causes ───────────────────────────

def test_abduce_surfaces_learned_cause_from_graph(monkeypatch):
    monkeypatch.setattr(diag, "_llm_circuit_open", lambda ctx: False)
    monkeypatch.setattr(diag, "_llm_disabled_in_config", lambda ctx: False)
    monkeypatch.setattr(cg, "get_causes",
                        lambda effect, min_score=0.3: [{"cause": "rate limit exceeded"}]
                        if effect == "llm failure" else [])
    hyps = diag.abduce("llm", {})
    learned = [h for h in hyps if h["source"] == "causal_graph"]
    assert any("rate limit" in h["cause"] for h in learned)


# ── READ: goal planning uses learned causes (means-ends) ────────────────────────

def test_causal_first_step_leads_with_strong_cause(monkeypatch):
    monkeypatch.setattr(cg, "get_causes",
                        lambda title, min_score=0.3: [
                            {"cause": "doing focused background research",
                             "causal_score": 0.82, "effect": title}])
    step = pg._causal_first_step("Understand black hole thermodynamics")
    assert step and "focused background research" in step


def test_causal_first_step_none_when_nothing_learned(monkeypatch):
    monkeypatch.setattr(cg, "get_causes", lambda *a, **k: [])
    assert pg._causal_first_step("Understand black hole thermodynamics") is None
    # too-short titles are ignored outright
    assert pg._causal_first_step("hi") is None
