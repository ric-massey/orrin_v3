# Originality veto on exemplar promotion (quality_standard/originality.py).
#
# The veto is a deterministic gate on ONE property — how copied an artifact is —
# NOT a quality judgment. These tests pin the property, not "goodness".
from __future__ import annotations

from brain.cognition.quality_standard import originality as O


def test_raw_fetch_provenance_is_vetoed():
    """A memo whose footer declares source: fetch_and_read is a raw web dump —
    the exact Run 9 pathology (a pasted PLOS abstract promoted as an exemplar)."""
    text = (
        "# Research memo: Some Article\n\n"
        "Some Article | Journal Authors Metrics Abstract " + ("blah " * 200) + "\n\n"
        "(read from: https://example.org/article)\n\n"
        "---\nsource: fetch_and_read\n"
    )
    derivative, reason, rep = O.check(text)
    assert derivative
    assert reason == "raw_fetch_dump"
    assert rep.raw_fetch and rep.provenance == "fetch_and_read"


def test_offline_stitch_header_is_vetoed():
    """The offline research fallback stamps a self-declaring header and stitches
    verbatim source excerpts into fenced blocks."""
    text = (
        "# Title\n\n"
        "*(Offline synthesis fallback: stitched key excerpts. Provide your own LLM.)*\n\n"
        "## Key excerpts\n- **[1] src**\n\n```\n" + ("copied text " * 50) + "\n```\n"
    )
    derivative, reason, _ = O.check(text)
    assert derivative
    assert reason == "offline_synthesis_stitch"


def test_mostly_quoted_is_vetoed():
    """Even without a provenance marker, a memo that is majority verbatim quoted
    blocks is too copied to auto-canonise."""
    authored = "# Memo\n\nHere is one short original sentence about the topic.\n\n"
    quoted = "```\n" + ("quoted source material " * 120) + "\n```\n"
    derivative, reason, rep = O.check(authored + quoted)
    assert derivative
    assert reason.startswith("quoted_material_")
    assert rep.quote_ratio >= 0.5


def test_authored_synthesis_passes():
    """A genuine synthesis memo (research_topic provenance, real prose, no dominant
    quoting) is NOT vetoed — the veto must not block real authored work."""
    body = (
        "This memo works through the question directly. " +
        "It states a claim, gives the reasoning behind it, and notes one consequence "
        "that follows for what to do next. " * 20
    )
    text = f"# Research memo: A Real Question\n\n{body}\n\n---\nsource: research_topic\n"
    derivative, reason, rep = O.check(text)
    assert not derivative, f"authored synthesis wrongly vetoed: {reason} {rep}"
    assert reason == "authored"


def test_no_sources_fails_open():
    """Absence of captured source docs must never trigger the verbatim veto —
    only PRESENCE with high overlap can. (goal_id resolves to nothing here.)"""
    text = f"# Memo\n\n{'genuine original analysis here. ' * 40}\n\n---\nsource: research_topic\n"
    derivative, reason, rep = O.check(text, goal_id="does-not-exist")
    assert not derivative
    assert rep.sources_found == 0
