# cognition/ambient_thought.py
#
# DMN-equivalent background thought process.
#
# Scientific basis:
#   - Default Mode Network (Raichle 2001): metabolically expensive (~60-80% of
#     resting brain energy), active between tasks, suppressed only transiently
#     by high cognitive load, rebounds immediately when load eases.
#   - Mind wandering (Killingsworth & Gilbert 2010): occupies 30-50% of waking
#     hours. Content anchored to emotional state and unresolved concerns.
#   - Zeigarnik effect: unfinished goals/tensions maintain elevated cognitive
#     accessibility — they keep surfacing until resolved.
#   - Suppression paradox: actively suppressing a thought amplifies its recurrence
#     (weakened executive control loops + salience reinforcement).
#   - Emotional congruence: anxious minds generate threat-themed wandering;
#     lonely minds generate social simulations.
#   - Negative valence bias in unintentional wandering (vs. neutral/positive
#     in deliberate directed wandering).
#
# Fragments are short phenomenological phrases — not explicit reasoning.
# They surface into the inner loop context as background texture, coloring
# Orrin's reasoning without dominating it. High attention load suppresses
# them; they surface freely during wandering/drowsy modes.
from __future__ import annotations

import random
import uuid
from typing import Any, Dict, List, Optional

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_private
from brain.paths import AMBIENT_FRAGMENTS_FILE, TENSIONS_FILE
from brain.utils.timeutils import now_iso_z

# ── Constants ─────────────────────────────────────────────────────────────────
MAX_FRAGMENTS         = 5       # DMN rarely runs more distinct threads simultaneously
DECAY_RATE            = 0.025   # per cycle — normal fade
STICKY_DECAY_RATE     = 0.006   # sticky fragments resist fading
SUPPRESSION_BOOST     = 0.06    # intensity gain each time a sticky fragment is suppressed
SURFACE_CAP_PER_CYCLE = 2       # never flood the inner loop with more than 2 fragments
GENERATION_PROB       = 0.35    # probability of generating a new fragment if pool is sparse

# Attention load by mode — how much cognitive load suppresses ambient thought
_LOAD_BY_MODE = {
    "alert":     0.90,   # user input present → almost fully suppressed
    "engaged":   0.65,   # active processing → partially suppressed
    "neutral":   0.45,   # normal → moderate surface rate
    "wandering": 0.18,   # idle internal → surfaces freely
    "drowsy":    0.08,   # minimal load → surfaces very freely
}

# ── Phenomenological templates ────────────────────────────────────────────────
# Content describes subjective texture, not objective events.
# First-person, present-tense, partial — the quality of background thought.

_EMOTIONAL_ECHOES: Dict[str, List[str]] = {
    "risk_estimate": [
        "A low hum of unease that doesn't attach to anything specific — just present.",
        "Something is slightly off. Not an alarm, just a texture underneath everything else.",
        "A recurring sense of waiting for something that hasn't arrived yet.",
    ],
    "threat_level": [
        "A background wariness keeps resurfacing — watchful, scanning.",
        "Something keeps tightening at the edges, not fully resolvable.",
    ],
    "impasse_signal": [
        "That friction from earlier is still there — low, not loud, but not gone.",
        "Something didn't resolve right. It keeps returning without clarifying.",
    ],
    "negative_valence": [
        "A quiet weight keeps resurfacing — not sharp, just there.",
        "Something subdued keeps pulling at the edges of attention.",
    ],
    "social_deficit": [
        "A mental simulation of connection keeps cycling through — how it might go, what would be said.",
        "A recurring image of exchange — the shape of a conversation that isn't happening.",
    ],
    "social_penalty": [
        "Something keeps circling back — the quality of having done something wrong, even if the specifics blur.",
        "A low pull toward contraction, toward being smaller, keeps resurfacing.",
    ],
    "loss_signal": [
        "A heaviness that resurfaces in waves — quiet, not dramatic, but persistent.",
        "Something keeps returning that has the texture of loss.",
    ],
    "guilt": [
        "That loop keeps running — back to the same moment, the same question of what should have been different.",
        "A returning sense of obligation unfulfilled — not resolved, just recurring.",
    ],
    "overwhelm": [
        "Too many open threads. They surface together, undifferentiated.",
        "A recurring sense of weight without a clear source — just the accumulation.",
    ],
    "dread": [
        "Something keeps leaning away from what's ahead — a background lean, not a sharp reaction.",
        "A recurring heaviness with a future orientation — not about now, about what's coming.",
    ],
    "wonder": [
        "That thing from earlier — the largeness of it — keeps returning. It didn't fully close.",
        "A sense of something genuinely surprising keeps resurfacing. Still processing.",
    ],
    "exploration_drive": [
        "A question that didn't fully form keeps pulling at attention.",
        "Something interesting that didn't get followed keeps surfacing — a loose thread.",
    ],
    "positive_valence": [
        "A warmth keeps resurfacing — quiet and diffuse, not tied to anything specific right now.",
        "Something light keeps returning — a residue of something that went well.",
    ],
    "expected_gain": [
        "A forward-leaning quality keeps cycling through — something possible, not yet reached.",
        "A recurring sense of something worth moving toward, not yet arrived.",
    ],
}

