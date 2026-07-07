# think/think_utils/talk_policy.py
from brain.core.runtime_log import get_logger
import os, re, sys, time
from brain.utils.log import log_activity, log_model_issue
from brain.behavior.speak import _derive_tone
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

# ===== Public constants (tweak as you like) =====
SPEAK_TYPES = {"speak", "ask_user", "user_response"}
RECENT_USER_CYCLES = 5            # user replied within last N cycles
SPEAK_COOLDOWN_CYCLES = 1         # must skip at least 1 cycle after talking
STAGNATION_SIGNAL_TALK_THRESHOLD = 0.65     # alone-talk allowed if stagnation_signal >= threshold

# ===== Local helpers (no import cycles) =====
def _clamp01(x):
    try: return max(0.0, min(1.0, float(x)))
    except (ValueError, TypeError): return 0.0  # intentional: non-numeric → 0.0

def _cycles(context):
    raw = context.get("cycle_count", 0)
    return raw.get("count", 0) if isinstance(raw, dict) else int(raw or 0)

def _best_user_input_mtime(context):
    """Find user_input.txt mtime; 0.0 if not found."""
    paths = []
    try:
        from brain.paths import USER_INPUT_FILE as UIF
        if UIF: paths.append(UIF)
    except ImportError:
        pass  # constant is optional; the cwd-relative probes below cover it
    try:
        cwd = context.get("cwd") or os.getcwd()
        paths.append(os.path.join(cwd, "data", "user_input.txt"))
        paths.append(os.path.join(cwd, "user_input.txt"))
    except Exception:
        paths.extend(["data/user_input.txt", "user_input.txt"])

    newest = 0.0
    for p in paths:
        # A missing candidate is the normal case (the file only exists once a user
        # has typed) — probe quietly and only surface genuinely unexpected errors.
        try:
            m = os.path.getmtime(p)
            if m > newest: newest = m
        except FileNotFoundError:
            continue
        except OSError as _e:
            record_failure("talk_policy._best_user_input_mtime", _e)
    return newest

def refresh_last_user_cycle(context):
    """
    If user_input.txt changed since last check, stamp last_user_cycle = current cycle.
    Also keeps last_user_input_ts.
    """
    try:
        mt = _best_user_input_mtime(context)
        prev = float(context.get("last_user_input_ts") or 0.0)
        if mt and mt > prev:
            context["last_user_input_ts"] = mt
            context["last_user_cycle"] = _cycles(context)
    except Exception as _e:
        record_failure("talk_policy.refresh_last_user_cycle", _e)

def _cycles_since(key, context, default_big=10_000):
    now = _cycles(context)
    last = context.get(key)
    if isinstance(last, (int, float)) and last >= 0:
        return now - int(last)
    return default_big

def _talk_drive_signal(context, affect_state):
    """Max of stagnation_signal and impasse_signal — the "I should say something
    unprompted" drive. Keying the gate to stagnation alone silenced Orrin for
    5.6 h of a run: reward pumping kept stagnation ≈ 0 while impasse (the actual
    'I'm stuck' indicator) sat at 0.85–1.0 the whole time."""
    def _read(core_dict, key):
        v = core_dict.get(key)
        if v is None:
            _ctx_emo = context.get("affect_state") or {}
            _ctx_core = _ctx_emo.get("core_signals") or _ctx_emo
            v = _ctx_core.get(key, 0.0)
        return _clamp01(v or 0.0)

    emo = (affect_state or {}) if isinstance(affect_state, dict) else {}
    # signals live in core_signals; fall back to context's affect_state
    core = emo.get("core_signals") or emo
    return max(_read(core, "stagnation_signal"), _read(core, "impasse_signal"))

# ===== Policy (HARD gate) =====
def talk_policy_allows(action_type, context, affect_state):
    """
    Rules:
    - If user responded within last 5 cycles:
        * allow ask_user/user_response only if not spoken last cycle
        * disallow monologue speak
    - If >5 cycles since user:
        * allow talk only if max(stagnation, impasse) >= threshold and not spoken last cycle
    """
    if action_type not in SPEAK_TYPES:
        return True

    refresh_last_user_cycle(context)
    since_user  = _cycles_since("last_user_cycle", context)
    since_speak = _cycles_since("last_speak_cycle", context)

    if since_speak < SPEAK_COOLDOWN_CYCLES:
        return False
    if since_user <= RECENT_USER_CYCLES:
        return True  # user is present — allow speak, ask_user, user_response
    return _talk_drive_signal(context, affect_state) >= STAGNATION_SIGNAL_TALK_THRESHOLD

