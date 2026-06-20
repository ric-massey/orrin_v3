# brain/symbolic/symbolic_reflection.py
# Central symbolic reflection engine — runs before any LLM-based reflection.
# Attempts to answer reflective queries using local symbolic sources only.
from __future__ import annotations
from core.runtime_log import get_logger

from typing import Any, Dict, Optional

from utils.json_utils import load_json, save_json
from utils.log import log_activity
from brain.paths import DATA_DIR
from utils.failure_counter import record_failure
_log = get_logger(__name__)

REFLECTION_STATS_FILE = DATA_DIR / "reflection_stats.json"

_REFLECTION_TYPES = {"outcome", "self_belief", "conversation", "cognition_schedule", "meta", "rules", "emotion"}


# ─── Query builders ───────────────────────────────────────────────────────────

def _build_query(reflection_type: str, data: Any) -> str:
    # Boundary-safe truncation only: raw [:N] slices here cut through
    # [EXTERNAL/UNTRUSTED …] wrappers in memory-derived data, and the sliced
    # tag flowed back into working/long memory via crystallization queries
    # (FINDINGS 2026-06-12 data sweep §9).
    from utils.text_sanity import truncate_clean as _tc

    if reflection_type == "outcome":
        if isinstance(data, list) and data:
            labels = [str(d.get("label", d.get("outcome", ""))) for d in data[:5] if isinstance(d, dict)]
            return f"pattern analysis of recent outcomes: {', '.join(labels)}"
        return "analyze recent outcome patterns"

    if reflection_type == "self_belief":
        if isinstance(data, str) and data:
            return f"self belief assessment: {_tc(data, 120)}"
        return "evaluate symbolic self-model domain quality and rule health"

    if reflection_type == "conversation":
        if isinstance(data, list) and data:
            snippets = [_tc(str(d.get("content", d.get("text", ""))), 60) for d in data[:3] if isinstance(d, dict)]
            return f"conversation pattern: {'; '.join(snippets)}"
        if isinstance(data, str) and data:
            return f"conversation reflection: {_tc(data, 120)}"
        return "reflect on recent conversation patterns"

    if reflection_type == "cognition_schedule":
        if isinstance(data, str) and data:
            return f"cognition schedule review: {_tc(data, 120)}"
        return "review recent cognition schedule patterns"

    if reflection_type == "meta":
        return "highest priority symbolic self-improvement opportunities"

    if reflection_type == "rules":
        if isinstance(data, list) and data:
            snippets = [_tc(str(d), 60) for d in data[:4] if d]
            return f"rule effectiveness from recent outcomes: {'; '.join(snippets)}"
        return "assess which symbolic rules are effective or need revision"

    if reflection_type == "emotion":
        if isinstance(data, (list, dict)) and data:
            if isinstance(data, list):
                snippets = [_tc(str(d.get("emotion", d) if isinstance(d, dict) else d), 40) for d in data[:4] if d]
                return f"emotional pattern analysis: {', '.join(snippets)}"
            return f"reflect on emotional state: {_tc(str(data), 120)}"
        return "analyze recent emotional patterns and stability"

    return _tc(str(data), 120) if data else f"reflect on {reflection_type}"


# ─── Type-specific fallback builders ─────────────────────────────────────────

def _build_from_self_model(reflection_type: str, data: Any) -> Optional[Dict]:
    try:
        from symbolic.symbolic_self_model import get_symbolic_self_model
        model = get_symbolic_self_model()
    except Exception as e:
        log_activity(f"[sym_reflect] self_model load error: {e}")
        return None

    kd = model.get("knowledge_domains", {})
    weak  = model.get("weak_areas", [])
    strong = model.get("strong_areas", [])
    health = model.get("rule_health", {})

    if reflection_type == "self_belief":
        parts = []
        if strong:
            parts.append(f"Strong areas: {', '.join(strong)}")
        if weak:
            parts.append(f"Weak areas: {', '.join(weak)}")
        conf = health.get("mean_confidence", 0.0)
        parts.append(f"Mean rule confidence: {conf:.2f}")
        pending = health.get("pending_revisions", 0)
        if pending:
            parts.append(f"{pending} rules pending revision")
        if not parts:
            return None
        text = ". ".join(parts) + "."
        return {"text": text, "source": "symbolic_self_model", "confidence": 0.70}

    if reflection_type == "meta":
        # Find lowest-quality domain as top improvement target
        if not kd:
            return None
        worst = min(kd.items(), key=lambda x: x[1].get("quality", 1.0), default=None)
        if worst is None:
            return None
        domain, stats = worst
        quality = stats.get("quality", 0.0)
        rule_count = stats.get("rule_count", 0)
        text = (
            f"Highest priority improvement: {domain} domain (quality={quality:.2f}, "
            f"{rule_count} rules). "
            f"Active rules: {health.get('active_rules', 0)}, "
            f"mean confidence: {health.get('mean_confidence', 0):.2f}."
        )
        return {"text": text, "source": "symbolic_self_model", "confidence": 0.65}

    if reflection_type == "cognition_schedule":
        active = health.get("active_rules", 0)
        pending = health.get("pending_revisions", 0)
        text = (
            f"Cognition state: {active} active rules, "
            f"{pending} pending revisions, "
            f"mean confidence {health.get('mean_confidence', 0):.2f}."
        )
        return {"text": text, "source": "symbolic_self_model", "confidence": 0.60}

    if reflection_type == "rules":
        active = health.get("active_rules", 0)
        mean_conf = health.get("mean_confidence", 0.0)
        pending = health.get("pending_revisions", 0)
        if active == 0:
            return None
        low_conf = [d for d, s in kd.items() if s.get("quality", 1.0) < 0.50]
        high_conf = [d for d, s in kd.items() if s.get("quality", 1.0) >= 0.75]
        parts = [f"{active} active rules, mean confidence {mean_conf:.2f}"]
        if low_conf:
            parts.append(f"weak domains needing revision: {', '.join(low_conf)}")
        if high_conf:
            parts.append(f"reliable domains: {', '.join(high_conf)}")
        if pending:
            parts.append(f"{pending} rules pending revision")
        return {"text": ". ".join(parts) + ".", "source": "symbolic_self_model", "confidence": 0.65}

    if reflection_type == "emotion":
        # Check for emotion-related causal edges or rule domains
        emotion_domains = [d for d in kd if any(
            w in d.lower() for w in ("emotion", "affect", "feel", "mood", "exploration_drive", "motivation")
        )]
        if not emotion_domains and not weak and not strong:
            return None
        parts = []
        if emotion_domains:
            parts.append(f"Emotion-related domains: {', '.join(emotion_domains)}")
        if weak:
            parts.append(f"Weak areas: {', '.join(weak[:3])}")
        conf = health.get("mean_confidence", 0.0)
        parts.append(f"Overall symbolic confidence: {conf:.2f}")
        return {"text": ". ".join(parts) + ".", "source": "symbolic_self_model", "confidence": 0.55}

    return None


