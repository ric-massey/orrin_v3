"""Phase 3B/3C — the grounding experiment harness (Grounded Cognition plan, Part F).

NOT a unit test of a feature — a falsifiable experiment with a declared baseline and
kill criterion. Hypothesis: Orrin can grow a GROUNDED concept (a predictive
signature over structural features, not an authored string) from real code-execution
outcomes, and it TRANSFERS to commands he has never seen.

The commands actually run in a subprocess; the grader is the REAL exit code (an
observable he did not author). The test families are split so that the held-out
TEST commands share the abstract structural signature of the TRAIN commands but
have different surface — so success is transfer, not memorisation.
"""
import brain.cognition.grounding.world_loop as wl
from brain.cognition.grounding.grounded_concept import GroundedConcept

# Train family A. Successes are well-formed; failures carry a transferable
# structural signature (an unbound name, or a literal divide-by-zero).
_TRAIN = [
    # exit 0
    "print(1)",
    "print(10 + 5)",
    "a = 2\nprint(a)",
    "print(len('abc'))",
    "print(3 * 3)",
    "x = 4\nprint(x * 2)",
    # exit != 0 — unbound name
    "print(foo)",
    "print(bar)",
    "result = baz + 1",
    # exit != 0 — divide by zero
    "print(8 / 0)",
    "print(10 % 0)",
]

# Held-out family A′ — UNSEEN surface, SAME abstract signatures.
_TEST = [
    "print(42)",          # exit 0
    "print(7 + 2)",       # exit 0
    "n = 9\nprint(n)",    # exit 0
    "print(qux)",         # unbound (new name) → fail
    "print(zonk)",        # unbound (new name) → fail
    "print(5 // 0)",      # divide by zero (new op) → fail
]


def test_world_loop_grades_against_the_real_interpreter():
    """The OBSERVE step is graded by the real exit code, not his logs."""
    c = GroundedConcept()
    ok = wl.run_episode("print(5)", c, learn=False)
    bad = wl.run_episode("print(definitely_unbound_xyz)", c, learn=False)
    assert ok["actual_success"] is True
    assert bad["actual_success"] is False
    assert ok["domain"] == "world"
    # the failing command's transferable structural feature is present
    assert "references_unbound_name" in bad["features"]


def test_learning_moves_prediction_toward_reality():
    """Prediction error drives the concept toward the real outcome (grounding)."""
    c = GroundedConcept()
    feats = wl.extract_features("print(missing_name)")
    before = c.predict(feats)
    for _ in range(6):                       # repeated real failures
        wl.run_episode("print(missing_name)", c, learn=True)
    after = c.predict(feats)
    assert before >= 0.45                     # no evidence yet → ~chance
    assert after < before                     # learned this fails
    assert after < 0.25


def test_grounding_experiment_reports_a_verdict_with_baseline():
    """The harness must always produce a well-formed, falsifiable verdict."""
    result = wl.run_experiment(_TRAIN, _TEST)
    assert result["verdict"] in ("transfer", "no_transfer")
    assert 0.0 <= result["accuracy"] <= 1.0
    assert result["base_rate"] == 0.5         # the test split is balanced (true chance)
    assert result["test_episodes"] == len(_TEST)
    # the carrying concept is inspectable as a SIGNATURE, not a stored string
    sig = result["signature"]
    assert isinstance(sig, dict)
    assert "references_unbound_name" in sig
    assert sig["references_unbound_name"]["p_success"] < 0.5   # learned: predicts failure


def test_transfer_appears_on_this_narrow_family():
    """For this narrow structural concept the radical reading should be LIVE:
    the learned signature predicts UNSEEN commands above chance. (A no_transfer
    result would also be informative — see Part F — but the mechanism should
    transfer here, proving the loop grounds and generalises.)"""
    result = wl.run_experiment(_TRAIN, _TEST)
    assert result["verdict"] == "transfer", result
    assert result["transfer"] >= wl.TRANSFER_MARGIN
    # not memorisation: no test command was in the training set
    assert not (set(_TRAIN) & set(_TEST))


def test_second_observable_is_genuinely_distinct():
    """Phase 4A: produces_stdout is a DIFFERENT external observable from exit code.
    A non-printing success exits 0 but produces no stdout — the two diverge."""
    c = GroundedConcept()
    rec = wl.run_episode("x = 5", c, target="exit_success", learn=False)
    assert rec["actual_success"] is True            # assignment succeeds
    rec2 = wl.run_episode("x = 5", c, target="produces_stdout", learn=False)
    assert rec2["actual_success"] is False          # but prints nothing — distinct observable


def test_second_observable_grounds_and_transfers():
    """The loop grounds a concept against produces_stdout and it transfers to unseen
    commands — richer grounding than exit code alone."""
    result = wl.run_experiment(_TRAIN, _TEST, target="produces_stdout")
    assert result["target"] == "produces_stdout"
    assert result["verdict"] == "transfer", result


def test_aggregator_explains_away_ambiguous_feature():
    """Phase 4A aggregator upgrade: a feature that merely co-occurs with a stronger
    failure signature (has_binop appears in both arithmetic successes and failures)
    must be learned as ~neutral, while the real discriminator is strongly negative —
    logistic regression 'explains away' what naive Bayes mis-blamed."""
    result = wl.run_experiment(_TRAIN, _TEST)
    sig = result["signature"]
    assert sig["references_unbound_name"]["weight"] < -1.0     # strong failure signal
    if "has_binop" in sig:
        assert abs(sig["has_binop"]["weight"]) < 1.0           # explained away → ~neutral


def test_budget_and_kill_criterion_are_declared():
    """3C: the budget + transfer margin exist up front, before any run."""
    assert wl.MAX_EPISODES > 0
    assert 0.0 < wl.TRANSFER_MARGIN < 1.0
    # a tiny budget is honoured (kill criterion can bite)
    result = wl.run_experiment(_TRAIN, _TEST, max_episodes=2)
    assert result["train_episodes"] == 2
    assert result["budget_exhausted"] is True
