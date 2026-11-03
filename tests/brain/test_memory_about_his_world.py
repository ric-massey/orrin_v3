"""Memory about his world (2026-11-02, after smoke life 3).

Smoke life 3's long memory was 43 % working-memory summaries, every one of them
commentary on his own state, and B3's 10 % self-log share was only enforced at
prune time (a full store). Commentary is no longer promoted, and the share holds
whenever a summary is written."""
from __future__ import annotations

import json

import pytest

from brain.utils.self_commentary import is_self_commentary

# The three templates that filled smoke life 3's summaries, as written.
SHADOW = {"content": "🌓 Shadow question: What would I sacrifice to achieve this?", "event_type": "self_query"}
DOMINANT = {"content": "Strongly defined dominant emotion: motivation (0.91)", "event_type": "dominant_affect"}
FLAT = {"content": "I've been running hot and flat — drive, curiosity all pinned high", "event_type": "affect_stagnation"}
CHUNK = {"content": "[Chunk: Strongly defined dominant emotion: motivation (0.91) | ...]", "event_type": "chunk"}
RESEARCH = {"content": "[research] eternalism: Eternalism is an ontological view …", "event_type": "world_perception"}
THOUGHT = {"content": "Ric said the bridge on the river trail is closed this week.", "event_type": "chunk"}


@pytest.mark.parametrize("e", [SHADOW, DOMINANT, FLAT, CHUNK])
def test_his_commentary_on_himself_is_recognised(e):
    assert is_self_commentary(e)


@pytest.mark.parametrize("e", [RESEARCH, THOUGHT])
def test_the_world_is_not(e):
    assert not is_self_commentary(e)


def test_only_world_entries_reach_the_summary(monkeypatch):
    import brain.cog_memory.working_memory as wm
    from brain.paths import WORKING_MEMORY_FILE
    WORKING_MEMORY_FILE.write_text("[]")
    promoted = []
    monkeypatch.setattr(wm, "summarize_and_promote_working_memory", lambda ms: promoted.extend(ms))
    # Chunking merges similar entries instead of evicting them; this test is about
    # what the salience gate lets through on eviction, so chunking is off.
    monkeypatch.setattr(wm, "_chunk_two_most_similar", lambda ms: False)
    for i in range(20):  # overflow the cap; every entry "referenced", as recall makes them
        for e in (SHADOW, DOMINANT, FLAT, RESEARCH):
            wm.update_working_memory(dict(e, content=f"{e['content']} {i}", referenced=1))
    assert promoted, "the research entries should still be promoted"
    assert not any(is_self_commentary(m) for m in promoted)


def test_summary_share_is_held_at_write_time(tmp_path, monkeypatch):
    import brain.cog_memory.long_memory as lm
    from brain.cog_memory.summarize_w_memory import summarize_and_promote_working_memory
    f = tmp_path / "long_memory.json"
    monkeypatch.setattr(lm, "LONG_MEMORY_FILE", f)
    rows = [{"content": f"[research] fact {i}", "event_type": "world_perception"} for i in range(9)]
    rows.append({"content": "📝 Working memory summary: x", "event_type": "summary"})
    f.write_text(json.dumps(rows))
    summarize_and_promote_working_memory([dict(RESEARCH, referenced=1)])
    assert len(json.loads(f.read_text())) == 10, "a second summary would be 2 of 11"
    f.write_text(json.dumps(rows[:9] * 3 + rows[9:]))
    summarize_and_promote_working_memory([dict(RESEARCH, referenced=1)])
    assert len(json.loads(f.read_text())) == 29
