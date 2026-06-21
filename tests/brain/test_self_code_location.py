# C3 (DESKTOP_APP_PLAN §10.1): Orrin's self-written code is STATE, not program.
# It must land in the writable per-user data tree (<data dir>/self_code/...), never
# the read-only program folder, with the manifest storing paths RELATIVE to that
# tree so a mind round-trips across machines on export/restore.
#
# These run under conftest's ORRIN_DATA_DIR isolation, so SELF_CODE_DIR resolves to
# the per-session tmp dir; the live-state tripwire additionally guarantees nothing
# here touches brain/data.
from pathlib import Path

import brain.paths as paths
import brain.agency.code_writer as code_writer
from brain.agency import self_code
from brain.core.manager import load_custom_cognition


def test_written_function_lands_in_writable_tree_not_program_folder():
    r = code_writer.write_cognitive_function(
        "reflect_on_unit", "unit-test fn", "return 'ok'", test=False
    )
    assert r["success"], r
    fp = Path(r["path"])
    # Inside the writable self-code tree …
    assert fp.parent == self_code.SELF_COGNITION_DIR
    assert paths.SELF_CODE_DIR in fp.resolve().parents
    # … and NOT in the read-only program folder.
    program_copy = paths.ROOT_DIR / "cognition" / "custom_cognition" / fp.name
    assert not program_copy.exists()


def test_manifest_path_is_relative_and_round_trips():
    code_writer.write_cognitive_function(
        "reflect_on_rel", "rel-path fn", "return 1", test=False
    )
    entries = self_code.load_manifest()
    entry = next(e for e in entries if e["name"] == "reflect_on_rel")
    assert not Path(entry["path"]).is_absolute()
    assert entry["path"] == "custom_cognition/reflect_on_rel.py"
    # The relative entry resolves back to the on-disk file.
    assert self_code.abs_path(entry).exists()


def test_startup_loader_picks_up_self_written_function():
    code_writer.write_cognitive_function(
        "reflect_on_boot", "boot-load fn", "return 2", test=False
    )
    fns = load_custom_cognition()
    assert "reflect_on_boot" in fns
    assert callable(fns["reflect_on_boot"])


def test_written_tool_lands_in_writable_skills_dir():
    t = code_writer.write_tool("unit_tool", "unit tool", "return 1", test=False)
    assert t["success"], t
    assert Path(t["path"]).parent == self_code.SELF_SKILLS_DIR


def test_delete_resolves_relative_entry_and_removes_file():
    code_writer.write_cognitive_function(
        "reflect_on_del", "del fn", "return 3", test=False
    )
    fp = self_code.SELF_COGNITION_DIR / "reflect_on_del.py"
    assert fp.exists()
    d = code_writer.delete_own_code("reflect_on_del")
    assert d["success"], d
    assert not fp.exists()
    assert all(e["name"] != "reflect_on_del" for e in self_code.load_manifest())


# ── Phase 3 tail: self-written code is normalized onto the brain.* namespace, so it
# resolves with only the repo root on sys.path (no legacy brain/ path affordance).
def test_normalize_rewrites_bare_first_party_imports_onto_brain():
    src = (
        "from utils.log import log_activity\n"
        "from cog_memory.working_memory import update_working_memory\n"
        "import cognition.foo\n"
        "from paths import WORKING_MEMORY_FILE\n"
    )
    out = self_code.normalize_self_code_imports(src)
    assert "from brain.utils.log import log_activity" in out
    assert "from brain.cog_memory.working_memory import update_working_memory" in out
    assert "import brain.cognition.foo" in out
    assert "from brain.paths import WORKING_MEMORY_FILE" in out
    # idempotent: a second pass changes nothing
    assert self_code.normalize_self_code_imports(out) == out


def test_normalize_leaves_stdlib_thirdparty_and_brain_imports_untouched():
    src = (
        "import os, json, requests\n"
        "from brain.utils.log import log_activity\n"
        "from datetime import datetime\n"
        "    from utils.json_utils import load_json\n"  # indented stays rewritten
    )
    out = self_code.normalize_self_code_imports(src)
    assert "import os, json, requests" in out
    assert "from brain.utils.log import log_activity" in out
    assert "from datetime import datetime" in out
    assert "    from brain.utils.json_utils import load_json" in out


def test_written_function_imports_resolve_without_brain_on_syspath():
    # The generated module must import live under the dedicated namespace with only
    # the repo root present — which is exactly what the suite runs with (pytest
    # pythonpath = .). A successful hot-registration proves its brain.* imports load.
    r = code_writer.write_cognitive_function(
        "reflect_on_imports", "import-resolution fn", "return 'ok'", test=False
    )
    assert r["success"], r
    body = (self_code.SELF_COGNITION_DIR / "reflect_on_imports.py").read_text()
    assert "from brain.cog_memory.working_memory import" in body
    assert "from brain.utils.log import" in body
    # no bare first-party import survived into the written file
    assert "\nfrom utils." not in body and "\nfrom cog_memory." not in body
