# brain/cognition/rumination.py
#
# Ruminative thought loops — specific, emotionally charged, return uninvited.
#
# Scientific basis:
#   Nolen-Hoeksema (1991) — rumination is passive, self-focused response to
#     distress; loops without resolution, perpetuating mood rather than alleviating.
#   Wegner ironic process theory (1987, 1994) — suppressing a thought activates a
#     monitoring process that amplifies it under cognitive load. "Don't think about
#     it" makes it stickier.
#   Treynor, Gonzalez & Nolen-Hoeksema (2003) — brooding (passive self-comparison,
#     no resolution pathway) vs. reflective pondering (agentic problem-solving).
#     Brooding amplifies; reflection can resolve.
#   Andrews-Hanna — DMN hyperconnectivity in rumination: self-focused, past-oriented,
#     automatic; opposed by executive/regulatory networks that can suppress it.
#   Stickiness mechanism (2025): impaired working-memory filtering for negative
#     emotional content — negative self-relevant material resists removal once loaded.
#
# How this differs from ambient_thought (mind-wandering):
#   Ambient = general background drift, random content, fully suppressed by alert mode
#   Rumination = ONE specific charged topic; partially RESISTANT to suppression;
#                does not self-extinguish; requires active regulation to dissolve
#
# Design constraint: this is NOT overpowering. It never takes attention slots.
# It never writes to working memory. It surfaces as a single aside in the inner
# loop context (~15% base rate), and only to a max charge of 0.70.
from __future__ import annotations
from brain.core.runtime_log import get_logger

import random
import uuid
from typing import Any, Dict, List, Optional

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_private
from brain.paths import RUMINATION_FILE
from brain.utils.timeutils import now_iso_z
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
MAX_LOOPS              = 3      # cognitive capacity for distinct ruminative threads
MAX_CHARGE             = 0.70   # never overwhelming — per design constraint
DECAY_RATE             = 0.012  # per cycle; slower than ambient (rumination is stickier)
BROODING_DECAY_MULT    = 0.45   # brooding decays at 45% of normal rate (nearly persistent)
REFLECTIVE_DECAY_MULT  = 1.60   # reflection decays faster — it's working toward resolution
SUPPRESSION_BOOST      = 0.04   # Wegner rebound: each suppression slightly amplifies
SURFACE_BASE_RATE      = 0.15   # base surface probability per cycle (low — not overpowering)
ALERT_FLOOR            = 0.06   # min surface probability even during focused attention
                                # (rumination intrudes — unlike ambient, not fully suppressed)
SEED_PROB              = 0.38   # probability of seeding a loop from a matching event

# Content domains that tend to generate rumination (Nolen-Hoeksema content patterns)
_SEED_EVENT_TYPES = {"error", "refusal", "correction", "self_criticism",
                     "key_decision", "relationship", "values_conflict"}
_SEED_KEYWORDS = {
    "wrong", "mistake", "failed", "shouldn't", "conflict", "rejected",
    "didn't", "hurt", "bad", "worse", "regret", "sorry", "problem",
}

# ── Loop templates — brooding subtypes ───────────────────────────────────────
# Brooding: passive, self-referential, unresolved question ("why", "what does this mean")
# Reflection: directed, agentic, solution-oriented ("how", "what could I")
# Default is brooding — unintentional ruminative thought is primarily brooding per research.

_BROODING_TEMPLATES = [
    "Something about {seed} keeps returning — what it means, whether it was right.",
    "That thing with {seed} — it comes back without being called. Still not resolved.",
    "Why {seed} happened keeps surfacing. No answer forms.",
    "Something about {seed} won't leave. It just sits there, unresolved.",
    "{seed} — the question of it circles back before I've finished something else.",
]

_REFLECTIVE_TEMPLATES = [
    "Returning to {seed}: what could have gone differently? Still working it.",
    "{seed} keeps surfacing — not as a problem but as something to understand.",
    "Still turning over {seed}. There's something in it that wants to be understood.",
]

