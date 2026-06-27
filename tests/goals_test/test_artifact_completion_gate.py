# Regression test for the 2026-06-24 "hollow completion" bug.
#
# The v2 finalize paths (runner._maybe_finalize, goals_daemon._finalize_goals) flipped a
# goal to DONE the moment all its plan steps were terminal — with no check that an
# artifact-requiring goal had actually produced anything. The GenericHandler runs an LLM
# reflection, logs a private thought, and marks the step DONE without writing a durable
# artifact, so requires_artifact=True goals were marked 100%/DONE while producing
# nothing. artifact_satisfied() is the gate: an artifact-required goal completes only
# with real production evidence.

from goals.model import Goal, Step, Status, artifact_satisfied

# Real content that passes the T0.5 quality predicate's negative gates (long
# enough, information-rich, not a template skeleton, not a machine-log stub).
_REAL = (
    "Local feedback coupling between many simple units and a shared field produces "
    "a measurable global pattern that none of the units represents on its own — "
    "convection cells, starling flocks, and market prices all share this signature. "
    "The coupling is the mechanism, and changing it is where intervention has leverage."
)
# The run's slop shapes the gate must now REJECT.
_STUB = "snapshot_goals → goals_state_20260622-004100.jsonl (lines=0)"
_TEMPLATE = ("what I actually know about emergence: question or desired change; "
             "relevant evidence; reasoned conclusion")


def _goal(requires_artifact: bool, gid: str = "g_test") -> Goal:
    return Goal(id=gid, title="Understand X more deeply", kind="generic",
                spec={"requires_artifact": requires_artifact})


def _step(gid: str = "g_test", artifacts=None) -> Step:
    return Step(id="s1", goal_id=gid, name="execute", action={},
                status=Status.DONE, artifacts=list(artifacts or []))


def test_non_artifact_goal_always_satisfied():
    """A goal that does not require an artifact is never gated."""
    assert artifact_satisfied(_goal(False), [_step()]) is True


def test_hollow_artifact_goal_not_satisfied(tmp_path, monkeypatch):
    """requires_artifact, no step.artifacts, empty/absent artifacts dir → NOT satisfied."""
    monkeypatch.setenv("ORRIN_GOALS_ARTIFACTS_DIR", str(tmp_path))
    assert artifact_satisfied(_goal(True), [_step()]) is False


def test_step_artifact_with_real_content_satisfies(tmp_path, monkeypatch):
    """A step artifact pointing at a REAL-content file satisfies the gate."""
    monkeypatch.setenv("ORRIN_GOALS_ARTIFACTS_DIR", str(tmp_path))
    out = tmp_path / "out.md"
    out.write_text(_REAL, encoding="utf-8")
    assert artifact_satisfied(_goal(True), [_step(artifacts=[str(out)])]) is True


def test_on_disk_real_content_satisfies(tmp_path, monkeypatch):
    """Real content in the goal's artifacts dir satisfies the gate even when
    step.artifacts is empty (research does not populate it)."""
    monkeypatch.setenv("ORRIN_GOALS_ARTIFACTS_DIR", str(tmp_path))
    gdir = tmp_path / "g_test"
    gdir.mkdir()
    (gdir / "doc_synthesis.md").write_text(_REAL, encoding="utf-8")
    assert artifact_satisfied(_goal(True), [_step()]) is True


def test_stub_ok_file_does_not_satisfy(tmp_path, monkeypatch):
    """T0.5: a machine-log s_*_ok.txt stub must NOT satisfy the gate (the loophole)."""
    monkeypatch.setenv("ORRIN_GOALS_ARTIFACTS_DIR", str(tmp_path))
    gdir = tmp_path / "g_test"
    gdir.mkdir()
    (gdir / "s_abc_ok.txt").write_text(_STUB, encoding="utf-8")
    assert artifact_satisfied(_goal(True), [_step()]) is False


def test_template_note_does_not_satisfy(tmp_path, monkeypatch):
    """T0.5: a grounded_parts-template note body must NOT satisfy the gate."""
    monkeypatch.setenv("ORRIN_GOALS_ARTIFACTS_DIR", str(tmp_path))
    gdir = tmp_path / "g_test"
    gdir.mkdir()
    (gdir / "note.txt").write_text(_TEMPLATE, encoding="utf-8")
    assert artifact_satisfied(_goal(True), [_step()]) is False


def test_one_real_file_among_stubs_satisfies(tmp_path, monkeypatch):
    """Permissive in spirit: a single real file satisfies even amid stubs."""
    monkeypatch.setenv("ORRIN_GOALS_ARTIFACTS_DIR", str(tmp_path))
    gdir = tmp_path / "g_test"
    gdir.mkdir()
    (gdir / "s_abc_ok.txt").write_text(_STUB, encoding="utf-8")
    (gdir / "real.md").write_text(_REAL, encoding="utf-8")
    assert artifact_satisfied(_goal(True), [_step()]) is True
