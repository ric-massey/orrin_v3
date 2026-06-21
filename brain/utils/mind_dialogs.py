"""
utils/mind_dialogs.py — native Save/Open dialog handlers for Mind export/import
over the pywebview bridge (E7, §9.6).

Binary can't ride the bridge's text REST proxy, so the whole transfer runs in
Python: a native file dialog picks the path and the archive bytes never cross into
JS. These live next to mind_archive (not in the bridge) so they're unit-testable
without importing the full FastAPI app — backend/server/bridge.py is a thin
delegator. They mirror the browser path's endpoints exactly, so the
safety-snapshot-first and refuse-foreign-archive guarantees are identical.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict

_FILE_TYPES = ("Orrin mind (*.orrindmind)", "All files (*.*)")


def _chosen_path(result: Any) -> Any:
    """create_file_dialog returns a sequence (OPEN) or a string/sequence (SAVE);
    normalize to the single path, or None if the dialog was dismissed."""
    if isinstance(result, (list, tuple)):
        return result[0] if result else None
    return result


def export_mind(window: Any) -> Dict[str, Any]:
    """Native Save dialog → write the full mind archive to the chosen path."""
    if window is None:
        return {"ok": False, "error": "no window"}
    try:
        import webview
        from brain.utils import mind_archive as _ma
        result = window.create_file_dialog(
            webview.FileDialog.SAVE,
            save_filename=_ma.export_filename(),
            file_types=_FILE_TYPES,
        )
        path = _chosen_path(result)
        if not path:
            return {"ok": False, "cancelled": True}
        Path(path).write_bytes(_ma.export_bytes())
        return {"ok": True, "path": str(path)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def import_mind(window: Any, post: Callable[..., Any]) -> Dict[str, Any]:
    """Native Open dialog → restore the mind from the chosen archive. The bytes stay
    in Python and go through the same /api/mind/import endpoint (safety copy first,
    foreign/newer archive refused, then restart). `post` is the in-process client's
    POST (so authorization rides the loopback identity)."""
    if window is None:
        return {"ok": False, "error": "no window"}
    try:
        import webview
        result = window.create_file_dialog(
            webview.FileDialog.OPEN,
            allow_multiple=False,
            file_types=_FILE_TYPES,
        )
        path = _chosen_path(result)
        if not path:
            return {"ok": False, "cancelled": True}
        data = Path(path).read_bytes()
        resp = post(
            "/api/mind/import", content=data,
            headers={"Content-Type": "application/octet-stream"},
        )
        try:
            payload = resp.json()
        except Exception:
            payload = {"detail": resp.text}
        out: Dict[str, Any] = {"ok": resp.status_code < 400, "status": resp.status_code}
        if isinstance(payload, dict):
            out.update(payload)
        return out
    except Exception as e:
        return {"ok": False, "error": str(e)}
