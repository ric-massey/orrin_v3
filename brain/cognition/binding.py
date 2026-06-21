"""Pre-workspace symbolic feature binding.

The binding stage adds bounded, unified situation candidates to the Global
Workspace competition. It never removes atomic candidates or declares anything
conscious; composites must win the existing salience competition.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from brain.cognition.global_workspace import _is_noise, _overlap, _tokens
from brain.utils.failure_counter import record_failure

MAX_ITEMS = 12
MAX_CLUSTER = 5
MAX_COMPOSITES = 3
LEXICAL_THRESHOLD = 0.34
COHERENCE_BONUS = 0.06
MAX_COHERENCE_BONUS = 0.18
ENTITY_BONUS = 0.05

_MOTION_WORDS = frozenset({
    "approach", "approaches", "approaching", "arrive", "arrives", "arriving",
    "move", "moves", "moving", "walk", "walks", "walking", "run", "runs",
    "running", "leave", "leaves", "leaving", "fall", "falls", "falling",
    "rise", "rises", "rising", "change", "changes", "changed", "changing",
    "open", "opens", "opened", "close", "closes", "closed", "pressing",
})


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return str(value or "").strip()


def _known_entities() -> Set[str]:
    try:
        from brain.cognition.world_model import _load_symbolic_model

        model = _load_symbolic_model()
        entities = model.get("entities") or {}
        return {str(key).lower() for key in entities} if isinstance(entities, dict) else set()
    except Exception as exc:
        record_failure("binding.known_entities", exc)
        return set()


def _entities_of(text: str, known_entities: Optional[Iterable[str]] = None) -> Set[str]:
    try:
        from brain.cognition.world_model import extract_entity_names

        return set(extract_entity_names(text, known_entities))
    except Exception as exc:
        record_failure("binding.entities_of", exc)
        return set()


def _item(
    source: str,
    content: str,
    salience: float,
    *,
    raw: Optional[Dict[str, Any]] = None,
    known_entities: Optional[Iterable[str]] = None,
    **metadata: Any,
) -> Optional[Dict[str, Any]]:
    content = _text(content)[:200]
    if not content or _is_noise(content):
        return None
    known = {str(value).lower() for value in known_entities or ()}
    entities = _entities_of(content, known)
    item = {
        "source": source[:48],
        "content": content,
        "salience": _f(salience),
        "tokens": _tokens(content),
        "entities": entities,
        "known_entities": entities & known,
        "raw": raw or {},
    }
    item.update(metadata)
    return item


def _dominant_affect(context: Dict[str, Any]) -> Optional[Tuple[str, float, str]]:
    state = context.get("affect_state") or {}
    core = state.get("core_signals") or state
    if not isinstance(core, dict):
        return None
    # core_signals mixes felt emotions with control/appraisal gauges (confidence,
    # resource_deficit, activation_level, …). Without this filter the argmax can
    # bind a NON-emotion as "a strong sense of <x>" and feed it to the appraisal/
    # hijack links, which key off the emotion name. Use the one canonical set.
    try:
        from brain.affect.apply_affective_feedback import NON_EMOTION_SIGNALS as _skip
    except Exception:
        _skip = frozenset()
    numeric = {
        str(k): _f(v) for k, v in core.items()
        if isinstance(v, (int, float)) and str(k) not in _skip
    }
    if not numeric:
        return None
    emotion = max(numeric, key=numeric.get)
    intensity = numeric[emotion]
    if intensity < 0.5:
        return None

    cause = ""
    causes = state.get("recent_emotion_causes") or []
    for entry in reversed(causes[-20:] if isinstance(causes, list) else []):
        if isinstance(entry, dict) and entry.get("emotion") == emotion:
            cause = _text(entry.get("cause")).replace("[appraisal] ", "", 1)
            break
    return emotion, intensity, cause


def _collect_items(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    known = _known_entities()
    items: List[Dict[str, Any]] = []

    def add(item: Optional[Dict[str, Any]]) -> None:
        if item is not None and len(items) < MAX_ITEMS:
            items.append(item)

    user_input = _text(context.get("latest_user_input"))
    if user_input:
        add(_item(
            "user", f'Ric said: "{user_input[:160]}"', 0.95,
            known_entities=known, role_hint="interlocutor", dedupe_text=user_input.lower(),
        ))

    dominant = _dominant_affect(context)
    if dominant:
        emotion, intensity, cause = dominant
        add(_item(
            "affect", f"a strong sense of {emotion.replace('_', ' ')}",
            0.40 + 0.40 * intensity, known_entities=known,
            role_hint="affect", emotion=emotion, intensity=intensity,
            appraisal_cause=cause,
        ))

    for signal in (context.get("top_signals") or [])[:3]:
        if not isinstance(signal, dict):
            continue
        content = _text(signal.get("content") or signal.get("summary"))
        tags = signal.get("tags") or []
        tags = [str(tag) for tag in tags] if isinstance(tags, list) else [str(tags)]
        # latest_user_input and its routed user signal are one datum, not two
        # independent facets; counting both creates a false coherence bonus.
        if user_input and "user_input" in tags and content.lower() == user_input.lower():
            continue
        add(_item(
            "signal", content,
            0.30 + 0.50 * _f(signal.get("signal_strength"), 0.4),
            raw=signal, known_entities=known, tags=tags,
            routing_target=_text(signal.get("routing_target")),
            role_hint="affect" if signal.get("_hijack") else "event",
            hijack_emotion=(tags[-1] if signal.get("_hijack") and tags else None),
        ))

    goal = context.get("committed_goal")
    if isinstance(goal, dict):
        title = _text(goal.get("title") or goal.get("name"))
        if title:
            add(_item(
                "goal", f"working toward: {title}", 0.55, raw=goal,
                known_entities=known, role_hint="goal", goal_title=title,
            ))

    action = context.get("last_function_chosen") or context.get("last_function")
    if action:
        add(_item(
            "action", f"just chose to {_text(action).replace('_', ' ')}", 0.45,
            known_entities=known, role_hint="event",
        ))

    for entry in reversed((context.get("working_memory") or [])[-8:]):
        content = _text(entry.get("content", entry) if isinstance(entry, dict) else entry)
        if len(content) < 20 or _is_noise(content):
            continue
        source = "subconscious" if isinstance(entry, dict) and (
            entry.get("source") == "subconscious"
            or entry.get("event_type") in {"subconscious_pattern", "incubated_insight", "emotional_residue"}
        ) else "thought"
        add(_item(
            source, content, 0.35, raw=entry if isinstance(entry, dict) else None,
            known_entities=known, role_hint="memory",
        ))
        break

    for offer in (context.get("_workspace_offers") or []):
        if not isinstance(offer, dict) or not offer.get("content"):
            continue
        add(_item(
            _text(offer.get("source") or "monitor"), _text(offer.get("content")),
            _f(offer.get("salience"), 0.5), raw=offer, known_entities=known,
            role_hint="event", exempt_habituation=bool(offer.get("exempt_habituation")),
        ))

    return items[:MAX_ITEMS]


def _goal_link(goal: Dict[str, Any], other: Dict[str, Any]) -> bool:
    if goal["source"] != "goal":
        goal, other = other, goal
    if goal["source"] != "goal":
        return False
    tags = {str(tag).lower() for tag in other.get("tags") or []}
    return bool(
        goal["tokens"] & other["tokens"]
        or tags & {"goal", "committed_goal", "objective", "plan", "stagnation_signal"}
    )


def _appraisal_link(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    affect, other = (a, b) if a["source"] == "affect" else (b, a)
    if affect["source"] != "affect":
        return False
    cause = _text(affect.get("appraisal_cause"))
    return bool(cause and (
        _overlap(cause, other["content"]) >= 0.22
        or cause.lower() in other["content"].lower()
        or other["content"].lower() in cause.lower()
    ))


def _hijack_link(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    affect, signal = (a, b) if a["source"] == "affect" else (b, a)
    if affect["source"] != "affect" or signal["source"] != "signal":
        return False
    return bool(
        signal.get("hijack_emotion")
        and signal.get("hijack_emotion") == affect.get("emotion")
    )


def _link(a: Dict[str, Any], b: Dict[str, Any]) -> Set[str]:
    reasons: Set[str] = set()
    for entity in sorted(a["entities"] & b["entities"]):
        reasons.add(f"entity:{entity}")
    if _overlap(a["content"], b["content"]) >= LEXICAL_THRESHOLD:
        reasons.add("lexical")
    if _appraisal_link(a, b):
        reasons.add("appraisal_cause")
    if _hijack_link(a, b):
        reasons.add("affect_hijack")
    if _goal_link(a, b):
        reasons.add("goal_relevance")
    return reasons


def _components(
    items: List[Dict[str, Any]],
    links: Dict[Tuple[int, int], Set[str]],
) -> List[Tuple[List[Dict[str, Any]], Set[str]]]:
    parent = list(range(len(items)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        a, b = find(left), find(right)
        if a != b:
            parent[b] = a

    for left, right in links:
        union(left, right)

    grouped: Dict[int, List[int]] = {}
    for index in range(len(items)):
        grouped.setdefault(find(index), []).append(index)

    out: List[Tuple[List[Dict[str, Any]], Set[str]]] = []
    for indexes in grouped.values():
        if len(indexes) < 2:
            continue
        # Keep the most salient facets when a transitive component exceeds the cap.
        kept = sorted(indexes, key=lambda i: items[i]["salience"], reverse=True)[:MAX_CLUSTER]
        reasons: Set[str] = set()
        kept_set = set(kept)
        for pair, pair_reasons in links.items():
            if pair[0] in kept_set and pair[1] in kept_set:
                reasons.update(pair_reasons)
        out.append(([items[i] for i in kept], reasons))
    return out


def _motion_text(text: str) -> str:
    words = re.findall(r"\b[a-zA-Z][a-zA-Z'-]{2,}\b", text)
    for index, word in enumerate(words):
        if word.lower() in _MOTION_WORDS:
            return " ".join(words[max(0, index - 1):index + 3])[:80]
    return ""


def _assign_roles(cluster: List[Dict[str, Any]]) -> Dict[str, Any]:
    facets: Dict[str, Any] = {}
    entity_scores: Dict[str, int] = {}
    for item in cluster:
        for entity in item["entities"]:
            # Existing world-model entities are stronger object candidates than
            # incidental relation tokens (e.g. "approaching" in "cat is
            # approaching"). Repetition across facets remains independently
            # useful evidence.
            weight = 3 if entity in item.get("known_entities", set()) else 1
            entity_scores[entity] = entity_scores.get(entity, 0) + weight
    if entity_scores:
        facets["object"] = max(entity_scores, key=lambda key: (entity_scores[key], -len(key), key))

    for item in sorted(cluster, key=lambda row: row["salience"], reverse=True):
        role = item.get("role_hint")
        if role == "affect":
            emotion = item.get("emotion") or item.get("hijack_emotion")
            if emotion and "affect" not in facets:
                facets["affect"] = {str(emotion): round(_f(item.get("intensity"), item["salience"]), 3)}
        elif role == "goal" and "goal" not in facets:
            facets["goal"] = item.get("goal_title") or item["content"]
        elif role == "memory" and "memory" not in facets:
            facets["memory"] = item["content"][:120]
        elif role == "interlocutor" and "interlocutor" not in facets:
            facets["interlocutor"] = item["content"][:120]
        else:
            motion = _motion_text(item["content"])
            if motion and "motion" not in facets:
                facets["motion"] = motion
            elif "event" not in facets:
                facets["event"] = item["content"][:120]
    return facets


def _render(facets: Dict[str, Any], cluster: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    obj = _text(facets.get("object"))
    event = _text(facets.get("motion") or facets.get("event"))
    if obj and event:
        parts.append(event if obj in event.lower() else f"{obj}: {event}")
    elif obj or event:
        parts.append(obj or event)

    affect = facets.get("affect")
    if isinstance(affect, dict) and affect:
        parts.append(next(iter(affect)).replace("_", " "))
    if facets.get("memory"):
        parts.append(f"remembering {_text(facets['memory'])}")
    if facets.get("goal"):
        parts.append(f"toward {_text(facets['goal'])}")
    if facets.get("interlocutor"):
        parts.append(_text(facets["interlocutor"]))

    if not parts:
        parts = [item["content"] for item in cluster[:2]]
    return " — ".join(dict.fromkeys(parts))[:200]


def _score(cluster: List[Dict[str, Any]], facets: Dict[str, Any]) -> float:
    coherence = min(MAX_COHERENCE_BONUS, COHERENCE_BONUS * (len(cluster) - 1))
    entity = ENTITY_BONUS if facets.get("object") else 0.0
    return round(min(1.0, max(item["salience"] for item in cluster) + coherence + entity), 3)


def bind_situation(context: dict) -> List[Dict[str, Any]]:
    """Bind this cycle's contents by shared referent.

    Fail-safe contract: every error returns ``[]`` and writes
    ``context["_bound_candidates"] = []``.
    """
    if not isinstance(context, dict):
        return []
    context["_bound_candidates"] = []
    try:
        items = _collect_items(context)
        links: Dict[Tuple[int, int], Set[str]] = {}
        for left in range(len(items)):
            for right in range(left + 1, len(items)):
                reasons = _link(items[left], items[right])
                if reasons:
                    links[(left, right)] = reasons

        composites: List[Dict[str, Any]] = []
        for cluster, reasons in _components(items, links):
            facets = _assign_roles(cluster)
            content = _render(facets, cluster)
            if not content:
                continue
            composites.append({
                "source": "binding",
                "kind": "situation",
                "content": content,
                "salience": _score(cluster, facets),
                "object": facets.get("object"),
                "facets": facets,
                "members": [item["source"] for item in cluster],
                "referent_links": sorted(reasons),
                "exempt_habituation": any(item.get("exempt_habituation") for item in cluster),
            })

        composites.sort(key=lambda row: row["salience"], reverse=True)
        context["_bound_candidates"] = composites[:MAX_COMPOSITES]
        return context["_bound_candidates"]
    except Exception as exc:
        record_failure("binding.bind_situation", exc)
        context["_bound_candidates"] = []
        return []