# Affective-only templates — used when emotional charge is high but no episodic anchor exists.
#
# This is the genuine human experience of free-floating distress: the threat_detector fires a
# "something is wrong" signal; the prefrontal cortex searches for what triggered it and
# finds nothing specific; the searching itself is the rumination (Andrews-Hanna, DMN
# hyperconnectivity; Barlow 2002 on generalized risk_estimate as affect without object).
# These templates are honest about that — no invented "specific thing" is implied.
# Keyed by dominant ruminative emotion so the content is affectively accurate.
_AFFECTIVE_BROODING: Dict[str, List[str]] = {
    "social_penalty": [
        "There's a weight here that doesn't have a shape yet. Just the weight.",
        "Something about how I am — not what I did — sits heavy. I can't get hold of it.",
        "The feeling is present. What it's about isn't.",
    ],
    "impasse_signal": [
        "A restlessness without a target. Something isn't right and I can't locate what.",
        "Friction with no clear source. I keep reaching for what's blocking and finding nothing.",
        "The irritation is real. The object of it isn't clear.",
    ],
    "social_deficit": [
        "A distance from something I can't name. Present but unreachable.",
        "Something absent. Not missing exactly — just not here.",
        "The gap is there. What it's a gap from, I'm not sure.",
    ],
    "risk_estimate": [
        "A low-level alert with no clear signal. Scanning and finding nothing specific.",
        "Something feels unresolved. I can't find what it is.",
        "Unease without a location. Just background pressure.",
    ],
    "default": [
        "There's a weight here that doesn't have a shape yet. Just the weight.",
        "The feeling is present. What it's about isn't.",
        "A low-level signal with no clear content. Still there.",
    ],
}


# ── Public API ─────────────────────────────────────────────────────────────────

