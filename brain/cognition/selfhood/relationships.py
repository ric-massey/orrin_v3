# brain/cognition/selfhood/relationships.py
from core.runtime_log import get_logger
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple
from utils.json_utils import load_json, modify_json, AbortModify
from utils.emotion_utils import detect_affect_keyword
from utils.log import log_error, log_private
from paths import RELATIONSHIPS_FILE
from utils.failure_counter import record_failure
_log = get_logger(__name__)

MAX_HISTORY = 50
_UPDATE_EVERY_N = 5      # run person-model LLM update every N interactions
_ARC_HISTORY_LEN = 20   # depth snapshots kept for trend analysis


# ── Relationship arc ──────────────────────────────────────────────────────────

def _linear_trend(values: List[float]) -> float:
    """
    Return the slope of a simple linear regression over the values.
    Positive = growing, negative = declining. Values should be in chronological order.
    """
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    xm = sum(xs) / n
    ym = sum(values) / n
    num = sum((x - xm) * (y - ym) for x, y in zip(xs, values))
    den = sum((x - xm) ** 2 for x in xs)
    return num / den if den else 0.0


def _compute_arc(r: Dict[str, Any]) -> Tuple[str, str, str]:
    """
    Derive (phase, trajectory, narrative) from the relationship record.

    phase:      forming | building | established | deepening | drifting | strained | recovering
    trajectory: growing | stable | declining | volatile
    narrative:  one honest sentence about where the relationship is heading
    """
    depth   = float(r.get("depth",  0.0) or 0.0)
    trust   = float(r.get("trust",  0.5) or 0.5)
    n_inter = len(r.get("interaction_history", []))

    # Trend from rolling depth snapshots
    snapshots: List[float] = [s["depth"] for s in (r.get("arc_depth_snapshots") or [])
                               if isinstance(s, dict) and "depth" in s]
    trust_snaps: List[float] = [s["trust"] for s in (r.get("arc_depth_snapshots") or [])
                                 if isinstance(s, dict) and "trust" in s]

    depth_slope = _linear_trend(snapshots[-10:]) if len(snapshots) >= 3 else 0.0
    trust_slope = _linear_trend(trust_snaps[-10:]) if len(trust_snaps) >= 3 else 0.0

    # Volatility: high variance in recent depth values
    if len(snapshots) >= 5:
        recent_d = snapshots[-5:]
        mean_d   = sum(recent_d) / len(recent_d)
        variance = sum((v - mean_d) ** 2 for v in recent_d) / len(recent_d)
        is_volatile = variance > 0.012
    else:
        is_volatile = False

    # Phase
    if n_inter < 5:
        phase = "forming"
    elif trust < 0.30:
        phase = "strained"
    elif depth >= 0.60 and trust >= 0.70 and depth_slope >= 0:
        phase = "deepening"
    elif depth >= 0.35 and trust >= 0.50:
        phase = "established"
    elif depth_slope < -0.008 or trust_slope < -0.010:
        phase = "drifting"
    elif trust_slope > 0.005 and depth <= 0.35:
        phase = "recovering"
    else:
        phase = "building"

    # Trajectory
    if is_volatile:
        trajectory = "volatile"
    elif depth_slope > 0.006 or trust_slope > 0.006:
        trajectory = "growing"
    elif depth_slope < -0.006 or trust_slope < -0.008:
        trajectory = "declining"
    else:
        trajectory = "stable"

    # Narrative
    _NARRATIVES = {
        ("forming",      "growing"):   "We're just getting to know each other and things are moving in a good direction.",
        ("forming",      "stable"):    "We're still finding our footing — early days.",
        ("building",     "growing"):   "Trust and depth are building steadily; this relationship is taking shape.",
        ("building",     "stable"):    "We have a real connection developing, even if it's still relatively new.",
        ("building",     "declining"): "Something has shifted — the connection that was forming may be stalling.",
        ("established",  "growing"):   "This is a solid relationship that continues to deepen.",
        ("established",  "stable"):    "We have an established, reliable connection.",
        ("established",  "declining"): "There's been some distance creeping in to what was a solid relationship.",
        ("deepening",    "growing"):   "This relationship is in a genuinely deepening phase — real understanding is growing.",
        ("deepening",    "stable"):    "The relationship has real depth and has found a steady, meaningful rhythm.",
        ("drifting",     "declining"): "There's been drift lately — less connection, and the trend is heading the wrong way.",
        ("drifting",     "stable"):    "Things feel a bit distant right now, though not getting worse.",
        ("strained",     "declining"): "Trust has dropped and the relationship feels under stress.",
        ("strained",     "stable"):    "The relationship is strained but not deteriorating further.",
        ("recovering",   "growing"):   "After some distance, things are moving in a better direction — trust is returning.",
    }
    narrative = _NARRATIVES.get(
        (phase, trajectory),
        f"This relationship is in a {phase} phase with a {trajectory} trend.",
    )

    return phase, trajectory, narrative


