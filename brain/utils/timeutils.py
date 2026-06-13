from __future__ import annotations

from datetime import datetime, timezone


def now_iso_z() -> str:
    """Return the current UTC time as ISO-8601 with a Z suffix, e.g. '2024-01-15T12:34:56.789123Z'."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
