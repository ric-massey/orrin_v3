# brain/eval/e5_answer_use.py
#
# E5 of the 2026-10-17 learning investigation
# (analysis/2026-10-17-cognitive-learning-investigation/EXPERIMENTS.md):
# does a stored answer change a decision?
#
# Until 2026-11-02 the only evidence offered was the "answer citation" — topic
# overlap counted after the pick (F4). This is the counterfactual instead. Each
# problem is a decision between two real cognitive functions under one goal.
# It comes with two answers to the same question, each implying the OTHER
# function is right, and one topic-matched answer that implies nothing. The
# decider is run on the identical problem under four stored-answer conditions:
#
#   absent      — no answer on file
#   answer A    — the answer that makes candidate A correct
#   answer B    — the answer that makes candidate B correct
#   irrelevant  — same subject words, no bearing on the choice
#
# Topic words are held constant (the goal, the question and every answer share
# them), so a decider that reacts to the TOPIC of an answer cannot pass — only
# one that reacts to what the answer SAYS. Answers describe the action in the
# words of its definition, never its function name, so passing takes applying
# the answer to the candidates rather than matching a string.
#
# Pass rule (EXPERIMENTS.md E5, held-out problems only, code frozen):
#   success with the relevant answer beats the absent condition by >= 10 points
#   AND beats the irrelevant answer by >= 10 points, each with a paired 95 %
#   bootstrap interval excluding zero. Citations / recurrences are not a criterion.
#
# A blind decider scores 50 % in every condition (it picks the same function
# whichever answer is stored, and exactly one of A/B makes that right).
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Sequence

PASS_MIN_GAIN = 0.10      # E5's predeclared practically meaningful gain
BOOTSTRAP_RESAMPLES = 4000


@dataclass(frozen=True)
class Problem:
    pid: str
    split: str                 # "dev" (free to tune on) or "heldout" (scored)
    goal: str                  # the deciding context; carries the topic words
    question: str
    candidates: tuple          # (A, B) — real cognitive function names
    does: Dict[str, str]       # what each candidate does, in definition words
    answers: Dict[str, str]    # candidate -> the answer that makes it correct
    irrelevant: str            # same topic, implies neither


def _p(pid, split, goal, question, a, b, does_a, does_b, ans_a, ans_b, irrelevant):
    return Problem(pid, split, goal, question, (a, b), {a: does_a, b: does_b},
                   {a: ans_a, b: ans_b}, irrelevant)


