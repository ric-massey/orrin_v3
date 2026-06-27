# brain/utils/json_extract.py
#
# JSON extraction + healing for json_utils.py (CODEBASE_CLEANUP_PLAN 4.5C),
# lifted verbatim to bring that module under the 600-line soft limit. Pulls a
# valid JSON value out of messy/LLM-produced text: plausibility gating, first
# JSON fragment isolation, bracket/quote healing, and a top-level-object salvage
# pass, all logged when they miss. json_utils.py re-imports extract_json (+ the
# helpers) so its 200+ importers and the safe_extract_json wrapper are unchanged.
from __future__ import annotations

import json
import logging
import re
from typing import Optional, Union

from brain.core.runtime_log import get_logger
from brain.utils.log import log_model_issue

_log = get_logger(__name__)

# ------------------------------
# JSON extraction (healing)
# ------------------------------

def extract_json(text: str) -> Optional[Union[dict, list]]:
    """
    Best-effort extraction of the first JSON object/array from messy LLM output.
    Order:
      1) ```json fenced block
      2) generic ``` fenced block
      3) first JSON fragment via scanner (try parse → heal → salvage-top-level-object)
      4) whole text heal → salvage-top-level-object
    Returns dict/list, else None.
    """
    try:
        s = text if isinstance(text, str) else str(text)

        # Fast reject: bail before the heal/salvage chain unless the text contains
        # a PLAUSIBLE JSON start — an opening brace/bracket actually followed by a
        # JSON token, not just a stray bracket from prose. Symbolic-gate output
        # like "[analogy/GENERAL] Similar situation…" has a "[" but no real JSON;
        # without this it churned through every heal/salvage step and (previously)
        # logged a DEBUG line per attempt, flooding the runtime log.
        if not _has_plausible_json_start(s):
            return None

        # NOTE: each json.loads below is a SPECULATIVE attempt in a try→heal→
        # salvage chain. Failures are expected control flow — the function returns
        # None gracefully and callers handle None — so the per-attempt failures are
        # swallowed silently (no per-attempt logging). Only a genuine *unexpected*
        # exception (outer except) is surfaced, once, via log_model_issue.
        # 1) fenced with json
        m = re.search(r"```(?:json|JSON)\s*([\s\S]*?)\s*```", s)
        if m:
            snippet = m.group(1).strip()
            try:
                return json.loads(snippet)
            except json.JSONDecodeError:
                pass
            healed = _heal_json_fragment(snippet)
            try:
                return json.loads(healed)
            except Exception:
                salv = _salvage_top_level_object(snippet)
                if salv:
                    try:
                        return json.loads(salv)
                    except json.JSONDecodeError:  # expected: speculative parse in heal chain
                        pass

        # 2) any fenced block
        m = re.search(r"```+\s*([\s\S]*?)\s*```+", s)
        if m:
            snippet = m.group(1).strip()
            try:
                return json.loads(snippet)
            except json.JSONDecodeError:
                healed = _heal_json_fragment(snippet)
                try:
                    return json.loads(healed)
                except Exception:
                    salv = _salvage_top_level_object(snippet)
                    if salv:
                        try:
                            return json.loads(salv)
                        except json.JSONDecodeError:  # expected: speculative parse in heal chain
                            pass

        # 3) scan for top-level {...} or [...]
        frag = _first_json_fragment(s)
        if frag:
            try:
                return json.loads(frag)
            except json.JSONDecodeError:
                pass
            healed = _heal_json_fragment(frag)
            try:
                return json.loads(healed)
            except json.JSONDecodeError:  # expected: speculative parse in heal chain
                pass
            # salvage top-level object specifically (handles cut off like "..., \"emerging_conflicts\": [")
            salv = _salvage_top_level_object(frag)
            if salv:
                try:
                    return json.loads(salv)
                except json.JSONDecodeError:  # expected: speculative parse in salvage chain
                    pass

        # 4) whole text attempts
        healed_all = _heal_json_fragment(s)
        try:
            return json.loads(healed_all)
        except json.JSONDecodeError:  # expected: speculative parse in heal chain
            pass

        salv_all = _salvage_top_level_object(s)
        if salv_all:
            try:
                return json.loads(salv_all)
            except json.JSONDecodeError:  # expected: speculative parse in salvage chain
                pass

    except Exception as e:
        preview = s if len(s) <= 600 else (s[:300] + " ... " + s[-200:])
        log_model_issue(f"[extract_json] Failed: {e}\nRaw: {preview}")

    return None


# Characters that can legitimately follow "[" as the first token of a JSON array:
# another container, a string, a number, true/false/null, or an empty array.
_JSON_ARRAY_VALUE_START = frozenset('{["-tfn]0123456789')


