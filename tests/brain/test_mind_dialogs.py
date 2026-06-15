# E7 — native Save/Open dialog over the bridge (§9.6). Binary export/import can't
# ride the text REST proxy, so the transfer runs in Python via the native file
# dialog. These unit-test the handlers (brain.utils.mind_dialogs) directly with a
# fake window, so no FastAPI app is imported. Runs under conftest's ORRIN_DATA_DIR
# isolation.
from utils import mind_dialogs as md


class _FakeWindow:
    """Stands in for the pywebview window: create_file_dialog returns a preset path."""

    def __init__(self, dialog_result):
        self._result = dialog_result
        self.calls = []

    def create_file_dialog(self, dialog_type, **kwargs):
        self.calls.append((dialog_type, kwargs))
        return self._result


def test_export_writes_archive_to_chosen_path(tmp_path, monkeypatch):
    # E7's job: take the dialog's path and write the archive bytes there. Stub
    # export_bytes (mind_archive's own, separately-tested job) to keep this a unit
    # test of the dialog plumbing.
    from utils import mind_archive
    monkeypatch.setattr(mind_archive, "export_bytes", lambda: b"PK\x03\x04 fake archive")
    dest = tmp_path / "keepsake.orrindmind"
    out = md.export_mind(_FakeWindow((str(dest),)))
    assert out["ok"] is True
    assert out["path"] == str(dest)
    assert dest.read_bytes() == b"PK\x03\x04 fake archive"  # exact bytes written


def test_export_cancelled_when_dialog_dismissed():
    assert md.export_mind(_FakeWindow(None)) == {"ok": False, "cancelled": True}


def test_export_without_window_reports_error():
    assert md.export_mind(None)["error"] == "no window"


def test_import_cancelled_when_dialog_dismissed():
    assert md.import_mind(_FakeWindow(None), post=lambda *a, **k: None) == {
        "ok": False,
        "cancelled": True,
    }


def test_import_without_window_reports_error():
    assert md.import_mind(None, post=lambda *a, **k: None)["error"] == "no window"


def test_import_reads_file_and_posts_bytes(tmp_path):
    # Read the chosen file, POST its bytes to the import endpoint, shape the response.
    archive = tmp_path / "incoming.orrindmind"
    archive.write_bytes(b"PK\x03\x04 pretend archive bytes")
    posted = {}

    class _Resp:
        status_code = 200

        def json(self):
            return {"restarting": True}

    def _post(path, content=None, headers=None):
        posted["path"] = path
        posted["content"] = content
        return _Resp()

    out = md.import_mind(_FakeWindow((str(archive),)), post=_post)
    assert posted["path"] == "/api/mind/import"
    assert posted["content"] == archive.read_bytes()  # exact bytes forwarded
    assert out["ok"] is True and out["restarting"] is True


def test_import_surfaces_refusal_status(tmp_path):
    archive = tmp_path / "foreign.orrindmind"
    archive.write_bytes(b"nope")

    class _Resp:
        status_code = 400

        def json(self):
            return {"detail": "foreign archive"}

    out = md.import_mind(_FakeWindow((str(archive),)), post=lambda *a, **k: _Resp())
    assert out["ok"] is False and out["status"] == 400 and out["detail"] == "foreign archive"
