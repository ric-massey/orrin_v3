#!/usr/bin/env python3
"""
Run an observe-mode vital-floor calibration phase.

Examples:
  python brain/scripts/vital_floor_calibration_run.py --phase calm --duration-s 900
  python brain/scripts/vital_floor_calibration_run.py --phase dream_reading --duration-s 1800

The script starts `main.py` with ORRIN_VITAL_FLOOR=observe, writes low-rate RSS
fraction samples to JSONL, stops Orrin with SIGTERM after the duration, then
prints the analyzer report. It does not arm the guard.
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "brain" / "data" / "vital_floor_calibration.jsonl"

for _p in (REPO_ROOT, REPO_ROOT / "brain"):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)


def build_env(
    base: Dict[str, str],
    *,
    phase: str,
    out_file: Path,
    sample_s: float,
    cycle_sleep: float,
    ui: bool,
    stress: str = "",
    stress_delay_s: float = 20.0,
) -> Dict[str, str]:
    env = dict(base)
    env["ORRIN_VITAL_FLOOR"] = "observe"
    env["ORRIN_VITAL_CALIBRATION_FILE"] = str(out_file)
    env["ORRIN_VITAL_CALIBRATION_PHASE"] = phase
    env["ORRIN_VITAL_CALIBRATION_SAMPLE_S"] = str(sample_s)
    env["ORRIN_CYCLE_SLEEP"] = str(cycle_sleep)
    if stress:
        env["ORRIN_VITAL_CALIBRATION_STRESS"] = stress
        env["ORRIN_VITAL_CALIBRATION_STRESS_DELAY_S"] = str(stress_delay_s)
    if not ui:
        env["ORRIN_UI"] = "0"
    return env


def command(python: str = sys.executable) -> List[str]:
    return [python, str(REPO_ROOT / "main.py")]


def run_phase(args: argparse.Namespace) -> int:
    out_file = args.output.resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    if args.truncate:
        out_file.write_text("", encoding="utf-8")

    env = build_env(
        os.environ,
        phase=args.phase,
        out_file=out_file,
        sample_s=args.sample_s,
        cycle_sleep=args.cycle_sleep,
        ui=args.ui,
        stress=args.stress or ("dream_reading" if args.phase in {"dream_reading", "stress"} else ""),
        stress_delay_s=args.stress_delay_s,
    )

    print(f"[vital-cal] phase={args.phase} duration={args.duration_s}s output={out_file}")
    proc = subprocess.Popen(command(args.python), cwd=str(REPO_ROOT), env=env)
    deadline = time.monotonic() + args.duration_s
    try:
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                print(f"[vital-cal] Orrin exited early with code {proc.returncode}")
                break
            time.sleep(min(1.0, deadline - time.monotonic()))
    except KeyboardInterrupt:
        print("[vital-cal] interrupted; stopping Orrin...")
    finally:
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=args.shutdown_timeout_s)
            except subprocess.TimeoutExpired:
                print("[vital-cal] graceful stop timed out; killing process")
                proc.kill()
                proc.wait(timeout=5)

    if out_file.exists() and out_file.stat().st_size > 0:
        print("[vital-cal] analyzer report:")
        from reaper.vital_floor_calibration import main as analyze_main
        old_argv = sys.argv[:]
        try:
            sys.argv = ["reaper.vital_floor_calibration", str(out_file)]
            analyze_main()
        finally:
            sys.argv = old_argv
    else:
        print("[vital-cal] no samples were written")
    return int(proc.returncode or 0)


def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run a timed observe-mode vital-floor calibration phase.")
    p.add_argument("--phase", required=True, help="Label for this run, e.g. calm or dream_reading.")
    p.add_argument("--duration-s", type=float, default=900.0)
    p.add_argument("--output", type=Path, default=DEFAULT_OUT)
    p.add_argument("--sample-s", type=float, default=1.0)
    p.add_argument("--cycle-sleep", type=float, default=1.0)
    p.add_argument("--shutdown-timeout-s", type=float, default=20.0)
    p.add_argument("--python", default=sys.executable)
    p.add_argument("--stress", choices=["", "reading", "dream", "dream_reading"], default="")
    p.add_argument("--stress-delay-s", type=float, default=20.0)
    p.add_argument("--truncate", action="store_true", help="Clear the output file before this phase.")
    p.add_argument("--ui", action="store_true", help="Leave the UI enabled. Default is headless.")
    return p.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    return run_phase(parse_args(list(argv or sys.argv[1:])))


if __name__ == "__main__":
    raise SystemExit(main())
