"""Runnable grounding experiment (Phase 3, Part F) — `python -m
brain.cognition.grounding.experiment`.

Generates a larger command family than the unit harness, runs the budgeted
predict→act→observe→learn loop, and prints a verdict with the numbers attached.
Either verdict is an informative result (Part F): 'transfer' means the radical
reading is live for this narrow competence (→ Phase 4A); 'no_transfer' within
budget means single-agent grounding is too slow here without priors (→ Phase 4B,
bring the numbers to Ric).

Honest scope: this grounds the NARROW concept "will this command exit cleanly?"
in the real interpreter's exit code — a concrete external observable Orrin did not
author. It is the narrowest true claim (symbol grounded in another symbol, the
exit code), not general semantic grounding. The point is to measure whether the
LOOP grounds and transfers at all, on this much data — not to declare the project
won.
"""
from __future__ import annotations

import random
from typing import List, Tuple

from brain.cognition.grounding.world_loop import run_experiment, MAX_EPISODES, OBSERVABLES

# Disjoint surface pools so TRAIN and TEST never share a command (no memorisation).
_TRAIN_NAMES = ["foo", "bar", "baz", "qux", "spam", "eggs", "alpha", "beta"]
_TEST_NAMES = ["zonk", "wibble", "frob", "glorp", "snork", "plugh", "xyzzy", "thud"]


def _well_formed(rng: random.Random) -> str:
    a, b = rng.randint(1, 20), rng.randint(1, 20)
    return rng.choice([
        f"print({a})",
        f"print({a} + {b})",
        f"print({a} * {b})",
        f"x = {a}\nprint(x + {b})",
        f"print(len('{'z' * (a % 6 + 1)}'))",
    ])


def _unbound(rng: random.Random, names: List[str]) -> str:
    nm = rng.choice(names)
    return rng.choice([f"print({nm})", f"y = {nm} + 1", f"print({nm} * 2)"])


def _div_zero(rng: random.Random) -> str:
    a = rng.randint(1, 50)
    return rng.choice([f"print({a} / 0)", f"print({a} % 0)", f"print({a} // 0)"])


def _family(rng: random.Random, n: int, names: List[str]) -> List[str]:
    cmds: List[str] = []
    for _ in range(n):
        kind = rng.random()
        if kind < 0.5:
            cmds.append(_well_formed(rng))      # exit 0
        elif kind < 0.8:
            cmds.append(_unbound(rng, names))   # NameError
        else:
            cmds.append(_div_zero(rng))         # ZeroDivisionError
    return cmds


def build_families(seed: int = 7, n_train: int = 120, n_test: int = 40) -> Tuple[List[str], List[str]]:
    rng = random.Random(seed)
    train = _family(rng, n_train, _TRAIN_NAMES)
    test = _family(rng, n_test, _TEST_NAMES)
    return train, test


def report(result: dict) -> str:
    lines = [
        "─" * 64,
        f"GROUNDING EXPERIMENT [{result['target']}] — verdict: {result['verdict'].upper()}",
        "─" * 64,
        f"  accuracy on unseen commands : {result['accuracy']:.3f}",
        f"  base rate (chance)          : {result['base_rate']:.3f}",
        f"  transfer (acc - chance)     : {result['transfer']:+.3f}  (margin {result['margin']})",
        f"  train episodes / test       : {result['train_episodes']} / {result['test_episodes']}",
        "  learned concept signature (feature → weight, P(success)):",
    ]
    for f, s in sorted(result["signature"].items(), key=lambda kv: kv[1]["weight"]):
        lines.append(f"      {f:28s} w={s['weight']:+.2f}  p={s['p_success']:.2f}  (ev {s['evidence']})")
    lines.append("─" * 64)
    return "\n".join(lines)


def main() -> dict:
    train, test = build_families()
    last = {}
    for target in OBSERVABLES:
        last = run_experiment(train, test, target=target, max_episodes=MAX_EPISODES)
        print(report(last))
    return last


if __name__ == "__main__":
    main()
