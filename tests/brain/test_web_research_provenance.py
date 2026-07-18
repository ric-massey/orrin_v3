# R10-3: research memos file by PROVENANCE, not by whichever goal holds the slot.
#
# Run 9's drive-by fetch_and_read intake (an off-topic RSS scrape) landed inside
# a FAILING goal's artifact dir, corrupting the "artifacts ⇒ not FAILED" audit.
# Only content DERIVED FROM the bound goal (origin=="goal") may file under and
# credit that goal; slot-blind intake files under artifacts/intake/ with no
# goal credit.

from brain.cognition import web_research as wr
from brain.paths import GOALS_DIR


def _body(seed: str) -> str:
    # Varied, non-boilerplate prose so the effect ledger credits it as novel
    # (a repetitive stock string is scored as boilerplate and never written).
    return (
        f"Findings on {seed}: recent measurements suggest an unexpected coupling "
        f"between local density and observed drift. The {seed} regime shows a "
        f"threshold near which coherence collapses, and the transition appears "
        f"reversible under gentle perturbation. Several groups have replicated the "
        f"core result, though the mechanism behind {seed} remains contested. "
        f"A minority argue the effect is an artifact of the instrument used to "
        f"probe {seed}, but blind trials weaken that objection considerably."
    )


def test_slot_blind_intake_files_under_intake_not_the_bound_goal():
    ctx = {"committed_goal": {"id": "g_failing", "title": "some goal"}}
    wr._write_research_memo("Off-topic RSS scrape", _body("off-topic rss"), ctx,
                            source="fetch_and_read", origin="rss")

    intake_dir = GOALS_DIR / "artifacts" / "intake"
    goal_dir = GOALS_DIR / "artifacts" / "g_failing"
    assert intake_dir.exists() and any(intake_dir.glob("memo_*.md"))
    assert not goal_dir.exists(), "slot-blind intake must not land in the goal dir"


def test_goal_derived_content_files_under_the_goal():
    ctx = {"committed_goal": {"id": "g_real", "title": "black holes"}}
    wr._write_research_memo("Black holes", _body("black holes"), ctx,
                            source="research_topic", origin="goal")

    goal_dir = GOALS_DIR / "artifacts" / "g_real"
    assert goal_dir.exists() and any(goal_dir.glob("memo_*.md"))


def test_intake_memo_is_not_credited_to_the_goal_on_the_ledger():
    import json
    from brain.agency.effect_ledger import EFFECT_LEDGER_FILE
    ctx = {"committed_goal": {"id": "g_slot", "title": "slot holder"}}
    wr._write_research_memo("Unrelated intake topic", _body("unrelated intake"), ctx,
                            source="fetch_and_read", origin="working_memory")

    rows = []
    if EFFECT_LEDGER_FILE.exists():
        for line in EFFECT_LEDGER_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    credited = [r for r in rows
                if str((r.get("metadata") or {}).get("topic", "")).startswith("Unrelated intake")
                and r.get("goal_id") == "g_slot"]
    assert not credited, "intake memo must not be credited to the slot-holding goal"
