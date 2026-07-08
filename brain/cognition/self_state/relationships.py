# brain/cognition/self_state/relationships.py
from brain.core.runtime_log import get_logger
import json
from datetime import datetime, timezone
from typing import Dict, Any
from brain.utils.json_utils import load_json, modify_json, AbortModify
from brain.utils.signal_keyword_utils import detect_signal_keyword
from brain.utils.log import log_error, log_private
from brain.paths import RELATIONSHIPS_FILE
from brain.utils.failure_counter import record_failure
# Relationship-arc trend analysis, extracted to relationship_arc.py (Phase 4.5C).
from brain.cognition.self_state.relationship_arc import _update_arc  # noqa: F401
_log = get_logger(__name__)

MAX_HISTORY = 50
_UPDATE_EVERY_N = 5      # run person-model LLM update every N interactions


def _interaction_hash(user_input: str, orrin_reply: str) -> str:
    """Semantic identity of one exchange (case/whitespace-insensitive) — F21."""
    import hashlib
    import re as _re
    norm = _re.sub(r"\s+", " ", f"{user_input}|{orrin_reply}".strip().lower())
    return hashlib.md5(norm.encode("utf-8", errors="replace")).hexdigest()[:12]



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
        emotion_result = detect_signal_keyword(user_input)
        emotion = (emotion_result.get("emotion") if isinstance(emotion_result, dict) else str(emotion_result)).lower()

        # handle both flat and nested shapes
        affect_state = context.get("affect_state", {}) or {}
        core = affect_state.get("core_signals", affect_state)  # fallback to flat
        conflict_signal = float(core.get("conflict_signal", 0) or 0)
        reward_positive   = float(core.get("reward_positive", 0) or 0)

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

            # history — F21: deduped by semantic hash. A repeated identical
            # exchange (the F7 stuck-utterance loop) refreshes the timestamp of
            # the existing entry instead of stacking copies of the same line.
            _hist = r.setdefault("interaction_history", [])
            _sig = _interaction_hash(user_input, orrin_reply)
            _dup = next((h for h in reversed(_hist[-10:])
                         if isinstance(h, dict)
                         and _interaction_hash(h.get("user", ""), h.get("orrin", "")) == _sig),
                        None)
            if _dup is not None:
                _dup["timestamp"] = datetime.now(timezone.utc).isoformat()
                _dup["repeats"] = int(_dup.get("repeats") or 1) + 1
            else:
                _hist.append({
                    "user": user_input,
                    "orrin": orrin_reply,
                    "emotion": emotion,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            r["interaction_history"] = _hist[-MAX_HISTORY:]

            old_impression = r.get("impression", "")
            old_influence = float(r.get("influence_score", 0.5) or 0.5)
            old_trust = float(r.get("trust", 0.5) or 0.5)
            old_depth = float(r.get("depth", 0.0) or 0.0)

            # influence nudges
            if emotion in ["gratitude", "reward_positive", "affection", "trust"]:
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
            elif emotion in ["reward_positive", "exploration_drive"]:
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
            elif reward_positive > 0.6:
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
            _apply_relationship_signal_feedback(r, emotion, old_depth, old_trust, context)

        # --- lock released; relationships.json already saved ---

        # working memory note on notable change
        if notable_change:
            from brain.cog_memory.working_memory import update_working_memory
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


def _apply_relationship_signal_feedback(
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

    Met wants   → small boost to reward_positive/expected_gain
    Unmet wants → small increase in social_deficit (stored as reward_negative proxy)
    """
    if not isinstance(context, dict):
        return

    pos_emotions = {"gratitude", "reward_positive", "affection", "trust", "exploration_drive"}
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
            from brain.control_signals.homeostasis import pump_signal
            pump_signal(core, "reward_positive", 0.06)
            pump_signal(core, "expected_gain",    0.04)
        elif unmet_count >= 3 and emotion in neg_emotions:
            # All three wants unmet *and* the interaction felt hostile — real disconnection
            core["reward_negative"] = min(1.0, float(core.get("reward_negative", 0.0) or 0) + 0.08)

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
        record_failure("relationships._apply_relationship_signal_feedback", _e)


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
        from brain.symbolic.llm_gate import gated_generate
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
        from brain.symbolic.llm_gate import gated_generate
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


# Read-only presentation views extracted to relationship_views.py (F21 size
# ratchet, 2026-07-08); re-imported so external callers keep their paths.
from brain.cognition.self_state.relationship_views import (  # noqa: E402,F401
    summarize_relationships as summarize_relationships,
    get_relationship_context_for_prompt as get_relationship_context_for_prompt,
)
