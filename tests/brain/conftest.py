"""Fixtures shared by tests/brain."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def restore_session_data(tmp_path):
    """The adapter wipes DATA_DIR on every call; give the rest of the session its
    shared data dir back afterwards."""
    import shutil
    from brain.paths import DATA_DIR
    keep = tmp_path / "data_snapshot"
    if Path(DATA_DIR).exists():
        shutil.copytree(DATA_DIR, keep)
    yield
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    if keep.exists():
        shutil.copytree(keep, DATA_DIR)
