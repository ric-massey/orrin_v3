# agency/skills/save_note.py
from __future__ import annotations

from datetime import datetime, timezone
from utils.log import log_activity, log_error
from brain.paths import DATA_DIR


def save_note(args=None, **kwargs) -> dict:
    """
    Save a timestamped note to data/notes/.
    args: str content, or dict with 'content' and optional 'title'.
    Returns {"success": bool, "path": str}
    """
    if isinstance(args, dict):
        kwargs.update(args)
        args = None

    content = str(args or kwargs.get("content") or kwargs.get("text") or "")
    if not content.strip():
        return {"success": False, "error": "No content to save"}

    title = str(kwargs.get("title", "note")).strip().replace(" ", "_").replace("/", "-")[:40]
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    filename = f"{ts}_{title}.txt"

    notes_dir = DATA_DIR / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    file_path = notes_dir / filename

    try:
        header = f"[{datetime.now(timezone.utc).isoformat()}]\n"
        file_path.write_text(header + content, encoding="utf-8")
        log_activity(f"Note saved: {filename}")
        return {"success": True, "path": str(file_path), "filename": filename}
    except Exception as e:
        log_error(f"save_note failed: {e}")
        return {"success": False, "error": str(e)}
