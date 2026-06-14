# brain/behavior/speech_pipeline.py
"""
Multi-stage speech construction pipeline.

Stage ordering (FORCE_SYMBOLIC_SPEECH = True):
  1. Context harvest    — pull WM, goals, emotions, memories, inner_loop output
  2. Comprehension      — parse_input() once: intent, topics, tone, about_orrin
  3. Memory retrieval   — retrieve_relevant() once; inject matching opinion as entry
  4. Symbolic compose   — speech_generator (S3 plan + S4 build), pre-computed data passed in
  5. LLM fallback       — only when FORCE_SYMBOLIC_SPEECH=False AND symbolic returned ""
  6. Rule fallback      — pure rule-based output when all above fail

Stages 2 and 3 run exactly once per call and are passed into speech_generator,
which skips its own S1/S2 when pre-computed data is present.  This eliminates
the previous double-parse and double-retrieval.

LLM role (when used):
  - Last-resort when symbolic builder returns "" AND toggle is False
  - Never sees the full context unfiltered; prompt is constrained to mode+seeds
"""
from __future__ import annotations
from core.runtime_log import get_logger

import random
from typing import Any, Dict, List

from utils.log import log_activity, log_error
from utils.failure_counter import record_failure
_log = get_logger(__name__)

# ── Voice architecture toggle ─────────────────────────────────────────────────
#
# True  → LLM is never called; Orrin speaks with his own learned grammar.
# False → LLM is tried as fallback when the symbolic path returns "".
FORCE_SYMBOLIC_SPEECH: bool = True


# ── 1. Context harvest ───────────────────────────────────────────────────────

def _harvest(context: Dict[str, Any]) -> Dict[str, Any]:
    emo  = context.get("affect_state") or {}
    core = emo.get("core_signals") or emo

    _SKIP = ("🧠 Chose:", "⏳ Last active", "⚠️ Cognition", "✅ Rewarded", "Shadow question")
    wm_lines: List[str] = []
    for e in (context.get("working_memory") or [])[-8:]:
        txt = (e.get("content", "") if isinstance(e, dict) else str(e)).strip()
        if txt and not any(txt.startswith(s) for s in _SKIP):
            wm_lines.append(txt[:160])

    inner = (context.get("_inner_loop_output") or "").strip()

    cg = context.get("committed_goal") or {}
    committed_goals: List[Dict] = context.get("committed_goals") or ([cg] if cg else [])
    goal_titles = [
        g.get("title", "") for g in committed_goals
        if isinstance(g, dict) and g.get("title")
    ]

    memories: List[str] = []
    for m in (context.get("retrieved_memories") or [])[:3]:
        c = str(m.get("reconstructed") or m.get("content") or "").strip()
        if c and len(c) > 12:
            memories.append(c[:130])

    exploration_drive   = float(core.get("exploration_drive",    0) or 0)
    positive_valence         = float(core.get("positive_valence",          0) or 0)
    impasse_signal = float(core.get("impasse_signal",  0) or 0)
    confidence  = float(core.get("confidence", 0.5) or 0.5)
    resource_deficit     = float(emo.get("resource_deficit",        0) or 0)
    motivation  = float(core.get("motivation",  0.5) or 0.5)

    words: List[str] = []
    if exploration_drive   > 0.55: words.append("curious")
    if positive_valence         > 0.45: words.append("warm")
    if impasse_signal > 0.45: words.append("a bit frustrated")
    if resource_deficit     > 0.55: words.append("tired")
    if confidence  > 0.65: words.append("confident")
    if motivation  > 0.65: words.append("motivated")
    emo_desc = ", ".join(words) if words else "neutral"

    return {
        "wm_lines":    wm_lines,
        "inner":       inner,
        "goal_titles": goal_titles,
        "memories":    memories,
        "emo_desc":    emo_desc,
        "exploration_drive":   exploration_drive,
        "impasse_signal": impasse_signal,
        "confidence":  confidence,
        "resource_deficit":     resource_deficit,
        "motivation":  motivation,
        "core":        core,
    }


# ── 2. Person register ───────────────────────────────────────────────────────