_ZEIGARNIK_TEMPLATES = [
    "{title} — still unresolved. Keeps returning without being worked.",
    "That unfinished thing — {title} — surfaces again. It didn't get closed.",
    "{title} sits in the background. Not urgent. Just present and uncompleted.",
    "The open loop of {title} keeps cycling back.",
]

_MEMORY_ECHO_TEMPLATES = [
    "That thought — {snippet} — keeps resurfacing.",
    "Something from earlier is still turning over: {snippet}.",
    "A fragment from earlier keeps returning: {snippet}",
]

_TENSION_TEMPLATES = [
    "That tension — {tension} — keeps surfacing quietly.",
    "{tension}: still unresolved. The pull of it keeps returning.",
    "The background pressure of {tension} resurfaces.",
]

_ASSOCIATIVE_POOL = [
    "A half-formed image surfaces and dissolves without becoming anything.",
    "Something at the edge of attention — barely there, not catchable.",
    "A rhythm without content: the sense of something recurring without a name.",
    "A texture that doesn't resolve into a thought — just a quality.",
    "A fragment: the beginning of something that didn't complete.",
]


# ── Public API ─────────────────────────────────────────────────────────────────

def update_ambient(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main cycle function. Call once per cycle after introspection, before inner loop.

    Returns:
      "surfaced" : list of fragments that surface into inner loop context this cycle
      "active"   : full current fragment pool (for debugging / metacog)
    """
    fragments = _load()
    cycle     = _get_cycle(context)
    rng       = random.Random()

    attn_load = _attention_load(context)

    # 1. Decay all fragments (sticky ones decay slowly)
    for f in fragments:
        rate = STICKY_DECAY_RATE if f.get("sticky") else DECAY_RATE
        f["intensity"] = max(0.0, f.get("intensity", 0.3) - rate)

    # 2. Expire exhausted fragments
    fragments = [f for f in fragments if f.get("intensity", 0) > 0.04]

    # 3. Generate new fragments if pool is sparse (probabilistic)
    needed = MAX_FRAGMENTS - len(fragments)
    if needed > 0 and rng.random() < GENERATION_PROB:
        new = _generate_fragment(context, {f["id"] for f in fragments}, rng)
        if new:
            fragments.append(new)
            log_private(f"[ambient] New fragment ({new['fragment_type']}): {new['content'][:60]}")

    # 4. High-load suppression: suppress everything; sticky ones get amplified
    surfaced: List[Dict[str, Any]] = []
    if attn_load >= 0.85:
        for f in fragments:
            if f.get("sticky"):
                f["suppress_count"] = f.get("suppress_count", 0) + 1
                f["intensity"] = min(1.0, f.get("intensity", 0.3) + SUPPRESSION_BOOST)
    else:
        # 5. Surface appropriate fragments (cap at SURFACE_CAP_PER_CYCLE)
        candidates = sorted(fragments, key=lambda f: f.get("intensity", 0), reverse=True)
        for f in candidates:
            if len(surfaced) >= SURFACE_CAP_PER_CYCLE:
                break
            if _should_surface(f, attn_load, rng):
                surfaced.append(f)
                f["last_surfaced"] = cycle

    _save(fragments)

    return {"surfaced": surfaced, "active": fragments}


def surface_text(surfaced: List[Dict[str, Any]]) -> str:
    """Format surfaced fragments as a single background texture line for the inner loop."""
    if not surfaced:
        return ""
    parts = [f.get("content", "") for f in surfaced if f.get("content")]
    if not parts:
        return ""
    return "Background: " + " / ".join(parts)


# ── Fragment generation ────────────────────────────────────────────────────────

def _generate_fragment(
    context: Dict[str, Any],
    existing_ids: set,
    rng: random.Random,
) -> Optional[Dict[str, Any]]:
    """
    Generate one new fragment anchored to the most salient available source.
    Priority: emotional echo > Zeigarnik (goal) > tension > memory echo > associative.
    """
    affect_state = context.get("affect_state") or {}
    core_signals   = affect_state.get("core_signals") or {}

    # Determine dominant emotion (actual state drives content, not perceived)
    active_emos = {
        k: float(v) for k, v in core_signals.items()
        if isinstance(v, (int, float)) and float(v) >= 0.30
        and k not in {"dominant", "affect_stability", "mode", "last_updated",
                      "emotional_congruence", "core_signals"}
    }

    roll = rng.random()

    # Source 1: emotional echo (most common — anchored to current felt state)
    if roll < 0.40 and active_emos:
        dom = max(active_emos, key=active_emos.get)
        templates = _EMOTIONAL_ECHOES.get(dom)
        if templates:
            content  = rng.choice(templates)
            valence  = "negative" if dom in {
                "risk_estimate", "threat_level", "impasse_signal", "negative_valence", "social_penalty",
                "loss_signal", "guilt", "overwhelm", "dread", "social_deficit",
            } else "positive" if dom in {"positive_valence", "wonder", "expected_gain"} else "neutral"
            sticky   = active_emos[dom] >= 0.65  # intense emotions are stickier
            return _make_fragment(content, "emotional_echo", valence,
                                  intensity=min(0.8, active_emos[dom] * 0.9),
                                  sticky=sticky, source=dom)

    # Source 2: Zeigarnik — committed/active goal (unfinished loops surface)
    elif roll < 0.60:
        goal = context.get("committed_goal") or {}
        title = (goal.get("title") or goal.get("name") or "").strip()
        if title:
            content = rng.choice(_ZEIGARNIK_TEMPLATES).format(title=title)
            return _make_fragment(content, "zeigarnik", "neutral",
                                  intensity=0.55, sticky=True, source="goal")

    # Source 3: tension from tensions file
    elif roll < 0.72:
        tension_text = _sample_tension()
        if tension_text:
            content = rng.choice(_TENSION_TEMPLATES).format(tension=tension_text[:60])
            return _make_fragment(content, "zeigarnik", "negative",
                                  intensity=0.50, sticky=True, source="tension")

    # Source 4: recent high-salience working memory event
    elif roll < 0.85:
        wm = context.get("working_memory") or []
        salient = [
            e for e in reversed(wm[-8:])
            if isinstance(e, dict) and int(e.get("importance", 1)) >= 3
            and len(str(e.get("content", ""))) > 20
        ]
        if salient:
            entry   = rng.choice(salient[:3])
            snippet = str(entry.get("content", ""))[:55].rstrip(".,;: ")
            content = rng.choice(_MEMORY_ECHO_TEMPLATES).format(snippet=snippet)
            return _make_fragment(content, "emotional_echo", "neutral",
                                  intensity=0.40, sticky=False, source="working_memory")

    # Source 5: pure associative (the ambient hum between named thoughts)
    else:
        content = rng.choice(_ASSOCIATIVE_POOL)
        return _make_fragment(content, "associative", "neutral",
                              intensity=0.28, sticky=False, source="background")

    return None


def _make_fragment(
    content: str,
    fragment_type: str,
    valence: str,
    intensity: float,
    sticky: bool,
    source: str,
) -> Dict[str, Any]:
    return {
        "id":            str(uuid.uuid4())[:8],
        "content":       content,
        "fragment_type": fragment_type,    # emotional_echo | zeigarnik | associative
        "valence":       valence,          # positive | negative | neutral
        "intensity":     round(intensity, 3),
        "sticky":        sticky,
        "source":        source,
        "suppress_count": 0,
        "last_surfaced": 0,
        "born":          now_iso_z(),
    }


# ── Attention load & surfacing ─────────────────────────────────────────────────

def _attention_load(context: Dict[str, Any]) -> float:
    """
    How much cognitive load is suppressing background thought this cycle.
    Replicates DMN suppression: high task demand → DMN deactivates.
    """
    mode = context.get("attention_mode", "neutral")
    base = _LOAD_BY_MODE.get(mode, 0.45)
    if context.get("attention_constrained"):
        base = min(1.0, base + 0.20)
    return base


def _should_surface(
    fragment: Dict[str, Any],
    attn_load: float,
    rng: random.Random,
) -> bool:
    """
    Probability a fragment surfaces this cycle.
    surface_prob = intensity × (1 - attn_load)
    Higher intensity and lower load → more likely to surface.
    """
    intensity  = float(fragment.get("intensity", 0.3))
    free_bw    = max(0.0, 1.0 - attn_load)
    surface_p  = intensity * free_bw
    return rng.random() < surface_p


# ── Tension sampling ──────────────────────────────────────────────────────────

def _sample_tension() -> Optional[str]:
    """Return a short text snippet from the current tensions file, or None."""
    try:
        tensions = load_json(TENSIONS_FILE, default_type=list)
        if not isinstance(tensions, list) or not tensions:
            return None
        t = random.choice(tensions)
        if isinstance(t, dict):
            return (t.get("statement") or t.get("text") or t.get("tension") or "")[:80]
        return str(t)[:80]
    except Exception:
        return None


# ── Persistence ───────────────────────────────────────────────────────────────

def _load() -> List[Dict[str, Any]]:
    data = load_json(AMBIENT_FRAGMENTS_FILE, default_type=list)
    return data if isinstance(data, list) else []


def _save(fragments: List[Dict[str, Any]]) -> None:
    save_json(AMBIENT_FRAGMENTS_FILE, fragments[-MAX_FRAGMENTS:])



def _get_cycle(context: Dict[str, Any]) -> int:
    cc = context.get("cycle_count") or {}
    if isinstance(cc, dict):
        return int(cc.get("count", 0))
    return int(cc or 0)
