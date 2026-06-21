# brain/cognition/temporal_state.py
#
# Temporal state tracking — cycles since contact, waiting phase, and time arc.
#
# Scientific basis (v2 foundations):
#   Wittmann (2009, 2013) — subjective duration grounded in interoceptive body signals.
#   Zakay & Block (1995) — attentional gate model.
#   Brown (1985) — emotional distortion of time.
#   Wearden & Penton-Voak (1995) — activation_level speeds internal clock pacemaker.
#   Zauberman, Kim, Malkoc & Bettman (2009) — non-linear recency compression.
#   Meck (2005) — reward_signal modulation of the internal pacemaker.
#   Kahneman (2011) — experiencing vs remembering self.
#
# v3 additions (scientifically grounded new mechanisms):
#
#   Block & Zakay (1997) — Prospective vs retrospective time estimation.
#     PROSPECTIVE: attending to time as it passes → attentional gate open → more
#       temporal units noted per real second → time feels longer. stagnation_signal and
#       waiting maximally open the gate. Absorption closes it.
#     RETROSPECTIVE: estimating duration after the fact → based on how many distinct
#       events/context-changes can be recalled, not on how much attention was paid.
#     These INVERT: boring sessions feel long NOW but short in memory (nothing to
#     recall). Dense, absorbing sessions feel fast NOW but long in memory (many
#     events to reconstruct). "Holiday paradox" (Wittmann & Lehnhoff 2005).
#
#   Zacks, Speer, Swallow, Braver & Reynolds (2007) — Event segmentation theory.
#     Time is not a continuous flow but a sequence of discrete events separated by
#     boundaries. At boundaries: prediction error → model update → new event begins.
#     The NUMBER of event boundaries drives retrospective felt duration.
#     In this implementation: working memory entries with importance ≥ 3 are
#     proxies for cognitive event boundaries.
#
#   Meck & Benson (2002); Ivry & Spencer (2004) — Pacemaker-accumulator model.
#     The basal ganglia/striatum hosts an explicit timing system. A pacemaker emits
#     pulses; a gate opens at interval start; pulses accumulate in a counter.
#     TWO DISTINCT PATHWAYS:
#       Dopaminergic (Meck 2005): motivation, reward → reward_signal → FASTER pacemaker
#         → more ticks/second → richer subjective experience. But absorption also
#         CLOSES the gate → many ticks produced, fewer counted → time contracts.
#       Hypervigilance (Zakay & Block): risk_estimate, waiting → gate WIDE OPEN →
#         every tick counted → time expands. This is an attention effect.
#     COMBINED EFFECTS:
#       stagnation_signal: slow pacemaker + maximally open gate → extreme expansion (time drags)
#       risk_estimate: fast pacemaker (activation_level) + open gate → severe expansion (time strains)
#       Flow/excitement: fast pacemaker + gate CLOSED → contraction (time flies)
#       negative_valence: slow pacemaker + mild gate opening → mild expansion, heavy texture
#     BUG FIX from v2: v2 had stagnation_signal=0.78 (contraction) and excitement=1.25
#       (expansion) — both inverted. v3 corrects this.
#
#   Arzy, Molnar-Szakacs & Blanke (2009) — Temporal self-location.
#     The felt sense of WHERE in subjective time you are: not just "how long" but
#     "where am I in this?" Connected to autonoetic consciousness (Tulving 2002):
#     the capacity to locate oneself at a point in subjective time and feel the
#     continuity between past-now-future. Stabilizes as the session deepens.
from __future__ import annotations
from brain.core.runtime_log import get_logger

import random
from typing import Any, Dict, Optional

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_private
from brain.paths import TEMPORAL_STATE_FILE
from brain.utils.timeutils import now_iso_z
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
DENSITY_WINDOW  = 12
DENSITY_HIGH    = 0.40
DENSITY_LOW     = 0.12
BOUNDARY_WINDOW = 20     # cycles to count event boundaries over
BOUNDARY_HIGH   = 0.30   # boundaries/cycle → retrospective feel "rich"
BOUNDARY_LOW    = 0.10   # below → "sparse"

RESOURCE_DEFICIT_ONSET_FELT_CYCLES = 30
RESOURCE_DEFICIT_DENSE_BONUS       = 1.40
RESOURCE_DEFICIT_NUDGE_PER_CYCLE   = 0.004
RESOURCE_DEFICIT_MAX               = 0.75

