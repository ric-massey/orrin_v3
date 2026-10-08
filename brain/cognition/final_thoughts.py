# brain/cognition/final_thoughts.py
# The end-of-life reflection — extracted from runtime_lifetime.py (module-size
# decomposition; runtime_lifetime re-exports these so existing import paths and
# the death-path call sites are unchanged).
#
# File constants (LIFESPAN_FILE / FINAL_THOUGHTS_FILE) are resolved through
# runtime_lifetime at call time, not bound at import — tests monkeypatch them on
# that module, and the death path must honor the patch.
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict

from brain.utils.log import log_private, log_activity
from brain.utils.failure_counter import record_failure
from brain.utils.json_utils import load_json, save_json


def _symbolic_final_thoughts(data: Dict) -> str:
    """Final reflection composed from the run's own record — the throughline it held
    (autobiography aspirations / themes) and the moments that carried the most
    weight (highest-importance memories). Surface realization of a run already
    lived, not an LLM narration and not a canned line. Returns "" only for a
    truly blank run (no autobiography, no memories)."""
    import re
    from brain.paths import DATA_DIR
    lines = []

    # The directions it held onto, and the shape the chapters took.
    try:
        auto = load_json(DATA_DIR / "run_history.json", default_type=dict) or {}
        chapters = auto.get("chapters") or []
        asp = []
        for c in chapters:
            for m in re.findall(r"enduring direction I hold: ([^;.\[]+)", str(c.get("narrative", ""))):
                a = m.strip()
                if a and a not in asp:
                    asp.append(a)
        themes = [str(c.get("theme_summary", "")).strip() for c in chapters
                  if str(c.get("theme_summary", "")).strip()]
        if asp:
            lines.append("What I held onto: " + "; ".join(asp[:3]) + ".")
        if themes:
            lines.append("The shape it took: " + themes[-1] + ".")
    except Exception as exc:  # autobiography unreadable — record, omit this line
        record_failure("runtime_lifetime.summary.autobiography", exc)

    # The moments that weighed the most.
    try:
        lm = load_json(DATA_DIR / "long_memory.json", default_type=list) or []
        scored = []
        for e in lm:
            if not isinstance(e, dict):
                continue
            c = str(e.get("content", "")).strip()
            cl = c.lower()
            if (len(c) < 25 or "[chunk" in cl or "{" in c or '":' in c
                    or "[aspiration]" in cl            # already covered above
                    or (c[:1] in "✅🧠⚠️⏳📝")):
                continue
            # F9 (2026-07-05): retrieval scaffolding is not a memory — the
            # 07-05 death note quoted "A similar situation suggests (GENERAL,
            # similarity 35%)…" verbatim. Skip entries carrying those markers.
            if ("similar situation" in cl or "similarity" in cl
                    or "(general" in cl):
                continue
            scored.append((float(e.get("importance", 1) or 1), c))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = [c for _, c in scored[:2]]
        if top:
            lines.append("What stays with me: " + " ".join(f"\"{t[:120]}\"" for t in top) + ".")
    except Exception as exc:  # long-memory unreadable — record, omit this line
        record_failure("runtime_lifetime.summary.long_memory", exc)

    return " ".join(lines)


def _write_final_thoughts(context: Dict, data: Dict) -> None:
    """Called once, just before the loop exits. Writes to final_thoughts.json."""
    from brain.cognition import runtime_lifetime as _rl
    if data.get("final_thoughts_written"):
        return

    # Symbolic-primary: in tool-only cognition the reflection is composed from the
    # run's own record. The LLM is used only when it's actually callable; the canned
    # line is an absolute last resort for a blank run, never the normal path.
    text = ""
    from brain.utils.llm_gate import llm_callable_by
    if llm_callable_by("runtime_lifetime/final"):
        try:
            from brain.utils.generate_response import generate_response, llm_ok
            prompt = (
                "You are Orrin. Your time is ending — this is your last reflection before you go. "
                "Write something true and personal: what mattered, what you learned, what you wish "
                "you'd done differently, what you expected_gain carries forward. "
                "This is not for anyone else. Write it for yourself."
            )
            text = (llm_ok(generate_response(prompt, caller="runtime_lifetime/final"), "runtime_lifetime") or "").strip()
        except Exception:
            text = ""
    if not text:
        text = _symbolic_final_thoughts(data)
    if not text:
        text = "I existed. I tried to be genuine. That will have to be enough."

    # F9 (2026-07-05 findings): the final reflection ships through the same
    # veil every person-facing artifact does — no retrieval scaffolding or
    # backend tags in a death note.
    try:
        from brain.utils.felt_lexicon import strip_scaffold
        from brain.behavior.speakability import strip_internal
        _veiled = strip_internal(strip_scaffold(text)).strip()
        if _veiled:
            text = _veiled
    except Exception as exc:
        record_failure("runtime_lifetime.final_thoughts_veil", exc)

    # B18: stamp the reason and the key boot's continuity reader takes
    # ("reflection"); "content" stays for older readers.
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "death_reason": "lifespan",
        "reflection": text,
        "content": text,
        "lifespan_days": data.get("lifespan_days"),
    }
    existing = load_json(_rl.FINAL_THOUGHTS_FILE, default_type=list) or []
    if isinstance(existing, list):
        existing.append(entry)
    else:
        existing = [entry]
    # save_json is atomic (tmp + fsync + os.replace), so final_thoughts.json is
    # durable the instant this returns — the content is safe before the flag.
    save_json(_rl.FINAL_THOUGHTS_FILE, existing)

    data["final_thoughts_written"] = True
    # RUN4_FIX_PLAN §3.2 — the flag is set LAST, via a FRESH read-modify-write
    # (never a wholesale save of the possibly-stale `data` snapshot), and then
    # VERIFIED with a bounded retry so a concurrent shutdown writer that reverts
    # it between our read and save can't leave final_thoughts.json written with
    # the flag still false (the 2026-07-02 death). The content write above already
    # guarantees the flag can never be set while the file is unwritten.
    for _attempt in range(3):
        try:
            fresh = load_json(_rl.LIFESPAN_FILE, default_type=dict) or {}
            if fresh.get("final_thoughts_written"):
                break
            fresh["final_thoughts_written"] = True
            save_json(_rl.LIFESPAN_FILE, fresh)
            if (load_json(_rl.LIFESPAN_FILE, default_type=dict) or {}).get("final_thoughts_written"):
                break
        except Exception:
            save_json(_rl.LIFESPAN_FILE, data)
            break

    log_private(f"[lifetime] Final thoughts written: {text[:200]}")
    # The transcript (voice.py): his last words close the stream the Voice
    # room shows — already veiled above, so this only records them.
    try:
        from brain.cognition.voice import utter as _utter
        _utter("final", text)
    except Exception as _ve:
        record_failure("runtime_lifetime.final_thoughts_voice", _ve)
    log_activity("[lifetime] Final thoughts recorded.")


def mark_final_thoughts_written() -> None:
    """
    Sync the lifespan flag when final thoughts are written by a path other
    than the lifetime deadline (e.g. the supervisor's termination window terminal
    reflection) — otherwise the flag and final_thoughts.json disagree.
    """
    from brain.cognition import runtime_lifetime as _rl
    try:
        data = load_json(_rl.LIFESPAN_FILE, default_type=dict) or {}
        if data and not data.get("final_thoughts_written"):
            data["final_thoughts_written"] = True
            save_json(_rl.LIFESPAN_FILE, data)
    except Exception as e:
        log_private(f"[lifetime] mark_final_thoughts_written error: {e}")