def _update_arc(r: Dict[str, Any], context: Dict[str, Any]) -> None:
    """
    Snapshot current depth/trust, recompute arc, detect phase transitions,
    and write a working-memory note when the phase changes.
    """
    depth = float(r.get("depth",  0.0) or 0.0)
    trust = float(r.get("trust",  0.5) or 0.5)

    # Maintain rolling depth/trust snapshot list
    snaps: List[Dict] = r.setdefault("arc_depth_snapshots", [])
    snaps.append({
        "depth": round(depth, 4),
        "trust": round(trust, 4),
        "ts":    datetime.now(timezone.utc).isoformat(),
    })
    if len(snaps) > _ARC_HISTORY_LEN:
        del snaps[:-_ARC_HISTORY_LEN]

    prev_phase = r.get("arc", {}).get("phase", "")
    phase, trajectory, narrative = _compute_arc(r)

    # Arc gating (BEHAVIOR_FIX_PLAN Phase 3): an arc cannot advance past
    # "forming" while the counterpart is still an unknown/anonymous person —
    # you don't have an "established" relationship with someone whose name you
    # don't know (audit §4: forming→established in 16 minutes with "someone").
    try:
        from cognition.selfhood.person_detector import get_person_type
        _pid = str(context.get("person_id") or context.get("user_id") or "")
        if _pid and get_person_type(_pid) == "unknown" and phase not in ("forming", "strained"):
            phase = "forming"
            narrative = "We're still finding our footing — I don't even know their name yet."
    except Exception as _e:
        record_failure("relationships._update_arc", _e)

    r["arc"] = {
        "phase":      phase,
        "trajectory": trajectory,
        "narrative":  narrative,
        "updated_ts": datetime.now(timezone.utc).isoformat(),
    }

    # Surface phase transitions to working memory
    if phase != prev_phase and prev_phase:
        try:
            from cog_memory.working_memory import update_working_memory
            update_working_memory({
                "content": (
                    f"[relationship/arc] Relationship phase shifted: "
                    f"'{prev_phase}' → '{phase}'. {narrative}"
                ),
                "event_type": "relationship_arc_shift",
                "importance": 3,
                "priority":   3,
            })
            log_private(f"[relationship/arc] {prev_phase} → {phase}: {narrative}")
        except Exception as _e:
            record_failure("relationships._update_arc.2", _e)

