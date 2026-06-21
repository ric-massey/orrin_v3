def test_sensory_stream_splits_home_and_world_sense(monkeypatch):
    from brain.embodiment.sensory_stream import SensoryStream

    stream = SensoryStream()
    monkeypatch.setattr(
        stream,
        "_system_vitals",
        lambda: {"cpu_percent": 12.0, "memory_percent": 40.0, "memory_available_gb": 4.2, "disk_percent": 55.0},
    )
    monkeypatch.setattr(stream, "_detect_code_changes", lambda: False)
    monkeypatch.setattr(stream, "_read_log_tail", lambda: ["did a thing"])

    def fake_changes(watch_dirs=None, *, zone="home"):
        if zone == "home":
            return [{"path": "docs/plan.md", "dir": "docs", "age_s": 1.0, "zone": "home"}]
        return [{"path": "outside.txt", "dir": "outside", "age_s": 1.0, "zone": "world"}]

    monkeypatch.setattr(stream, "_detect_fs_changes", fake_changes)

    field = stream._sample()

    assert field["home_sense"]["mood"] == "ambient"
    assert field["home_sense"]["fs_changes"][0]["zone"] == "home"
    assert field["world_sense"]["mood"] == "stirring"
    assert field["world_sense"]["fs_changes"][0]["zone"] == "world"
    assert len(field["fs_changes"]) == 2  # legacy merged view preserved
    assert field["environment_mood"] == "active"


def test_world_model_preserves_home_world_sense(monkeypatch):
    from brain.embodiment.world_model import WorldModel
    from brain.embodiment import sensory_stream

    monkeypatch.setattr(
        sensory_stream,
        "get_field",
        lambda: {
            "system": {
                "cpu_percent": 10.0,
                "memory_percent": 45.0,
                "memory_available_gb": 4.0,
                "disk_percent": 50.0,
            },
            "home_sense": {
                "mood": "active",
                "fs_changes": [{"path": "docs/plan.md", "zone": "home"}],
                "own_code_modified": False,
                "log_tail": [],
            },
            "world_sense": {
                "mood": "distant",
                "fs_changes": [],
            },
            "environment_mood": "active",
            "fs_changes": [{"path": "docs/plan.md", "zone": "home"}],
            "own_code_modified": False,
            "log_tail": [],
        },
    )

    model = WorldModel()
    monkeypatch.setattr(model, "_last_net_check", 10**12)
    model._last_net_ok = True

    snap = model._take_snapshot({})

    assert snap["home_mood"] == "active"
    assert snap["world_mood"] == "distant"
    assert snap["home_changes"] == 1
    assert snap["world_changes"] == 0
    assert snap["fs_changes"] == 1
