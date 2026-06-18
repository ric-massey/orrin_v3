# System Metrics — What Valence / Arousal / Homeostasis / Curiosity Are, Why They Move, and How to Keep Their History

*Sixth companion. Answers: can we see the history of the Brain-page System Metrics, what drives them, and the fix so their full history is retained going forward.*

---

## What each metric actually is (source of truth)

The Brain-page System Metrics are built in `brain/ORRIN_loop.py:228-243` from the affect state (`a` = affect_state, `cs` = core_signals) and served/charted by `backend/server/hub.py`. Exact definitions:

| UI metric | Formula (ORRIN_loop.py) | Plain meaning |
|---|---|---|
| **valence** | `0.5 + 0.5 · affect.valence` (`:230`) | Overall pleasant↔unpleasant. Raw valence runs −1..1; centred to 0.5 for the UI. 0.64 ≈ raw +0.28 (mildly positive). |
| **arousal** | `affect.activation_level` (`:231`) | General activation/energy of feeling, not its sign. |
| **homeostasis** | `1 − mean(|signal − setpoint|)·1.6` over all core signals (`:211-217`) | How close *all* his emotions are to their baselines. 1.0 = everything at rest; drops as any signal departs its setpoint. |
| **curiosity** | `core.exploration_drive` (`:239`) | His exploration drive, surfaced directly. |

(For context, the same block also emits energy = `1−resource_deficit`, fatigue = `resource_deficit`, motivation, confidence, distress = `negative_load/2.5`, stability = `affect_stability`, learning = fraction of recently-resolved predictions that came true.)

---

## Why they move — the drivers

- **curiosity = exploration_drive.** It rises when novelty is detected, decays through habituation/satiety, and is re-pumped every time he picks `seek_novelty`/`look_outward`. Because novelty almost always resolved to *neutral* for him (semantic_facts: `seek_novelty → neutral`, conf 0.91) the drive was **never satisfied**, so curiosity stayed pinned high (~0.85, range 0.76–0.91). It moves in small ripples as novelty signals fire and habituation damps them.
- **arousal = activation_level.** Tracks how activated he is; rises on novelty/exploration bursts and decays toward rest. Held moderate (~0.38) — engaged, not agitated.
- **valence** moves with the **reward channel**: each agentic/clarity/stability reward nudges it up, each penalty (`log_penalty_signal`, failure-tagged event) nudges it down. It stayed mildly positive (~0.64) because almost nothing tagged as failure — his stuckness was never appraised as negative (see `run_analysis.md`), so there was little to push valence down.
- **homeostasis = inverse total deviation from setpoints.** It falls whenever any core signal sits far from its baseline. **Key coupling: his own high curiosity depresses his homeostasis** — `exploration_drive` parked at ~0.85 is far above its setpoint, so it drags the homeostasis composite down to ~0.78 even though nothing is "wrong." Homeostasis therefore moves opposite to whichever signal is currently most off-baseline (exploration_drive, impasse_signal, motivation).

**What the live window showed (cycles ~7,800 → 8,323, the only history that survived):** all four sit in a tight, flat band — valence 0.59–0.68, arousal 0.34–0.40, homeostasis 0.74–0.81, curiosity 0.76–0.91 — and barely move across ~500 cycles. The only directional signal is a **downward drift in valence and arousal at the end of the window**, consistent with the late-life `impasse_signal`/brooding (the `cognitive_cost` alarm from `deeper_pass.md`) finally leaking into the `distress`→valence channel. In short: a high-curiosity, low-distress, near-baseline equilibrium — the numeric face of "full of the urge to explore, content, going nowhere."

---

## Why we could only see ~240 cycles — and the fix (shipped)

`telemetry_history.json` is a **rolling window capped at `HISTORY_CAP` (240 points)** — sized for the live UI chart, overwritten as it fills, and never rotated (`hub.py` `_save_history` writes `points[-HISTORY_CAP:]`). So it can answer "what are these right now?" but **not** "how did they change over a whole life?" Everything older than the last ~240 samples was gone.

**Fix implemented in `backend/server/hub.py`:** an append-only long-term archive.
- New `telemetry_archive.jsonl` (uncapped, one JSON line per telemetry point) alongside the rolling window.
- Every history point is buffered and flushed to the archive on the existing ~15-point cadence (`_archive_points`), so there's no extra per-cycle filesystem cost and the live chart is unchanged.
- Best-effort (wrapped in try/except) — telemetry can never crash the loop.

**Result going forward:** the next life will accumulate a complete, timestamped trajectory of valence/arousal/homeostasis/curiosity (and every other metric in the point: energy, fatigue, motivation, confidence, distress, stability, learning), so the "why is X changing?" question becomes answerable across the *whole* run, not just the last 4 minutes.

**How to read it later:**
```bash
# full series of one metric over the whole life
python3 -c "import json; [print(p['cycle'], p.get('valence'), p.get('curiosity')) \
  for p in map(json.loads, open('brain/data/telemetry_archive.jsonl'))]"
```

*Note:* this only retains history from the next run onward — this life's early data is already overwritten and cannot be recovered.

---

*Generated 2026-06-17. One code change (telemetry archival in `hub.py`); analysis otherwise.*
