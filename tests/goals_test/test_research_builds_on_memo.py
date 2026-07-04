# Run 4 fix A2 (RUN4_FIX_PLAN_2026-07-04 §A2, research-handler half): a second
# same-topic synthesis reads the first memo, cites it, and credits tier-3 reuse.

import brain.agency.effect_ledger as el
from goals.model import Goal, Step, Status
from goals.handlers.research import ResearchHandler


def _mk_goal(gid, title):
    return Goal(id=gid, title=title, kind="research", spec={})


def _synth_step(gid):
    return Step(id=f"s_{gid}", goal_id=gid, name="synthesize findings",
                action={"op": "synthesize"}, status=Status.READY)


def test_second_memo_builds_on_and_credits_first(tmp_path, monkeypatch):
    monkeypatch.setattr(el, "EFFECT_LEDGER_FILE", tmp_path / "effect_ledger.jsonl",
                        raising=False)
    el.reset_for_tests()
    art_base = tmp_path / "artifacts"
    ctx = {"artifacts_dir": str(art_base)}

    # First goal: produce a memo, register it on the ledger with its path.
    g1 = _mk_goal("g-evo-1", "Evolutionary biology synthesis")
    d1 = art_base / g1.id
    d1.mkdir(parents=True)
    (d1 / "doc_01.txt").write_text(
        "Natural selection acts on heritable variation in evolutionary biology; "
        "genetic drift and mutation add distinct population dynamics.", encoding="utf-8")
    prior = ResearchHandler().tick(g1, _synth_step(g1.id), ctx)
    assert prior.status == Status.DONE
    memo1 = next(art_base.glob(f"{g1.id}/*.md"))
    el.record_effect("file_write", memo1.read_text(encoding="utf-8"),
                     goal_id=g1.id, metadata={"path": str(memo1)})
    assert el.hash_for_path(memo1) is not None

    # Second, same-topic goal: its synthesis should find + cite + credit the first.
    g2 = _mk_goal("g-evo-2", "Evolutionary biology overview and synthesis")
    d2 = art_base / g2.id
    d2.mkdir(parents=True)
    (d2 / "doc_01.txt").write_text(
        "Evolutionary biology also studies speciation and adaptation over deep time.",
        encoding="utf-8")
    out = ResearchHandler().tick(g2, _synth_step(g2.id), ctx)
    assert out.status == Status.DONE

    memo2 = next(art_base.glob(f"{g2.id}/*.md")).read_text(encoding="utf-8")
    assert "Builds on:" in memo2
    assert el.reuse_count(el.hash_for_path(memo1)) >= 1
