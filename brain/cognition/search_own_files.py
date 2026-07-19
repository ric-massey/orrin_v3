# brain/cognition/search_own_files.py
# Cognitive function: Orrin searches his own data and source files for content
# relevant to his current goal or working memory thread.
#
# When selected by the bandit, it derives a search query from context (committed
# goal title, recent working memory, or user input), runs grep_files, and writes
# findings to working memory and long memory so future cycles can build on them.
from __future__ import annotations
from brain.cognition.global_workspace import bound_goal

import re
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

    # M4 (Run 11 §2) — BEHAVIORAL introspection. This function used to grep
    # Orrin's data + source files; with the anatomy membrane (M1/M2/M3) the
    # reasoning layer reads behavior, not blueprints: what he REMEMBERS, what
    # tends to PRECEDE what (learned causal history), what keeps FAILING, and
    # what he himself WROTE (the diary exception). Same felt output, honest diet.
    terms = [w for w in re.findall(r"[a-z0-9_]+", query.lower()) if len(w) > 2]
    findings: List[Dict[str, Any]] = []   # {kind, key, text}

    # 1. Memories — his own past, through the memory system.
    try:
        from brain.paths import LONG_MEMORY_FILE
        from brain.utils.json_utils import load_json
        for i, entry in enumerate(reversed(load_json(LONG_MEMORY_FILE, default_type=list) or [])):
            if len([f for f in findings if f["kind"] == "memory"]) >= 6:
                break
            text = str(entry.get("content", "") if isinstance(entry, dict) else entry)
            low = text.lower()
            if terms and sum(1 for t in terms if t in low) >= max(1, len(terms) // 2):
                findings.append({"kind": "memory", "key": f"mem:{hash(text) & 0xffffffff:x}",
                                 "text": text.strip()[:160]})
    except Exception as _me:
        log_private(f"[search_own_files] memory read failed: {_me}")

    # 2. Learned causal history — what tends to bring what about, from lived
    # evidence (the M4 target for "trace what drives X" introspection goals).
    try:
        from brain.symbolic.causal_graph import get_all_edges
        for e in get_all_edges():
            if len([f for f in findings if f["kind"] == "pattern"]) >= 4:
                break
            cause, effect = str(e.get("cause", "")), str(e.get("effect", ""))
            blob = f"{cause} {effect}".lower()
            if terms and any(t in blob for t in terms):
                seen = int(e.get("evidence_count", e.get("count", 1)) or 1)
                findings.append({
                    "kind": "pattern", "key": f"edge:{cause[:30]}->{effect[:30]}",
                    "text": f"in my experience, '{cause[:60]}' tends to lead to "
                            f"'{effect[:60]}' (seen {seen}×)"})
    except Exception as _ce:
        log_private(f"[search_own_files] causal read failed: {_ce}")

    # 3. Failure history — where I keep stumbling (counts, not transcripts).
    try:
        from brain.utils.failure_counter import get_summary
        for site, data in (get_summary() or {}).items():   # already count-desc
            if len([f for f in findings if f["kind"] == "stumble"]) >= 3:
                break
            n = int((data or {}).get("count", 0) or 0) if isinstance(data, dict) else int(data or 0)
            if terms and any(t in str(site).lower() for t in terms):
                findings.append({"kind": "stumble", "key": f"fail:{site}",
                                 "text": f"'{site}' has failed on me {n}×"})
    except Exception as _fe:
        log_private(f"[search_own_files] failure read failed: {_fe}")

    # 4. Diary — things I authored (credited effect bodies); membrane-exempt.
    try:
        from brain.agency.skills.grep_files import grep_files
        from brain.paths import DATA_DIR
        _diary = grep_files({"query": re.escape(query[:60]), "max_results": 5,
                             "root": str(DATA_DIR / "effect_artifacts"),
                             "file_pattern": "*.txt", "context_lines": 0})
        for m in (_diary.get("matches") or [])[:3]:
            findings.append({"kind": "diary", "key": f"diary:{m.get('file', '')}",
                             "text": str(m.get("text", "")).strip()[:160]})
    except Exception as _de:
        log_private(f"[search_own_files] diary read failed: {_de}")

    # Fix 4 (explore_loop_fix_plan.md) — record cross-call novelty so a goal that
    # keeps re-running the same search over a finite corpus is seen as making no
    # NEW progress. Novelty unit = the evidence KEY (memory/edge/site), the
    # behavioral analogue of the old file-level unit.
    _goal_id = str((bound_goal(context) or {}).get("id")
                   or (bound_goal(context) or {}).get("title") or "")
    try:
        from brain.cognition import novelty_memory
        _nov = novelty_memory.observe(_goal_id, "search_own_files",
                                      sorted({f["key"] for f in findings}))
    except Exception:
        _nov = None

    count = len(findings)
    if not findings:
        msg = f"I searched my memory and history for '{query}' and found nothing."
        update_working_memory({"content": msg, "event_type": "search",
                               "importance": 1, "priority": 1})
        _record_habituation(msg, context)
        return msg

    # A repeat search that surfaced nothing new: say so plainly rather than
    # re-reporting the same findings as if they were a fresh discovery.
    if _nov is not None and not _nov.get("novel", True):
        _msg = (f"I searched myself for '{query}' again and found nothing new "
                f"(this corner of me feels exhausted for now).")
        _record_habituation(_msg, context)
        return _msg

    _KIND_FELT = {"memory": "something I remember", "pattern": "a pattern in my own history",
                  "stumble": "a place I keep stumbling", "diary": "a note I once wrote"}
    felt_lines = [f"Looking into myself about '{query}':"]
    for f in findings[:6]:
        felt_lines.append(f"  {_KIND_FELT.get(f['kind'], 'a trace')}: {f['text']}")
    if count > 6:
        felt_lines.append(f"  (and {count - 6} more traces)")
    summary = "\n".join(felt_lines)

    update_working_memory({
        "content": summary,
        "event_type": "file_search_result",
        "importance": 3,
        "priority": 2,
    })

    # Long memory gets the evidence keys (internal audit trail).
    long_summary = f"[self_search] Query: '{query}' — {count} finding(s). Top: " + "; ".join(
        f["key"] for f in findings[:3]
    )
    update_long_memory(
        long_summary,
        emotion="exploration_drive",
        event_type="file_search",
        importance=2,
        context=context,
    )

    log_activity(f"[search_own_files] '{query}' → {count} behavioral findings")
    log_private("[search_own_files] raw: " + "; ".join(f["key"] for f in findings[:5]))
    _record_habituation(summary, context)
    return summary