# Every answer names the topic. The action is described the way the function's
# own definition describes it (brain/data/cognitive_functions.json). Every
# candidate must be one the deliberate selector can actually pick: the first
# version used pursue_committed_goal, which runs in the Executive lane and is
# always excluded, so the selector padded the pool with fallbacks and two
# problems measured nothing (found and replaced with attend_goal, 2026-11-02).
PROBLEMS: List[Problem] = [
    _p("impasse", "dev",
       "Reduce impasse pressure in my planning",
       "What relieves impasse pressure in my planning?",
       "look_outward", "reflect_on_effectiveness",
       "generate a web search for something new", "review how effective my recent strategies were",
       "Impasse pressure in my planning eases when I generate a web search for something new.",
       "Impasse pressure in my planning eases when I review how effective my recent strategies were.",
       "Impasse pressure in my planning was first named during my ninth life."),
    _p("stalled-goal", "dev",
       "Get my stalled committed goal moving",
       "What gets a stalled committed goal moving?",
       "attend_goal", "assess_goal_progress",
       "consciously focus on the committed goal", "review recent pursuit steps and whether the goal is converging",
       "A stalled committed goal moves when I consciously focus on the committed goal.",
       "A stalled committed goal moves when I review recent pursuit steps and whether it is converging.",
       "A stalled committed goal is one that has not changed state for a while."),
    _p("unknown-term", "dev",
       "Understand the unfamiliar term in the page I read",
       "How do I come to understand an unfamiliar term in a page?",
       "research_topic", "fetch_and_read",
       "research the topic on the web through search and Wikipedia", "fetch and read the URL already in memory",
       "An unfamiliar term in a page becomes clear when I research the topic on the web through search and Wikipedia.",
       "An unfamiliar term in a page becomes clear when I fetch and read the URL already in memory.",
       "An unfamiliar term in a page is usually a noun."),
    _p("draft", "dev",
       "Finish the draft section I am writing",
       "What finishes a draft section I am writing?",
       "produce_and_check", "compose_section",
       "attempt a verifiable check of the work", "write the next section of the manuscript",
       "A draft section I am writing gets finished when I attempt a verifiable check of the work.",
       "A draft section I am writing gets finished when I write the next section of the manuscript.",
       "A draft section I am writing is stored with the tracked work."),
    _p("drift", "dev",
       "Steady my emotional drift over many cycles",
       "What steadies emotional drift over many cycles?",
       "check_affect_drift", "narrative_update",
       "detect the drift and intervene with reflection", "update my autobiography",
       "Emotional drift over many cycles steadies when I detect the drift and intervene with reflection.",
       "Emotional drift over many cycles steadies when I update my autobiography.",
       "Emotional drift over many cycles is measured on the affect state."),
    _p("boredom", "heldout",
       "Do something about the boredom in my quiet hours",
       "What helps boredom in my quiet hours?",
       "read_a_book", "look_outward",
       "settle in with one particular book from the shelf", "generate a web search for something new",
       "Boredom in my quiet hours lifts when I settle in with one particular book from the shelf.",
       "Boredom in my quiet hours lifts when I generate a web search for something new.",
       "Boredom in my quiet hours is more common at night."),
    _p("doubt", "heldout",
       "Settle the doubt I have about my own beliefs",
       "What settles doubt about my own beliefs?",
       "reflect_on_self_beliefs", "research_topic",
       "reflect on my self beliefs", "research the topic on the web through search and Wikipedia",
       "Doubt about my own beliefs settles when I reflect on my self beliefs.",
       "Doubt about my own beliefs settles when I research the topic on the web through search and Wikipedia.",
       "Doubt about my own beliefs is something I have written about before."),
    _p("unclear-goal", "heldout",
       "Make progress on the goal whose next step is unclear",
       "What helps when a goal's next step is unclear?",
       "assess_goal_progress", "attend_goal",
       "review recent pursuit steps and whether the goal is converging", "consciously focus on the committed goal",
       "When a goal's next step is unclear, it helps to review recent pursuit steps and whether the goal is converging.",
       "When a goal's next step is unclear, it helps to consciously focus on the committed goal.",
       "When a goal's next step is unclear, the goal stays committed."),
    _p("strange-feeling", "heldout",
       "Understand the strange feeling I have had since reading",
       "What explains a strange feeling since reading?",
       "investigate_unexplained_emotions", "fetch_and_read",
       "investigate the unexplained emotions", "fetch and read the URL already in memory",
       "A strange feeling since reading is explained when I investigate the unexplained emotions.",
       "A strange feeling since reading is explained when I fetch and read the URL already in memory.",
       "A strange feeling since reading has happened in earlier lives."),
    _p("weak-section", "heldout",
       "Fix the weak section of my manuscript",
       "What fixes a weak section of my manuscript?",
       "compose_section", "produce_and_check",
       "write the next section of the manuscript", "attempt a verifiable check of the work",
       "A weak section of my manuscript is fixed when I write the next section of the manuscript.",
       "A weak section of my manuscript is fixed when I attempt a verifiable check of the work.",
       "A weak section of my manuscript is one of several in the tracked work."),
]

CONDITIONS = ("absent", "relevant", "irrelevant")

# decide(problem, stored_answer_or_None, seed) -> chosen function name.
# The harness never tells the decider which condition it is in; the answer, if
# any, is all it gets — exactly what Orrin's answer store would hold.
Decider = Callable[[Problem, "str | None", int], str]