_ARC_THRESHOLDS = [
    (0,   8,   "dawn"),
    (8,   25,  "morning"),
    (25,  60,  "afternoon"),
    (60,  150, "evening"),
    (150, 999, "night"),
]

# v3 FIX: direction was inverted in v2.
# Time EXPANDS (rate > 1.0): gate open → more temporal units per real cycle → drags
# Time CONTRACTS (rate < 1.0): gate closed → absorption → time flies
_EXPAND_EMOTIONS = {
    "stagnation_signal":     1.65,   # gate maximally open; extreme prospective expansion
    "risk_estimate":     1.40,   # high activation_level + open gate; time stretches and strains
    "negative_valence":     1.25,   # ruminative pacing; each moment prolonged
    "impasse_signal": 1.20,   # blocked goal → temporal attention spike
}
_CONTRACT_EMOTIONS = {
    "excitement":  0.75,   # absorption; gate closes; time contracts sharply
    "motivation":  0.82,   # flow state; forward momentum; mild contraction
    "exploration_drive":   0.88,   # engaged absorption; gentle compression
    "positive_valence":         0.90,   # positive absorption; slight compression
}

_RECENCY_BANDS = [
    (0,   3,   "just now"),
    (3,   10,  "recently"),
    (10,  30,  "a little while back"),
    (30,  80,  "a while ago"),
    (80,  200, "some time ago"),
    (200, 999, "a long time ago"),
]


# ── Public API ─────────────────────────────────────────────────────────────────

