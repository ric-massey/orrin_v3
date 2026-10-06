"""scripts/site_update.py: the progress-note writer for the Orrin page. Pure parts
only — publishing touches git and the live site, so it is exercised by hand."""
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "site_update", Path(__file__).resolve().parents[1] / "scripts" / "site_update.py")
assert _spec and _spec.loader
su = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(su)

SRC = """// header
window.ORRIN_UPDATES = [
  {
    date: "2026-10-04",
    kind: "build",
    title: "older",
    body: "older body",
  },
];
"""


def test_insert_puts_new_entry_first():
    e = su.make_entry("run result", "Run 13", "It ran.  Twice\nover.", when="2026-10-06")
    out = su.insert_entry(SRC, e)
    assert out.index('"Run 13"') < out.index('"older"')
    assert 'body: "It ran. Twice over.",' in out          # whitespace folded to one line
    assert out.count("window.ORRIN_UPDATES = [") == 1


def test_quotes_are_escaped_as_js_strings():
    e = su.make_entry("note", 'He said "hi"', "x", when="2026-10-06")
    assert 'title: "He said \\"hi\\"",' in su.insert_entry(SRC, e)


@pytest.mark.parametrize("kw", [
    {"kind": "rumour"},
    {"title": "  "},
    {"body": "<b>bold</b>"},
    {"href": "https://example.com/x"},
])
def test_bad_entries_refused(kw):
    args = {"kind": "note", "title": "t", "body": "b", "href": None} | kw
    with pytest.raises(ValueError):
        su.make_entry(args["kind"], args["title"], args["body"], args["href"])


def test_missing_marker_refused():
    with pytest.raises(ValueError):
        su.insert_entry("window.SOMETHING_ELSE = [];", su.make_entry("note", "t", "b"))
