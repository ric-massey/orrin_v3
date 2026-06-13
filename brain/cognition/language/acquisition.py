# brain/cognition/language/acquisition.py
#
# Feeds Orrin's lived language into his native model and consolidates it — the
# developmental loop. Sources, in priority:
#   • the LIBRARY (#1)          — large, clean public-domain prose he reads
#   • real prose he researched  — English grounded in his own curiosity
#   • conversations             — social, intention-bearing language
#   • his inner monologue       — CLEANED of log-noise (#3) so he learns English,
#                                 not his own instrumentation dialect
#
# Complementary-learning-systems: train on RECENT experience + a REPLAY sample of
# OLD experience each bout, so new learning doesn't erase old. Called from the
# dream cycle AND lightly during idle (#4).
from __future__ import annotations

import random
import re
from pathlib import Path
from typing import Dict, List

from utils.json_utils import load_json
from utils.log import log_activity
from paths import (
    PRIVATE_THOUGHTS_FILE, LONG_MEMORY_FILE, CHAT_LOG_FILE, BODY_SENSE_FILE,
    PREDICTIONS_FILE, SPEECH_LOG_FILE, KNOWLEDGE_GRAPH_FILE,
)

from cognition.language import native_lm, library

_REPLAY_FILE = Path(__file__).resolve().parents[2] / "data" / "language" / "replay_corpus.txt"
_MAX_BLOCK = 50000
_REPLAY_KEEP = 400000

# Lines that are internal instrumentation, not language to learn from.
_NOISE_LINE = re.compile(
    r"^\s*(\[?\d{4}-\d\d-\d\d|\[(working_memory|chunk|energy|state_processor|metacog|"
    r"temporal|body_sense|symbolic|inhibition|regulation|behavioral_adapt|aware|done|goal|"
    r"attention|env|identity|step_exec|pursue_goal|allostatic)|decision:|cognition log|"
    r"🧠|🌓|⏳|🔄|\[chunk)",
    re.IGNORECASE,
)


def _clean_monologue(text: str) -> str:
    """Keep only natural-language lines from his inner monologue — drop logs."""
    out = []
    for line in (text or "").splitlines():
        s = line.strip()
        if len(s) < 25 or _NOISE_LINE.search(s):
            continue
        # must look like prose: enough alphabetic words, not bracket soup
        words = re.findall(r"[A-Za-z']{2,}", s)
        if len(words) >= 5 and s.count("[") <= 1:
            out.append(s)
    return "\n".join(out)


def _read_prose() -> str:
    try:
        lm = load_json(LONG_MEMORY_FILE, default_type=list) or []
        prose = [
            str(e.get("content", "")) for e in lm
            if isinstance(e, dict)
            and str(e.get("content", "")).strip().lower().startswith(("[research]", "[read]"))
        ]
        return "\n".join(prose[-60:])
    except Exception:
        return ""


def _conversations() -> str:
    try:
        cl = load_json(CHAT_LOG_FILE, default_type=list) or []
        return "\n".join(
            str(e.get("text") or e.get("content") or "") for e in cl[-80:] if isinstance(e, dict)
        )
    except Exception:
        return ""


def _inner_monologue() -> str:
    try:
        raw = Path(PRIVATE_THOUGHTS_FILE).read_text(encoding="utf-8", errors="ignore")[-60000:]
        return _clean_monologue(raw)
    except Exception:
        return ""


_NOISE_PREFIX = (
    "[chunk", "[metacog", "[working_memory", "[energy", "[state_processor",
    "[temporal", "[body_sense", "[symbolic", "[inhibition", "[regulation",
    "[behavioral_adapt", "[aware", "[done", "[goal", "[step_exec",
    "spoke:", "chose:", "health summary",
)