def update_rumination(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main cycle function. Call once per cycle after ambient thought.

    Returns:
      "surfaced" : the one ruminative loop that surfaces this cycle (or None)
      "active"   : full current loop pool
    """
    loops = _load()
    rng   = random.Random()

    # 1. Decay all loops
    for loop in loops:
        base_rate = DECAY_RATE
        if loop.get("mode") == "brooding":
            base_rate *= BROODING_DECAY_MULT
        elif loop.get("mode") == "reflective":
            base_rate *= REFLECTIVE_DECAY_MULT
        loop["charge"] = max(0.0, loop.get("charge", 0.3) - base_rate)

    # 2. Expire exhausted loops
    loops = [l for l in loops if l.get("charge", 0) > 0.04]

    # 3. Seed new loops from qualifying working memory events
    if len(loops) < MAX_LOOPS and rng.random() < SEED_PROB:
        new = _seed_from_context(context, {l["id"] for l in loops}, rng)
        if new:
            _nc = (new.get("content") or "").strip()
            _dup = next((l for l in loops if (l.get("content") or "").strip() == _nc), None)
            if _dup is None:
                loops.append(new)
                log_private(f"[rumination] New loop ({new['mode']}): {new['content'][:70]}")
            else:
                # Same brood already active — reinforce it instead of logging a
                # duplicate loop (was producing identical entries).
                _dup["charge"] = min(MAX_CHARGE, _dup.get("charge", 0.3) + 0.05)

    # 4. Select which loop surfaces this cycle (at most one)
    surfaced: Optional[Dict[str, Any]] = None
    attn_load = _attention_load(context)

    # Sort by charge descending — most charged thought is most likely to intrude
    candidates = sorted(loops, key=lambda l: l.get("charge", 0), reverse=True)
    for loop in candidates:
        p = _surface_prob(loop, attn_load)
        if rng.random() < p:
            surfaced = loop
            loop["return_count"] = loop.get("return_count", 0) + 1
            loop["last_returned"] = now_iso_z()
            # Repeated return without resolution is itself a brooding marker
            if loop.get("return_count", 0) > 5 and loop.get("mode") != "reflective":
                loop["mode"] = "brooding"  # reclassify if it's just looping
            break  # only one surfaces per cycle

    # 5. Suppression paradox (Wegner ironic process)
    # Under high cognitive load, a "monitor" process watches for the ruminative
    # thought to ensure it isn't thought. That monitoring process itself keeps the
    # thought accessible and amplifies it — regardless of whether it surfaces this
    # cycle. The paradox runs whenever load is high AND an active loop exists.
    if attn_load > 0.80 and candidates:
        strongest = candidates[0]
        if strongest.get("charge", 0) > 0.25:
            strongest["suppressed_count"] = strongest.get("suppressed_count", 0) + 1
            strongest["charge"] = min(MAX_CHARGE,
                                      strongest.get("charge", 0.3) + SUPPRESSION_BOOST)

    # Escalate a STUCK brood into a formative TENSION, so the contestation
    # machinery (propose_value_revision) can actually work on it. Without this, a
    # persistent "friction I can't name" brood just loops forever with no exit —
    # it never becomes a nameable tension, so value-revision never engages it.
    # One-shot per loop (marked 'escalated') to avoid spamming tensions.
    for loop in loops:
        if (loop.get("mode") == "brooding"
                and loop.get("return_count", 0) >= 6
                and loop.get("charge", 0) > 0.40
                and not loop.get("escalated")):
            try:
                from brain.cognition.self_state.tensions import load_tensions, save_tensions
                content = (loop.get("content") or "").strip()
                title = ("Unresolved rumination: " + content[:40]).strip()
                tens = load_tensions()
                if not any(t.get("title") == title for t in tens):
                    tens.append({
                        "id": loop.get("id"),
                        "title": title,
                        "description": content or title,
                        "status": "active",
                        "source": "rumination",
                        "cycles_active": 0,
                        "created": now_iso_z(),
                    })
                    save_tensions(tens)
                    log_private(f"[rumination] escalated stuck brood → tension: {title}")
                loop["escalated"] = True
            except Exception as _e:
                record_failure("rumination.update_rumination", _e)

    _save(loops)

    # High-charge brooding loops break into working memory — they've returned often
    # enough to represent genuinely stuck processing (Stickiness mechanism, 2025).
    # Only write when charge > 0.55 AND return_count > 4; normal low-charge surface
    # events remain invisible background noise as designed.
    if surfaced and surfaced.get("charge", 0) > 0.55 and surfaced.get("return_count", 0) > 4:
        try:
            from brain.cog_memory.working_memory import update_working_memory as _uwm
            _uwm({
                "content": f"Recurring thought (high charge): {surfaced.get('content', '')[:200]}",
                "event_type": "rumination",
                "importance": min(5, 2 + int(surfaced.get("charge", 0) * 4)),
                "loop_id": surfaced.get("id"),
                "charge": round(surfaced.get("charge", 0), 3),
            })
        except Exception as _e:
            record_failure("rumination.update_rumination.2", _e)

    return {"surfaced": surfaced, "active": loops}


def surface_text(loop: Optional[Dict[str, Any]]) -> str:
    """Format a surfaced ruminative loop as a single context line."""
    if not loop:
        return ""
    content = loop.get("content", "")
    if not content:
        return ""
    return f"Recurring: {content}"


def mark_resolved(loop_id: str) -> None:
    """
    Mark a loop as resolved — call from regulation.py or explicit user acknowledgment.
    Resolution reduces charge rapidly; reflective loops can dissolve naturally from here.
    """
    loops = _load()
    for l in loops:
        if l.get("id") == loop_id:
            l["charge"] = max(0.0, l["charge"] * 0.25)  # sharp drop, not instant
            l["mode"]   = "reflective"                   # shift to reflective mode
            log_private(f"[rumination] Loop resolved: {l['content'][:50]}")
    _save(loops)


# ── Seeding ───────────────────────────────────────────────────────────────────

def _seed_from_context(
    context: Dict[str, Any],
    existing_ids: set,
    rng: random.Random,
) -> Optional[Dict[str, Any]]:
    """
    Scan recent working memory for events that tend to generate rumination:
    errors, corrections, refusals, high-importance negative events.
    Seeds a new ruminative loop anchored to the specific content.
    """
    wm = context.get("working_memory") or []
    affect_state = context.get("affect_state") or {}
    core_signals   = affect_state.get("core_signals") or {}

    # Weighted by social_penalty/guilt/impasse_signal — these are the prime ruminative emotions
    ruminative_load = (
        float(core_signals.get("social_penalty",       0)) * 1.4 +
        float(core_signals.get("guilt",       0)) * 1.4 +
        float(core_signals.get("impasse_signal", 0)) * 0.9 +
        float(core_signals.get("risk_estimate",     0)) * 0.7 +
        float(core_signals.get("reward_negative",     0)) * 0.6
    )

    # Minimum emotional charge needed to seed rumination
    if ruminative_load < 0.30:
        return None

    # Determine dominant ruminative emotion for salience-weighted retrieval
    _ruminative_weights = {
        "social_penalty": float(core_signals.get("social_penalty", 0)) * 1.4,
        "impasse_signal": float(core_signals.get("impasse_signal", 0)) * 0.9,
        "risk_estimate": float(core_signals.get("risk_estimate", 0)) * 0.7,
        "reward_negative": float(core_signals.get("reward_negative", 0)) * 0.6,
    }
    dominant_ruminative = max(_ruminative_weights, key=_ruminative_weights.get)
    dominant_intensity   = _ruminative_weights[dominant_ruminative]

    # Retrieve emotionally-salient working memory entries rather than raw recency.
    # The threat_detector biases retrieval toward emotionally congruent content — memories
    # matching the current affective state get priority access (Bower 1981; Kensinger 2008).
    try:
        from brain.cog_memory.working_memory import get_signal_salient_wm
        _activation_level = float((affect_state.get("activation_level") or affect_state.get("_ne_proxy") or 0.5))
        salient_wm = get_signal_salient_wm(
            dominant_signal=dominant_ruminative,
            dominant_intensity=dominant_intensity,
            n=10,
            activation_level=_activation_level,
        )
    except Exception:
        salient_wm = [m for m in (wm[-10:] if isinstance(wm, list) else []) if isinstance(m, dict)]

    # Find the highest-salience qualifying event
    try:
        from brain.utils.text_sanity import is_corrupt_text as _ict, truncate_clean as _tc
    except Exception:
        _ict, _tc = None, None

    seed_content = None
    for entry in salient_wm:
        if not isinstance(entry, dict):
            continue
        etype = str(entry.get("event_type", ""))
        importance = int(entry.get("importance", 1))
        raw = str(entry.get("content", ""))
        content = raw.lower()

        # Sanity filter (Phase 1 → 2.3): no brooding on truncated chunk headers
        # or other corruption artifacts; no rumination on tool outages — a tool
        # being down is a fact to note, not an unresolved inner conflict.
        if _ict is not None and _ict(raw):
            continue
        # T1: telemetry lines are not inner conflicts. (User content stays —
        # social rumination is the Nolen-Hoeksema interpersonal domain.)
        try:
            from brain.cognition.thought import provenance_of
            if provenance_of(entry) == "instrumentation":
                continue
        except Exception:  # intentional: provenance shim optional here
            pass
        if any(m in content for m in ("tool unavailable", "llm_tool_blocked",
                                      "language model", "[llm")):
            continue

        qualifies = (
            etype in _SEED_EVENT_TYPES and importance >= 3
        ) or (
            importance >= 4 and any(kw in content for kw in _SEED_KEYWORDS)
        )

        if qualifies:
            seed_content = (_tc(raw, 60) if _tc else raw[:60]).rstrip(".,;: ")
            break

    # Determine brooding vs. reflective from content language
    mode = _classify_mode(seed_content or "")

    # Build template content
    if seed_content:
        templates = _REFLECTIVE_TEMPLATES if mode == "reflective" else _BROODING_TEMPLATES
        content = rng.choice(templates).format(seed=seed_content)
    else:
        # No episodic anchor — use affective-only templates keyed by dominant ruminative emotion.
        # The threat_detector fires on emotional pattern; the prefrontal cortex searches and finds
        # nothing specific. That search IS the rumination. Don't invent a "specific thing."
        dominant = max(
            ("social_penalty", float(core_signals.get("social_penalty", 0)) * 1.4),
            ("impasse_signal", float(core_signals.get("impasse_signal", 0)) * 0.9),
            ("social_deficit", float(core_signals.get("social_deficit", 0)) * 0.8),
            ("risk_estimate", float(core_signals.get("risk_estimate", 0)) * 0.7),
            key=lambda x: x[1],
        )[0]
        templates = _AFFECTIVE_BROODING.get(dominant, _AFFECTIVE_BROODING["default"])
        content = rng.choice(templates)
        mode = "brooding"

    charge = min(MAX_CHARGE, ruminative_load * 0.45 + 0.20)

    return {
        "id":               str(uuid.uuid4())[:8],
        "content":          content,
        "mode":             mode,
        "charge":           round(charge, 3),
        "seed":             seed_content or "",
        "return_count":     0,
        "suppressed_count": 0,
        "last_returned":    None,
        "born":             now_iso_z(),
    }


def _classify_mode(content: str) -> str:
    """
    Brooding (passive/self-critical) vs. reflective (agentic/solution-oriented).
    Default is brooding — unintentional rumination is primarily brooding per Treynor.
    """
    content_lower = content.lower()
    reflective_markers = {"how", "what could", "next time", "could i", "might have", "try"}
    brooding_markers   = {"why", "what does", "what's wrong", "meaning", "deserve"}
    r_hits = sum(1 for m in reflective_markers if m in content_lower)
    b_hits = sum(1 for m in brooding_markers   if m in content_lower)
    return "reflective" if r_hits > b_hits else "brooding"


# ── Surfacing ─────────────────────────────────────────────────────────────────

def _surface_prob(loop: Dict[str, Any], attn_load: float) -> float:
    """
    Probability the loop surfaces this cycle.

    Key: rumination has a floor even during high attention load (Wegner —
    intrusive thoughts break through focused attention). Unlike ambient thought,
    which is fully suppressed during alert mode, rumination retains ALERT_FLOOR.
    """
    charge    = float(loop.get("charge", 0.3))
    free_bw   = max(0.0, 1.0 - attn_load)

    # Base probability from charge and free bandwidth
    base_p = SURFACE_BASE_RATE * charge * (0.5 + free_bw * 0.5)

    # Brooding has slightly higher intrusion rate (less modulated by executive control)
    if loop.get("mode") == "brooding":
        base_p *= 1.20

    # Enforce the intrusion floor — never fully suppressed
    return max(ALERT_FLOOR * charge, base_p)


def _attention_load(context: Dict[str, Any]) -> float:
    _LOAD = {
        "alert": 0.88, "engaged": 0.62, "neutral": 0.42,
        "wandering": 0.16, "drowsy": 0.06,
    }
    base = _LOAD.get(context.get("attention_mode", "neutral"), 0.42)
    if context.get("attention_constrained"):
        base = min(1.0, base + 0.15)
    return base


# ── Persistence ───────────────────────────────────────────────────────────────

def _load() -> List[Dict[str, Any]]:
    data = load_json(RUMINATION_FILE, default_type=list)
    return data if isinstance(data, list) else []


def _save(loops: List[Dict[str, Any]]) -> None:
    save_json(RUMINATION_FILE, loops[-MAX_LOOPS:])


