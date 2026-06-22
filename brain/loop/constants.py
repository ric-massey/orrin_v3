"""Shared cognitive-loop constants (Phase 4A).

Lives in its own module so both the loop entrypoint and the extracted
brain/loop/* stages can import it without a circular dependency.
"""
from __future__ import annotations

# Functions that engage Orrin with his environment rather than pure internal computation.
# Clark (1997) embodied cognition; Lave (1988) situated action.
# Used by the outward-debt counter below and by finalize.py's satisfaction scorer.
_OUTWARD_FNS: frozenset[str] = frozenset({
    "look_outward", "look_around", "leave_note", "write_desktop_note",
    "survey_environment", "read_clipboard", "announce_to_dashboard",
    "seek_novelty", "pursue_committed_goal", "write_cognitive_function",
    "write_tool", "wikipedia_search", "read_rss", "research_topic",
    "fetch_and_read", "search_own_files", "grep_files", "check_user_presence",
    "save_note", "notify_user",
})