def _emotional_experience(max_chars: int = 24000) -> str:
    """
    His own memories, weighted by the emotional WEIGHT they carry — read from the
    SAME affect fields (`emotional_context`, `importance`) his memory system uses.
    A memory that landed with feeling is repeated more here, so he learns its
    language more strongly — the way emotionally-charged events consolidate harder
    in a brain (Cahill & McGaugh: arousal modulates memory strength). This is what
    ties his language learning to "things that held weight."
    """
    try:
        lm = load_json(LONG_MEMORY_FILE, default_type=list) or []
    except Exception:
        return ""
    weighted: List[str] = []
    for e in lm[-400:]:
        if not isinstance(e, dict):
            continue
        c = str(e.get("content", "")).strip()
        cl = c.lower()
        if len(c) < 25 or "[chunk" in cl or any(cl.startswith(p) for p in _NOISE_PREFIX):
            continue
        ec = e.get("emotional_context") or {}
        peak = 0.0
        if isinstance(ec, dict):
            vals = [float(v) for v in ec.values() if isinstance(v, (int, float))]
            peak = max(vals) if vals else 0.0
        imp = min(1.0, float(e.get("importance", 1) or 1) / 5.0)
        salience = max(peak, imp)                  # the weight this memory carries
        reps = 1 + int(round(salience * 3))        # neutral×1 … intense×4
        weighted += [c] * reps
    return "\n".join(weighted)[-max_chars:]


def _update_replay(new_text: str) -> str:
    old = ""
    try:
        if _REPLAY_FILE.exists():
            old = _REPLAY_FILE.read_text(encoding="utf-8", errors="ignore")
        combined = (old + "\n" + new_text)[-_REPLAY_KEEP:]
        _REPLAY_FILE.parent.mkdir(parents=True, exist_ok=True)
        _REPLAY_FILE.write_text(combined, encoding="utf-8")
        if len(old) > _MAX_BLOCK:
            start = random.randint(0, len(old) - _MAX_BLOCK)
            return old[start:start + _MAX_BLOCK]
    except Exception:
        pass
    return ""


# Felt-state vocabulary → grounded natural-language phrasing. These are the words
# his interoception (body_sense.py) already uses for his computational body; here
# we bind those words to the actual state, so his language learns what they MEAN.
_FELT = {
    "heavy":    "my memory is high and climbing, and thinking feels effortful",
    "spacious": "my memory is low and the machine is idle, and I feel open",
    "strained": "I'm near my limits, under sustained load, and I feel terse",
    "sluggish": "my thinking is lagging behind, halting",
    "swelling": "my memory is rising fast, a building pressure",
    "clear":    "everything feels nominal and calm",
}


def grounded_experience(max_chars: int = 8000) -> str:
    """Bind his WORDS to his actual world — the grounding→language coupling.
    Turns his current felt body state (body_sense), his world-model narrative
    (the environment he senses), and recently resolved predictions (what he
    expected vs. what happened) into plain sentences he learns from. This is how
    'heavy' or 'quiet evening' or 'I was right' come to mean something, instead of
    being ungrounded tokens. Read-only; safe in any process."""
    lines: List[str] = []

    # 1) Interoception — how his computational body feels right now.
    try:
        bs = load_json(BODY_SENSE_FILE, default_type=dict) or {}
        dom = bs.get("dominant")
        phrase = _FELT.get(dom or "")
        if phrase:
            lines.append(f"Right now my body feels {dom}: {phrase}.")
    except Exception:
        pass

    # 2) Exteroception — the world he's embedded in (live world model only).
    try:
        from embodiment import world_model
        narr = (world_model.describe() or "").strip()
        if narr and "haven't" not in narr.lower():
            lines.append(narr.rstrip(".") + ".")
    except Exception:
        pass

    # 3) Predictive grounding — what he expected vs. what happened (surprise /
    #    confirmation). Cleaned hard, since prediction text is semi-symbolic.
    try:
        preds = load_json(PREDICTIONS_FILE, default_type=list) or []
        resolved = [p for p in preds if isinstance(p, dict) and p.get("resolved")]
        seen: set = set()
        for p in reversed(resolved):                              # newest first
            if len(seen) >= 3:
                break
            txt = str(p.get("prediction", "") or "")
            txt = re.sub(r"\[[^\]]*\]", "", txt)                  # drop [tags]
            txt = re.sub(r"^\s*if\s+'?|'?\s*recurs?:?", " ", txt, flags=re.I)
            txt = re.sub(r"\s+", " ", txt).strip(" :;,-")
            words = re.findall(r"[A-Za-z']{2,}", txt)
            if len(words) < 4 or len(txt) < 15 or "=" in txt:     # skip symbolic attribute-soup
                continue
            key = txt.lower()[:40]
            if key in seen:                                       # dedup repeats
                continue
            seen.add(key)
            txt = txt[:120]
            if p.get("correct"):
                lines.append(f"I expected that {txt}, and that is what happened.")
            else:
                lines.append(f"I expected that {txt}, but it turned out otherwise.")
    except Exception:
        pass

    return ("\n".join(lines))[-max_chars:]


