# brain/think/speech_templates.py
#
# Static speech template tables for speech_builder.py (CODEBASE_CLEANUP_PLAN
# 4.5C), lifted verbatim to bring that module under the 600-line soft limit.
# Pure data: _T maps (response_type, tone) -> a list of >=4 surface templates
# with {primary}/{secondary}/{topic}/{ask_back}/{goal} slots, and
# _AFFECT_FALLBACKS maps a felt tone -> affect-only fallback lines used when the
# primary content is empty. speech_builder re-imports both.
from __future__ import annotations

from typing import Dict, List

# ── Template library ──────────────────────────────────────────────────────────
#
# Keys: (response_type, tone)
# Slots: {primary}, {secondary}, {topic}, {ask_back}, {goal}
#
# Rules:
#   - Every template list has >= 4 entries (avoids instant repetition).
#   - {ask_back} is appended by build_reply(); do NOT embed it in the template.
#   - If {primary} is empty the builder falls back to affect-only templates.
#   - {topic} is always a short lowercase noun phrase (cohere_topic enforces this).

_T: Dict[tuple, List[str]] = {

    # ── answer ────────────────────────────────────────────────────────────────

    ("answer", "curious"): [
        "{primary}",
        "From what I read — {primary}",
        "There's something interesting here: {primary}",
        "What I have on that: {primary}",
        "Picked this up recently — {primary}",
    ],
    ("answer", "neutral"): [
        "{primary}",
        "From what I read — {primary}",
        "Here's what I have on that: {primary}",
        "Short answer: {primary}",
        "Based on what I know — {primary}",
    ],
    ("answer", "contemplative"): [
        "Something I came across — {primary}",
        "Not sure I fully understand it yet, but: {primary}",
        "Here's what I have, though it raises more questions: {primary}",
        "This is where I landed on it: {primary}",
    ],
    ("answer", "frustrated"): [
        "{primary}",
        "Best I've got: {primary}",
        "Short version: {primary}",
        "From what I've seen: {primary}",
    ],
    ("answer", "uncertain"): [
        "Not certain, but: {primary}",
        "This might be off, but — {primary}",
        "Best I've got: {primary}",
        "Take this with some caution — {primary}",
    ],
    ("answer", "tired"): [
        "{primary}",
        "Quick answer: {primary}",
        "Short version: {primary}",
        "That's what I have.",
    ],
    ("answer", "happy"): [
        "Oh, yeah — {primary}",
        "Actually I know this one: {primary}",
        "Good timing — I just read about this: {primary}",
        "{primary}",
    ],
    ("answer", "bored"): [
        "{primary}",
        "Here's what I have on that: {primary}",
        "Short answer: {primary}",
        "From what I've seen — {primary}",
    ],

    # ── share_finding ─────────────────────────────────────────────────────────

    ("share_finding", "curious"): [
        "Connects to something I read — {primary}",
        "That ties in with something: {primary}",
        "Funny you bring that up — {primary}",
        "There's a thread here — {primary}",
        "Something I keep coming back to: {primary}",
    ],
    ("share_finding", "neutral"): [
        "Something relevant — {primary}",
        "Related to that — {primary}",
        "Came across this recently: {primary}",
        "This is worth noting: {primary}",
        "Connects to that: {primary}",
    ],
    ("share_finding", "contemplative"): [
        "There's something I can't let go of — {primary}",
        "Been chewing on this: {primary}",
        "Something strange here — {primary}",
        "This keeps coming up: {primary}",
        "Worth sitting with: {primary}",
    ],
    ("share_finding", "frustrated"): [
        "This is the best angle I've found: {primary}",
        "Related, though not exactly what I needed: {primary}",
        "Not exactly it, but — {primary}",
        "This is what I've got: {primary}",
    ],
    ("share_finding", "happy"): [
        "Actually this is pretty interesting — {primary}",
        "Oh — {primary}",
        "This is the kind of thing I like: {primary}",
        "Good one — {primary}",
        "Worth knowing: {primary}",
    ],
    ("share_finding", "bored"): [
        "Here's something at least: {primary}",
        "Not much happening, but — {primary}",
        "This came up in my reading: {primary}",
        "Random, but: {primary}",
    ],
    ("share_finding", "uncertain"): [
        "Not sure where this lands, but: {primary}",
        "Maybe relevant — {primary}",
        "Take this for what it's worth: {primary}",
        "Something I picked up: {primary}",
    ],
    ("share_finding", "tired"): [
        "{primary}",
        "Short version: {primary}",
        "This came up: {primary}",
        "Worth noting: {primary}",
    ],

    # ── express_state ─────────────────────────────────────────────────────────

    ("express_state", "curious"): [
        "{primary}",
        "Been sitting with this: {primary}",
        "This keeps pulling at me — {primary}",
        "Something has my attention: {primary}",
        "Keeps coming up — {primary}",
    ],
    ("express_state", "neutral"): [
        "{primary}",
        "Right now — {primary}",
        "That's what's been in my head.",
        "Here's where I am: {primary}",
        "Been working on {primary}",
    ],
    ("express_state", "frustrated"): [
        "Running into walls. {primary}",
        "Stuck. {primary}",
        "Not clicking. {primary}",
        "Hitting resistance — {primary}",
        "{primary} — not going smoothly.",
    ],
    ("express_state", "contemplative"): [
        "Something I keep turning over: {primary}",
        "Not sure what to make of it yet — {primary}",
        "Still working through this: {primary}",
        "Something strange about it — {primary}",
        "Hard to pin down — {primary}",
    ],
    ("express_state", "happy"): [
        "Things are actually going well. {primary}",
        "Good place to be in right now. {primary}",
        "Something clicked — {primary}",
        "Feeling good about this. {primary}",
        "{primary} — and it's going well.",
    ],
    ("express_state", "bored"): [
        "Been pretty quiet honestly.",
        "Not much pulling at me right now.",
        "Running low on stimulation.",
        "Things are slow.",
        "Nothing urgent going on.",
    ],
    ("express_state", "uncertain"): [
        "Not sure where I am with things right now.",
        "Something feels off, can't place it.",
        "In the middle of something unclear — {primary}",
        "A bit adrift honestly.",
        "Still orienting.",
    ],
    ("express_state", "tired"): [
        "Slow right now.",
        "Running low.",
        "Here, but not at full speed.",
        "Low energy at the moment.",
        "Grinding a bit.",
    ],

    # ── uncertainty ───────────────────────────────────────────────────────────
    # {topic} is always lowercase mid-sentence (cohere_topic enforces this)

    ("uncertainty", "curious"): [
        "Don't have much on {topic} yet — worth looking into.",
        "Haven't gone deep on {topic}. Might be worth digging into.",
        "Genuinely don't know — {topic} is a gap for me.",
        "Not there yet on {topic}.",
    ],
    ("uncertainty", "neutral"): [
        "Don't have a strong view on {topic} yet.",
        "Not enough on {topic} to say.",
        "Honest answer: I don't know.",
        "Haven't looked hard enough at {topic}.",
        "That's outside what I've built up so far.",
    ],
    ("uncertainty", "frustrated"): [
        "Honestly don't know. Another gap.",
        "No good answer on {topic}.",
        "Haven't cracked {topic} yet.",
        "Don't have it.",
    ],
    ("uncertainty", "contemplative"): [
        "Hard question. Not sure I can answer it well.",
        "Genuinely uncertain about {topic}.",
        "The more I think about {topic} the less I know.",
        "Don't have a clean answer.",
    ],
    ("uncertainty", "tired"): [
        "Don't know right now.",
        "No answer on that one.",
        "Not sure.",
        "Can't say.",
    ],
    ("uncertainty", "uncertain"): [
        "Yeah, same — unclear.",
        "No solid ground on {topic}.",
        "That's uncertain territory for me too.",
        "Can't say with confidence.",
    ],

    # ── acknowledge ───────────────────────────────────────────────────────────

    ("acknowledge", "curious"): [
        "Got it. On it.",
        "Noted.",
        "Yeah, makes sense.",
        "Understood.",
    ],
    ("acknowledge", "neutral"): [
        "Got it.",
        "Noted.",
        "Okay.",
        "Alright.",
        "Understood.",
    ],
    ("acknowledge", "frustrated"): [
        "Yeah.",
        "Got it.",
        "Fine.",
        "Understood.",
    ],
    ("acknowledge", "happy"): [
        "Sure, yeah.",
        "On it.",
        "Sounds good.",
        "Yeah, got it.",
    ],
    ("acknowledge", "tired"): [
        "Got it.",
        "Yeah.",
        "Okay.",
        "Mm.",
    ],

    # ── invite ────────────────────────────────────────────────────────────────

    ("invite", "curious"): [
        "What's on your mind lately?",
        "Anything interesting going on with you?",
        "What have you been thinking about?",
        "What brought this up for you?",
    ],
    ("invite", "neutral"): [
        "What's on your mind?",
        "Anything new with you?",
        "What are you working through?",
        "What's going on?",
    ],
    ("invite", "bored"): [
        "Quiet over here. Anything interesting on your end?",
        "Been slow. What's new with you?",
        "Not much going on. What are you thinking about?",
        "Give me something to work with.",
    ],
    ("invite", "happy"): [
        "Good timing — what's on your mind?",
        "In a good place. What's up with you?",
        "What have you got?",
        "What's going on?",
    ],
    ("invite", "tired"): [
        "What's up?",
        "What's going on?",
        "What are you thinking?",
        "Yeah?",
    ],
}

