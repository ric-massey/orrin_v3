"""The exemplar leak (2026-11-02): smoke life 4, running in scratch dirs, promoted an
incubation-babble note into the committed golden set
(tests/fixtures/quality_golden/exemplars/), and it was swept into a commit."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from brain import paths

JUNK = (Path(__file__).resolve().parents[1] / "fixtures" / "smoke4" / "junk_incubation_exemplar.md").read_text()


def test_an_isolated_life_does_not_write_the_committed_set():
    # the suite runs with ORRIN_DATA_DIR set (conftest), exactly like a smoke life
    assert os.environ.get("ORRIN_DATA_DIR")
    assert paths.QUALITY_EXEMPLARS_WRITE_DIR != paths.QUALITY_EXEMPLARS_DIR
    assert paths.DATA_DIR in paths.QUALITY_EXEMPLARS_WRITE_DIR.parents


def test_readers_see_this_lifes_promotions_too():
    assert paths.exemplar_dirs() == [paths.QUALITY_EXEMPLARS_DIR, paths.QUALITY_EXEMPLARS_WRITE_DIR]


def test_a_life_in_place_still_promotes_into_the_committed_set(monkeypatch):
    monkeypatch.setattr(paths, "QUALITY_EXEMPLARS_WRITE_DIR", paths.QUALITY_EXEMPLARS_DIR)
    assert paths.exemplar_dirs() == [paths.QUALITY_EXEMPLARS_DIR]


def test_the_smoke4_note_is_refused_as_self_talk():
    from brain.cognition.quality_standard.originality import is_self_talk
    talk, why = is_self_talk(JUNK)
    assert talk, why


def test_tags_match_in_any_case_but_the_research_wrapper_is_not_a_tag():
    from brain.utils.text_sanity import internal_marks
    assert internal_marks("- [Incubation] While sitting with: something")
    assert internal_marks("[Chunk: something]")
    assert not internal_marks("[research] eternalism: [EXTERNAL/UNTRUSTED source=web] Eternalism is")


@pytest.mark.parametrize("p", sorted((paths.QUALITY_EXEMPLARS_DIR).glob("*.md")), ids=lambda p: p.name)
def test_no_committed_exemplar_is_self_talk(p):
    from brain.cognition.quality_standard.originality import is_self_talk
    assert not is_self_talk(p.read_text())[0]
