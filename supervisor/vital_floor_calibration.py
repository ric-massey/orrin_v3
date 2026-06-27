from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List


# Armed thresholds (mirror supervisor/vital_floor.py dataclass defaults, calibrated
# 2026-06-17). Used only to turn an observed peak into a "minimum viable body"
# recommendation; kept here as constants so the analyzer stays import-free.
_ARMED_WARN_FRAC = 0.50
_ARMED_SHED_FRAC = 0.55

# Oscillation verdict cutoff, in fraction-of-grant units. §8.2 asks whether pressure
# *slams* between near-empty and near-full (a fast sawtooth that warrants a per-phase
# band) or drifts gently. That is a question about the size of consecutive swings, NOT
# the total range over a long run — a slow idle drift can cover a wide range with tiny
# steps. So the verdict keys on the 95th-percentile consecutive step; range/max_step are
# reported as context.
_SLAM_STEP = 0.15

_GB = float(1024 * 1024 * 1024)


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    vals = sorted(values)
    idx = (len(vals) - 1) * max(0.0, min(100.0, pct)) / 100.0
    lo = int(idx)
    hi = min(lo + 1, len(vals) - 1)
    if lo == hi:
        return vals[lo]
    frac = idx - lo
    return vals[lo] * (1.0 - frac) + vals[hi] * frac


def load_samples(path: Path) -> List[Dict[str, Any]]:
    samples: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:  # intentional: skip malformed sample line
            continue
        try:
            frac = float(rec.get("frac"))
        except (ValueError, TypeError):  # intentional: skip non-numeric frac
            continue
        if frac > 0:
            rec["frac"] = frac
            samples.append(rec)
    return samples