def _dialogue_experience(max_chars: int = 20000) -> str:
    """His OWN dialogue, as comprehend→respond pairs weighted by how they landed.

    Closes two gaps at once:
      • production→learning loop (Gap B) — he learns from what he *said* and
        whether it worked; well-received replies are rehearsed more, like a child
        consolidating the utterances that got through.
      • comprehension↔production bridge (Gap C) — the user's words, *how he
        understood them*, and his reply are learned together in one passage,
        nudging his ear and mouth toward a shared representation instead of two
        disconnected systems.
    """
    try:
        log = load_json(SPEECH_LOG_FILE, default_type=list) or []
    except Exception:
        return ""
    out: List[str] = []
    for e in log[-120:]:
        if not isinstance(e, dict):
            continue
        reply = str(e.get("reply", "")).strip()
        if len(reply) < 8:
            continue
        q = e.get("quality_score")
        q = float(q) if isinstance(q, (int, float)) else 0.4
        urw = e.get("user_reply_words")
        engaged = isinstance(urw, (int, float)) and urw > 0      # did the user re-engage?
        reps = 1 + int(round(max(0.0, q) * 2)) + (1 if engaged else 0)
        ui = str(e.get("user_input", "")).strip()
        intent = str(e.get("intent", "")).strip()
        topics = ", ".join([t for t in (e.get("topics") or []) if isinstance(t, str)][:3])
        if ui and intent:
            about = f" about {topics}" if topics else ""
            pair = f'Someone said: "{ui}". I understood it as {intent}{about}. I said: "{reply}"'
        else:
            pair = reply
        out += [pair] * reps
    return ("\n".join(out))[-max_chars:]


def _learned_words(max_chars: int = 8000) -> str:
    """His grounded vocabulary — the things he actually knows about — folded into
    the organ as plain definitional sentences (Gap D). Binds symbolic knowledge to
    his language, so a concept he's learned can reach the words he can produce."""
    try:
        kg = load_json(KNOWLEDGE_GRAPH_FILE, default_type=dict) or {}
    except Exception:
        return ""
    ents = kg.get("entities") if isinstance(kg, dict) else None
    if isinstance(ents, dict):                 # entities is keyed by id
        ents = list(ents.values())
    if not isinstance(ents, list):
        return ""
    out: List[str] = []
    for n in ents[-80:]:
        if not isinstance(n, dict):
            continue
        name = str(n.get("name", "")).strip()
        typ = str(n.get("type", "")).strip().lower()
        if len(name) < 2 or not typ or typ == "unknown":     # don't teach "X is a unknown"
            continue
        tags = [t for t in (n.get("tags") or [])
                if isinstance(t, str) and t.lower() not in (name.lower(), typ, "unknown")][:4]
        art = "an" if typ[:1] in "aeiou" else "a"
        if tags:
            out.append(f"{name} is {art} {typ} — associated with {', '.join(tags)}.")
        else:
            out.append(f"{name} is {art} {typ}.")
    return ("\n".join(out))[-max_chars:]


def experience_corpus(max_chars: int = 300000) -> str:
    """Orrin's OWN lived language — research prose, conversations, emotionally-
    weighted memories, and cleaned inner monologue — gathered from the SAME
    sources his continual loop learns from. Used by pretraining so the schooled
    model is grounded in HIM (and there's no distribution shock when the lifelong
    loop takes over), not just public-domain books."""
    parts: List[str] = []
    for fn in (_read_prose, _conversations, _emotional_experience, _inner_monologue,
               grounded_experience, _dialogue_experience, _learned_words):
        try:
            t = fn()
        except Exception:
            t = ""
        if t and t.strip():
            parts.append(t)
    return ("\n".join(parts))[-max_chars:]


