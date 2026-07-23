# 1D.3 (Run 12) — spread effect-credit past self_understanding.
# Run 11 ground truth (demo_runs/2026-07-21-run): commitment was diverse across
# all four aspirations but contributions were 19/0/0/0. Chain of causes:
#   (a) the commitment path re-mints goals with a bare driven_by="will",
#       shredding provenance ("Understand foundations of quantum mechanics
#       more deeply" → driven_by: will, serves: None);
#   (b) the learned will→aspiration link had been captured by
#       self_understanding (0.74 > the 0.5 seed) partly via a circular
#       learning signal — zero-evidence goals "evidenced" their own intent
#       prior and taught it back to the EMA;
#   (c) contact goals could not even be BORN in an empty room, so
#       genuine_contact earned zero structurally.
# The titles below are the actual completed-goal titles from the Run 11 capture.

import json

import pytest

from brain.cognition import intrinsic_objectives as io
from brain.cognition import intrinsic_generators as ig
from brain.paths import GOALS_FILE, COMPLETED_GOALS_FILE

_SELF = "Understand my own mind and how I work"
_WORLD = "Understand the world more deeply"
_CONTACT = "Be genuinely useful and connected to the people I talk to"


@pytest.fixture(autouse=True)
def _isolate_learned_link():
    """credit_objectives EMA-learns into the session-shared drive-credit file;
    restore it (and the goal stores) so this slice's completions don't leak a
    learned weight into test_objective_quick_wins' pristine-seed assertions."""
    files = (io._DRIVE_CREDIT_FILE, GOALS_FILE, COMPLETED_GOALS_FILE)
    saved = {f: (f.read_text(encoding="utf-8") if f.exists() else None) for f in files}
    try:
        yield
    finally:
        for f, text in saved.items():
            if text is None:
                if f.exists():
                    f.unlink()
            else:
                f.write_text(text, encoding="utf-8")


# ── content routing (the real Run 11 titles) ─────────────────────────────────

def test_world_research_titles_route_to_world():
    for title in (
        "Understand foundations of quantum mechanics more deeply",
        "Understand history of written language more deeply",
        "Answer: What do I now know about foundations of quantum mechanics "
        "that I could not have said before?",
    ):
        assert io.content_aspiration({"title": title}) == _WORLD, title


def test_introspective_titles_route_to_self():
    for title in (
        "Understand my own mind and how I work more deeply",
        "Trace in my own history what drives 'dream'",
        "Answer: What do I now know about my own mind and how I work that "
        "I could not have said before?",
    ):
        assert io.content_aspiration({"title": title}) == _SELF, title


def test_ambiguous_content_returns_none():
    # A tie is ambiguity, not evidence — no stamp, fall through to the drive link.
    assert io.content_aspiration({"title": "Strengthen EMOTIONAL symbolic reasoning"}) is None


# ── the circular learning signal is dead ─────────────────────────────────────

def test_zero_evidence_completion_teaches_nothing(monkeypatch):
    monkeypatch.setattr(io, "_serves_aspiration", lambda d: _SELF if d == "will" else "")
    assert io._evidenced_aspiration({"title": "qzx vbnm", "driven_by": "will"}) is None


# ── credit lands where the outcome says, not where the will-link points ──────

def test_credit_objectives_spreads_past_self_understanding():
    completed = [
        {"id": "g-quantum", "status": "completed", "driven_by": "will",
         "source": "commitment",
         "title": "Understand foundations of quantum mechanics more deeply"},
        {"id": "g-lang", "status": "completed", "driven_by": "will",
         "source": "commitment",
         "title": "Understand history of written language more deeply"},
        {"id": "g-mind", "status": "completed", "driven_by": "self_understanding",
         "title": "Understand my own mind and how I work more deeply"},
    ]
    GOALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    GOALS_FILE.write_text(json.dumps(completed), encoding="utf-8")
    COMPLETED_GOALS_FILE.write_text("[]", encoding="utf-8")

    io.credit_objectives({})

    goals = json.loads(GOALS_FILE.read_text(encoding="utf-8"))
    counts = {g["title"]: g.get("contribution_count", 0)
              for g in goals if g.get("_aspiration")}
    assert counts[_WORLD] == 2, counts
    assert counts[_SELF] == 1, counts
    assert sum(1 for c in counts.values() if c > 0) >= 2


# ── the commitment re-mint keeps provenance ──────────────────────────────────

def test_commitment_remint_stamps_serves():
    from brain.cognition.commitment import _link_commitment_to_goal
    GOALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    GOALS_FILE.write_text("[]", encoding="utf-8")
    _link_commitment_to_goal("Understand foundations of quantum mechanics more deeply")
    goals = json.loads(GOALS_FILE.read_text(encoding="utf-8"))

    def _walk(nodes):
        for n in nodes or []:
            if isinstance(n, dict):
                yield n
                yield from _walk(n.get("subgoals"))

    minted = [g for g in _walk(goals) if g.get("source") == "commitment"]
    assert minted, "commitment goal was not minted"
    assert minted[0].get("serves") == _WORLD
    assert minted[0].get("driven_by") == "will"


# ── contact goals can be born in an empty room ───────────────────────────────

def test_unattended_contact_goal_is_minted_from_a_finding():
    long_mem = [
        {"content": "[world_perception] From searching 'ant colonies': "
                    "Ants coordinate through pheromone trails, not central control."},
    ]
    out = ig._contact_goals({}, long_mem)
    assert out, "no contact goal born in an empty room"
    g = out[0]
    assert g["driven_by"] == "genuine_contact"
    assert g["title"].startswith("Leave Ric a note about")
    # …and it still routes its credit to the contact aspiration.
    assert io.content_aspiration(g) == _CONTACT


def test_attended_contact_goal_still_shares_live():
    long_mem = [
        {"content": "[world_perception] From searching 'ant colonies': "
                    "Ants coordinate through pheromone trails, not central control."},
    ]
    out = ig._contact_goals({"user_present_recent": True}, long_mem)
    assert out and out[0]["title"].startswith("Share with Ric")