def _oscillation(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Shape of how memory pressure moves within one phase (§8.2): does the felt
    band swing gently around a center, or slam between near-empty and near-full?

    Samples are ordered by `monotonic_s` when present (else input order), and the
    absolute step between consecutive fracs measures the swing.
    """
    ordered = sorted(
        records,
        key=lambda r: r["monotonic_s"] if isinstance(r.get("monotonic_s"), (int, float)) else 0.0,
    )
    fracs = [float(r["frac"]) for r in ordered]
    rng = (max(fracs) - min(fracs)) if fracs else 0.0
    steps = [abs(b - a) for a, b in zip(fracs, fracs[1:])]
    max_step = max(steps) if steps else 0.0
    p95_step = _percentile(steps, 95) if steps else 0.0
    slams = p95_step > _SLAM_STEP
    return {
        "range": round(rng, 4),
        "max_step": round(max_step, 4),
        "p95_step": round(p95_step, 4),
        "mean_step": round(mean(steps), 4) if steps else 0.0,
        "verdict": "slams" if slams else "gentle",
    }


def _rss_bytes(rec: Dict[str, Any]) -> float:
    """Absolute RSS for a sample — prefer the recorded bytes, else reconstruct from
    frac × the grant the sample was taken under."""
    rb = rec.get("rss_bytes")
    if isinstance(rb, (int, float)) and rb > 0:
        return float(rb)
    bb = rec.get("budget_bytes")
    if isinstance(bb, (int, float)) and bb > 0:
        return float(rec["frac"]) * float(bb)
    return 0.0


def _min_viable_body(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Smallest grant that completes a full dream+reading cycle without thrashing
    (§8.3). The grant is hardware-independent in *bytes*, so we work from observed
    peak RSS, not the fraction (which is relative to whatever grant was sampled).

    Uses the heaviest phase (dream/reading/stress) when the run is labelled that
    way, else all samples. The floor is the grant at which that peak would exactly
    hit the shed line; the recommendation keeps the peak at the warn line for headroom.
    """
    heavy = [s for s in samples if any(k in str(s.get("phase") or "").lower()
                                       for k in ("dream", "read", "stress"))]
    used = heavy or samples
    peak = max((_rss_bytes(s) for s in used), default=0.0)
    if peak <= 0.0:
        return {}
    return {
        "from_phase": "dream/reading" if heavy else "all-samples",
        "peak_rss_gb": round(peak / _GB, 3),
        "floor_grant_gb": round(peak / _ARMED_SHED_FRAC / _GB, 3),
        "recommended_grant_gb": round(peak / _ARMED_WARN_FRAC / _GB, 3),
        "note": (
            "floor_grant = peak/shed_frac (below this, a dream+reading peak forces "
            "shedding); recommended_grant = peak/warn_frac (peak only reaches the warn "
            f"line). Armed warn={_ARMED_WARN_FRAC}, shed={_ARMED_SHED_FRAC}."
        ),
    }


def summarize(samples: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    sample_list = list(samples)
    by_phase: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for rec in sample_list:
        by_phase[str(rec.get("phase") or "unspecified")].append(rec)

    phases: Dict[str, Dict[str, Any]] = {}
    all_vals: List[float] = []
    for phase, recs in sorted(by_phase.items()):
        vals = [float(r["frac"]) for r in recs]
        all_vals.extend(vals)
        phases[phase] = {
            "n": len(vals),
            "mean": round(mean(vals), 4),
            "p50": round(_percentile(vals, 50), 4),
            "p90": round(_percentile(vals, 90), 4),
            "p95": round(_percentile(vals, 95), 4),
            "p99": round(_percentile(vals, 99), 4),
            "max": round(max(vals), 4),
            "oscillation": _oscillation(recs),
        }

    if not all_vals:
        return {"n": 0, "phases": {}, "recommendation": {}, "min_viable_body": {}}

    p50 = _percentile(all_vals, 50)
    p95 = _percentile(all_vals, 95)
    p99 = _percentile(all_vals, 99)
    peak = max(all_vals)

    warn = min(0.90, max(0.50, p95 + 0.05))
    shed = min(0.98, max(warn + 0.05, p99 + 0.03, peak + 0.02))
    recover = max(0.10, min(warn - 0.08, p50 + 0.05))

    return {
        "n": len(all_vals),
        "phases": phases,
        "recommendation": {
            "warn_frac": round(warn, 3),
            "shed_frac": round(shed, 3),
            "recover_frac": round(recover, 3),
            "sustain_s": 8.0,
            "note": "Candidate thresholds from the supplied samples; verify in observe mode before changing armed defaults.",
        },
        "min_viable_body": _min_viable_body(sample_list),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize ORRIN_VITAL_CALIBRATION_FILE samples.")
    parser.add_argument("path", type=Path)
    args = parser.parse_args()

    report = summarize(load_samples(args.path))
    print(json.dumps(report, indent=2, sort_keys=True))

    # §8.2 oscillation shape — per-phase swing verdict.
    phases = report.get("phases") or {}
    if phases:
        print()
        print("Oscillation shape (§8.2):")
        for phase, p in phases.items():
            osc = p.get("oscillation") or {}
            print(f"  {phase}: {osc.get('verdict', '?')} "
                  f"(range {osc.get('range', 0)}, p95 step {osc.get('p95_step', 0)})")

    # §8.3 minimum viable body.
    mvb = report.get("min_viable_body") or {}
    if mvb:
        print()
        print("Minimum viable body (§8.3):")
        print(f"  peak RSS {mvb['peak_rss_gb']} GB (from {mvb['from_phase']})")
        print(f"  floor grant {mvb['floor_grant_gb']} GB · recommended {mvb['recommended_grant_gb']} GB")

    rec = report.get("recommendation") or {}
    if rec:
        print()
        print("Suggested observe run:")
        print(f"ORRIN_VITAL_WARN_FRAC={rec['warn_frac']}")
        print(f"ORRIN_VITAL_SHED_FRAC={rec['shed_frac']}")
        print(f"ORRIN_VITAL_RECOVER_FRAC={rec['recover_frac']}")
        print(f"ORRIN_VITAL_SUSTAIN_S={rec['sustain_s']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