# ─── Core reflection engine ───────────────────────────────────────────────────

def symbolic_first_reflection(
    reflection_type: str,
    context: Optional[Dict] = None,
    data: Any = None,
) -> Optional[Dict]:
    """
    Attempt to produce a reflection result using only local symbolic sources.
    Returns {"text": str, "source": str, "confidence": float} or None.
    """
    if reflection_type not in _REFLECTION_TYPES:
        log_activity(f"[sym_reflect] Unknown reflection type: {reflection_type}")
        return None

    query = _build_query(reflection_type, data)
    ctx = context or {}
    result: Optional[Dict] = None

    # Stage 1: reasoning router
    try:
        from symbolic import reasoning_router
        routed = reasoning_router.route(query, context=ctx)
        if routed.get("resolved") and routed.get("answer") and routed.get("source") != "suppressed":
            result = {
                "text":       routed["answer"],
                "source":     f"router/{routed['source']}",
                "confidence": 0.75,
            }
    except Exception as e:
        log_activity(f"[sym_reflect] router error: {e}")

    # Stage 2: causal explanation (especially for outcome type)
    if result is None:
        try:
            from symbolic.causal_graph import causal_explanation
            causal = causal_explanation(query)
            if causal:
                result = {
                    "text":       causal,
                    "source":     "causal_graph",
                    "confidence": 0.68,
                }
        except Exception as e:
            log_activity(f"[sym_reflect] causal_graph error: {e}")

    # Stage 3: analogy engine for conversation type
    if result is None and reflection_type == "conversation":
        try:
            from symbolic.analogy_engine import best_analogue_answer
            analogy = best_analogue_answer(query)
            if analogy:
                result = {
                    "text":       analogy,
                    "source":     "analogy_engine",
                    "confidence": 0.62,
                }
        except Exception as e:
            log_activity(f"[sym_reflect] analogy_engine error: {e}")

    # Stage 4: self-model insight
    if result is None:
        result = _build_from_self_model(reflection_type, data)

    if result is None:
        _record_stat("llm")
        return None

    # Crystallize the symbolic result
    try:
        from symbolic.crystallization import crystallize
        crystallize(
            query,
            result["text"],
            outcome=0.70,
            caller=f"symbolic_reflection/{reflection_type}",
        )
    except Exception as e:
        log_activity(f"[sym_reflect] crystallize error: {e}")

    _record_stat("symbolic")
    log_activity(
        f"[sym_reflect] {reflection_type} resolved via {result['source']} "
        f"(conf={result['confidence']:.2f})"
    )
    return result


# ─── Summarise for WM injection ───────────────────────────────────────────────

def summarise_for_reflection(reflection_type: str, data: Any) -> str:
    """Return a short text summary of data suitable for working-memory injection."""
    if isinstance(data, str):
        return data[:200]

    if isinstance(data, list):
        if not data:
            return f"No {reflection_type} data available."
        if reflection_type == "outcome":
            labels = [
                str(d.get("label", d.get("outcome", d.get("score", ""))))
                for d in data[:5] if isinstance(d, dict)
            ]
            return f"Recent outcomes: {', '.join(str(l) for l in labels if l)}."
        snippets = [
            str(d.get("content", d.get("text", d.get("summary", ""))))[:60]
            for d in data[:3] if isinstance(d, dict)
        ]
        return "; ".join(s for s in snippets if s) or f"{len(data)} {reflection_type} entries."

    if isinstance(data, dict):
        return str(data)[:200]

    return f"Reflection on {reflection_type}."


# ─── Stats ───────────────────────────────────────────────────────────────────

def _record_stat(kind: str) -> None:
    """Increment symbolic or llm reflection counter."""
    try:
        stats = load_json(REFLECTION_STATS_FILE, default_type=dict)
        stats[kind] = stats.get(kind, 0) + 1
        save_json(REFLECTION_STATS_FILE, stats)
    except Exception as _e:
        record_failure("symbolic_reflection._record_stat", _e)


def get_reflection_stats() -> Dict:
    """Return counts of symbolic vs LLM reflections."""
    stats = load_json(REFLECTION_STATS_FILE, default_type=dict)
    symbolic = stats.get("symbolic", 0)
    llm = stats.get("llm", 0)
    total = symbolic + llm
    return {
        "symbolic": symbolic,
        "llm":      llm,
        "total":    total,
        "symbolic_ratio": round(symbolic / total, 3) if total else 0.0,
    }
