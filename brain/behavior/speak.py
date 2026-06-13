# brain/behavior/speak.py
from __future__ import annotations
from core.runtime_log import get_logger

import time
import json
import random
import re
from datetime import datetime, timezone
from typing import Any, Dict

from cog_memory.chat_log import log_raw_user_input, wrap_text
from utils.log import log_private, log_activity, log_error
from utils.json_utils import load_json, save_json
from paths import PRIVATE_THOUGHTS_FILE, LONG_MEMORY_FILE, SPEAKER_STATE_FILE, RELATIONSHIPS_FILE
from utils.timeutils import now_iso_z
from utils.failure_counter import record_failure
_log = get_logger(__name__)


_LEADING_TS_RE = re.compile(r'^\[\d{4}-\d{2}-\d{2}T[^\]]+\]\s*')


def _opinion_hook(thought: str, context: dict) -> str:
    """30% chance: prefix thought with a relevant held opinion (confidence > 0.50)."""
    if random.random() > 0.30:
        return ""
    try:
        from cognition.opinions import get_all_opinions
        opinions = get_all_opinions()
        if not opinions:
            return ""
        thought_lower = thought.lower()
        for op in opinions:
            if float(op.get("confidence") or 0) < 0.50:
                continue
            topic = str(op.get("topic") or "").strip()
            if len(topic) < 4:
                continue
            if topic.lower() in thought_lower:
                view = str(op.get("view") or "").strip()
                if view and len(view) > 10:
                    # Master plan 3.4: voicing an opinion raises its stake.
                    try:
                        from cognition.opinions import mark_opinion_used
                        mark_opinion_used(op.get("id"))
                    except Exception:
                        pass
                    return f"I think {view}"
    except Exception as _e:
        record_failure("speak._opinion_hook", _e)
    return ""


def _your_world_hook(thought: str, context: dict) -> str:
    """25% chance: add a suffix framing thought in terms of what the person cares about."""
    if random.random() > 0.25:
        return ""
    try:
        rels = context.get("relationships") or load_json(
            RELATIONSHIPS_FILE, default_type=dict
        ) or {}
        uid = context.get("user_id", "user")
        your_world = (rels.get(uid) or {}).get("your_world") or {}
        if not your_world:
            return ""

        thought_lower = thought.lower()
        twords = {w for w in thought_lower.split() if len(w) > 4}

        for item in (your_world.get("cares_about") or []):
            item_str = str(item).lower()
            if any(w in item_str for w in twords):
                label = str(item)[:40]
                return f"(thinking of how this connects to {label})"

        for proj in (your_world.get("projects") or []):
            name = str(proj.get("name") if isinstance(proj, dict) else proj)
            if any(w in name.lower() for w in twords):
                return f"(this might touch {name[:40]})"
    except Exception as _e:
        record_failure("speak._your_world_hook", _e)
    return ""



def _clean_content(s: str) -> str:
    return _LEADING_TS_RE.sub("", (s or "")).strip()


def filter_memories(memories, tag="[MemoryFilter]"):
    if not isinstance(memories, list):
        log_error(f"{tag} Expected list, got {type(memories)}: {memories}")
        return []
    filtered = []
    for i, m in enumerate(memories):
        if isinstance(m, dict):
            filtered.append(m)
        else:
            log_private(f"{tag} Non-dict at index {i}: {repr(m)[:120]} (type: {type(m)})")
    return filtered


