# R10-11: the causal graph must not be 100% interoceptive. The external observer
# banks at least one WORLD edge (time-of-day → host load) whose endpoints are not
# internal signals/actions, satisfying the world_knowledge aspiration's graph.

import brain.symbolic.external_observer as ext
from brain.symbolic import causal_graph as cg


def test_observation_creates_a_world_domain_edge():
    ext._last_obs_ts = 0.0
    edge = ext.observe_external_causality({"cpu_util": 0.9})
    assert edge is not None
    assert edge["domain"] == "world", "external observation must be a world edge, not self"
    assert "host machine is busy" in edge["effect"]


def test_observation_is_throttled():
    ext._last_obs_ts = 0.0
    first = ext.observe_external_causality({"cpu_util": 0.1})
    assert first is not None
    # Immediately again → throttled, banks nothing.
    assert ext.observe_external_causality({"cpu_util": 0.1}) is None


def test_at_least_one_outward_edge_exists_after_observing():
    ext._last_obs_ts = 0.0
    ext.observe_external_causality({"cpu_util": 0.5})
    edges = cg._load_edges()
    outward = [e for e in edges if e.get("domain") == "world"]
    assert outward, "≥1 edge whose endpoints are external world facts"
