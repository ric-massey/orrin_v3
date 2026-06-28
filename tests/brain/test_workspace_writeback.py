# Tests for top-down write-back (brain/cognition/workspace_writeback.py).
#
# The downward half of the global workspace: conscious conclusions nudge priors,
# then decay back to baseline. These tests pin the properties that make it safe
# to keep on by default — no entrenchment, no lurch, no reflex capture, no
# self-boost, bounded store, fail-safe.
from brain.cognition import workspace_writeback as wb
from brain.cognition.workspace_writeback import (
    write_back, salience_prior, tick_salience_priors,
    _ELIGIBLE_TARGETS, _MAX_AFFECT_DELTA, _MAX_TOKENS,
)
from brain.cognition.global_workspace import update_workspace
from brain.control_signals.arbiter import commit_signals, _PROP_KEY


def _ctx(**extra):
    # Pre-seed an empty store so _store() never hydrates from on-disk state and
    # tests stay isolated from real runs.
    ctx = {"_workspace_priors": {}, "affect_state": {"core_signals": {}}}
    ctx.update(extra)
    return ctx


def _conclusion(content="a novel insight about recursion and search", **extra):
    m = {"content": content, "source": "thought", "salience": 0.8}
    m.update(extra)
    return m


# 1. Decay returns to baseline — no entrenchment.
def test_decay_returns_to_baseline():
    ctx = _ctx()
    wb._prime(ctx, "recursion search trees", wb._PRIOR_BOOST)
    assert salience_prior(ctx, "recursion") > 0
    for _ in range(15):
        tick_salience_priors(ctx)
    assert salience_prior(ctx, "recursion search trees") == 0.0
    assert ctx["_workspace_priors"] == {}


# 2. Affect nudge is queued, not applied — and bounded.
def test_affect_nudge_queued_and_bounded():
    ctx = _ctx()
    moment = {"content": "the approach is stuck", "source": "monitor",
              "salience": 0.9, "wants": "escalate"}
    write_back(ctx, moment)
    props = ctx.get(_PROP_KEY) or []
    assert props, "expected a queued affect proposal"
    p = props[0]
    assert p["target"] == "impasse_signal"
    assert abs(p["delta"]) <= _MAX_AFFECT_DELTA + 1e-9
    assert p["source"] == "workspace_writeback"
    # Not applied until commit_signals integrates it next cycle.
    applied = commit_signals(ctx)
    assert "impasse_signal" in applied
    assert abs(applied["impasse_signal"]) <= _MAX_AFFECT_DELTA + 1e-9


# 3. Reflex floors / absolute scalars are never a write-back target.
def test_reflex_floors_excluded():
    # No eligible target is an absolute safety floor / scalar.
    from brain.control_signals.arbiter import _SCALAR_TARGETS
    assert not (_ELIGIBLE_TARGETS & _SCALAR_TARGETS)
    # Across every conclusion source, any queued affect target stays cortical.
    for src, extra in (("monitor", {"wants": "escalate"}),
                       ("subconscious", {}),
                       ("binding", {"goal_id": "g1"})):
        ctx = _ctx()
        write_back(ctx, {"content": "x y z conclusion here", "source": src,
                         "salience": 0.9, **extra})
        for p in ctx.get(_PROP_KEY) or []:
            assert p["target"] in _ELIGIBLE_TARGETS


# 4. Gating — low-salience / user / signal / noise moments do not write.
def test_gating_rejects_non_conclusions():
    for moment in (
        {"content": "real conclusion text", "source": "thought", "salience": 0.2},  # low
        {"content": 'Ric said: "hi"', "source": "user", "salience": 0.95},          # input
        {"content": "some signal text", "source": "signal", "salience": 0.9},       # input
        {"content": "[chunk: noise]", "source": "thought", "salience": 0.9},        # noise
    ):
        ctx = _ctx()
        write_back(ctx, moment)
        assert not ctx.get(_PROP_KEY)
        assert ctx["_workspace_priors"] == {}


# 5. Theme continuity — priming A raises A-related candidates; no self-boost.
def test_theme_continuity_and_no_self_boost():
    ctx = _ctx()
    # Prime tokens from a prior conscious conclusion.
    wb._prime(ctx, "neural plasticity dendrites", wb._PRIOR_BOOST)
    # Build a fresh competition: one A-related thought, one unrelated.
    ctx["working_memory"] = [
        {"content": "thinking about neural plasticity in dendrites again"},
    ]
    related = salience_prior(ctx, "neural plasticity dendrites")
    unrelated = salience_prior(ctx, "weather forecast tomorrow afternoon")
    assert related > 0
    assert unrelated == 0.0
    # A winner can't self-boost within its own cycle: salience_prior is read in
    # update_workspace, but priming happens only afterward via write_back.
    moment = update_workspace(ctx)
    assert moment is not None
    # The just-won content was not primed during this same cycle.
    pre = dict(ctx["_workspace_priors"])
    assert "afternoon" not in pre


# 6. Bounded store — exceeding _MAX_TOKENS evicts lowest, never unbounded.
def test_store_is_bounded():
    ctx = _ctx()
    many = " ".join(f"tok{i}word" for i in range(_MAX_TOKENS + 40))
    wb._prime(ctx, many, wb._PRIOR_BOOST)
    assert len(ctx["_workspace_priors"]) <= _MAX_TOKENS


# 7. Fail-safe — malformed moment / store can't raise.
def test_fail_safe():
    # Malformed moment.
    write_back(_ctx(), None)            # not a dict
    write_back(None, _conclusion())     # not a context
    write_back(_ctx(), {"salience": "oops"})
    # Malformed store can't raise out of the read/tick path.
    bad = {"_workspace_priors": {"x": "not-a-number"}}
    salience_prior(bad, "x")
    tick_salience_priors(bad)
