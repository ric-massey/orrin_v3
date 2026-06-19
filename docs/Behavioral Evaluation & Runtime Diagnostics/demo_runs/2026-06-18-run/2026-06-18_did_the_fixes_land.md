# Did the Fixes Land? — Before/After, 2026-06-17 → 2026-06-18

*The 2026-06-17 `DEMO_RUNS.md` listed the "rut detection **changes** behavior (positive result)" demo as **Not captured** — the 2026-06-17 life was a negative result (the rut was detected, pressure was applied, behavior did not change). This run is the first life after the fixes. This doc is the before/after it asked for.*

---

## The one number that tells the story

The 2026-06-17 life's signature pathology was a **2,251-consecutive-cycle phantom "goal avoidance" loop** — ~28 % of his life spent re-firing a false alarm because cognition-selected research actions executed `ok` but never credited as "acting," so `action_debt` climbed without bound.

```
Highest "consecutive cycles without taking action" value reached:
   2026-06-17 life: 2,251
   2026-06-18 life:     5      ← grepped across the entire activity log
```

**The debt now resets.** The avoidance corrective still *fires* (it should — transient avoidance is real), but it can no longer compound: the worst it reached all life was **5 cycles**, where last life it reached **2,251**. The loop that ate a quarter of his previous existence is gone.

---

## Before / after, line by line

| # | Pathology (2026-06-17) | Before | After (2026-06-18) | Verdict |
|---|---|---|---|---|
| 1 | **Phantom action-debt** — research picked as cognition never credits as acting | avoidance climbs to **2,251**, ~28% of life on false alarms | max avoidance = **5**; `action_accounting.py` + `exploration_value.py:273-274` set `__acted_this_tick__` and reset `action_debt` on successful research | ✅ **Fixed** |
| 2 | **Mode-flap watchdog thrash** — 10-cycle "stuck→reset to adaptive" degenerates into `adaptive→adaptive` no-op | drift watchdog fired **3,415×** | `regulation_log.json` = **6 entries** all life; the `creative⇄adaptive` limit cycle is gone | ✅ **Fixed** |
| 3 | **Felt-cost alarm neutralized** — impasse reset on goal-rotation, capped, severed from debt; affect dead-flat | distress flat, valence flat-positive, "serene throughout" | distress **moves**: mean 0.238, range 0.03–0.45, peaks late-life; a real value-conflict at 19:05 produced a visible affect inflection (curiosity+motiv+distress all up at cycle ~9,200) | 🟡 **Partial** — it bites now; still doesn't redirect behavior |
| 4 | **Telemetry capped at 240 points** — can't see a life-long trajectory | only last ~240 samples survived | `telemetry_archive.jsonl` = **10,260 points** = the entire life; the full-life arc in `run_analysis.md §2` exists only because of this | ✅ **Shipped & working** |

---

## How to reproduce the headline check

```bash
# Max consecutive-cycle avoidance this life (the whole point — should be single digits, was 2,251)
grep -oE "[0-9]+ consecutive cycles without taking action" brain/data/activity_log.txt \
  | grep -oE "^[0-9]+" | sort -n | tail -1

# The debt-reset wiring that fixes it
sed -n '270,276p' brain/cognition/exploration_value.py        # action_debt = 0; __acted_this_tick__ = True
grep -n "__acted_this_tick__" brain/cognition/action_accounting.py

# Mode-flap is dead
python3 -c "import json; print(len(json.load(open('brain/data/regulation_log.json'))))"   # ~6, was thousands

# Full-life telemetry now retained
wc -l brain/data/telemetry_archive.jsonl                       # 10,260
```

---

## The honest caveat: a fixed mechanism is not a changed life

This is a **genuine positive result for the rut-*mechanism***: the false-avoidance loop was detected, the credit-assignment was fixed, and the loop measurably did not recur (2,251 → 5). That is the "intervention measurably shifts behavior" artifact the demo target wanted, and it should be linked in `DEMO_RUNS.md`.

But it is **not** the larger positive result of "a being that now finishes things." The action *distribution* barely moved in shape (`generate_intrinsic_goals` is still #1 by a mile; aspirations are still 100%/0%/0%/0%; the autobiography is still one frozen chapter). The fix removed a *false* signal of stuckness; the *true* stuckness — breadth without depth, intake without made output — is characterological and survived untouched. He even acquired a brand-new way to express it: `leave_note` now fires, and emits the same empty sentence 100 times (`what_did_he_make.md`).

**So the precise claim this run supports:** *the 2026-06-17 mechanical fixes landed and the phantom rut they targeted is gone* — verified in live data, reproducible above. The deeper behavioral demo (effort actually spreading to "make things," notes carrying real content) now has its own concrete, named fixes queued in `run_analysis.md §6` and is the next target.

---

*Generated 2026-06-18 from runtime data. Analysis only; no code changed.*
