#!/usr/bin/env python3
"""Run E5 (does a stored answer change a decision?) on Orrin's real selector.

    .venv/bin/python scripts/run_e5.py [--seeds 20] [--split heldout|dev|all] [--out report.json]

Runs in a scratch data dir (never brain/data). The oracle and blind deciders run
first: if the oracle fails or the blind one passes, the harness is broken and the
selector's result means nothing. See brain/eval/e5_answer_use.py.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

_scratch = Path(tempfile.mkdtemp(prefix="orrin-e5-"))
for k in ("DATA", "LOGS", "THINK", "STATE"):
    os.environ[f"ORRIN_{k}_DIR"] = str(_scratch / k.lower())
os.environ.setdefault("ORRIN_KEYRING", "0")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from brain.eval import e5_answer_use as e5  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--split", default="heldout", choices=("heldout", "dev", "all"))
    ap.add_argument("--out")
    a = ap.parse_args()

    reports = {}
    for name, fn in (("oracle", e5.oracle_decider), ("blind", e5.blind_decider),
                     ("topic", e5.topic_decider), ("orrin_selector", e5.orrin_selector_decider)):
        r = e5.run(fn, name=name, seeds=a.seeds, split=a.split)
        reports[name] = r
        print(r.summary(), "\n")

    sane = reports["oracle"].passed and not reports["blind"].passed and not reports["topic"].passed
    print("harness check:", "OK" if sane else "BROKEN — ignore the selector result")
    if a.out:
        Path(a.out).write_text(json.dumps({k: vars(v) for k, v in reports.items()}, indent=1))
    return 0 if sane else 2


if __name__ == "__main__":
    raise SystemExit(main())
