# brain/cognition/planning/satiety_note.py
#
# RUN4_FIX_PLAN §B3 — the "what I learned" note that makes a satiety refusal
# PRODUCTIVE instead of terminal. Extracted from goal_outcomes.py (which is at
# the module-size soft limit) as its own bottom-up leaf; goal_outcomes imports
# write_learned_note from here.
#
# A read-heavy "understand X" goal records no ledger effect, so it could never
# satiety-close (19 refusals / 0 closures across three runs). On the first
# refusal we write down what was learned about the topic through the effect
# ledger — the note IS the qualifying effect, so the close then completes
# legitimately. A goal that genuinely learned nothing writes no note (the
# ledger's own MIN_ARTIFACT_CHARS / novelty gates reject it) and the refusal
# stands honestly.
from __future__ import annotations

from typing import Any, Dict, List, Optional

from brain.utils.json_utils import load_json
from brain.utils.log import log_activity
from brain.utils.failure_counter import record_failure
from brain.paths import LONG_MEMORY_FILE

_STRIP_PREFIXES = ("understand ", "follow-up on ", "open question:",
                   "the causes of ", "pick up my thread on ")


def write_learned_note(goal: Dict[str, Any], context: Optional[Dict[str, Any]]) -> bool:
    """Produce a "here's what I learned" note from the goal's topic and record it
    through the effect ledger. Returns True only when a NOVEL, substantive effect
    was actually credited."""
    try:
        title = str(goal.get("title") or goal.get("name") or "").strip()
        gid = str(goal.get("id") or goal.get("title") or "")
        if not gid:
            return False
        topic = title
        for pfx in _STRIP_PREFIXES:
            if topic.lower().startswith(pfx):
                topic = topic[len(pfx):]
                break
        topic = topic.strip(" :?.").strip()
        toks = {w.lower() for w in topic.split() if len(w) > 3}
        learned: List[str] = []
        ctx = context or {}
        for entry in reversed((ctx.get("working_memory") or [])[-40:]):
            text = entry.get("content") if isinstance(entry, dict) else entry
            text = str(text or "").strip()
            if len(text) > 30 and (not toks or any(t in text.lower() for t in toks)):
                learned.append(text)
            if len(learned) >= 6:
                break
        if len(learned) < 2:
            try:
                mem = load_json(LONG_MEMORY_FILE, default_type=list) or []
            except Exception:
                mem = []
            for entry in reversed(list(mem)[-60:]):
                text = entry.get("content") if isinstance(entry, dict) else entry
                text = str(text or "").strip()
                if len(text) > 30 and (not toks or any(t in text.lower() for t in toks)):
                    learned.append(text)
                if len(learned) >= 6:
                    break
        if len(learned) < 2:
            return False   # genuinely nothing to write down — refusal stands
        note = (f"What I learned about {topic or title}:\n\n"
                + "\n".join(f"- {s[:400]}" for s in learned[:6]))
        from brain.agency.effect_ledger import record_effect
        row = record_effect("note_novel", note, goal_id=gid, context=ctx,
                            metadata={"source": "satiety_learned_note", "topic": topic})
        if row is not None:
            log_activity(f"[goals] Wrote a 'what I learned' note for "
                         f"{title[:50]!r} — satiety close can now complete legitimately.")
            return True
        return False
    except Exception as _e:
        record_failure("goals.write_learned_note", _e)
        return False
