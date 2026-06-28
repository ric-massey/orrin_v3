# brain/cognition/search_own_files.py
# Cognitive function: Orrin searches his own data and source files for content
# relevant to his current goal or working memory thread.
#
# When selected by the bandit, it derives a search query from context (committed
# goal title, recent working memory, or user input), runs grep_files, and writes
# findings to working memory and long memory so future cycles can build on them.
from __future__ import annotations
from brain.cognition.global_workspace import bound_goal

from typing import Dict, Any, List

from brain.utils.log import log_activity, log_private
from brain.cog_memory.working_memory import update_working_memory
from brain.cog_memory.long_memory import update_long_memory


def _record_habituation(result_text: str, context: Dict[str, Any]) -> None:
    """Feed search_own_files's outcome into its explore/exploit habituation so a barren
    self-search self-suppresses the same way look_outward does (exploration_value)."""
    try:
        from brain.cognition.exploration_value import ReachOutcome, record_reach_outcome
        gain = record_reach_outcome("search_own_files", str(result_text), None, context)
        acted = bool(result_text and not str(result_text).lstrip().startswith(("❌", "⚠️")))
        context["_last_reach_outcome"] = ReachOutcome(
            "home", acted=acted, is_external=False, info_gain=gain,
            created_memory=acted, satisfied_curiosity=gain > 0.0,
            inner_fn="search_own_files", text=str(result_text or ""),
        )
    except (ImportError, TypeError, ValueError):  # best-effort habituation feed — never block the search
        pass


def search_own_files(context: Dict[str, Any] = None, query: str = "", **_) -> str:
    """
    Search Orrin's own files for content matching a derived or explicit query.

    Query derivation priority:
      1. Explicit `query` argument (if provided by selector/LLM)
      2. Committed goal title
      3. Latest user input (first 80 chars)
      4. Most recent substantive working memory entry
    """
    context = context or {}

    # Derive query if not explicitly given
    if not query:
        goal = bound_goal(context) or {}
        query = (goal.get("title") or goal.get("name") or "").strip()

    if not query:
        query = str(context.get("latest_user_input") or "").strip()[:80]

    if not query:
        wm = context.get("working_memory") or []
        for entry in reversed(wm[-8:]):
            text = entry if isinstance(entry, str) else (
                entry.get("content", "") if isinstance(entry, dict) else ""
            )
            text = str(text or "").strip()
            if len(text) > 15 and not text.startswith("[metacog]") and not text.startswith("🧠"):
                query = text[:80]
                break

    if not query:
        return "⚠️ No query could be derived from current context."

    try:
        from brain.agency.skills.grep_files import grep_files
    except ImportError:
        return "❌ grep_files skill not available."

    # Default search: data files first (memories, goals, state)
    result = grep_files({
        "query": query,
        "max_results": 20,
        "context_lines": 1,
    })

    if not result.get("success"):
        return f"❌ File search failed: {result.get('error', 'unknown error')}"

    matches: List[Dict[str, Any]] = result.get("matches", [])
    count = result.get("count", 0)

    if not matches:
        # Widen to source files if data search found nothing
        result2 = grep_files({
            "query": query,
            "root": ".",
            "file_pattern": "*.py",
            "max_results": 15,
            "context_lines": 1,
        })
        if result2.get("success"):
            matches = result2.get("matches", [])
            count = result2.get("count", 0)

    # Fix 4 (explore_loop_fix_plan.md) — record cross-call novelty so a goal that
    # keeps re-running the same search over a finite corpus is seen as making no
    # NEW progress. Feeds the satiety close (Fix 1) and the stall signature (Fix 3).
    # Recorded for BOTH outcomes: empty matches ⇒ a barren call (raises the streak).
    _goal_id = str((bound_goal(context) or {}).get("id")
                   or (bound_goal(context) or {}).get("title") or "")
    try:
        from brain.cognition import novelty_memory
        # Novelty unit = the FILE (area), not file:line. An exploration goal asks
        # "what's here?" — the answer is which files/areas exist, not line numbers.
        # File-level is also stable against Orrin's own constantly-growing log/memory
        # files: re-matching the same content at a NEW line number (because the log
        # grew) is NOT new exploration — but a new file:line registered as false
        # novelty and prevented the goal from ever reaching satiety (observed live).
        _files = sorted({str(m.get("file", "")).strip() for m in matches if m.get("file")})
        _nov = novelty_memory.observe(_goal_id, "search_own_files", _files)
    except Exception:
        _nov = None

    if not matches:
        msg = f"No results found for '{query}' in local files."
        update_working_memory({"content": f"I searched myself for '{query}' and found nothing.", "event_type": "search", "importance": 1, "priority": 1})
        _record_habituation(msg, context)
        return msg

    # A repeat search that surfaced nothing new: say so plainly rather than
    # re-reporting the same matches as if they were a fresh discovery.
    if _nov is not None and not _nov.get("novel", True):
        _msg = (f"I searched myself for '{query}' again and found nothing new "
                f"(this corner of me feels exhausted for now).")
        _record_habituation(_msg, context)
        return _msg

    # Translate file paths to felt spatial locations — Orrin knows WHERE in himself
    # something lives without knowing the file coordinate.
    try:
        from brain.cognition.perception.file_sense import path_to_felt_location, is_self_path, summarise_locations
        _use_felt = True
    except Exception:
        _use_felt = False

    # Build felt summary for working memory
    if _use_felt:
        felt_lines = []
        seen_locations = {}  # location → list of text snippets
        for m in matches[:8]:
            fpath = m.get("file", "")
            self_path = is_self_path(fpath)
            location = path_to_felt_location(fpath, is_self=self_path)
            text = (m.get("text") or "").strip()[:120]
            if location not in seen_locations:
                seen_locations[location] = []
            seen_locations[location].append(text)

        all_paths = [m.get("file", "") for m in matches[:8]]
        where = summarise_locations(all_paths)

        felt_lines.append(f"I found something in {where} that relates to '{query}':")
        for location, snippets in list(seen_locations.items())[:4]:
            felt_lines.append(f"  In {location}: {snippets[0]}")
        if count > 5:
            felt_lines.append(f"  (and {count - 5} more traces)")

        summary = "\n".join(felt_lines)
    else:
        summary_lines = [f"Found {count} result(s) for '{query}':"]
        for m in matches[:5]:
            summary_lines.append(f"  {m['file']}:{m['line']} — {m['text'][:120]}")
        summary = "\n".join(summary_lines)

    update_working_memory({
        "content": summary,
        "event_type": "file_search_result",
        "importance": 3,
        "priority": 2,
    })

    # Long memory gets the raw paths (internal audit trail — not shown to Orrin's LLM)
    long_summary = f"[file_search] Query: '{query}' — {count} match(es). Top: " + "; ".join(
        f"{m['file']}:{m['line']}" for m in matches[:3]
    )
    update_long_memory(
        long_summary,
        emotion="exploration_drive",
        event_type="file_search",
        importance=2,
        context=context,
    )

    log_activity(f"[search_own_files] '{query}' → {count} matches")
    log_private("[search_own_files] raw: " + "; ".join(f"{m['file']}:{m['line']}" for m in matches[:5]))
    _record_habituation(summary, context)
    return summary