# ===== Policy (SOFT bias for scorer) =====
def talk_policy_score_bias(action_type, context, affect_state):
    if action_type not in SPEAK_TYPES:
        return 0.0
    if not talk_policy_allows(action_type, context, affect_state):
        return -1.0  # make it very unlikely to be picked
    b = _talk_drive_signal(context, affect_state)
    return 0.10 * (b - STAGNATION_SIGNAL_TALK_THRESHOLD)  # small nudge above threshold

# ===== Self-initiated speech habituation (F7, 2026-07-05 findings) =====
# The 07-05 run sent 388 near-identical express_state utterances ("something
# present but hard to name… Am I off on that?"), 4 of them inside 40 seconds.
# Two gates, both only for SELF-INITIATED speech (a user reply is never gated):
#   * minimum-interval floor between any two self-initiated sends;
#   * content habituation — repeating essentially the same utterance requires
#     an escalating interval (base × 2^n_identical), the B1 eff=raw/(1+k·n)
#     idea applied to the mouth.
_SELF_SPEAK_MIN_INTERVAL_S = 90.0
_SELF_SPEAK_SIMILAR = 0.75          # token-Jaccard at/above this = "the same thing"
_SELF_SPEAK_REPEAT_BASE_S = 600.0   # first repeat waits 10 min, then 20, 40…
_SELF_SPEAK_WINDOW = 24             # utterances remembered
_self_speech_log: list = []         # [(token_set, ts), ...] newest last
_last_self_speak_ts: float = 0.0

_WORD_RE_TP = re.compile(r"[a-z']{2,}")


def _utterance_tokens(text: str) -> frozenset:
    return frozenset(_WORD_RE_TP.findall(str(text or "").lower()))


def _self_speech_allowed(text: str, now: float = None) -> bool:
    """Gate a self-initiated utterance; records it when allowed."""
    global _last_self_speak_ts
    now = time.time() if now is None else now
    if now - _last_self_speak_ts < _SELF_SPEAK_MIN_INTERVAL_S:
        return False
    toks = _utterance_tokens(text)
    if toks:
        n_identical = 0
        last_similar_ts = 0.0
        for prior, ts in _self_speech_log:
            union = len(toks | prior)
            if union and len(toks & prior) / union >= _SELF_SPEAK_SIMILAR:
                n_identical += 1
                last_similar_ts = max(last_similar_ts, ts)
        if n_identical:
            required = _SELF_SPEAK_REPEAT_BASE_S * (2 ** min(n_identical - 1, 5))
            if now - last_similar_ts < required:
                return False
    _self_speech_log.append((toks, now))
    del _self_speech_log[:-_SELF_SPEAK_WINDOW]
    _last_self_speak_ts = now
    return True


# ===== “Speak” plumbing (no direct speaker.speak) =====
def _emit_reply_line(text: str) -> None:
    try:
        if isinstance(text, str) and text.strip():
            sys.stdout.write(f"REPLY: {text}\n")
            sys.stdout.flush()
            log_activity(f"REPLY: {text[:200]}")  # also log for audit trail
            # Deliver back to the Face UI message that prompted this (no-op when
            # nothing is awaiting — i.e. spontaneous speech). Closes brain→Face.
            try:
                from brain.behavior.face_bridge import deliver_reply as _deliver_reply
                _deliver_reply(text)
            except Exception as _de:
                record_failure("talk_policy._emit_reply_line", _de)
    except Exception as _e:
        record_failure("talk_policy._emit_reply_line.2", _e)