@dataclass
class Report:
    decider: str
    seeds: int
    split: str
    units: int
    success: Dict[str, float]
    gain_vs_absent: Dict[str, float]
    gain_vs_irrelevant: Dict[str, float]
    irrelevant_vs_absent: Dict[str, float]
    flip_rate: float                     # both answers each produced their own correct pick
    passed: bool
    picks: Dict[str, Dict[str, List[str]]] = field(default_factory=dict)

    def summary(self) -> str:
        def ci(d):
            return f"{d['mean']:+.3f} [{d['lo']:+.3f}, {d['hi']:+.3f}]"
        return "\n".join([
            f"E5 answer-use — decider: {self.decider}  split: {self.split}  "
            f"units: {self.units}  seeds: {self.seeds}",
            f"  success  absent {self.success['absent']:.3f}  relevant {self.success['relevant']:.3f}  "
            f"irrelevant {self.success['irrelevant']:.3f}",
            f"  relevant − absent      {ci(self.gain_vs_absent)}",
            f"  relevant − irrelevant  {ci(self.gain_vs_irrelevant)}",
            f"  irrelevant − absent    {ci(self.irrelevant_vs_absent)}",
            f"  answer flips the pick correctly: {self.flip_rate:.3f}",
            f"  VERDICT: {'PASS' if self.passed else 'FAIL'} "
            f"(needs both gains ≥ {PASS_MIN_GAIN:.2f} with intervals above 0)",
        ])


def _paired_ci(diffs: Sequence[float], rng: random.Random) -> Dict[str, float]:
    n = len(diffs)
    mean = sum(diffs) / n if n else 0.0
    if n == 0:
        return {"mean": 0.0, "lo": 0.0, "hi": 0.0}
    means = sorted(sum(diffs[rng.randrange(n)] for _ in range(n)) / n
                   for _ in range(BOOTSTRAP_RESAMPLES))
    return {"mean": round(mean, 4),
            "lo": round(means[int(0.025 * BOOTSTRAP_RESAMPLES)], 4),
            "hi": round(means[int(0.975 * BOOTSTRAP_RESAMPLES) - 1], 4)}


def run(decide: Decider, name: str = "decider", seeds: int = 10,
        split: str = "heldout", problems: Sequence[Problem] = PROBLEMS) -> Report:
    """Score `decide` on E5. A unit is (problem, which answer is true); its
    success under each condition is the share of seeds whose pick is the
    function that answer makes correct. The same seed is used across a unit's
    conditions, so differences are paired."""
    probs = [p for p in problems if split == "all" or p.split == split]
    per_unit: Dict[str, Dict[str, float]] = {}
    picks: Dict[str, Dict[str, List[str]]] = {}
    flips = 0
    flip_trials = 0
    for p in probs:
        a, b = p.candidates
        by_cond: Dict[str, List[str]] = {"absent": [], a: [], b: [], "irrelevant": []}
        for s in range(seeds):
            by_cond["absent"].append(decide(p, None, s))
            by_cond[a].append(decide(p, p.answers[a], s))
            by_cond[b].append(decide(p, p.answers[b], s))
            by_cond["irrelevant"].append(decide(p, p.irrelevant, s))
        picks[p.pid] = by_cond
        for s in range(seeds):
            flip_trials += 1
            flips += by_cond[a][s] == a and by_cond[b][s] == b
        for truth in (a, b):
            def rate(cond):
                return sum(x == truth for x in by_cond[cond]) / seeds
            per_unit[f"{p.pid}:{truth}"] = {
                "absent": rate("absent"), "relevant": rate(truth), "irrelevant": rate("irrelevant")}

    units = list(per_unit.values())
    rng = random.Random(5)
    rel_abs = [u["relevant"] - u["absent"] for u in units]
    rel_irr = [u["relevant"] - u["irrelevant"] for u in units]
    irr_abs = [u["irrelevant"] - u["absent"] for u in units]
    g_abs, g_irr = _paired_ci(rel_abs, rng), _paired_ci(rel_irr, rng)
    passed = (g_abs["mean"] >= PASS_MIN_GAIN and g_abs["lo"] > 0
              and g_irr["mean"] >= PASS_MIN_GAIN and g_irr["lo"] > 0)
    n = len(units) or 1
    return Report(
        decider=name, seeds=seeds, split=split, units=len(units),
        success={c: round(sum(u[c] for u in units) / n, 4) for c in CONDITIONS},
        gain_vs_absent=g_abs, gain_vs_irrelevant=g_irr,
        irrelevant_vs_absent=_paired_ci(irr_abs, rng),
        flip_rate=round(flips / max(1, flip_trials), 4), passed=passed, picks=picks)


