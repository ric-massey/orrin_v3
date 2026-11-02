"""The registry leak (2026-11-02): every public function in a brain.cognition
module became a selectable cognitive function, so the pool was half plumbing and
Run 13 spent 35 picks on cpu_count. Only declared cognition is selectable now
(selection/candidates._is_declared_cognition)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import brain
from tests.brain.test_e5_harness import restore_session_data  # noqa: F401 — fixture

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "run13"
HELPERS = ["cpu_count", "cadence_multiplier", "heavy_cycle_frequency", "budget_bytes",
           "record_failure", "rebirth_if_elapsed", "mark_final_thoughts_written",
           "bound_goal", "rung", "life_status", "mark_consequential_cognition"]


@pytest.fixture
def real_pool(restore_session_data):
    from brain.think.think_utils.selection.candidates import _load_action_defs
    from brain.paths import COGNITIVE_FUNCTIONS_LIST_FILE
    _load_action_defs()  # the registry persists its own list on load; replace it after
    shutil.copy(Path(brain.__file__).parent / "data" / "cognitive_functions.json",
                COGNITIVE_FUNCTIONS_LIST_FILE)
    return set(_load_action_defs()[0])


def test_helpers_are_not_selectable(real_pool):
    assert not set(HELPERS) & real_pool


def test_every_genuine_run13_pick_stays_selectable(real_pool):
    picked = set(json.loads((FIX / "picked_functions.json").read_text()))
    lost = picked - real_pool
    assert lost == {"cpu_count", "cadence_multiplier", "heavy_cycle_frequency"}, sorted(lost)


def test_declared_without_description_names_are_real():
    from brain.think.think_utils.selection.candidates import _DECLARED_WITHOUT_DESCRIPTION
    from brain.registry.cognition_registry import COGNITIVE_FUNCTIONS
    listed = {e["name"] for e in json.loads(
        (Path(brain.__file__).parent / "data" / "cognitive_functions.json").read_text())
        if isinstance(e, dict)}
    stale = {n for n in _DECLARED_WITHOUT_DESCRIPTION if n not in COGNITIVE_FUNCTIONS and n not in listed}
    assert not stale, stale


def test_authored_functions_are_selectable(monkeypatch):
    from brain.think.think_utils.selection import candidates as c
    from brain.registry import cognition_registry as reg
    monkeypatch.setitem(reg.COGNITIVE_FUNCTIONS, "orrin_wrote_this",
                        {"function": lambda context=None: "ok", "authored": True})
    monkeypatch.setitem(reg.COGNITIVE_FUNCTIONS, "helper_nobody_declared",
                        {"function": lambda context=None: 1})
    assert c._is_declared_cognition("orrin_wrote_this")
    assert not c._is_declared_cognition("helper_nobody_declared")


def test_fails_open_when_the_manifest_cannot_be_read(monkeypatch, tmp_path):
    from brain.think.think_utils.selection import candidates as c
    from brain.think.think_utils.selection import catalog
    monkeypatch.setitem(c._declared_cache, "names", None)
    monkeypatch.setattr(catalog, "_CAPS_PATH", tmp_path / "missing.json")
    assert c._is_declared_cognition("cpu_count")