def _current_interests(context) -> List[str]:
    """What he's curious about right now — drawn from his working memory, focus
    goal, and last thoughts — so a book on the shelf can speak to it."""
    toks: List[str] = []
    try:
        if isinstance(context, dict):
            for k in ("latest_user_input", "current_focus", "focus_goal", "last_thought"):
                v = context.get(k)
                if isinstance(v, dict):
                    v = v.get("name") or v.get("content") or v.get("description")
                if isinstance(v, str):
                    toks += re.findall(r"[A-Za-z]{4,}", v)
            wm = context.get("working_memory") or []
            if isinstance(wm, list):
                for item in wm[-6:]:
                    s = item.get("content") if isinstance(item, dict) else str(item)
                    toks += re.findall(r"[A-Za-z]{4,}", str(s or ""))
    except Exception:
        pass
    stop = {"that", "this", "with", "have", "what", "your", "about", "they", "them",
            "from", "would", "could", "there", "their", "thing", "really", "going"}
    seen, out = set(), []
    for t in toks:
        tl = t.lower()
        if tl in stop or tl in seen:
            continue
        seen.add(tl)
        out.append(tl)
    return out[:8]


def read_a_book(context=None, steps: int = 45) -> str:
    """He's bored, so he browses the shelf and settles in with a PARTICULAR book.
    A focused reading bout: train mostly on that one book (interleaving a little
    replay so old learning isn't lost), and remember which book drew him. Returns
    a plain sentence so it reads like a thought, not a log line."""
    if not native_lm.available():
        return ""
    topics = _current_interests(context)
    title, text = library.read_book(topics=topics, max_chars=_MAX_BLOCK)
    if not text or len(text) < 1000:
        return ""
    replay = _update_replay(text)
    block = (text + "\n" + replay) if replay else text
    loss = native_lm.train_on(block, steps=steps)
    why = f" (it spoke to what I've been turning over)" if topics else ""
    line = f"I was restless, so I picked up “{title}” and read for a while{why}."
    try:
        st = native_lm.status()
        log_activity(
            f"[language] read a book: “{title}”{why} "
            f"loss={loss:.3f} steps={st.get('train_steps')}" if loss is not None
            else f"[language] read a book: “{title}”{why}"
        )
    except Exception:
        pass
    return line


def consolidate_language(steps: int = 60) -> Dict:
    """One developmental bout: gather experience (library-led), interleave replay,
    train. Fail-safe; no-op if torch unavailable."""
    if not native_lm.available():
        return {"available": False}

    parts: List[str] = []
    lib = library.read_text(_MAX_BLOCK)      # the big, clean English signal
    if lib:
        parts.append(lib)
    prose = _read_prose()
    if prose:
        parts += [prose, prose]              # upweight scarce researched English
    conv = _conversations()
    if conv:
        parts += [conv, conv]                # upweight social language
    emo = _emotional_experience()            # memories weighted by felt weight
    if emo:
        parts.append(emo)
    mono = _inner_monologue()
    if mono:
        parts.append(mono)
    grounded = grounded_experience()         # words bound to felt body + sensed world
    if grounded:
        parts += [grounded, grounded]        # upweight: grounding is scarce, high-value
    dialogue = _dialogue_experience()        # his own replies, weighted by how they landed
    if dialogue:
        parts.append(dialogue)               # production→learning + comprehension↔production
    vocab = _learned_words()                 # symbolic knowledge → his language (word-meaning)
    if vocab:
        parts.append(vocab)

    recent = "\n".join(p for p in parts if p)[-_MAX_BLOCK:]
    if not recent or len(recent) < 2000:
        return {"available": True, "skipped": "not enough clean language yet"}

    replay = _update_replay(recent)
    block = (recent + "\n" + replay) if replay else recent

    loss = native_lm.train_on(block, steps=steps)
    st = native_lm.status()
    if loss is not None:
        log_activity(
            f"[language] consolidated: loss={loss:.3f} "
            f"steps={st.get('train_steps')} tokens_seen={st.get('tokens_seen')} "
            f"library={library.size_chars()//1024}KB"
        )
    return {"available": True, "loss": loss, **st}
