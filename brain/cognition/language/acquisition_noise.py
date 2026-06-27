# brain/cognition/language/acquisition_noise.py
#
# Log-noise filtering for acquisition.py (CODEBASE_CLEANUP_PLAN 4.5C), lifted
# verbatim to bring that module under the 600-line soft limit. Distinguishes
# real language to learn from (prose, dialogue, felt narrative) from internal
# instrumentation lines (telemetry markers, key=value logs): _is_log_noise and
# _clean_monologue. acquisition.py re-imports both for its corpus readers.
from __future__ import annotations

import re

# Lines that are internal instrumentation, not language to learn from.
_NOISE_LINE = re.compile(
    r"^\s*(\[?\d{4}-\d\d-\d\d|\[(working_memory|chunk|energy|state_processor|metacog|"
    r"temporal|body_sense|symbolic|inhibition|regulation|behavioral_adapt|aware|done|goal|"
    r"attention|env|identity|step_exec|pursue_goal|allostatic)|decision:|cognition log|"
    r"🧠|🌓|⏳|🔄|\[chunk)",
    re.IGNORECASE,
)

# Telemetry / instrumentation markers that must NEVER train his language organ.
# These are his MECHANISM (decision dumps, bandit weights, working-memory
# summaries), not his experience — even paraphrased they aren't "what happened to
# him," so they are dropped outright. Substrings are matched case-insensitively;
# kept specific (quoted JSON keys, tagged prefixes, status emojis) so ordinary
# prose — including dialogue and book text — passes untouched.
_TELEMETRY_MARKERS = (
    "🧠", "🌓", "⏳", "🔄", "📝",
    "chose:", "working memory summary", "during reasoning", "event types:",
    '"weights"', '"features_on"', '"via":', '"band":', '"drive":', '"novel":',
    '"goal":', '"emo":', '"dir":', "multi-factor", "decision_id",
    "[chunk", "[metacog", "[working_memory", "[energy", "[state_processor",
    "[temporal", "[body_sense", "[symbolic", "[inhibition", "[regulation",
    "[behavioral_adapt", "[aware", "[done", "[goal", "[step_exec", "[pursue_goal",
    "cpu=", "health summary",
)


def _is_log_noise(line: str) -> bool:
    """True for instrumentation/telemetry that is his MECHANISM, not his lived
    experience — bandit weights, decision dumps, working-memory summaries. Such
    lines must never train the language organ (it learns the distribution it is
    fed). His experience re-enters as first-person felt prose via
    narrate_experience(). Conservative on prose: a structural JSON drop requires
    an actual brace, so book dialogue ('"Yes," he said') is never mistaken for a
    data dump."""
    s = (line or "").strip().lower()
    if not s:
        return True
    if any(m in s for m in _TELEMETRY_MARKERS):
        return True
    # JSON / data soup: a brace plus a quoted-key colon, or several quoted-key colons.
    if ("{" in s or "}" in s) and '":' in s:
        return True
    if s.count('":') >= 2:
        return True
    # Almost no letters → numbers/punctuation soup, not language.
    alpha = sum(c.isalpha() for c in s)
    if alpha < max(8, int(len(s) * 0.45)):
        return True
    return False


def _clean_monologue(text: str) -> str:
    """Keep only natural-language lines from his inner monologue — drop logs."""
    out = []
    for line in (text or "").splitlines():
        s = line.strip()
        if len(s) < 25 or _NOISE_LINE.search(s) or _is_log_noise(s):
            continue
        # must look like prose: enough alphabetic words, not bracket soup
        words = re.findall(r"[A-Za-z']{2,}", s)
        if len(words) >= 5 and s.count("[") <= 1:
            out.append(s)
    return "\n".join(out)
