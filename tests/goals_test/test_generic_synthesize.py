# Run 4 fix A3 (RUN4_FIX_PLAN_2026-07-04 §A3): the daemon-executable `synthesize`
# lane. A generic goal with a synthesize spec plans a READY step (not the WAITING
# external-pursuit placeholder), produces a real artifact file, and credits reuse
# on the prior memos it built on.

import brain.agency.effect_ledger as el
from goals.model import Goal, Status
from goals.handlers.generic import GenericHandler, _daemon_executable


def _goal(gid, topic):
    return Goal(id=gid, title=f"Turn what I know about {topic} into a written synthesis",
                kind="generic", spec={"synthesize": topic, "from_artifacts": True})


def test_synthesize_spec_is_daemon_executable():
    assert _daemon_executable({"synthesize": "evolution"})
    assert not _daemon_executable({})


def test_synthesize_plans_ready_step():
    steps = GenericHandler().plan(_goal("g1", "evolution"), {})
    assert len(steps) == 1
    assert steps[0].status == Status.READY


def test_synthesize_produces_artifact_and_credits_prior(tmp_path, monkeypatch):
    monkeypatch.setattr(el, "EFFECT_LEDGER_FILE", tmp_path / "effect_ledger.jsonl",
                        raising=False)
    el.reset_for_tests()
    # Force the offline fallback so the test needs no LLM.
    monkeypatch.setattr("goals.handlers.generic._llm_call",
                        lambda *a, **k: "[llm_unavailable: test]")

    art_base = tmp_path / "artifacts"
    # A prior memo on evolution, produced + ledger-registered by an earlier goal.
    prior_dir = art_base / "g-prior"
    prior_dir.mkdir(parents=True)
    prior_memo = prior_dir / "research_memo.md"
    prior_memo.write_text(
        "Evolution proceeds by natural selection on heritable variation; "
        "genetic drift and mutation add further population-level dynamics.",
        encoding="utf-8")
    el.record_effect("file_write", prior_memo.read_text(encoding="utf-8"),
                     goal_id="g-prior", metadata={"path": str(prior_memo)})
    prior_hash = el.hash_for_path(prior_memo)
    assert prior_hash is not None

    ctx = {"artifacts_dir": str(art_base)}
    g = _goal("g-syn", "evolution")
    step = GenericHandler().plan(g, ctx)[0]
    out = GenericHandler().tick(g, step, ctx)

    assert out.status == Status.DONE
    produced = art_base / "g-syn" / "synthesis.md"
    assert produced.is_file()
    assert produced.stat().st_size > 0
    # The step carries the produced path so the runner's effect chokepoint sees it.
    assert str(produced) in (out.artifacts or [])
    # Prior memo was reused.
    assert el.reuse_count(prior_hash) >= 1


def test_synthesize_fails_honestly_with_no_source_and_no_llm(tmp_path, monkeypatch):
    monkeypatch.setattr(el, "EFFECT_LEDGER_FILE", tmp_path / "effect_ledger.jsonl",
                        raising=False)
    el.reset_for_tests()
    monkeypatch.setattr("goals.handlers.generic._llm_call",
                        lambda *a, **k: "[llm_unavailable: test]")
    ctx = {"artifacts_dir": str(tmp_path / "artifacts")}
    g = _goal("g-empty", "quantum gravity nobody noted")
    step = GenericHandler().plan(g, ctx)[0]
    out = GenericHandler().tick(g, step, ctx)
    assert out.status == Status.FAILED