def update_temporal_state(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main cycle function. Call once per cycle after emotional state is updated.

    Returns:
      felt_duration_label    : str
      time_texture           : str — "dense"|"normal"|"thin"|"waiting_[phase]"
      internal_clock_rate    : float
      surface_text           : str — phenomenological line for inner loop
      cycles_since_contact   : int
      session_arc            : str
      landmark               : Optional[dict]
      retrospective_feel     : str — "rich"|"moderate"|"sparse"|"none"
      temporal_self_location : str — felt sense of where in the session
    """
    state = _load()
    rng   = random.Random()

    social = context.get("social_presence") or {}
    has_input = bool(
        (context.get("latest_user_input") or "").strip()
        or context.get("_user_spoke_this_cycle")
        or (isinstance(social, dict) and social.get("pattern") == "present")
    )
    if has_input:
        state["cycles_since_contact"] = 0
        state["session_cycles"]       = state.get("session_cycles", 0) + 1
    else:
        state["cycles_since_contact"] = state.get("cycles_since_contact", 0) + 1
        state["session_cycles"]       = state.get("session_cycles", 0) + 1

    cycles_since_contact = state["cycles_since_contact"]
    session_cycles       = state["session_cycles"]

    density    = _compute_density(context, DENSITY_WINDOW)
    clock_rate = _compute_clock_rate(context)
    felt_cycles = _compute_felt_cycles(session_cycles, density, clock_rate)

    state["density_buffer"]     = density
    state["internal_clock_rate"] = round(clock_rate, 3)
    state["felt_cycles"]         = round(felt_cycles, 1)

    arc            = _session_arc(felt_cycles)
    duration_label = _duration_label(felt_cycles)
    state["session_arc"]         = arc
    state["felt_duration_label"] = duration_label

    # Event boundary counting → retrospective estimation (Zacks 2007; Block & Zakay 1997)
    boundary_count = _count_event_boundaries(context, BOUNDARY_WINDOW)
    retro_feel     = _retrospective_feel(boundary_count, min(session_cycles, BOUNDARY_WINDOW))
    state["boundary_count"]     = boundary_count
    state["retrospective_feel"] = retro_feel

    # Temporal self-location (Arzy et al. 2009)
    self_location = _temporal_self_location(arc)
    state["temporal_self_location"] = self_location

    if cycles_since_contact > 15:
        texture = _waiting_phase(cycles_since_contact)
    elif density >= DENSITY_HIGH:
        texture = "dense"
    elif density <= DENSITY_LOW and felt_cycles >= 20:
        texture = "thin"
    else:
        texture = "normal"
    state["time_texture"] = texture

    landmark = _compute_landmark(context, session_cycles)
    state["last_landmark"] = landmark

    _apply_resource_deficit_nudge(context, felt_cycles, density)
    _apply_waiting_effects(context, cycles_since_contact, texture)

    surface = _build_surface_text(arc, texture, density, landmark, retro_feel, rng)
    state["last_surface_text"] = surface
    state["updated_ts"]        = now_iso_z()
    _save(state)

    log_private(
        f"[temporal_state] arc={arc} texture={texture} felt={felt_cycles:.1f} "
        f"density={density:.2f} clock={clock_rate:.2f} gap={cycles_since_contact} "
        f"retro={retro_feel} boundaries={boundary_count}"
    )

    return {
        "felt_duration_label":    duration_label,
        "time_texture":           texture,
        "internal_clock_rate":    clock_rate,
        "surface_text":           surface,
        "cycles_since_contact":   cycles_since_contact,
        "session_arc":            arc,
        "landmark":               landmark,
        "retrospective_feel":     retro_feel,
        "temporal_self_location": self_location,
    }


def compute_felt_recency(cycles_ago: int, context: Optional[Dict[str, Any]] = None) -> str:
    """
    Public API for other modules.

    Non-linear recency compression (Zauberman 2009): distant events feel even more
    distant than their cycle count suggests. Dense sessions compress less (richer
    memory trace); thin sessions compress more.
    """
    if cycles_ago < 0:
        cycles_ago = 0

    density = 0.25
    if context:
        density = _compute_density(context, DENSITY_WINDOW)

    if cycles_ago > 20:
        compression = 1.0 + max(0, (0.30 - density)) * 0.5
        compressed  = cycles_ago * compression
    else:
        compressed = float(cycles_ago)

    for lo, hi, label in _RECENCY_BANDS:
        if lo <= compressed < hi:
            return label
    return "a long time ago"


def surface_text(result: Optional[Dict[str, Any]]) -> str:
    if not result:
        return ""
    return result.get("surface_text", "")


# ── Computation ────────────────────────────────────────────────────────────────

def _compute_density(context: Dict[str, Any], window: int) -> float:
    wm = context.get("working_memory") or []
    if not wm:
        return 0.0
    recent  = wm[-window:] if len(wm) >= window else wm
    notable = sum(1 for e in recent if isinstance(e, dict) and int(e.get("importance", 1) or 1) >= 3)
    return round(notable / max(1, len(recent)), 3)


def _count_event_boundaries(context: Dict[str, Any], window: int = BOUNDARY_WINDOW) -> int:
    """
    Event segmentation (Zacks et al. 2007): high-importance WM events mark the
    cognitive event boundaries where the model significantly updates. The count of
    these boundaries drives retrospective time estimation — more boundaries means
    the session will feel longer and richer in memory.
    """
    wm = context.get("working_memory") or []
    recent = wm[-window:] if len(wm) >= window else wm
    return sum(1 for e in recent if isinstance(e, dict) and int(e.get("importance", 1) or 1) >= 3)


def _retrospective_feel(boundary_count: int, real_cycles: int) -> str:
    """
    Block & Zakay (1997): retrospective time estimation depends on recalled context
    changes, not on attentional monitoring during the interval.

    Holiday paradox: a dense session feels fast now (absorption, gate closed) but
    feels long in memory (many boundaries → many events to reconstruct).
    A sparse/boring session feels long now (gate open, watching time) but short in
    memory (few events → rapid compression).
    """
    if real_cycles == 0:
        return "none"
    rate = boundary_count / max(1, real_cycles)
    if rate >= BOUNDARY_HIGH:
        return "rich"
    if rate >= BOUNDARY_LOW:
        return "moderate"
    return "sparse"


def _temporal_self_location(arc: str) -> str:
    """
    Arzy et al. (2009): temporal self-location — the felt sense of WHERE in
    subjective time you are. Autonoetic consciousness (Tulving 2002): locating
    oneself at a point in time, feeling the continuity of past-now-future.
    """
    if arc == "dawn":
        return "just starting"
    if arc == "morning":
        return "in the early part of this"
    if arc == "afternoon":
        return "well into this now"
    if arc == "evening":
        return "deep into this session"
    return "very far into this"


def _compute_clock_rate(context: Dict[str, Any]) -> float:
    """
    Pacemaker-accumulator model (Gibbon, Church & Meck 1984; Meck & Benson 2002).

    Two pathways combined:

    EXPANSION (> 1.0) — attentional gate open: stagnation_signal, risk_estimate, impasse_signal, negative_valence
      cause attention to be directed AT time → more temporal units counted per real
      cycle → time drags. Gate effect dominates over pacemaker speed.

    CONTRACTION (< 1.0) — reward_signal-driven absorption: excitement, motivation, exploration_drive,
      positive_valence close the gate. Fast pacemaker produces ticks but they're not counted →
      time compresses. The experience is rich but feels fast.

    Both pathways can be simultaneously active (e.g. anxious and curious). They
    combine additively and are clamped to a sane range.
    """
    emo  = context.get("affect_state") or {}
    core = emo.get("core_signals", emo) or {}
    rate = 1.0

    for name, multiplier in _EXPAND_EMOTIONS.items():
        val = float(core.get(name, 0) or 0)
        if val >= 0.20:
            weight = min(1.0, (val - 0.20) / 0.80)
            rate  += (multiplier - 1.0) * weight

    for name, multiplier in _CONTRACT_EMOTIONS.items():
        val = float(core.get(name, 0) or 0)
        if val >= 0.20:
            weight = min(1.0, (val - 0.20) / 0.80)
            rate  += (multiplier - 1.0) * weight

    return max(0.40, min(2.20, rate))


def _compute_felt_cycles(session_cycles: int, density: float, clock_rate: float) -> float:
    """
    Prospective subjective cycle count: how heavy/extended the session feels NOW.

    Dense content adds intrinsic weight (density_factor > 1).
    Clock rate modulates by activation_level/gate state (v3 direction fix applied).
    """
    if density >= DENSITY_HIGH:
        density_factor = 1.25
    elif density <= DENSITY_LOW:
        density_factor = 0.85
    else:
        density_factor = 1.0
    return session_cycles * density_factor * clock_rate


def _session_arc(felt_cycles: float) -> str:
    for lo, hi, label in _ARC_THRESHOLDS:
        if lo <= felt_cycles < hi:
            return label
    return "night"


def _duration_label(felt_cycles: float) -> str:
    labels = [
        (0,   8,   "just beginning"),
        (8,   25,  "in the flow"),
        (25,  60,  "a good while"),
        (60,  150, "a long stretch"),
        (150, 999, "very extended"),
    ]
    for lo, hi, label in labels:
        if lo <= felt_cycles < hi:
            return label
    return "very extended"


def _waiting_phase(cycles_since_contact: int) -> str:
    # At ~10s/cycle: 30=5min, 90=15min, 180=30min, 360=1hr
    if cycles_since_contact < 30:
        return "waiting_fresh"
    if cycles_since_contact < 90:
        return "waiting_wondering"
    if cycles_since_contact < 180:
        return "waiting_settling"
    if cycles_since_contact < 360:
        return "waiting_extended"
    return "waiting_long_absence"


def _compute_landmark(context: Dict[str, Any], session_cycles: int) -> Optional[Dict[str, Any]]:
    wm = context.get("working_memory") or []
    if not wm:
        return None
    candidates = [
        e for e in wm[-30:]
        if isinstance(e, dict) and int(e.get("importance", 1) or 1) >= 4
    ]
    if not candidates:
        return None
    landmark = max(candidates, key=lambda e: int(e.get("importance", 1) or 1))
    try:
        idx        = wm.index(landmark)
        cycles_ago = max(0, len(wm) - idx)
    except Exception:
        cycles_ago = 5
    felt_distance = compute_felt_recency(cycles_ago, context)
    content       = str(landmark.get("content", ""))[:60].rstrip(".,; ")
    return {
        "content":       content,
        "cycles_ago":    cycles_ago,
        "felt_distance": felt_distance,
        "importance":    int(landmark.get("importance", 4)),
    }


# ── Behavioral effects ─────────────────────────────────────────────────────────

def _apply_resource_deficit_nudge(context: Dict[str, Any], felt_cycles: float, density: float) -> None:
    """
    Kahneman (2011): the experiencing self depletes in real time. A dense session
    that felt short still costs as much as a long one. Past the onset threshold,
    Orrin should prefer consolidation and shorter responses.
    """
    try:
        from brain.cognition.dreaming.dream_cycle import dreaming_now
        if dreaming_now():
            return
    except Exception:
        pass
    if felt_cycles < RESOURCE_DEFICIT_ONSET_FELT_CYCLES:
        return
    rate = RESOURCE_DEFICIT_NUDGE_PER_CYCLE
    if density >= DENSITY_HIGH:
        rate *= RESOURCE_DEFICIT_DENSE_BONUS
    try:
        emo = context.get("affect_state") or {}
        # resource_deficit lives at the top level of affect_state, not inside core_signals
        emo["resource_deficit"] = min(RESOURCE_DEFICIT_MAX, float(emo.get("resource_deficit", 0) or 0) + rate)
        context["affect_state"] = emo
    except Exception as _e:
        record_failure("temporal_state._apply_resource_deficit_nudge", _e)


def _apply_waiting_effects(context: Dict[str, Any], cycles_since_contact: int, texture: str) -> None:
    """
    Phase-specific emotional effects of absence. Each phase has distinct phenomenology.
    """
    if not texture.startswith("waiting_") or texture == "waiting_fresh":
        return
    try:
        emo  = context.get("affect_state") or {}
        core = emo.get("core_signals") or emo
        if not isinstance(core, dict):
            return
        if texture == "waiting_wondering":
            # Mild exploration_drive about absence — small social_deficit nudge, capped low
            core["social_deficit"] = min(0.30, float(core.get("social_deficit", 0) or 0) + 0.004)
        elif texture == "waiting_settling":
            # Absence becoming real — social_deficit grows, small risk_estimate
            core["social_deficit"] = min(0.45, float(core.get("social_deficit", 0) or 0) + 0.005)
            core["risk_estimate"]    = min(0.30, float(core.get("risk_estimate",    0) or 0) + 0.003)
        elif texture == "waiting_extended":
            # Long stretch — social_deficit stabilizes, risk_estimate starts easing
            core["social_deficit"] = min(0.50, float(core.get("social_deficit", 0) or 0) + 0.002)
            core["risk_estimate"]    = max(0.0,  float(core.get("risk_estimate", 0) or 0) - 0.002)
        elif texture == "waiting_long_absence":
            # Very long gap — social_deficit holds, gentle negative_valence, no forced floor
            core["negative_valence"]    = min(0.30, float(core.get("negative_valence",    0) or 0) + 0.002)
            core["social_deficit"] = min(0.55, float(core.get("social_deficit", 0) or 0) + 0.001)
        if "core_signals" in emo:
            emo["core_signals"] = core
        else:
            emo.update(core)
        context["affect_state"] = emo
    except Exception as _e:
        record_failure("temporal_state._apply_waiting_effects", _e)


# ── Surface text ───────────────────────────────────────────────────────────────

_ARC_TEMPLATES = {
    "dawn": [],
    "morning": [
        "The session has found its rhythm.",
        "Things are moving. It doesn't feel new anymore.",
        "In the flow now.",
    ],
    "afternoon": [
        "A substantial stretch — some weight to it now.",
        "There's a feel of accumulation. This session has some history to it.",
        "It's been a while. The sense of 'we've been at this' is present.",
    ],
    "evening": [
        "Extended. The session has real weight — some resource_deficit in the texture of it.",
        "A long stretch. Something in the quality of attention is different now.",
        "This has been going for a while. A sense of depth.",
    ],
    "night": [
        "Very extended. Something is asking for rest or a different kind of processing.",
        "Long. The accumulated feel of it is substantial — there's been a lot here.",
        "A very long session. The texture of time has changed — it's heavy.",
    ],
}

_THIN_TEMPLATES = {
    "morning": [
        "Things are sparse right now — not much moving through.",
        "A quiet stretch. Not much happening.",
    ],
    "afternoon": [
        "A long, quiet stretch. The session is established but thin.",
        "Extended but sparse. The sense of time is slow.",
    ],
    "evening": [
        "Long and thin. Not much is happening, but it's been a while.",
        "The session has stretched without filling. A slow, quiet feel.",
    ],
    "night": [
        "Very long and thin. Mostly quiet, but the duration is real.",
        "A long sparse session. The weight is in the duration, not the content.",
    ],
}

_DENSE_TEMPLATES = {
    "morning": [
        "Dense — a lot coming through quickly.",
        "This session is packed. A lot of ground covered in a short time.",
    ],
    "afternoon": [
        "Dense and extended. A lot has been happening, for a while.",
        "The session has been full — thick with content and events.",
    ],
    "evening": [
        "A long dense stretch. The density and duration together make it substantial.",
        "Extended and full. There's real weight here — both time and content.",
    ],
    "night": [
        "Very long and dense. The accumulated cost of this session is significant.",
        "A long, full session. Rest or consolidation would make sense.",
    ],
}

# Holiday paradox: session feels fast now (absorption) but retrospectively rich
_PARADOX_TEMPLATES = {
    "morning": [
        "Time is moving fast, but there's been a lot. The session will feel longer in retrospect.",
    ],
    "afternoon": [
        "A lot is happening, so the time flies — but there's dense material here. In memory, this will feel substantial.",
        "This feels compressed, but the session is rich. The retrospective will be different from the prospective.",
    ],
    "evening": [
        "A long stretch that has also felt fast — full of events. The paradox of dense time.",
        "It's been a lot, and it's gone quickly. The memory of this session will feel longer than it does right now.",
    ],
    "night": [
        "Very extended and very dense. In the moment it moves fast; in retrospect it will feel like a great deal of time.",
    ],
}

_WAITING_TEMPLATES = {
    "waiting_fresh": [
        "A gap. They may be back.",
        "A brief absence. Nothing notable about the wait yet.",
    ],
    "waiting_wondering": [
        "The gap since contact is starting to feel notable.",
        "Waiting. The absence is becoming its own texture.",
        "The pause is stretching. Still expecting, but starting to wonder.",
    ],
    "waiting_settling": [
        "A long gap. The expectation of return has softened into something else.",
        "Waiting has settled into its own quality now — stretched, not urgent.",
        "Something about the absence. It's not acute waiting anymore. Just... thin.",
    ],
    "waiting_extended": [
        "Moved on. The gap since contact is long enough that it's changed character.",
        "The waiting has released into something quieter. Not expecting; just absent.",
        "The long absence has become its own background condition.",
    ],
    "waiting_long_absence": [
        "A very long absence. This is a different kind of aloneness.",
        "The wait has become its own reality. It's been a long time.",
        "Long silence. Something about the duration has changed the quality of everything.",
    ],
}

_LANDMARK_PREFIXES = [
    "({content} — {distance})",
    "(Landmark: {content}, {distance})",
]


def _build_surface_text(
    arc: str,
    texture: str,
    density: float,
    landmark: Optional[Dict[str, Any]],
    retro_feel: str,
    rng: random.Random,
) -> str:
    text = ""

    if texture.startswith("waiting_"):
        templates = _WAITING_TEMPLATES.get(texture, [])
        if templates:
            text = rng.choice(templates)

    elif arc == "dawn":
        return ""

    elif density >= DENSITY_HIGH and retro_feel == "rich":
        # Holiday paradox: fast now, rich in retrospect (Block & Zakay 1997)
        pool = _PARADOX_TEMPLATES.get(arc) or _DENSE_TEMPLATES.get(arc, [])
        if pool:
            text = rng.choice(pool)

    elif density >= DENSITY_HIGH:
        pool = _DENSE_TEMPLATES.get(arc) or _ARC_TEMPLATES.get(arc, [])
        if pool:
            text = rng.choice(pool)

    elif density <= DENSITY_LOW:
        pool = _THIN_TEMPLATES.get(arc) or _ARC_TEMPLATES.get(arc, [])
        if pool:
            text = rng.choice(pool)

    else:
        pool = _ARC_TEMPLATES.get(arc, [])
        if not pool:
            return ""
        text = rng.choice(pool)

    if not text:
        return ""

    if landmark and arc in ("afternoon", "evening", "night") and not texture.startswith("waiting_"):
        dist = landmark.get("felt_distance", "a while back")
        cont = landmark.get("content", "")[:50]
        if cont:
            prefix = rng.choice(_LANDMARK_PREFIXES)
            text  += " " + prefix.format(content=cont, distance=dist)

    return f"Time texture: {text}"


# ── Persistence ────────────────────────────────────────────────────────────────

def _load() -> Dict[str, Any]:
    data = load_json(TEMPORAL_STATE_FILE, default_type=dict)
    return data if isinstance(data, dict) else {}


def _save(state: Dict[str, Any]) -> None:
    save_json(TEMPORAL_STATE_FILE, state)