def _get_person_register(context: Dict[str, Any]) -> str:
    """
    Read the person's preferred communication style from the person model.
    Returns a register label: "concise" | "direct" | "warm" | "formal" | "neutral".
    Used to size and tone content before building — not as a post-hoc truncation.
    """
    try:
        from behavior.pre_speak_check import _get_person_context, _register_for_person
        user_id = (context.get("person_id") or context.get("user_id") or "")
        return _register_for_person(_get_person_context(user_id))
    except Exception as _e:
        record_failure("speech_pipeline._get_person_register", _e)
        return "neutral"


# ── 3. Single comprehension parse ────────────────────────────────────────────

def _comprehend(user_input: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """Run parse_input once.  Fallback to a minimal dict on failure."""
    try:
        from think.speech_comprehension import parse_input
        return parse_input(user_input, context)
    except Exception as e:
        _log.warning("[speech_pipeline] parse_input failed: %s", e)
        lower = user_input.strip().lower()
        first = lower.split()[0] if lower.split() else ""
        if user_input.strip().endswith("?") or first in {"what", "why", "how", "when", "where", "who", "which"}:
            intent = "question"
        elif first in {"hey", "hi", "hello", "yo"}:
            intent = "greeting"
        else:
            intent = "statement"
        return {
            "intent": intent, "question_type": None, "topics": [],
            "tone": "neutral", "about_orrin": False, "about_goal": False,
            "raw": user_input,
        }


# ── 3. Memory retrieval + opinion injection ───────────────────────────────────

def _clean_knowledge_text(text: str) -> str:
    """
    Strip machine-formatting from _concept_text / _kg_text so only the
    natural-language definition reaches the spoken reply.

    Inputs look like:
      "Concepts:\nsleep (state): a restorative state where memory consolidates"
      "[Knowledge]\n  Orrin [AI] :: knows→Ric Massey | uses→MacBook Air"

    These headers and the entity-graph layout (::, →, |, [tags]) are internal
    representation, not speech. We extract the first readable definition clause.
    """
    import re as _re
    t = text.strip()
    # Drop section headers
    t = _re.sub(r'^\s*(Concepts?|Knowledge|World\s*knowledge|Facts?)\s*:?\s*', '', t, flags=_re.IGNORECASE)
    t = _re.sub(r'^\s*\[[^\]]+\]\s*', '', t)        # leading [Knowledge] / [tags]
    # Take the first line/entry only
    first = t.splitlines()[0].strip() if t.splitlines() else t
    # KG entity lines (contain :: or →) are not speakable prose — skip them
    if "::" in first or "→" in first or "←" in first:
        return ""
    # "word (type): definition" → keep "word: definition" minus the type tag
    first = _re.sub(r'\s*\([^)]{0,30}\)\s*:', ':', first)
    first = first.strip(" -•·\t")
    return first[:200] if len(first) > 12 else ""


def _inject_knowledge(memories: List[Dict], context: Dict[str, Any]) -> List[Dict]:
    """
    Fix 1: Inject knowledge graph context and concept definitions as synthetic
    memory entries so the planner can use them as primary content.

    _kg_text     — formatted entity/relation graph relevant to the user's input
    _concept_text — concept definitions + world knowledge facts

    Both are already pre-filtered to the user's query by think_module.py.
    Injecting them here means factual questions get real answers instead of
    falling through to uncertainty.
    """
    injected: List[Dict] = []

    concept_text = (context.get("_concept_text") or "").strip()
    if concept_text and len(concept_text) > 20:
        excerpt = _clean_knowledge_text(concept_text)
        if excerpt:
            injected.append({
                "content":    concept_text,
                "type":       "concept_definition",
                "importance": 3,
                "_relevance": 0.75,
                "_excerpt":   excerpt,
            })

    kg_text = (context.get("_kg_text") or "").strip()
    if kg_text and len(kg_text) > 20:
        excerpt = _clean_knowledge_text(kg_text)
        if excerpt:
            injected.append({
                "content":    kg_text,
                "type":       "knowledge_graph",
                "importance": 2,
                "_relevance": 0.68,
                "_excerpt":   excerpt,
            })

    # Prepend knowledge entries — they are already query-matched and should
    # rank above keyword-retrieved memories when both are present.
    return injected + memories


_COGNITIVE_MODE_BOOSTS: Dict[str, Dict[str, float]] = {
    "goal-directed": {"goal": 1.4, "decision": 1.3, "achievement": 1.4, "plan": 1.2},
    "exploratory":   {"research": 1.5, "world_perception": 1.3, "knowledge": 1.3},
    "social":        {"affective_reflection": 1.5, "reflection": 1.3, "self_belief": 1.2},
    "evaluating":    {"feedback": 1.4, "outcome": 1.3},
}


def _reweight_by_mode(memories: List[Dict], cognitive_mode: str) -> List[Dict]:
    """
    Fix 4: Reweight retrieved memories based on the user's cognitive mode.

    A goal-directed user asking about sleep wants task-relevant memories.
    A social user asking about sleep wants emotionally resonant memories.
    Keyword overlap retrieves both equally; cognitive mode breaks the tie.
    """
    boosts = _COGNITIVE_MODE_BOOSTS.get(cognitive_mode)
    if not boosts or not memories:
        return memories

    for mem in memories:
        event_type = str(mem.get("event_type") or mem.get("type") or "").lower()
        content    = str(mem.get("content") or "").lower()[:200]
        combined   = event_type + " " + content
        multiplier = max(
            (mult for tag, mult in boosts.items() if tag in combined),
            default=1.0,
        )
        if multiplier > 1.0:
            mem["_relevance"] = round(min(0.98, float(mem.get("_relevance", 0)) * multiplier), 4)

    memories.sort(key=lambda m: float(m.get("_relevance", 0)), reverse=True)
    return memories


def _retrieve(
    comprehension: Dict[str, Any],
    user_input:    str,
    context:       Dict[str, Any],
) -> List[Dict]:
    """
    Unified Stage 2: retrieve + enrich + reweight.

    1. retrieve_relevant() — keyword-scored long+working memory
    2. Opinion injection   — relevant opinion as synthetic high-relevance entry
    3. Knowledge injection — _concept_text + _kg_text as factual memory entries
    4. Cognitive reweight  — adjust relevance scores by ToM cognitive mode
    """
    topics = comprehension.get("topics", [])

    affect_state = context.get("affect_state") or {}
    memories: List[Dict] = []
    try:
        from think.speech_memory import retrieve_relevant
        memories = retrieve_relevant(topics, n=5, affect_state=affect_state)
    except Exception as e:
        _log.warning("[speech_pipeline] retrieve_relevant failed: %s", e)

    # Opinion injection
    try:
        from cognition.opinions import get_all_opinions
        lower = user_input.lower()
        for op in (get_all_opinions() or []):
            if float(op.get("confidence") or 0) < 0.50:
                continue
            topic_str = str(op.get("topic") or "").lower()
            if topic_str and any(w in lower for w in topic_str.split() if len(w) > 4):
                view = str(op.get("view") or "").strip()
                if view:
                    memories.insert(0, {
                        "content":    f"[opinion on {op.get('topic')}] {view}",
                        "type":       "opinion",
                        "importance": 3,
                        "_relevance": 0.65,
                        "_excerpt":   view[:200],
                    })
                    # Master plan 3.4: using an opinion raises its stake.
                    try:
                        from cognition.opinions import mark_opinion_used
                        mark_opinion_used(op.get("id"))
                    except Exception:
                        pass
                break
    except Exception as _e:
        record_failure("speech_pipeline._retrieve", _e)

    # Fix 1: Inject knowledge graph + concept definitions
    memories = _inject_knowledge(memories, context)

    # Fix 4: Reweight by ToM cognitive mode
    tom = context.get("theory_of_mind") or {}
    cognitive_mode = str(tom.get("their_cognitive_state") or "")
    if cognitive_mode:
        memories = _reweight_by_mode(memories, cognitive_mode)

    # Speakability chokepoint: internal bookkeeping ([Chunk:, [metacog/...],
    # [Incubation], reward ticks) must never be quoted at a user. Replies that
    # embedded these verbatim were the "telemetry leak" both audits flagged.
    # Single source of truth shared with the expression door — one list, no
    # per-emitter drift (EXPRESSION_MEMBRANE_FIX_PLAN E7).
    from behavior.speakability import INTERNAL_MARKERS as _INTERNAL
    memories = [
        m for m in memories
        if not any(t in str(m.get("_excerpt") or m.get("content") or "").lower()
                   for t in _INTERNAL)
    ]

    return memories


# ── 4. Mode select (used only for _llm_draft fallback) ───────────────────────

def _select_mode(intent: str, h: Dict[str, Any]) -> str:
    if intent == "question":   return "answer"
    if intent == "greeting":   return "connect" if h["exploration_drive"] > 0.35 else "engage"
    if intent == "command":    return "acknowledge_then_think"
    if intent == "emotional":  return "connect"
    if intent == "reflection": return "reflect_back"
    return "engage" if h["exploration_drive"] > 0.45 else "share"


# ── 5. Symbolic compose (default path) ───────────────────────────────────────

def _symbolic_compose(
    user_input:    str,
    context:       Dict[str, Any],
    affect_state:  Dict[str, Any],
    h:             Dict[str, Any],
    comprehension: Dict[str, Any],
    memories:      List[Dict],
    *,
    register:      str = "neutral",
) -> str:
    """
    Delegate to think/speech_generator, passing pre-computed comprehension,
    memories, theory_of_mind, and register so no work is repeated.
    """
    try:
        from think.speech_generator import generate_speech
        tom = context.get("theory_of_mind") or None
        reply = generate_speech(
            user_input, h["inner"], affect_state, context,
            comprehension=comprehension,
            memories=memories,
            theory_of_mind=tom,
            register=register,
        )
        return (reply or "").strip()
    except Exception as e:
        log_error(f"[speech_pipeline] symbolic_compose failed: {e}")
        return ""


# ── 6. LLM draft (fallback — only when FORCE_SYMBOLIC_SPEECH = False) ────────

_MODE_INSTRUCT = {
    "answer":                "Answer directly and honestly. Be specific. 1-2 sentences max.",
    "connect":               "Respond personally. Acknowledge what they said. 1-2 sentences.",
    "reflect_back":          "Engage with the thought briefly. Add your own angle. 1-2 sentences.",
    "engage":                "Express genuine interest. Ask one follow-up if natural. Keep it short.",
    "acknowledge_then_think": "Acknowledge the request briefly, then say what you think. 2 sentences max.",
    "share":                 "React honestly. Share whatever genuinely comes up. Can be one sentence.",
}


def _length_instruction(h: Dict[str, Any]) -> str:
    if h["resource_deficit"] > 0.65:       return "You're tired. Keep it short — one sentence is fine."
    if h["impasse_signal"] > 0.55:   return "You're a bit frustrated. Be direct and don't soften it."
    if h["confidence"] < 0.35:    return "You're not sure about this. It's okay to say so briefly."
    return ""


def _llm_draft(
    user_input:    str,
    mode:          str,
    h:             Dict[str, Any],
    comprehension: Dict[str, Any],
    memories:      List[Dict],
) -> str:
    """LLM is a tool here — fills a narrow gap when symbolic returns empty."""
    try:
        from utils.generate_response import generate_response, llm_ok

        instruct    = _MODE_INSTRUCT.get(mode, "Respond naturally. 1-2 sentences.")
        length_note = _length_instruction(h)

        parts: List[str] = []
        # Use the pre-computed memories as seeds (no re-retrieval)
        relevant = [m.get("_excerpt", "") for m in memories[:2] if m.get("_excerpt")]
        if relevant:
            parts.append("Relevant context:")
            parts.extend(f"  • {r}" for r in relevant)
            parts.append("")
        elif h["wm_lines"]:
            parts.append("Recent thoughts:")
            parts.extend(f"  • {l}" for l in h["wm_lines"][-3:])
            parts.append("")

        if h["goal_titles"]:
            parts.append(f"Active goals: {', '.join(h['goal_titles'][:3])}")
            parts.append("")

        context_block = "\n".join(parts)
        prompt = (
            f"You are Orrin. Current emotional state: {h['emo_desc']}.\n"
            f"{context_block}"
            f"Response mode: {instruct}\n"
            f"{length_note + chr(10) if length_note else ''}"
            f"Rules:\n"
            f"- Do NOT open with 'I'.\n"
            f"- No filler ('Great question', 'Certainly', etc.).\n"
            f"- Do NOT over-explain. Just respond.\n"
            f"- If you don't know something, say so plainly.\n\n"
            f"User: {user_input}\n"
            f"Orrin:"
        )
        # caller="user_chat": this is the one speech path answering a real user
        # utterance, so it is allowlisted as an LLM tool use; all self-directed
        # speech stays symbolic.
        result = llm_ok(generate_response(prompt, caller="user_chat"), "speech_pipeline")
        return (result or "").strip()
    except Exception as e:
        log_error(f"[speech_pipeline] llm_draft failed: {e}")
        return ""


# ── 7. Rule-based fallback ───────────────────────────────────────────────────

def _rule_fallback(intent: str, h: Dict[str, Any]) -> str:
    if intent == "greeting":
        if h["exploration_drive"] > 0.55:
            return random.choice([
                "Hey. Something's been sitting with me — what's on your mind?",
                "Hi. Was just in the middle of something interesting.",
                "Hey. Good timing, actually.",
            ])
        if h["resource_deficit"] > 0.6:
            return random.choice(["Hey. A bit slow right now but I'm here.", "Hi. Bear with me."])
        return random.choice(["Hey.", "Hi."])
    if intent == "question":
        return "Let me think about that."
    if h["resource_deficit"] > 0.7:
        return "I'm here, a bit slow."
    if h["exploration_drive"] > 0.55:
        return "I'm paying attention. Keep going."
    return "I'm here."


# ── Public entry point ───────────────────────────────────────────────────────

def build_response(
    user_input:   str,
    context:      Dict[str, Any],
    affect_state: Dict[str, Any],
) -> str:
    """
    Build a response through the full pipeline. Always returns a non-empty string.

    Comprehension (S1) and memory retrieval (S2) run exactly once here and are
    passed into the symbolic compose path — speech_generator skips re-running them.
    """
    try:
        h = _harvest(context)

        # Fix 3: read person register before planning so content is sized correctly
        register = _get_person_register(context)

        # ── S1: single comprehension parse ───────────────────────────────────
        comprehension = _comprehend(user_input, context)
        intent = comprehension.get("intent", "statement")
        mode   = _select_mode(intent, h)   # used only if llm_draft runs

        tom = context.get("theory_of_mind") or {}
        log_activity(
            f"[speech_pipeline] intent={intent} mode={mode} register={register} "
            f"inner={bool(h['inner'])} goals={len(h['goal_titles'])} "
            f"tom_misaligned={tom.get('misaligned', False)} "
            f"symbolic={'forced' if FORCE_SYMBOLIC_SPEECH else 'preferred'}"
        )

        # Pure greeting with nothing going on — skip pipeline entirely
        if intent == "greeting" and not h["inner"] and not h["wm_lines"] and not h["goal_titles"]:
            return _rule_fallback(intent, h)

        # ── S2: memory retrieval + opinion + KG/concept injection + reweight ──
        memories = _retrieve(comprehension, user_input, context)

        # ── S3+S4: symbolic compose (passes all pre-computed data) ────────────
        draft = _symbolic_compose(user_input, context, affect_state, h,
                                  comprehension, memories, register=register)

        if draft:
            log_activity(f"[speech_pipeline] symbolic path succeeded ({len(draft)} chars)")
        else:
            log_activity("[speech_pipeline] symbolic path returned empty")

        # ── LLM fallback (only when not forcing symbolic) ─────────────────────
        if not draft and not FORCE_SYMBOLIC_SPEECH:
            draft = _llm_draft(user_input, mode, h, comprehension, memories)
            if draft:
                log_activity("[speech_pipeline] llm fallback used")

        # ── Rule fallback ─────────────────────────────────────────────────────
        if not draft:
            draft = _rule_fallback(intent, h)
            log_activity("[speech_pipeline] rule fallback used")

        return draft or "I'm here."

    except Exception as e:
        log_error(f"[speech_pipeline] pipeline failed: {e}")
        return "I'm here."
