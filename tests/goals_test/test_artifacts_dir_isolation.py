# Golden rule 3 regression (2026-07-20 smoke finding): goal handlers' artifacts
# base must resolve through the env-aware resolver, never a cwd-relative
# literal — the smoke life's daemon wrote research memos into the LIVE repo's
# data/goals/artifacts despite ORRIN_STATE_DIR isolation.

from pathlib import Path

from goals.handlers.base import default_artifacts_dir


def test_explicit_ctx_wins():
    assert default_artifacts_dir({"artifacts_dir": "/x/y"}) == Path("/x/y")


def test_state_dir_env_is_honored(monkeypatch, tmp_path):
    monkeypatch.delenv("ORRIN_GOALS_DIR", raising=False)
    monkeypatch.setenv("ORRIN_STATE_DIR", str(tmp_path / "state"))
    got = default_artifacts_dir({})
    assert got == (tmp_path / "state" / "goals" / "artifacts").resolve(), (
        "isolation must hold: no cwd-relative fallback while ORRIN_STATE_DIR is set")


def test_goals_dir_env_outranks_state_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("ORRIN_GOALS_DIR", str(tmp_path / "g"))
    monkeypatch.setenv("ORRIN_STATE_DIR", str(tmp_path / "state"))
    assert default_artifacts_dir({}) == (tmp_path / "g").resolve() / "artifacts"


def test_housekeeping_ctx_path_honors_state_dir(monkeypatch, tmp_path):
    from goals.handlers.housekeeping import _ctx_path
    monkeypatch.setenv("ORRIN_STATE_DIR", str(tmp_path / "state"))
    got = _ctx_path({}, "GOALS_SNAP_DIR", "data/goals/snapshots")
    assert got == (tmp_path / "state" / "goals" / "snapshots").resolve(), (
        "snapshot default must not be cwd-relative under isolation")