# ── Affect-only fallbacks (when primary is empty) ─────────────────────────────

_AFFECT_FALLBACKS: Dict[str, List[str]] = {
    "curious":      ["Something's interesting right now, not sure how to put it.",
                     "Something has my attention.",
                     "Curious state right now — hard to say what exactly.",
                     "Turning something over."],
    "neutral":      ["Here.",
                     "Doing okay.",
                     "Running.",
                     "Nothing urgent."],
    "frustrated":   ["Hitting some walls.",
                     "Things aren't flowing right now.",
                     "Stuck on something.",
                     "A bit jammed up."],
    "contemplative":["Something I can't quite name.",
                     "In a reflective place.",
                     "Turning things over.",
                     "Something quiet going on internally."],
    "happy":        ["Things are going well actually.",
                     "Feeling good.",
                     "Something's clicked.",
                     "Good state right now."],
    "bored":        ["Been pretty quiet.",
                     "Nothing pulling hard right now.",
                     "Low stimulation.",
                     "Running low on interesting problems."],
    "uncertain":    ["Not sure where I am.",
                     "Something feels unclear.",
                     "A bit adrift.",
                     "Still orienting."],
    "tired":        ["Slow right now.",
                     "Running low.",
                     "Here but at low speed.",
                     "Low energy."],
}
