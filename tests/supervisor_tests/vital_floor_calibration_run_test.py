from pathlib import Path

from brain.scripts import vital_floor_calibration_run as runner


def test_build_env_forces_observe_mode_and_headless(tmp_path):
    out = tmp_path / "samples.jsonl"
    env = runner.build_env(
        {"ORRIN_VITAL_FLOOR": "act", "KEEP": "yes"},
        phase="calm",
        out_file=out,
        sample_s=2.5,
        cycle_sleep=3.0,
        ui=False,
        stress="",
    )

    assert env["KEEP"] == "yes"
    assert env["ORRIN_VITAL_FLOOR"] == "observe"
    assert env["ORRIN_VITAL_CALIBRATION_FILE"] == str(out)
    assert env["ORRIN_VITAL_CALIBRATION_PHASE"] == "calm"
    assert env["ORRIN_VITAL_CALIBRATION_SAMPLE_S"] == "2.5"
    assert env["ORRIN_CYCLE_SLEEP"] == "3.0"
    assert env["ORRIN_UI"] == "0"


def test_build_env_can_leave_ui_enabled(tmp_path):
    env = runner.build_env(
        {},
        phase="dream_reading",
        out_file=tmp_path / "samples.jsonl",
        sample_s=1.0,
        cycle_sleep=1.0,
        ui=True,
        stress="dream_reading",
        stress_delay_s=7.0,
    )

    assert "ORRIN_UI" not in env
    assert env["ORRIN_VITAL_CALIBRATION_PHASE"] == "dream_reading"
    assert env["ORRIN_VITAL_CALIBRATION_STRESS"] == "dream_reading"
    assert env["ORRIN_VITAL_CALIBRATION_STRESS_DELAY_S"] == "7.0"


def test_command_points_at_repo_main():
    cmd = runner.command("python-test")

    assert cmd[0] == "python-test"
    assert Path(cmd[1]).name == "main.py"
    assert Path(cmd[1]).exists()