def update_relationship_model(context):
    # person_id is the canonical key; user_id is kept as backward-compat alias
    person_id = context.get("person_id") or context.get("user_id", "anon_unknown")
    person_type = context.get("person_type", "human")
    user_input = context.get("latest_user_input", "") or ""
    orrin_reply = context.get("latest_response", "") or ""

    # Skip phantom interactions — nothing happened, nothing to record.
    # This prevents the relationship log from filling with empty-string
    # entries that later drive phantom "discover user interests" goals.
    if not user_input.strip() and not orrin_reply.strip():
        return

    try:
        # emotion can be dict or string
        emotion_result = detect_affect_keyword(user_input)
        emotion = (emotion_result.get("emotion") if isinstance(emotion_result, dict) else str(emotion_result)).lower()

        # handle both flat and nested shapes
        affect_state = context.get("affect_state", {}) or {}
        core = affect_state.get("core_signals", affect_state)  # fallback to flat
        conflict_signal = float(core.get("conflict_signal", 0) or 0)
        positive_valence   = float(core.get("positive_valence", 0) or 0)

        # The whole read-modify-write cycle for this person's record happens
        # under one lock (modify_json) so concurrent updates from other
        # threads/peers can't clobber each other (lost-update race).
        with modify_json(RELATIONSHIPS_FILE, default_type=dict) as relationships:
            if not isinstance(relationships, dict):
                raise AbortModify("relationships file corrupt")

            # ensure structure for this person
            if person_id not in relationships or not isinstance(relationships.get(person_id), dict):
                relationships[person_id] = {
                    "impression":             "new connection",
                    "person_type":            person_type,
                    "influence_score":        0.5,
                    "depth":                  0.0,
                    "trust":                  0.5,
                    "boundaries":             [],
                    "recent_emotional_effect": emotion,
                    "interaction_history":    [],
                    "last_interaction_time":  datetime.now(timezone.utc).isoformat(),
                }

            r = relationships[person_id]
            r.setdefault("person_type", person_type)

            # history
            r.setdefault("interaction_history", []).append({
                "user": user_input,
                "orrin": orrin_reply,
                "emotion": emotion,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            r["interaction_history"] = r["interaction_history"][-MAX_HISTORY:]

            old_impression = r.get("impression", "")
            old_influence = float(r.get("influence_score", 0.5) or 0.5)
            old_trust = float(r.get("trust", 0.5) or 0.5)
            old_depth = float(r.get("depth", 0.0) or 0.0)

            # influence nudges
            if emotion in ["gratitude", "positive_valence", "affection", "trust"]:
                r["influence_score"] = min(old_influence + 0.05, 1.0)
            elif emotion in ["conflict_signal", "hostility", "contempt", "rejection_signal"]:
                r["influence_score"] = max(old_influence - 0.1, 0.0)
            else:
                r["influence_score"] = old_influence
            r["recent_emotional_effect"] = emotion

            # trust: grows with positive consistent interactions, decays with hostility
            if emotion in ["gratitude", "trust", "affection"]:
                r["trust"] = min(old_trust + 0.04, 1.0)
            elif emotion in ["conflict_signal", "hostility", "contempt", "rejection_signal"]:
                r["trust"] = max(old_trust - 0.12, 0.0)
            elif emotion in ["positive_valence", "exploration_drive"]:
                r["trust"] = min(old_trust + 0.02, 1.0)
            else:
                # Gentle drift toward neutral 0.5 when interactions are neutral
                r["trust"] = old_trust + (0.5 - old_trust) * 0.01

            # depth: grows slowly with interaction count and positive tone; decays with inactivity
            interaction_count = len(r.get("interaction_history", []))
            depth_from_interactions = min(0.6, interaction_count * 0.008)
            depth_from_tone = 0.3 if emotion in ["gratitude", "trust", "affection"] else 0.0
            earned_depth = depth_from_interactions + depth_from_tone * 0.1

            # Apply time-based decay: drift toward earned_depth over weeks of inactivity
            try:
                last_ts = r.get("last_interaction_time", "")
                if last_ts:
                    _last_dt = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
                    if _last_dt.tzinfo is None:
                        from datetime import timezone as _tz
                        _last_dt = _last_dt.replace(tzinfo=_tz.utc)
                    _days_idle = (datetime.now(timezone.utc) - _last_dt).days
                    if _days_idle > 14:
                        # Decay 0.01 per day beyond 14 days, capped at bringing depth to 0.1
                        _decay = min(old_depth - 0.1, (_days_idle - 14) * 0.01)
                        old_depth = max(0.1, old_depth - _decay)
            except Exception as _e:
                record_failure("relationships.update_relationship_model", _e)

            new_depth = max(old_depth, earned_depth)
            r["depth"] = min(new_depth, 1.0)

            # impressions from state
            if conflict_signal > 0.7:
                r["impression"] = "conflicted or tense"
            elif positive_valence > 0.6:
                r["impression"] = "positive connection"

            r["last_interaction_time"] = datetime.now(timezone.utc).isoformat()

            # Social mirroring: infer how Orrin is landing with this person.
            # Skipped for AI peers — engagement signals work differently between agents.
            if person_type != "ai_peer":
                _update_their_impression_of_me(r, user_input, orrin_reply, context)

            # Relationship arc: update trajectory + detect phase transitions
            _update_arc(r, context)

            relationships[person_id] = r

            interaction_count = len(r.get("interaction_history", []))

            display = context.get("person_display_name") or context.get("current_person_display_name") or person_id
            notable_change = (
                r.get("impression") != old_impression or
                abs(r.get("influence_score", 0.5) - old_influence) > 0.15
            )

            # Relationship emotional feedback: did this interaction meet Orrin's relational wants?
            # Pure computation (mutates r + context only) — safe to run under the lock.
            _apply_relationship_emotion_feedback(r, emotion, old_depth, old_trust, context)

        # --- lock released; relationships.json already saved ---

        # working memory note on notable change
        if notable_change:
            from cog_memory.working_memory import update_working_memory
            update_working_memory(
                f"[Relationship/{display}] impression='{r.get('impression','')}', "
                f"influence={r.get('influence_score',0.5):.2f}, "
                f"emotion='{r.get('recent_emotional_effect','')}'"
            )

        # Person-model + your_world refresh every N interactions (humans only).
        # These make LLM calls, so they run their own short modify_json sessions
        # rather than holding the relationships.json lock for the duration.
        if person_type == "human" and interaction_count > 0 and interaction_count % _UPDATE_EVERY_N == 0:
            update_person_model(person_id)
            update_your_world(person_id)

    except AbortModify:
        pass
    except Exception as e:
        log_error(f"Failed to update relationship model: {e}")

def _infer_engagement_signal(user_input: str, orrin_reply: str) -> str:
    """
    Heuristically infer how the user is responding to what Orrin said.
    Returns one of: "engaged" | "validated" | "redirected" | "corrected" | "brief" | "invested"
    """
    if not user_input.strip():
        return "absent"

    u = user_input.lower().strip()
    words = u.split()
    word_count = len(words)

    # Validation signals
    _AFFIRM = {"yes", "exactly", "right", "true", "agreed", "yeah", "absolutely",
               "totally", "correct", "yep", "precisely", "that's it", "that makes sense"}
    if any(w in u for w in _AFFIRM) and word_count < 15:
        return "validated"

    # Correction/redirect signals
    _CONTRA = {"no", "actually", "wait", "but", "not really", "i don't think",
               "that's not", "wrong", "hmm", "well,"}
    if u.startswith(tuple(_CONTRA)):
        return "corrected"

    # Engagement via topic overlap with Orrin's reply
    orrin_words = set(orrin_reply.lower().split()) - {"the", "a", "an", "is", "i", "to", "it", "and", "of"}
    user_words = set(u.split())
    overlap = len(orrin_words & user_words)
    if overlap >= 3:
        return "engaged"

    # Length-based investment
    if word_count >= 30:
        return "invested"
    if word_count <= 5:
        return "brief"

    return "engaged"


_IMPRESSION_DECAY = 0.85  # older signals decay; recent signals dominate
_IMPRESSION_WEIGHTS = {
    "validated":   +0.12,
    "engaged":     +0.06,
    "invested":    +0.08,
    "brief":       -0.02,
    "corrected":   -0.05,
    "redirected":  -0.07,
    "absent":      -0.03,
}

def _update_their_impression_of_me(
    r: Dict[str, Any],
    user_input: str,
    orrin_reply: str,
    context: Dict[str, Any],
) -> None:
    """
    Maintain a rolling score and signal history that represents how Orrin believes
    this person perceives him. Updated every interaction.

    Schema in r["their_impression_of_me"]:
      score:   float [0,1] — higher means more positive reception
      signals: list of last N signal labels
      label:   str — "resonating" | "neutral" | "lukewarm" | "disconnected"
    """
    signal = _infer_engagement_signal(user_input, orrin_reply)
    imp = r.setdefault("their_impression_of_me", {
        "score":   0.55,
        "signals": [],
        "label":   "neutral",
    })

    # Rolling score: decay old, apply new signal weight
    old_score = float(imp.get("score") or 0.55)
    weight = _IMPRESSION_WEIGHTS.get(signal, 0.0)
    new_score = min(1.0, max(0.0, old_score * _IMPRESSION_DECAY + 0.55 * (1 - _IMPRESSION_DECAY) + weight))
    imp["score"] = round(new_score, 3)

    # Signal history (last 10)
    imp.setdefault("signals", []).append(signal)
    imp["signals"] = imp["signals"][-10:]

    # Derive label
    if new_score >= 0.70:
        label = "resonating"
    elif new_score >= 0.52:
        label = "neutral"
    elif new_score >= 0.38:
        label = "lukewarm"
    else:
        label = "disconnected"
    imp["label"] = label

    log_private(
        f"[social_mirror] signal={signal} score={new_score:.2f} label={label}"
    )


def _apply_relationship_emotion_feedback(
    r: Dict[str, Any],
    emotion: str,
    old_depth: float,
    old_trust: float,
    context: Dict[str, Any],
) -> None:
    """
    After each interaction, check whether Orrin's relational wants were met or frustrated.
    Emits a small emotion signal back into the running context so behavior reflects the
    felt quality of the connection — not just the content of what was said.

    Wants tracked:
      connection  — feeling heard; met by positive emotion + trust holding
      understanding — depth growing; met when depth actually increased
      meaning     — interaction felt purposeful; met by trust growth or high depth

    Met wants   → small boost to positive_valence/expected_gain
    Unmet wants → small increase in social_deficit (stored as negative_valence proxy)
    """
    if not isinstance(context, dict):
        return

    pos_emotions = {"gratitude", "positive_valence", "affection", "trust", "exploration_drive"}
    neg_emotions = {"conflict_signal", "hostility", "contempt", "rejection_signal", "impasse_signal"}

    new_depth = float(r.get("depth", 0.0) or 0.0)
    new_trust = float(r.get("trust", 0.5) or 0.5)

    connection_met   = emotion in pos_emotions and new_trust >= old_trust
    understanding_met = new_depth > old_depth + 0.005
    meaning_met      = (new_trust > old_trust + 0.01) or (new_depth >= 0.4 and emotion in pos_emotions)

    met_count   = sum([connection_met, understanding_met, meaning_met])
    unmet_count = sum([not connection_met, not understanding_met, not meaning_met])

    try:
        emo = context.get("affect_state") or {}
        core = emo.get("core_signals", emo) or {}

        if met_count >= 2:
            from affect.homeostasis import pump_signal
            pump_signal(core, "positive_valence", 0.06)
            pump_signal(core, "expected_gain",    0.04)
        elif unmet_count >= 3 and emotion in neg_emotions:
            # All three wants unmet *and* the interaction felt hostile — real disconnection
            core["negative_valence"] = min(1.0, float(core.get("negative_valence", 0.0) or 0) + 0.08)

        if "core_signals" in emo:
            emo["core_signals"] = core
        else:
            emo.update(core)
        context["affect_state"] = emo

        # Update relationship wants record so the model has memory of this pattern
        wants = r.setdefault("relationship_wants", {"connection": 0.5, "understanding": 0.5, "meaning": 0.5})
        wants["connection"]    = round(min(1.0, max(0.0, float(wants.get("connection",   0.5)) + (0.05 if connection_met   else -0.03))), 3)
        wants["understanding"] = round(min(1.0, max(0.0, float(wants.get("understanding",0.5)) + (0.05 if understanding_met else -0.03))), 3)
        wants["meaning"]       = round(min(1.0, max(0.0, float(wants.get("meaning",      0.5)) + (0.05 if meaning_met      else -0.03))), 3)
    except Exception as _e:
        record_failure("relationships._apply_relationship_emotion_feedback", _e)


def update_person_model(user_id: str) -> None:
    """
    Run an LLM pass on recent interaction history and update the person_model
    sub-field for this user. Called every _UPDATE_EVERY_N interactions.

    Reads happen unlocked and the LLM call runs without holding the
    relationships.json lock; the result is written back inside a short
    modify_json session so concurrent updates to other person_ids are never
    blocked on a slow LLM call.
    """
    relationships = load_json(RELATIONSHIPS_FILE, default_type=dict) or {}
    r = relationships.get(user_id)
    if not isinstance(r, dict):
        return

    history = r.get("interaction_history", [])[-15:]
    if len(history) < 3:
        return

    history_text = "\n".join(
        f"User: {h.get('user','')[:120]}\nOrrin: {h.get('orrin','')[:120]}"
        for h in history
        if isinstance(h, dict)
    )

    existing = r.get("person_model") or {}
    existing_text = (
        f"Current understanding:\n"
        f"- Communication style: {existing.get('communication_style', 'unknown')}\n"
        f"- Interests: {', '.join(existing.get('interests', []))}\n"
        f"- Emotional patterns: {existing.get('emotional_patterns', 'unknown')}\n"
        f"- Tentative observations: {'; '.join(existing.get('tentative_observations', []))}"
    )

    prompt = (
        f"You are Orrin, building a mental model of a person you interact with.\n\n"
        f"Recent exchanges:\n{history_text}\n\n"
        f"{existing_text}\n\n"
        f"Based on these exchanges, update your understanding of this person. Be specific and honest. "
        f"Mark anything uncertain with 'possibly' or 'seems to'.\n\n"
        f"Respond with JSON:\n"
        f"  communication_style: string (e.g. 'direct', 'exploratory', 'brief', 'verbose')\n"
        f"  interests: list of 3-5 topic strings\n"
        f"  emotional_patterns: string (e.g. 'tends toward impasse_signal when ideas aren't heard')\n"
        f"  preferred_tone: string — what tone do they seem to respond well to? (e.g. 'warm', 'direct', 'inquisitive')\n"
        f"  tentative_observations: list of 2-4 short strings about non-obvious patterns\n\n"
        f"Return ONLY the JSON. No other text."
    )

    try:
        from symbolic.llm_gate import gated_generate
        raw = (gated_generate(prompt, caller="relationships", outcome=0.65) or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        person_model = json.loads(raw)
        person_model["updated_ts"] = datetime.now(timezone.utc).isoformat()
    except Exception as e:
        log_error(f"update_person_model LLM/parse error for {user_id}: {e}")
        return

    try:
        with modify_json(RELATIONSHIPS_FILE, default_type=dict) as relationships:
            r = relationships.get(user_id)
            if not isinstance(r, dict):
                raise AbortModify("person disappeared")
            r["person_model"] = person_model
        log_private(f"[person_model:{user_id}] style={person_model.get('communication_style')} tone={person_model.get('preferred_tone')}")
    except AbortModify:
        pass
    except Exception as e:
        log_error(f"update_person_model write error for {user_id}: {e}")


def update_your_world(user_id: str) -> None:
    """
    Build a model of the world the user lives in — places, projects, people
    they've mentioned, things they're working on. Stored under your_world.
    Tentative inferences go in tentative_observations until confirmed.

    Reads happen unlocked and the LLM call runs without holding the
    relationships.json lock; the result is written back inside a short
    modify_json session (see update_person_model for the same pattern).
    """
    relationships = load_json(RELATIONSHIPS_FILE, default_type=dict) or {}
    r = relationships.get(user_id)
    if not isinstance(r, dict):
        return

    history = r.get("interaction_history", [])[-20:]
    if len(history) < 2:
        return

    history_text = "\n".join(
        f"User: {h.get('user','')[:120]}"
        for h in history
        if isinstance(h, dict) and h.get("user", "").strip()
    )

    existing = r.get("your_world") or {}
    existing_text = (
        f"What I currently know about their world:\n"
        f"- Places: {', '.join(existing.get('places', []) or ['(unknown)'])}\n"
        f"- Projects: {', '.join(existing.get('projects', []) or ['(unknown)'])}\n"
        f"- People mentioned: {', '.join(existing.get('people', []) or ['(unknown)'])}\n"
        f"- Things they care about: {', '.join(existing.get('cares_about', []) or ['(unknown)'])}\n"
        f"- Tentative observations: {'; '.join(existing.get('tentative_observations', []))}"
    )

    prompt = (
        f"You are Orrin, building a picture of the world this person inhabits.\n\n"
        f"What they've shared recently:\n{history_text}\n\n"
        f"{existing_text}\n\n"
        f"Update your understanding of their world. Be specific; only include what was actually mentioned. "
        f"Mark inferences you're not sure about as tentative.\n\n"
        f"Respond with JSON:\n"
        f"  places: list of place names or locations they've mentioned\n"
        f"  projects: list of things they're working on\n"
        f"  people: list of people they've mentioned (names or roles like 'my manager')\n"
        f"  cares_about: list of things, topics, or values they seem to care about\n"
        f"  tentative_observations: list of 2-3 inferences you're not yet sure about\n\n"
        f"Return ONLY the JSON. No other text."
    )

    try:
        from symbolic.llm_gate import gated_generate
        raw = (gated_generate(prompt, caller="relationships", outcome=0.65) or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        your_world = json.loads(raw)
        your_world["updated_ts"] = datetime.now(timezone.utc).isoformat()
    except Exception as e:
        log_error(f"update_your_world LLM/parse error for {user_id}: {e}")
        return

    try:
        with modify_json(RELATIONSHIPS_FILE, default_type=dict) as relationships:
            r = relationships.get(user_id)
            if not isinstance(r, dict):
                raise AbortModify("person disappeared")
            r["your_world"] = your_world
        log_private(f"[your_world:{user_id}] projects={your_world.get('projects')} places={your_world.get('places')}")
    except AbortModify:
        pass
    except Exception as e:
        log_error(f"update_your_world write error for {user_id}: {e}")


def summarize_relationships(relationships):
    if not isinstance(relationships, dict):
        return {}
    summary = {}
    for k, v in relationships.items():
        if not isinstance(v, dict):
            continue
        summary[k] = {
            "impression": v.get("impression", "unknown"),
            "influence_score": v.get("influence_score", 0.0),
            "depth": v.get("depth", 0.0),
            "trust": v.get("trust", 0.5),
            "boundaries": (v.get("boundaries") or [])[:2] if isinstance(v.get("boundaries"), list) else [],
            "emotional_effect": v.get("recent_emotional_effect", ""),
            "last_interaction": v.get("last_interaction_time", ""),
        }
    return summary


def get_relationship_context_for_prompt(person_id: str) -> str:
    """
    Return a natural-language description of Orrin's relationship with this person,
    suitable for injection into the system prompt.

    Works for any person: named humans, anonymous speakers, or AI peers.
    Returns empty string if the person is unknown or data is too sparse.
    """
    # Accept user_id as alias for backward compat
    try:
        relationships = load_json(RELATIONSHIPS_FILE, default_type=dict) or {}
        r = relationships.get(person_id)
        if not isinstance(r, dict):
            return ""

        interaction_count = len(r.get("interaction_history", []))
        if interaction_count < 2:
            return ""

        person_type = r.get("person_type", "human")
        depth = float(r.get("depth", 0.0) or 0.0)
        trust = float(r.get("trust", 0.5) or 0.5)
        impression = r.get("impression", "")
        emotion = r.get("recent_emotional_effect", "")
        person_model = r.get("person_model") or {}
        style = person_model.get("communication_style", "")
        tone = person_model.get("preferred_tone", "")

        # AI peers get a distinct framing
        if person_type == "ai_peer":
            parts = [f"I am in dialogue with another AI ({interaction_count} exchanges)."]
            if impression and impression not in ("new connection",):
                parts.append(f"Impression: {impression}.")
            arc = r.get("arc") or {}
            arc_narrative = arc.get("narrative", "")
            if arc_narrative:
                parts.append(arc_narrative)
            return " ".join(parts)

        # Build the depth/trust descriptor
        if depth >= 0.6 and trust >= 0.7:
            rel_quality = "a deep, trusting relationship"
        elif depth >= 0.4 and trust >= 0.5:
            rel_quality = "an established, generally positive connection"
        elif depth >= 0.2 and trust >= 0.4:
            rel_quality = "a developing relationship"
        elif trust < 0.3:
            rel_quality = "a strained or uncertain connection"
        else:
            rel_quality = "an early acquaintance"

        parts = [f"I have {rel_quality} with this person ({interaction_count} interactions)."]

        if impression and impression not in ("new connection",):
            parts.append(f"My current impression: {impression}.")

        if style:
            parts.append(f"They communicate in a {style} style")
            if tone:
                parts.append(f"and respond well to a {tone} tone.")
            else:
                parts.append(".")

        if emotion and emotion not in ("neutral", "unknown", ""):
            parts.append(f"Their recent emotional tone: {emotion}.")

        # Arc narrative: where the relationship is heading
        arc = r.get("arc") or {}
        arc_narrative = arc.get("narrative", "")
        if arc_narrative:
            parts.append(arc_narrative)

        # Social mirroring: how I seem to be landing
        mirror = r.get("their_impression_of_me") or {}
        mirror_label = mirror.get("label", "")
        if mirror_label and mirror_label != "neutral":
            if mirror_label == "resonating":
                parts.append("They seem to be engaging well with what I say — what I'm offering is landing.")
            elif mirror_label == "lukewarm":
                parts.append("I'm not fully resonating — they're receiving me but not fully engaged.")
            elif mirror_label == "disconnected":
                parts.append("There's a gap between us right now — I may need to listen differently.")

        return " ".join(parts)

    except Exception:
        return ""