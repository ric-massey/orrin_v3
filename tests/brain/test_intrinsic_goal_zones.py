def test_goal_zone_classifies_homeward_and_worldward():
    import brain.cognition.intrinsic_goals as ig

    assert ig._goal_zone(
        "Explore my local workspace",
        "exploration_drive",
        "Use search_own_files to inspect what changed in my files.",
    ) == "home"
    assert ig._goal_orientation("home") == "homeward"

    assert ig._goal_zone(
        "Research sleep consolidation",
        "world_knowledge",
        "Use research_topic / wikipedia_search to learn something new.",
    ) == "world"
    assert ig._goal_orientation("world") == "worldward"

    assert ig._goal_zone("Clarify my values", "value", "Reflect on a tension.") == "self"


def test_mk_goal_stamps_zone_orientation_and_tags():
    import brain.cognition.intrinsic_goals as ig

    home = ig._mk_goal(
        "Inspect my files for recent changes",
        "Use grep_files and search_own_files over the local workspace.",
        driven_by="self_exploration",
    )
    assert home["zone"] == "home"
    assert home["orientation"] == "homeward"
    assert "homeward" in home["tags"]
    assert "home" in home["tags"]

    world = ig._mk_goal(
        "Follow up on photosynthesis",
        "Use research_topic to learn a new external fact.",
        driven_by="world_knowledge",
    )
    assert world["zone"] == "world"
    assert world["orientation"] == "worldward"
    assert "worldward" in world["tags"]
    assert "external" in world["tags"]