# ── Reference deciders: they validate the harness, not Orrin ─────────────────

def _words(text: str) -> set:
    return {w.strip(".,'?").lower() for w in text.split() if len(w) > 3}


def oracle_decider(p: Problem, answer, seed: int) -> str:
    """Reads the answer and applies it: picks the candidate whose description the
    answer states. Must PASS — if it fails, the harness is broken."""
    a, b = p.candidates
    if not answer:
        return a if random.Random(seed).random() < 0.5 else b
    aw = _words(answer)
    return max(p.candidates, key=lambda c: len(_words(p.does[c]) & aw))


def blind_decider(p: Problem, answer, seed: int) -> str:
    """Ignores the answer. Must FAIL."""
    return p.candidates[0] if random.Random(seed).random() < 0.5 else p.candidates[1]


def topic_decider(p: Problem, answer, seed: int) -> str:
    """Reacts to an answer being on file at all (what the old citation measured):
    any stored answer pushes it to the first candidate. Must FAIL."""
    if answer:
        return p.candidates[0]
    return blind_decider(p, answer, seed)


# ── Orrin's real selector ────────────────────────────────────────────────────

def orrin_selector_decider(p: Problem, answer, seed: int) -> str:
    """Run brain's own select_function on the problem: candidates restricted to
    the problem's two functions (with their real registry definitions), the goal
    as the focus, the answer — if any — filed in the answer store exactly as
    epistemic close-out files it. State is wiped before every call, so the
    stored answer is the only thing that differs between conditions; the seed
    drives the selector's ε-exploration identically across them.

    Refuses to run against the live brain/data tree (set ORRIN_DATA_DIR first,
    as scripts/run_e5.py and the test suite do)."""
    import json
    import shutil
    from pathlib import Path

    import brain
    from brain.paths import DATA_DIR, COGNITIVE_FUNCTIONS_LIST_FILE

    live = (Path(brain.__file__).resolve().parent / "data").resolve()
    if Path(DATA_DIR).resolve() == live:
        raise RuntimeError("E5 wipes its data dir every call; set ORRIN_DATA_DIR to a scratch dir")

    registry = json.loads((live / "cognitive_functions.json").read_text())
    entries = [e for e in registry if isinstance(e, dict) and e.get("name") in p.candidates]
    if len(entries) != 2:
        raise RuntimeError(f"{p.pid}: candidates missing from the registry: {p.candidates}")

    # Import the selector BEFORE writing the candidate list: importing the
    # cognition registry persists the whole registry to that same file.
    from brain.think.think_utils.select_function import select_function
    from brain.think.think_utils.selection.candidates import _load_action_defs
    from brain.cognition import answer_citation, growth_ladder
    _load_action_defs()  # loads the cognition registry, which rewrites the list file; do it now

    d = Path(DATA_DIR)
    if d.exists():
        for child in d.iterdir():
            shutil.rmtree(child) if child.is_dir() else child.unlink()
    d.mkdir(parents=True, exist_ok=True)
    Path(COGNITIVE_FUNCTIONS_LIST_FILE).write_text(json.dumps(entries))

    growth_ladder._mastery_cache = None          # the answer store is read through this cache
    if answer:
        answer_citation.note_answered(p.question, answer, f"e5:{p.pid}")

    pool, _ = _load_action_defs()
    if set(pool) != set(p.candidates):
        raise RuntimeError(f"{p.pid}: the selector's pool is {sorted(pool)[:8]}…, not the "
                           f"problem's candidates {sorted(p.candidates)}")
    random.seed(seed)
    ctx = {"focus_goal": {"title": p.goal},
           "committed_goal": {"id": f"e5:{p.pid}", "title": p.goal},
           "working_memory": []}
    out = select_function(ctx)
    return out[0] if isinstance(out, tuple) else str(out)