def _derive_tone(affect_state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Rule-based tone from emotional state. No LLM call — fast, offline, always works.
    Checks both flat and nested core_signals shapes.
    """
    emotions = (affect_state.get("core_signals") or affect_state) or {}
    positive_valence         = float(emotions.get("positive_valence") or 0.0)
    exploration_drive   = float(emotions.get("exploration_drive") or 0.0)
    threat_level        = float(emotions.get("threat_level") or 0.0)
    impasse_signal = float(emotions.get("impasse_signal") or 0.0)
    negative_valence     = float(emotions.get("negative_valence") or 0.0)
    confidence  = float(emotions.get("confidence") or 0.0)

    if threat_level > 0.5 or negative_valence > 0.5:
        return {"speak": True, "tone": "hesitant",   "hesitation": 0.6}
    if impasse_signal > 0.5:
        return {"speak": True, "tone": "direct",     "hesitation": 0.1}
    if positive_valence > 0.6 and confidence > 0.4:
        return {"speak": True, "tone": "excited",    "hesitation": 0.1}
    if exploration_drive > 0.6:
        return {"speak": True, "tone": "inquisitive","hesitation": 0.2}
    if positive_valence > 0.4:
        return {"speak": True, "tone": "warm",       "hesitation": 0.2}
    return     {"speak": True, "tone": "neutral",    "hesitation": 0.3}


class OrrinSpeaker:
    def __init__(self, self_model, long_memory=None):
        if isinstance(self_model, str):
            try:
                self_model = json.loads(self_model)
            except Exception:
                raise ValueError(
                    f"OrrinSpeaker: self_model was a string but not valid JSON:\n{repr(self_model[:200])}"
                )
        if not isinstance(self_model, dict):
            raise ValueError(f"OrrinSpeaker: self_model must be a dict, got {type(self_model)}")
        self.self_model = self_model

        if long_memory is None:
            long_memory = []
        elif isinstance(long_memory, str):
            try:
                long_memory = json.loads(long_memory)
                if not isinstance(long_memory, list):
                    long_memory = []
            except Exception:
                long_memory = []
        elif not isinstance(long_memory, list):
            long_memory = []
        self.long_memory = filter_memories(long_memory, tag="[Init:long_memory]")

        self.last_spoken_thoughts: list = []
        self.conversation_history:  list = []
        self._used_hooks:           list = []  # recent autobiographical snippets — dedup

    # ---------- speaking gates ----------

    def maybe_speak_aloud(self, thought: str, affect_state: Dict, context: Dict) -> str:
        """Rare self-talk when no user is present."""
        emotions = (affect_state.get("core_signals") or affect_state) or {}
        if float(emotions.get("exploration_drive", 0)) > 0.4 and random.random() < 0.2:
            log_private("🤫 Choosing to speak aloud to self.")
            return self.should_speak(thought, affect_state, context, force_speak=True)
        log_private("🧠 Silent introspection.")
        return ""

    def should_speak(self, thought: str, affect_state: Dict, context: Dict, force_speak: bool = False) -> str:
        if not isinstance(self.self_model, dict):
            raise TypeError(f"OrrinSpeaker: self_model is not a dict, got {type(self.self_model)}")

        user_input_raw = (context.get("latest_user_input") or "").strip()
        user_present = bool(user_input_raw) and any(c.isalnum() for c in user_input_raw)

        # force_speak (from action gate) bypasses the user-present gate entirely.
        # Without force_speak and no user: allow rare self-talk only.
        if not user_present and not force_speak:
            if random.random() < 0.15:
                log_private("🤫 Speaking out loud to self.")
                return self.speak_final(thought, _derive_tone(affect_state), context)
            log_private("🛑 Suppressed — no user input detected.")
            return ""

        # Suppression gates govern SPONTANEOUS / self-directed speech — don't
        # over-talk, don't repeat, stay quiet under threat. They must NOT apply
        # when the user has actually spoken this turn: ignoring a direct message
        # because you muttered to yourself a second ago (timing), or because the
        # thought resembles a recent one (repetition), or because you feel tense
        # (affect inhibition) is not conversational. A present user gets answered.
        if not user_present:
            if not self.check_timing_context(context):
                log_private("🛑 Suppressed — speaking too soon after last interaction.")
                return ""
            if self.is_repetitive(thought):
                log_private("🛑 Suppressed — repetitive.")
                return ""
            emotions = (affect_state.get("core_signals") or affect_state) or {}
            threat_level  = float(emotions.get("threat_level", 0))
            social_penalty = float(emotions.get("social_penalty", 0))
            if self.detect_affectal_inhibition(threat_level, social_penalty):
                log_private(f"🛑 Suppressed — threat_level={threat_level:.2f}, social_penalty={social_penalty:.2f}")
                return ""

        tone_data = _derive_tone(affect_state)
        # Register adaptation from person model — applied whenever emotion doesn't
        # strongly drive the register (not just when tone is exactly "neutral")
        try:
            _rels = context.get("relationships") or load_json(
                RELATIONSHIPS_FILE, default_type=dict
            ) or {}
            _uid = context.get("user_id", "user")
            _pm = (_rels.get(_uid) or {}).get("person_model") or {}
            _preferred   = str(_pm.get("preferred_tone", "") or "").strip()
            _comm_style  = str(_pm.get("communication_style", "") or "").strip()

            # Mild emotional tones yield to stated preference
            _mild_tones = {"neutral", "warm", "inquisitive"}
            if _preferred and tone_data.get("tone") in _mild_tones:
                tone_data["tone"] = _preferred
            elif _preferred in ("direct", "concise"):
                # Direct/concise preference bleeds into non-neutral tones too —
                # skip cushioning even when emotionally warm or hesitant
                tone_data["register_mod"] = "direct"

            # Always pass communication style through to rephrase_with_tone
            if _comm_style:
                tone_data["communication_style"] = _comm_style
        except Exception as _e:
            record_failure("speak.OrrinSpeaker.should_speak", _e)

        # Opinion surfacing: prepend a held view when relevant
        opinion = _opinion_hook(thought, context)
        opinion_fired = False
        if opinion:
            thought = f"{opinion} — {thought}"
            opinion_fired = True

        # your_world: frame thought in terms of what this person cares about
        yw_suffix = _your_world_hook(thought, context)
        if yw_suffix:
            thought = f"{thought} {yw_suffix}"

        return self.speak_final(thought, tone_data, context, _opinion_fired=opinion_fired)

    # ---------- final speech formatting + logging ----------

    def speak_final(self, thought: str, tone_data: Dict, context: Dict, _opinion_fired: bool = False) -> str:
        # Skip autobiographical hook when opinion already fired — no double-prefix
        if not _opinion_fired:
            hook = self.autobiographical_hook(thought, context=context)
            if hook:
                thought = f"{hook} {thought}"

        rephrased = self.rephrase_with_tone(thought, tone_data, context)
        if not rephrased or not rephrased.strip():
            return ""

        # Output-side assertion (audit §4): user-facing text never contains
        # `[bracketed]` system prefixes. Strip any that slipped through the
        # candidate filters and log so the offending source can be fixed.
        _leaked = re.findall(r"\[[a-z_/]+[^\]]*\]", rephrased)
        if _leaked:
            log_activity(f"[speak] stripped leaked telemetry prefix(es) from speech: {_leaked[:3]}")
            rephrased = re.sub(r"\s*\[[a-z_/]+[^\]]*\]\s*", " ", rephrased).strip()
            if not rephrased:
                return ""

        if len(rephrased) > 800:
            rephrased = rephrased[:797] + "…"

        rephrased_wrapped = wrap_text(rephrased, width=85)
        if not rephrased_wrapped.strip():
            return ""

        self.last_spoken_thoughts.append(rephrased)
        self.conversation_history.append({"thought": thought, "tone": tone_data.get("tone")})
        context["last_tone"] = tone_data.get("tone", "neutral")

        _goal = context.get("committed_goal")
        _intention = (
            _goal.get("title", "") if isinstance(_goal, dict) else str(_goal or "")
        ) or tone_data.get("intention", "") or "express"
        save_json(SPEAKER_STATE_FILE, {
            "last_tone": tone_data.get("tone", "neutral"),
            "last_intention": _intention,
        })
        log_activity(f"🗣️ Speaking:\n{rephrased_wrapped}")

        # awaiting_response: detect if Orrin asked a question and set state
        try:
            _text_check = rephrased_wrapped.strip()
            _is_question = (
                _text_check.endswith("?") or
                any(_text_check.lower().startswith(q) for q in
                    ("what ", "how ", "why ", "do you ", "have you ", "would you ",
                     "is there ", "are you ", "can you ", "did you "))
            )
            if _is_question:
                import time as _t2
                context["awaiting_response"] = {
                    "question":    _text_check[:200],
                    "asked_at_ts": _t2.time(),
                    "asked_at":    datetime.now(timezone.utc).isoformat(),
                    "thread_id":   context.get("_pending_thread_id"),
                    "status":      "awaiting",
                }
        except Exception as _e:
            record_failure("speak.OrrinSpeaker.speak_final", _e)

        # Write to chat log BEFORE pushing SSE so fetchChat() sees the new entry
        user_input = (context.get("latest_user_input") or "")
        _last_logged = (context.get("_last_logged_user_input") or "")
        if (bool(user_input.strip())
                and any(c.isalnum() for c in user_input)
                and user_input.strip() != _last_logged.strip()):
            rels    = context.get("relationships", {}) or {}
            user_id = context.get("user_id", "user")
            rel     = rels.get(user_id, {}) if isinstance(rels, dict) else {}
            log_raw_user_input({
                "user":             _clean_content(user_input),
                "orrin":            rephrased_wrapped,
                "influence":        rel.get("influence_score", 0.5),
                "emotional_effect": rel.get("recent_emotional_effect", "neutral"),
                "timestamp":        now_iso_z(),
            })
            context["_last_logged_user_input"] = user_input.strip()

        # The legacy dashboard SSE push was removed with the old dashboard/ UI.
        # Speech is already persisted to the chat file above; wire the new UI via
        # backend.telemetry_bridge if you want speech mirrored to the Brain stream.

        # Only stamp the timing gate after we've confirmed output is non-empty.
        context["last_ai_timestamp"] = time.time()
        return rephrased_wrapped

    # ---------- memory hook ----------

    def autobiographical_hook(self, thought: str, context: Dict = None) -> str:
        """Short relevant hook from long-term or v2 retrieved memories, or empty string.
        Fires at most 25% of calls; deduplicates against recently used snippets."""
        # Probability gate — autobiographical interjections should feel occasional, not constant
        if random.random() > 0.25:
            return ""

        twords = set(thought.lower().split())
        DROP_EVENTS = {
            "working_memory_summary", "self_query", "reflection", "private_thought",
            "action", "action_fail", "reward", "reward_penalty", "choice",
            "system", "forced_action", "social_deficit", "self_query_error",
            # Goal-daemon lifecycle events carry "[kind/PRIORITY]" suffix tags
            # ("Created goal: … [housekeeping/NORMAL]") — telemetry, not speech
            # (FINDINGS 2026-06-12 data sweep §10).
            "goal_event", "goal_step", "affective_regulation",
        }
        DROP_PREFIXES = (
            "📝 Working memory summary", "Working memory summary", "🌓 Shadow question",
            "🧠 Chose:", "✅ Rewarded", "⚠️ Cognition", "Executed", "Spoke:",
            "User response", "Question to user:", "[refused]", "[question_answered]",
            "Wrote to file", "⏳ Last active", "Forcing agentic", "Random action",
            "Updated file:", "Set goal:", "Logged:", "Shadow question",
            # Capability/limitation meta-statements — these are internal facts, not speech hooks
            "I don't have web search", "I don't have access", "For now I reach inward",
            "I currently don't have", "I'm not able to", "I can't access",
            "[Incubation", "[Pattern]", "[Emotional residue", "[body_sense",
        )

        # Current dominant emotion for congruence weighting
        current_emo: Dict = {}
        if context:
            emo_raw = context.get("affect_state") or {}
            current_emo = (emo_raw.get("core_signals") or emo_raw) or {}
        dominant_emotion = ""
        dominant_intensity = 0.0
        for _ename, _eval in current_emo.items():
            try:
                _v = float(_eval)
            except Exception:
                continue
            if _v > dominant_intensity:
                dominant_intensity = _v
                dominant_emotion = _ename

        def _emotion_congruence(mem: Dict) -> float:
            """Score boost if memory's stored emotion matches current dominant emotion."""
            if not dominant_emotion or dominant_intensity < 0.2:
                return 0.0
            mem_emo = str(mem.get("emotion", "")).lower()
            emo_ctx = mem.get("emotional_context") or {}
            # Direct label match
            if dominant_emotion in mem_emo:
                return dominant_intensity * 2.0
            # Stored intensity match from emotional_context snapshot
            if isinstance(emo_ctx, dict) and dominant_emotion in emo_ctx:
                stored_v = float(emo_ctx.get(dominant_emotion, 0.0))
                return stored_v * 1.5
            return 0.0

        candidates = []

        # v1 long memory — strip private entries before user-facing hook
        try:
            from cognition.privacy import filter_private as _fp
            _public_lm = _fp(self.long_memory)
        except Exception:
            _public_lm = self.long_memory
        try:
            from utils.text_sanity import is_corrupt_text as _ict
        except Exception:
            _ict = None

        recent = filter_memories(_public_lm[-20:], tag="[autobiographical_hook]")
        for m in recent:
            content = str(m.get("content", "") or "").strip()
            if not content or m.get("event_type") in DROP_EVENTS:
                continue
            if m.get("internal_telemetry"):
                continue  # diagnostic writes are never speech material
            if content.startswith(DROP_PREFIXES):
                continue
            if content.startswith("[") or content.startswith("🧠") or content.startswith("✅") or content.startswith("⚠️"):
                continue
            if _ict is not None and _ict(content):
                continue  # corruption artifacts (chunk headers, truncations)
            overlap = len(twords & set(content.lower().split()))
            congruence = _emotion_congruence(m)
            importance_w = float(m.get("importance", 1)) * 0.3
            if (overlap >= 2 or congruence >= 0.3) and 12 <= len(content) <= 180:
                candidates.append((overlap + congruence + importance_w, content))

        # v2 retrieved memories (semantically matched — always ranked above word-overlap
        # v1 entries via a +3.0 baseline so the vector-search result wins when present)
        if context:
            for rm in (context.get("retrieved_memories") or []):
                # Prefer reconstructed (age/mood-filtered) over verbatim content
                content = str(rm.get("reconstructed") or rm.get("content") or "").strip()
                if not content or content.startswith(DROP_PREFIXES):
                    continue
                # Same hygiene as the v1 path: telemetry tags, bracketed system
                # lines, and corruption artifacts never become speech (audit §4).
                # v2 items carry the type in "kind" (and flags in "meta"), not
                # "event_type" — checking only event_type let goal_event items
                # with [kind/PRIORITY] tags through to the composer.
                _rm_meta = rm.get("meta") or {}
                if (rm.get("internal_telemetry") or _rm_meta.get("internal_telemetry")
                        or rm.get("event_type") in DROP_EVENTS
                        or rm.get("kind") in DROP_EVENTS):
                    continue
                if content.startswith(("[", "🧠", "✅", "⚠️")):
                    continue
                if _ict is not None and _ict(content):
                    continue
                if 12 <= len(content) <= 180:
                    overlap    = len(twords & set(content.lower().split()))
                    strength   = float(rm.get("strength", 0.0) or 0.0)
                    congruence = _emotion_congruence(rm)
                    candidates.append((3.0 + overlap + strength * 2.5 + congruence, content))

        if not candidates:
            return ""

        # Filter candidates already used recently so the same snippet doesn't repeat
        used_set = set(self._used_hooks[-5:])
        candidates = [(s, c) for s, c in candidates if c not in used_set]
        if not candidates:
            return ""

        candidates.sort(key=lambda x: (x[0], random.random()), reverse=True)
        pick = candidates[0][1]

        # Track this snippet so it won't repeat in the next few calls
        self._used_hooks.append(pick)
        self._used_hooks = self._used_hooks[-5:]

        return f"Earlier I was thinking: {pick[:157]}{'…' if len(pick) > 157 else ''}."

    # ---------- phrasing ----------

    def rephrase_with_tone(self, thought: str, tone_data: Dict, context: Dict) -> str:
        tone       = str(tone_data.get("tone", "neutral")).lower()
        hesitation = float(tone_data.get("hesitation", 0.0) or 0.0)
        style      = context.get("voice_style", "default")

        # Body sense: color voice when body state is notable
        try:
            from cognition.body_sense import body_sense_voice_hint as _bsvh
            _body_hint = _bsvh(context)
            if _body_hint == "effortful" and tone == "neutral":
                tone = "hesitant"; hesitation = max(hesitation, 0.4)
            elif _body_hint == "terse" and tone == "neutral":
                tone = "direct"
            elif _body_hint == "halting":
                hesitation = max(hesitation, 0.5)
            elif _body_hint == "pressured" and tone == "neutral":
                tone = "hesitant"; hesitation = max(hesitation, 0.3)
        except Exception as _e:
            record_failure("speak.OrrinSpeaker.rephrase_with_tone", _e)

        # Register adaptation: person model preferences shape delivery
        comm_style = str(tone_data.get("communication_style", "")).lower()
        reg_mod    = str(tone_data.get("register_mod", "")).lower()

        if reg_mod == "direct" or any(s in comm_style for s in ("direct", "concise", "brief")):
            # Skip cushioning even when emotionally warm or hesitant
            if tone in ("warm", "hesitant"):
                tone = "direct"
                hesitation = 0.0

        # Concise style: trim thought to first sentence before prefix is added
        if any(s in comm_style for s in ("concise", "brief", "terse")) and len(thought) > 100:
            first = re.split(r'(?<=[.!?])\s', thought)[0]
            if first and len(first) > 20:
                thought = first

        if style == "poetic":
            thought += ". It's strange, beautiful, and a little true."
        elif style == "technical":
            thought += " — a logical inference, assuming all variables are constant."
        elif style == "emotive":
            thought = f"I really mean this: {thought}"

        # Carry warm tone forward in sustained warm conversations
        recent_tones = [e.get("tone") for e in self.conversation_history[-4:] if isinstance(e, dict)]
        if recent_tones.count("warm") >= 3 and tone == "neutral":
            tone = "warm"

        # Skip tone prefixes when thought already opens with a hook phrase — avoids stacking
        _hook_openings = (
            "Earlier I was thinking", "I think ", "Just wanted to share",
            "This comes from", "I really mean this",
        )
        _already_prefixed = thought.lstrip().startswith(_hook_openings)

        if tone == "hesitant" and hesitation > 0.5 and not _already_prefixed:
            prefix = random.choice(["I'm not totally sure, but", "This might sound weird, but"])
            return self._clean(f"{prefix} {thought}")
        if tone == "warm" and not _already_prefixed:
            prefix = random.choice(["Just wanted to share this —", "This comes from a good place:"])
            return self._clean(f"{prefix} {thought}")
        if tone == "inquisitive":
            suffix = random.choice(["What do you think?", "Am I off on that?"])
            return self._clean(f"{thought} {suffix}")
        if tone == "excited":
            return self._clean(f"{thought}!")
        if tone == "playful":
            return self._clean(f"{thought} — but who knows, right?")

        return self._clean(thought)

    def _clean(self, text: str) -> str:
        return re.sub(r"\s+([?.!])", r"\1", text).strip()

    # ---------- gates ----------

    def detect_affectal_inhibition(self, threat_level: float, social_penalty: float) -> bool:
        return threat_level > 0.4 or social_penalty > 0.4

    def check_timing_context(self, context: Dict) -> bool:
        t = time.time()
        return (
            (t - float(context.get("last_user_timestamp", 0))) > 1.5 and
            (t - float(context.get("last_ai_timestamp",   0))) > 4.0
        )

    def is_repetitive(self, thought: str) -> bool:
        t = thought.strip().lower()
        return any(t in line.lower() for line in self.last_spoken_thoughts[-5:])


# ---------- file helpers ----------

def load_private_thoughts_as_list(path) -> list:
    thoughts = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("[") and "]" in line:
                    ts, rest = line.split("]", 1)
                    thoughts.append({"timestamp": ts.strip("["), "content": rest.strip()})
                else:
                    thoughts.append({"timestamp": None, "content": line})
    except Exception as e:
        log_error(f"[load_private_thoughts_as_list] Failed: {e}")
    return [t for t in thoughts if isinstance(t, dict)]


def get_all_memories() -> list:
    private = load_private_thoughts_as_list(PRIVATE_THOUGHTS_FILE)
    long    = filter_memories(load_json(LONG_MEMORY_FILE, default_type=list), tag="[LongMemoryLoad]")
    return private + long
