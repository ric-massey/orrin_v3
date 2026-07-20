# brain/cognition/unexpected_link.py
#
# D2 (Run 11 §5, CREATIVITY_NOVELTY Issue A) — "find an unexpected link" as its
# own selectable, separately-rewarded act. The similarity engine keeps serving
# "use memory to solve problems"; THIS act pays for distance: it seeds from a
# recent memory, asks the analogy engine's distant-connection mode for a
# surface-far / relation-sharing partner, and writes the link as a durable
# artifact. Reward arrives through the normal effect-ledger economy (novelty
# pricing applies), so creative connection earns cycles on its own merit and a
# link-stamping loop extinguishes itself economically. Symbolic-only — no LLM.
from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from brain.paths import LONG_MEMORY_FILE
from brain.utils.json_utils import load_json
from brain.utils.failure_counter import record_failure

# How far back the seed pool reaches. Recent enough to be live concerns, deep
# enough that the pool isn't the same three thoughts every pull.
_SEED_POOL = 40
_MIN_SEED_WORDS = 6


def _seed_candidates() -> List[Dict[str, Any]]:
    raw = load_json(LONG_MEMORY_FILE, default_type=list) or []
    pool = [
        e for e in raw[-_SEED_POOL:]
        if isinstance(e, dict) and len(str(e.get("content", "")).split()) >= _MIN_SEED_WORDS
    ]
    return pool


def find_unexpected_link(context: Optional[Dict[str, Any]] = None) -> str:
    """Pick a recent memory, find a surface-distant memory sharing an abstract
    relation with it, and record the bridge as an artifact. Returns prose, or
    "" when no genuine link exists this cycle (no fabrication on empty)."""
    context = context or {}
    try:
        from brain.symbolic.analogy_engine import find_distant_connections
    except Exception as exc:
        record_failure("unexpected_link.import", exc)
        return ""

    pool = _seed_candidates()
    random.shuffle(pool)
    seed: Optional[Dict[str, Any]] = None
    links: List[Dict[str, Any]] = []
    for cand in pool[:8]:   # a few tries, not a scan of the whole store
        found = find_distant_connections(str(cand.get("content", "")), top_n=1)
        if found:
            seed, links = cand, found
            break
    if seed is None or not links:
        return ""

    link = links[0]
    relations = ", ".join(link.get("shared_relations", [])) or "a shared relation"
    seed_text = str(seed.get("content", "")).strip()
    partner_text = str(link.get("content", "")).strip()
    prose = (
        f"Unexpected link ({relations}): \"{seed_text[:180]}\" connects to "
        f"\"{partner_text[:180]}\" — almost no shared vocabulary "
        f"(surface {link.get('surface')}), but both carry the same {relations} "
        f"structure. Worth asking what one situation predicts about the other."
    )

    try:
        from brain.cog_memory.working_memory import update_working_memory
        update_working_memory(prose, event_type="unexpected_link", importance=2)
    except Exception as exc:
        record_failure("unexpected_link.working_memory", exc)
    try:
        from brain.agency.effect_ledger import record_effect
        record_effect(
            "symbolic_artifact", prose,
            metadata={"connection": "distant", "relations": link.get("shared_relations", [])},
        )
    except Exception as exc:
        record_failure("unexpected_link.effect", exc)
    return prose
