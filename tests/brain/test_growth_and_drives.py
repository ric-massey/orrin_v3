# Run 11 §3 (growth: G1 ladder, G2 answer citation, G3 mastery) and §5 (drives:
# D2 distant connections, D3 novelty rebound), proven at the mechanism.

from brain.paths import LONG_MEMORY_FILE
from brain.utils.json_utils import save_json


# ── D3: novelty rebound ──────────────────────────────────────────────────────

def test_one_action_cannot_zero_the_novelty_drive():
    from brain.motivation import substrate as sub
    assert sub._NOVELTY_REBOUND, "flag must default ON for Run 11"
    eng = sub._MotivationEngine.__new__(sub._MotivationEngine)
    # Full satisfaction from a high state: relief is proportional, floored.
    after = eng._relieved(sub._NOVELTY_DRIVE, 0.8, 0.35)
    assert after > sub._NOVELTY_FLOOR, "one fed action must not extinguish novelty"
    assert after < 0.8, "relief must still relieve"
    # A feeding STREAK approaches the floor geometrically, never crosses it.
    v = 0.8
    for _ in range(50):
        v = eng._relieved(sub._NOVELTY_DRIVE, v, 0.35)
    assert v >= sub._NOVELTY_FLOOR - 1e-9
    # Other drives keep linear relief (D4 is explicitly out of this tune).
    assert abs(eng._relieved("connection", 0.5, 0.35) - 0.15) < 1e-9


def test_novelty_recovery_timescale_is_usable():
    from brain.motivation import substrate as sub
    _, rise, fall, _ = sub._DRIVE_DEFAULTS[sub._NOVELTY_DRIVE]
    assert fall / rise < 20, f"drain/recover asymmetry still extinguishing: {fall/rise:.0f}x"


# ── D2: distant connections ──────────────────────────────────────────────────

def _seed_long_memory(entries):
    save_json(LONG_MEMORY_FILE, [{"content": c, "event_type": "thought"} for c in entries])
    from brain.symbolic import analogy_engine as ae
    ae._CACHE = []          # drop the module cache so the seed is visible
    ae._CACHE_TS = 0.0


def test_distant_connection_requires_shared_relation_and_surface_distance():
    from brain.symbolic.analogy_engine import find_distant_connections
    _seed_long_memory([
        # Shared CAUSES relation, disjoint vocabulary → the creative leap.
        "Heavy rainfall causes flooding along the river delta each spring season",
        # Same vocabulary as the query → a neighbor, must be excluded.
        "Sleep deprivation causes memory failure during long focus periods often",
        # No abstract relation at all → no bridge, excluded.
        "The afternoon was quiet and the garden path wound between old trees",
    ])
    query = "sleep deprivation causes memory failure when focus runs long"
    links = find_distant_connections(query, top_n=3, min_score=0.2)
    assert links, "a relation-sharing, surface-distant memory must surface"
    assert all("CAUSES" in l["shared_relations"] for l in links)
    assert all(l["surface"] <= 0.15 for l in links), "neighbors must not qualify"
    assert not any("deprivation" in l["content"] for l in links)


def test_unexpected_link_act_records_a_durable_artifact():
    from brain.cognition import unexpected_link as ul
    _seed_long_memory([
        "Heavy rainfall causes flooding along the river delta each spring season",
        "Sleep deprivation causes memory failure during long focus periods often",
    ])
    prose = ul.find_unexpected_link({})
    assert prose and "CAUSES" in prose
    # Empty store → no fabrication.
    _seed_long_memory([])
    assert ul.find_unexpected_link({}) == ""


# ── G1: the difficulty ladder ────────────────────────────────────────────────

def test_streak_climbs_the_rung_and_failure_resets_streak_not_rung(tmp_path, monkeypatch):
    from brain.cognition import growth_ladder as gl
    monkeypatch.setattr(gl, "_STATE_FILE", tmp_path / "ladder.json")
    assert gl.rung() == 0
    for i in range(gl._STREAK_TO_CLIMB):
        gl.note_verified_success("answered_question", f"q{i}")
    assert gl.rung() == 1, "a verified streak climbs the bar"
    gl.note_verified_success("exemplar", "e1")
    gl.note_failed_attempt("g1")
    assert gl.rung() == 1, "one setback must not demote demonstrated competence"
    assert gl._state().get("streak") == 0, "but the streak re-arms from zero"


def test_harden_goal_applies_the_rung_to_making_goals_only(tmp_path, monkeypatch):
    from brain.cognition import growth_ladder as gl
    monkeypatch.setattr(gl, "_STATE_FILE", tmp_path / "ladder.json")
    for i in range(gl._STREAK_TO_CLIMB):
        gl.note_verified_success("answered_question", f"q{i}")
    making = {"requires_artifact": True, "definition_of_done": []}
    gl.harden_goal(making)
    crits = [c["criterion"] for c in making["definition_of_done"]]
    assert any("prior" in c.lower() for c in crits), "rung 1 requires build-on-prior"
    assert making["spec"]["build_on_prior"] is True
    assert making["ladder_rung"] == 1
    thinking = {"definition_of_done": []}
    gl.harden_goal(thinking)
    assert thinking["definition_of_done"] == [], "non-making goals are untouched"


# ── G2: the answer changes a later decision ──────────────────────────────────

def test_decision_reason_cites_a_consumed_answer(monkeypatch, tmp_path):
    from brain.cognition import answer_citation as ac
    monkeypatch.setattr(ac, "_FILE", tmp_path / "answered.json")
    ac.note_answered(
        "What tends to precede impasse pressure in my own experience?",
        "Long unbroken deliberation windows precede it.", "g_q1")
    reason: dict = {}
    ctx = {"focus_goal": {"title": "Reduce impasse pressure in my experience of planning"}}
    ac.annotate_reason(reason, ctx, "assess_goal_progress")
    assert "cites_answer" in reason, "the consumed answer must appear in the payload"
    assert reason["cites_answer"]["goal_id"] == "g_q1"
    rows = ac.cited_rows()
    assert rows and rows[0]["cited"] == 1 and rows[0]["last_cited_fn"] == "assess_goal_progress"
    # An unrelated decision context does not cite.
    reason2: dict = {}
    ac.annotate_reason(reason2, {"focus_goal": {"title": "Water the plants"}}, "speak")
    assert "cites_answer" not in reason2


# ── G3: mastery weighting ────────────────────────────────────────────────────

def test_mastery_weight_prefers_the_zone_next_to_competence(monkeypatch, tmp_path):
    from brain.cognition import growth_ladder as gl
    from brain.cognition import answer_citation as ac
    monkeypatch.setattr(gl, "_STATE_FILE", tmp_path / "ladder.json")
    monkeypatch.setattr(ac, "_FILE", tmp_path / "answered.json")
    gl._mastery_cache = None
    ac.note_answered("How does habituation shape signal routing pressure?", "…", "g1")
    gl._mastery_cache = None
    near = gl.mastery_weight("investigate habituation of routing pressure further")
    far = gl.mastery_weight("catalogue medieval shipbuilding techniques")
    assert near > far >= 1.0
    gl._mastery_cache = None