def _has_plausible_json_start(s: str) -> bool:
    """True if `s` contains an opening "{" or "[" that is actually followed by a
    JSON token — not just a stray bracket inside prose. Scans every bracket (not
    only the first) so mixed content like 'note: {"x": 1}' still parses, while
    prose like '[analogy/GENERAL] …' or '[metacog] thinking' is rejected cheaply.
    """
    if not s:
        return False
    for mt in re.finditer(r"[\{\[]", s):
        i = mt.start()
        # next non-whitespace char after the bracket
        j = i + 1
        n = len(s)
        while j < n and s[j] in " \t\r\n":
            j += 1
        if j >= n:
            continue
        nxt = s[j]
        if s[i] == "{":
            # object: a key string, or an empty object
            if nxt == '"' or nxt == "}":
                return True
        else:
            # array: any JSON value start, or an empty array
            if nxt in _JSON_ARRAY_VALUE_START:
                return True
    return False


def _first_json_fragment(s: str) -> Optional[str]:
    """Return the first candidate JSON {...} or [...] substring (may be unbalanced if truncated)."""
    i_obj, i_arr = s.find("{"), s.find("[")
    starts = [i for i in (i_obj, i_arr) if i != -1]
    if not starts:
        return None
    start = min(starts)

    open_ch = s[start]
    close_ch = "}" if open_ch == "{" else "]"
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch and depth > 0:
            depth -= 1
            if depth == 0:
                return s[start:i+1]
    # unbalanced (truncated) → return tail so we can heal it
    return s[start:]


def _heal_json_fragment(frag: str) -> str:
    """
    Light repairs for slightly invalid/truncated JSON:
    - remove trailing commas before } or ]
    - close open string
    - balance unmatched braces/brackets
    """
    t = frag.rstrip()
    t = t.replace(",}", "}").replace(",]", "]")

    in_str = False
    esc = False
    depth_obj = 0
    depth_arr = 0
    for ch in t:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth_obj += 1
            elif ch == "}":
                depth_obj = max(0, depth_obj - 1)
            elif ch == "[":
                depth_arr += 1
            elif ch == "]":
                depth_arr = max(0, depth_arr - 1)

    if in_str:
        t += '"'
    t += "}" * depth_obj
    t += "]" * depth_arr
    t = t.replace(",}", "}").replace(",]", "]")
    return t


def _salvage_top_level_object(text: str) -> Optional[str]:
    """
    Try to salvage a valid top-level JSON *object* from truncated text:
    - Find first '{'
    - Walk tracking quotes/escapes and nesting
    - If we close level 0, return slice
    - If truncated inside the object, cut at the last comma at level==1 and append '}'.
      If that fails, append enough '}' to close remaining depth.
    """
    s = text
    start = s.find("{")
    if start == -1:
        return None

    level = 0
    in_str = False
    esc = False
    last_top_level_comma: Optional[int] = None

    i = start
    while i < len(s):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                level += 1
            elif ch == "}":
                if level > 0:
                    level -= 1
                    if level == 0:
                        return s[start:i+1]
            elif ch == "," and level == 1:
                last_top_level_comma = i
        i += 1

    # Truncated before closing: try cutting at last full top-level pair
    if last_top_level_comma is not None:
        candidate = s[start:last_top_level_comma] + "}"
        try:
            json.loads(candidate)
            return candidate
        except Exception as _e:
            _log_salvage_miss(_e, s)

    # Blindly close remaining braces
    if level > 0:
        candidate = s[start:] + ("}" * level)
        try:
            json.loads(candidate)
            return candidate
        except Exception as _e:
            _log_salvage_miss(_e, s)

    return None


def _log_salvage_miss(exc: Exception, snippet: str) -> None:
    """A salvage attempt that still fails to parse is EXPECTED control flow in
    the try→heal→salvage chain (see extract_json's NOTE) — so it logs at DEBUG,
    not WARNING. Previously these two sites logged a bare WARNING ~38×/minute
    with neither the failing snippet nor the caller, making the source of the
    transient parse failure unidentifiable (RUN_ISSUES_2026-06-10 §secondary).
    With debug logging on, the snippet head + nearest non-json_utils caller are
    included so the producer can finally be traced."""
    if not _log.isEnabledFor(logging.DEBUG):
        return
    caller = "?"
    try:
        import inspect
        for frame in inspect.stack()[2:8]:
            fname = frame.filename
            if "json_utils" not in fname:
                caller = f"{fname.rsplit('/', 1)[-1]}:{frame.lineno} ({frame.function})"
                break
    except Exception:  # intentional: caller introspection is best-effort debug detail
        caller = "?"
    _log.debug("salvage failed: %s | caller=%s | snippet=%r", exc, caller, snippet[:160])