def speak_text(raw_text: str, context: dict, speaker) -> str:
    """
    Route text through tone shaping + speak_final; do NOT call speaker.speak.
    Emit REPLY for the UI and update last_ai_timestamp.

    When user input is present and _inner_loop_output is populated, speech_gate
    takes priority: it produces emotion-aware speech from Orrin's actual inner
    monologue rather than the raw LLM action content (which may be stale).
    Falls back to raw_text if speech_gate returns empty.
    """
    try:
        txt = (raw_text or "").strip()
        emo = context.get("affect_state", {}) or {}
        user_input = (context.get("latest_user_input") or "").strip()

        # Speech gate path: emotion-aware, driven by inner monologue.
        # When user input exists and inner thought is present, replace the raw LLM
        # action content with speech_gate's emotion-aware output, then let the full
        # speaker.should_speak() pipeline run — this preserves the chat log write,
        # SSE push, and timing stamp that live inside should_speak().
        # Clear previous cycle's plan so react/express paths don't accidentally
        # log a stale plan from the last generate_speech call.
        context.pop("_last_speech_plan",          None)
        context.pop("_last_speech_comprehension", None)

        _speech_plan          = {}
        _speech_comprehension = {}
        if user_input:
            # Always run speech_gate when the user has spoken — the 4-stage
            # pipeline handles empty inner content correctly (uses memory +
            # affect instead).  Requiring inner here would prevent the pipeline
            # from firing whenever the inner loop hasn't run yet, leaving Orrin
            # with nothing to say in no-LLM mode.
            try:
                from brain.behavior.speech_gate import build_speech as _build_speech
                _gate_reply = (_build_speech(user_input, context, emo) or "").strip()
                if _gate_reply:
                    txt = _gate_reply  # replace raw content; should_speak handles the rest
                    # Plan/comprehension are written to context by speech_generator
                    _speech_plan         = context.get("_last_speech_plan", {})
                    _speech_comprehension = context.get("_last_speech_comprehension", {})
            except Exception as _sg_e:
                log_model_issue(f"speech_gate failed, falling back to raw content: {_sg_e}")
        else:
            # Self-initiated speech (no user present): compose through the ONE
            # expression door rather than piping raw inner (raw_action) text out
            # (EXPRESSION_MEMBRANE_FIX_PLAN E5). The raw inner text is handed in
            # as a meaning kernel (seed) and reworded by the same composer that
            # builds replies; speakability is enforced so no backend tag ships.
            try:
                from brain.behavior.express_to_user import build_motive, compose_from_motive
                from brain.behavior.speakability import is_speakable
                _self_motive = build_motive(
                    context, intent="express_state", recipient="self", seed=txt)
                _composed = compose_from_motive(_self_motive, context)
                if _composed and is_speakable(_composed):
                    txt = _composed
                    context["_self_motive"] = _self_motive.to_dict()
            except Exception as _self_e:
                log_model_issue(f"self-speech compose failed, falling back to raw: {_self_e}")
            # F7 (2026-07-05): content habituation + minimum-interval floor for
            # self-initiated speech — saying essentially the same thing again
            # requires an escalating interval; a user reply is never gated here.
            if not _self_speech_allowed(txt):
                log_activity("[talk_policy] self-speech suppressed — repeated "
                             "content / minimum-interval floor (F7 habituation).")
                context.pop("_self_motive", None)
                return ""

        # Route through should_speak (owns chat log write, SSE, timing gate).
        rendered = speaker.should_speak(txt, emo, context, force_speak=True) or ""
        if not rendered:
            tone = _derive_tone(emo)
            rendered = speaker.speak_final(txt, tone, context)

        rendered = (rendered or "").strip()
        if rendered:
            _emit_reply_line(rendered)
            context["last_ai_timestamp"] = time.time()
            # Log the reply so the evaluator can score it next cycle.
            # response_type/tone/source are populated at GENERATION time
            # (BEHAVIOR_FIX_PLAN Phase 3): when the gate produced no plan,
            # synthesize a minimal one instead of logging empty fields — the
            # construction-grammar scores can't learn from blank buckets.
            try:
                from brain.think.speech_log import log_reply as _log_reply
                _self_motive = context.pop("_self_motive", None)
                if not _speech_plan:
                    _speech_plan = {
                        "response_type": "answer" if user_input else "express_state",
                        "tone": (_derive_tone(emo) or {}).get("tone", "neutral"),
                        # Provenance (E6/2.3): self-initiated speech now carries the
                        # motive it was composed from, so "why did he say this" is
                        # answerable and the construction-grammar scorer can learn
                        # per-intent — not a blank "raw_action" bucket.
                        "source": "composed" if _self_motive else "raw_action",
                    }
                if _self_motive:
                    _speech_plan["motive"] = _self_motive
                _last_id = _log_reply(
                    user_input    = user_input,
                    reply         = rendered,
                    plan          = _speech_plan,
                    comprehension = _speech_comprehension,
                )
                context["_last_speech_log_id"] = _last_id
            except Exception as _e:
                record_failure("talk_policy.speak_text", _e)
        return rendered
    except Exception as e:
        log_model_issue(f"speak_text failed: {e}")
        return ""
