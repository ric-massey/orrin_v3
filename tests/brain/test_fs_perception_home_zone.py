def test_categorise_splits_body_home_world():
    import cognition.perception.fs_perception as fs

    body, home, world = [], [], []
    fs._categorise("brain/cognition/body_sense.py", "modified", body, home, world)
    fs._categorise("docs/Core Architecture, Embodiment & Evolution/MASTER_PLAN_2026-06-16.md", "modified", body, home, world)
    fs._categorise("README.md", "modified", body, home, world)
    fs._categorise("external_note.txt", "modified", body, home, world)

    assert body == ["brain/cognition/body_sense.py"]
    assert home == [
        "docs/Core Architecture, Embodiment & Evolution/MASTER_PLAN_2026-06-16.md",
        "README.md",
    ]
    assert world == ["external_note.txt"]


def test_poll_emits_home_touched_signal(tmp_path, monkeypatch):
    import cognition.perception.fs_perception as fs

    docs = tmp_path / "docs"
    docs.mkdir()
    plan = docs / "plan.md"
    plan.write_text("before", encoding="utf-8")

    monkeypatch.setattr(fs, "_last_poll_ts", 0.0)
    monkeypatch.setattr(fs, "_mtime_snapshot", {"docs/plan.md": plan.stat().st_mtime - 2.0})
    monkeypatch.setattr(fs, "_POLL_INTERVAL_S", 0.0)
    monkeypatch.setattr(fs.time, "time", lambda: 1000.0)

    plan.write_text("after", encoding="utf-8")
    # Some filesystems round mtimes aggressively; force an unmistakable delta.
    new_mtime = plan.stat().st_mtime + 5.0
    import os
    os.utime(plan, (new_mtime, new_mtime))

    signals = fs.poll_fs_changes({"world_root": str(tmp_path)})

    assert len(signals) == 1
    assert "home_touched" in signals[0]["tags"]
    assert "world_changed" not in signals[0]["tags"]
