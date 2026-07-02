# AR9 (CODEBASE_AUDIT_2026-07-01 O1): a locked data dir (`uchg` immutable flag,
# permissions, read-only volume) must stop the boot with a clear message — not
# silently turn every artifact write into a failed goal for a whole run.
import os
import stat

import pytest

from runtime import preflight


def test_writable_data_dir_passes(tmp_path, monkeypatch):
    import brain.paths as paths
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    preflight._check_data_writable()  # must not raise/exit
    assert not (tmp_path / ".boot_write_probe").exists()  # probe cleaned up


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permission bits")
def test_locked_data_dir_fails_loudly(tmp_path, monkeypatch, capsys):
    import brain.paths as paths
    locked = tmp_path / "data"
    locked.mkdir()
    locked.chmod(stat.S_IRUSR | stat.S_IXUSR)  # r-x: probe write must fail
    monkeypatch.setattr(paths, "DATA_DIR", locked)
    try:
        with pytest.raises(SystemExit) as exc:
            preflight._check_data_writable()
        assert exc.value.code == 3
        err = capsys.readouterr().err
        assert "not writable" in err
        assert "chflags" in err  # points at the uchg class specifically
    finally:
        locked.chmod(stat.S_IRWXU)  # let pytest clean tmp_path up
