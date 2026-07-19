# Run 11 §2 — the anatomy membrane (M1 blueprints / M2 organs / M3 flight
# recorder + diary exception) and M4 behavioral introspection. The membrane is
# a WALL at the file-read chokepoints: an unidentified caller is reasoning-layer
# and gets the filter; agency organs pass with an explicit caller.

import json

from brain.paths import DATA_DIR, LOGS_DIR


# ── classification ───────────────────────────────────────────────────────────

def test_deny_reasons_cover_the_three_membranes():
    from brain.cognition.membrane import deny_reason
    # M1: source anywhere is a blueprint.
    assert deny_reason("brain/cognition/membrane.py") == "blueprint"
    assert deny_reason("frontend/src/App.tsx") == "blueprint"
    # M2: brain/data state files are organs.
    assert deny_reason(DATA_DIR / "bandit_state.json") == "organ_state"
    assert deny_reason(DATA_DIR / "runtime_lifetime.json") == "organ_state"
    # M3: machine transcripts are Ric-only.
    assert deny_reason(LOGS_DIR / "activity_log.txt") == "flight_recorder"
    # Diary exception: his own authored bodies stay readable.
    assert deny_reason(DATA_DIR / "effect_artifacts" / "abc123.txt") is None
    # Ordinary content elsewhere is not membraned.
    assert deny_reason("docs/README.md") is None


def test_organ_callers_pass_reasoning_fails_closed():
    from brain.cognition.membrane import read_allowed
    organ_file = DATA_DIR / "bandit_state.json"
    assert not read_allowed(organ_file)                      # no caller = reasoning
    assert not read_allowed(organ_file, caller="unknown")    # fail closed
    assert read_allowed(organ_file, caller="auto_repair")
    assert read_allowed("brain/loop/maintenance.py", caller="code_writer")


# ── grep_files chokepoint ────────────────────────────────────────────────────

def test_grep_files_hides_source_and_organs_from_reasoning(tmp_path):
    from brain.agency.skills.grep_files import grep_files
    # Plant the same needle in an organ file and a diary file.
    needle = "xenon_lantern_needle"
    (DATA_DIR / "effect_artifacts").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "effect_artifacts" / "note1.txt").write_text(
        f"a note I wrote about the {needle}", encoding="utf-8")
    (DATA_DIR / "world_model.json").write_text(
        json.dumps({"facts": [needle]}), encoding="utf-8")

    res = grep_files({"query": needle, "max_results": 20})
    assert res["success"]
    files = {m["file"] for m in res["matches"]}
    assert all("effect_artifacts" in f for f in files), (
        f"reasoning-layer grep leaked past the membrane: {files}")
    assert res["membrane_denied"] >= 1

    # An organ caller sees everything (source as a tool).
    res2 = grep_files({"query": needle, "max_results": 20, "caller": "self_extension"})
    files2 = {m["file"] for m in res2["matches"]}
    assert any("world_model.json" in f for f in files2)


# ── read_file chokepoint ─────────────────────────────────────────────────────

def test_read_file_denies_organ_state_to_reasoning():
    from brain.behavior.tools.toolkit import read_file
    (DATA_DIR / "runtime_lifetime.json").write_text("{}", encoding="utf-8")
    res = read_file(DATA_DIR / "runtime_lifetime.json")
    assert not res["success"] and "membrane" in res["error"]
    res2 = read_file(DATA_DIR / "runtime_lifetime.json", caller="auto_repair")
    assert res2["success"]


def test_read_file_diary_exception():
    from brain.behavior.tools.toolkit import read_file
    d = DATA_DIR / "effect_artifacts"
    d.mkdir(parents=True, exist_ok=True)
    (d / "deadbeef.txt").write_text("what I learned about noise", encoding="utf-8")
    res = read_file(d / "deadbeef.txt")
    assert res["success"] and "noise" in res["content"]


# ── M4: behavioral introspection ─────────────────────────────────────────────

def test_search_own_files_consumes_behavior_not_blueprints():
    from brain.cog_memory.long_memory import update_long_memory
    from brain.cognition.search_own_files import search_own_files

    update_long_memory("I noticed the impasse feeling rises after repeated "
                       "failed plans on the same goal.",
                       event_type="reflection", importance=3)
    out = search_own_files({"working_memory": []}, query="impasse feeling rises")
    assert "Looking into myself" in out
    assert "something I remember" in out
    # No file coordinates in what reaches the workspace.
    assert ".py" not in out


def test_causal_frontier_goals_are_history_framed(monkeypatch):
    import brain.cognition.intrinsic_generators as ig
    monkeypatch.setattr(
        "brain.symbolic.causal_graph.get_all_edges",
        lambda: [{"cause": "long stretches without progress",
                  "effect": "restlessness during long tasks",
                  "causal_score": 0.2, "evidence_count": 4}])
    goals = ig._causal_frontier_goals(limit=2)
    assert goals, "frontier goal must originate from a weak-cause gap"
    g = goals[0]
    assert g["title"].startswith("Trace in my own history"), g["title"]
    assert "code" not in g["title"]
    assert "grep" not in g["description"], "M4: no code-search framing"
    assert g.get("question", "").startswith("What tends to precede")
