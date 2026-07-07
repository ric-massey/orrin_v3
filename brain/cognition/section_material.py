# brain/cognition/section_material.py
#
# Source material for a long-form section — F1 (2026-07-05 findings).
#
# compose_section is grounded-or-failed: a section is drafted FROM real stores
# — credited ledger artifacts (bodies via the effect_artifacts sidecar),
# long-memory findings, and learned causal edges on the goal's topic — and an
# empty pool is a legitimate step failure ("nothing to synthesize"), never a
# template. Lives in cognition (not agency) because it reads the causal graph:
# symbolic → agency already exists for effect recording, so an agency →
# symbolic import would close a package cycle.
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple

from brain.agency.effect_ledger import MIN_ARTIFACT_CHARS
from brain.utils.failure_counter import record_failure

# How many source snippets a section needs before drafting is even attempted.
# One snippet is a quote, not a synthesis; the findings gate ("nothing to
# synthesize" is a legitimate failure) starts at two.
MIN_MATERIAL = 2
MAX_MATERIAL = 6

_STOP = frozenset({
    "that", "this", "with", "have", "what", "your", "about", "they", "them",
    "from", "would", "could", "there", "their", "thing", "understand",
    "into", "know", "written", "turn", "synthesis", "section", "write",
})

# (label, body, content_hash) — hash empty for non-ledger sources.
Material = Tuple[str, str, str]


def _tokens(text: str) -> set:
    return {w for w in re.findall(r"[a-z]{4,}", str(text or "").lower())
            if w not in _STOP}


def _ledger_material(toks: set) -> List[Material]:
    """Recent credited prose effects overlapping the topic, newest first.
    Bodies resolve through the effect_artifacts sidecar (the ledger itself is
    content-addressed)."""
    out: List[Material] = []
    try:
        from brain.agency import effect_ledger as _el
        from brain.agency.effect_artifacts import load as _load_artifact
        rows: List[Dict[str, Any]] = []
        with open(_el.EFFECT_LEDGER_FILE, "r", encoding="utf-8") as fh:
            for line in fh.readlines()[-400:]:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if isinstance(r, dict) and not r.get("dedupe") \
                        and r.get("kind") in ("note_novel", "tool_run_effect",
                                              "file_write", "message_answered"):
                    rows.append(r)
        for r in reversed(rows):
            h = str(r.get("content_hash") or "")
            body = _load_artifact(h) or ""
            if len(body) < MIN_ARTIFACT_CHARS:
                continue
            if toks and not (toks & _tokens(body[:1500])):
                continue
            label = f"{r.get('kind')} ({str(r.get('ts', ''))[:10]})"
            out.append((label, body[:1500].strip(), h))
            if len(out) >= MAX_MATERIAL:
                break
    except OSError:
        pass
    except Exception as exc:
        record_failure("section_material.ledger", exc)
    return out


def _memory_material(toks: set, limit: int) -> List[Material]:
    """Substantive long-memory findings overlapping the topic (no hash — these
    are memories, not ledger artifacts)."""
    out: List[Material] = []
    if limit <= 0:
        return out
    try:
        from brain.paths import LONG_MEMORY_FILE
        from brain.utils.json_utils import load_json
        mem = load_json(LONG_MEMORY_FILE, default_type=list) or []
        for e in reversed(list(mem)[-120:]):
            text = str((e.get("content") if isinstance(e, dict) else e) or "").strip()
            if len(text) < 80 or text.startswith("[Goal pursuit]"):
                continue
            if toks and not (toks & _tokens(text)):
                continue
            out.append(("long memory", text[:800], ""))
            if len(out) >= limit:
                break
    except Exception as exc:
        record_failure("section_material.memory", exc)
    return out


def _causal_material(toks: set, limit: int) -> List[Material]:
    """Learned causal edges whose cause/effect text overlaps the topic."""
    out: List[Material] = []
    if limit <= 0:
        return out
    try:
        from brain.symbolic.causal_graph import get_all_edges
        for e in get_all_edges():
            if not isinstance(e, dict):
                continue
            cause, effect = str(e.get("cause", "")), str(e.get("effect", ""))
            if toks and not (toks & _tokens(cause + " " + effect)):
                continue
            score = float(e.get("causal_score", 0) or 0)
            if score <= 0.2:
                continue
            out.append(("causal model",
                        f"I've observed that {cause[:120]} tends to lead to "
                        f"{effect[:120]} (confidence {score:.2f}).", ""))
            if len(out) >= limit:
                break
    except Exception as exc:
        record_failure("section_material.causal", exc)
    return out


def gather_material(goal: Dict[str, Any], section: str) -> List[Material]:
    """Real source material for this section, best-first: credited artifacts,
    then memory findings, then causal edges. Empty pool = nothing to synthesize."""
    topic = f"{goal.get('title') or goal.get('name') or ''} {section} " \
            f"{' '.join(map(str, (goal.get('grounded_parts') or [])[:3]))}"
    toks = _tokens(topic)
    material = _ledger_material(toks)
    material += _memory_material(toks, MAX_MATERIAL - len(material))
    material += _causal_material(toks, MAX_MATERIAL - len(material))
    return material[:MAX_MATERIAL]
