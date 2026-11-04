# An isolated life (ORRIN_DATA_DIR set) must never write into the live brain/data.
#
# 2026-11-02: three smoke lives ran with ORRIN_DATA_DIR pointed at scratch dirs, but
# native_lm.py built its checkpoint path from its own file location. Each smoke life
# trained its own tokenizer, saw a vocab change, started the transformer fresh and
# saved it over the live native_lm.pt, so Run 14 was born at step 0 and Run 13's
# 23,931 steps were lost. llm_router's cost log and demand_expectations' file had the
# same bypass, though nothing had written to them yet.
#
# Two checks. The runtime one imports those modules in a fresh interpreter with
# ORRIN_DATA_DIR set and asserts every path they write is under it. The static one
# fails on any new module that builds a data path from __file__ outside an
# import-failure fallback, unless it is listed below with its reason.
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BRAIN = REPO / "brain"

# module → why reading <repo>/brain/data directly is right there
_ALLOWED = {
    "brain/think/think_utils/selection/catalog.py":
        "reads the committed capability manifest that ships with the code",
    "brain/cognition/planning/step_execution.py":
        "reads the committed capability manifest that ships with the code",
    "brain/control_signals/reward_signals/action_reward_ema.py":
        "legacy repo-root location, read once to migrate into DATA_DIR",
    "brain/scripts/clean_corrupted_memory.py":
        "an operator script run by hand against the live mind",
}

_SELF_DATA = re.compile(r'Path\(__file__\)[^#\n]*["\']data["\']')


def test_writers_follow_orrin_data_dir(tmp_path):
    iso = tmp_path / "iso_data"
    code = (
        "import json\n"
        "import brain.cognition.language.native_lm as n\n"
        "import brain.cognition.language.tokenizer as t\n"
        "import brain.utils.llm_router as r\n"
        "import brain.eval.demand_expectations as d\n"
        "print(json.dumps([str(n._CKPT), str(t._PATH), str(r._COST_LOG_PATH),"
        " str(d._EXPECTATIONS_FILE)]))\n"
    )
    env = {**os.environ, "ORRIN_DATA_DIR": str(iso)}
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env,
                         capture_output=True, text=True, check=True)
    paths = json.loads(out.stdout.strip().splitlines()[-1])
    for p in paths:
        assert Path(p).resolve().is_relative_to(iso.resolve()), p


def _in_fallback(lines: list[str], i: int) -> bool:
    """True when line i sits in an `except` block (the import-failure fallback
    every DATA_DIR user keeps for when brain.paths cannot load)."""
    indent = len(lines[i]) - len(lines[i].lstrip())
    for j in range(i - 1, max(-1, i - 8), -1):
        s = lines[j]
        if not s.strip():
            continue
        if len(s) - len(s.lstrip()) < indent:
            return s.lstrip().startswith("except")
    return False


def test_no_module_builds_data_paths_from_its_own_location():
    found = []
    for f in sorted(BRAIN.rglob("*.py")):
        rel = f.relative_to(REPO).as_posix()
        if rel.startswith("brain/data/") or rel in _ALLOWED:
            continue
        lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, line in enumerate(lines):
            if _SELF_DATA.search(line) and not line.lstrip().startswith("#") \
                    and not _in_fallback(lines, i):
                found.append(f"{rel}:{i + 1}: {line.strip()}")
    assert not found, ("data paths built from __file__ ignore ORRIN_DATA_DIR; use "
                       "brain.paths.DATA_DIR:\n" + "\n".join(found))
