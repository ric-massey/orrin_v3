# Restart Note — 2026-06-24 (~08:32)

**Why:** mid-run diagnosis found Orrin was *alive but throttled into shallow idle*.
The host-resource guard was pausing the heavy (memory-hungry) cognitive cycles almost
continuously because the machine was swap-starved. Of 12.5k `run_log.txt` lines, ~all
the non-heartbeat output was `[host] PAUSE heavy cycles — swap_used 8–9.6GB > pause=4.0GB`
ping-ponging with `resume`. Result: no new artifacts since 01:21, LLM-dependent paths
no-op'ing, only light heartbeat cycles advancing.

**Root cause (not an Orrin bug):** this is an **Apple M1 with 8 GB unified memory**
(soldered — not upgradeable). The host swap guard is *working correctly*; the box
simply had no RAM headroom. The user freed RAM (closed Opera/Chrome): swap dropped
8.8 GB → ~3.9 GB, but the running instance stayed paused because of the guard's
anti-flap hysteresis (leaving PAUSE requires recovering past the **warn** line, not
just back under the pause line).

## What changed
1. **Swap thresholds are now env-tunable** (`watchdogs.py`, new `_swap_gb_env` helper):
   - `ORRIN_SWAP_WARN_GB`  (default 2)
   - `ORRIN_SWAP_PAUSE_GB` (default 4)
   Defaults unchanged; bad/empty values warn and fall back. Existing tests pass values
   explicitly, so unaffected.
2. **Restarted with raised thresholds + max RAM grant**, frontend OFF:
   ```sh
   ORRIN_BODY_BUDGET_FRACTION=0.95 ORRIN_SWAP_WARN_GB=4 ORRIN_SWAP_PAUSE_GB=6 ./run_orrin.sh
   ```
   - `ORRIN_BODY_BUDGET_FRACTION=0.95` → granted body **6.0 GB** (the max possible on
     8 GB RAM; clamped by the non-overridable 2 GB host survival reserve).
   - **No Vite frontend** started (`run_orrin.sh` doesn't launch it, and none was
     running). Telemetry/UI bridge not up this session by design.

## Stop / start performed
- Graceful `SIGINT` to the old python (pid 63434) → clean shutdown in 15s, data lock
  released; old wrapper + caffeinate killed. No `.lock` files left.
- New instance: `main.py` pid 92330, wrapper 92322, caffeinate 92326. **launch #0 @ 08:32:47.**

## Verification (immediately post-restart)
- Cycles advancing (resumed at cog_cycle ~5522 from persisted state).
- Real cognitive output observed (not just heartbeat):
  `REPLY: I'm acting on my goal… Review known persons and last contact timestamps!`
- **0 host PAUSE events since launch #0.** Swap 3.7 GB sits below both new lines.
- Orrin RSS 0.83 GB at boot (will grow as models load).
- System free ~33%.

## Watch-items / caveats
- **Inherent tension on 8 GB.** A 6 GB body on an 8 GB box leaves ~2 GB for the OS +
  everything else. If other apps come back or Orrin's working set grows, the machine
  will swap again and — even at pause=6 GB — the guard will pause heavy cycles. Giving
  Orrin "as much RAM as possible" here trades idle-safety for swap risk; the durable
  fix is a bigger machine (16 GB+) or keeping other apps closed.
- **Possible RSS growth/leak.** Before the restart, Orrin's RSS had climbed 0.88 → 1.29 GB
  over ~15 min. Re-baselined to 0.83 GB now — **watch whether it climbs again**; if it
  trends up steadily that's a genuine leak worth chasing (vs. one-time model load).
- These env settings are **launch-time only** (read at import / first call). They are
  NOT persisted in `run_orrin.sh` — a plain `./run_orrin.sh` reverts to defaults
  (warn 2 / pause 4 / body fraction 0.50). Re-export them or bake into the launcher to
  keep them.
