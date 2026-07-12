# Run 6 (2026-07-10 → 2026-07-11) — reading order

Sixth acceptance life. **13,341 cycles, ~15.5 h, zero crashes, clean death.**
Staging run for the Run 6 fix build (`RUN6_FIX_PLAN_2026-07-08.md`, commit `584b76a`)
and the Companion & Presence build (commit `e4abfe7`).

**Verdict: gate NOT passed — S10/avoidance/convergence 🔴, S7 regressed, S9 🟡 —
but the failure changed species: the monopoly now lives in the learned value signal
itself (poisoned by the QuadRF fetch loop), not in any static sort.**

| Order | File | What it answers |
|---|---|---|
| 1 | `DEMO_RUN_2026-07-11.md` | Did the gate pass? (No.) What worked, what broke, item by item |
| 2 | `RUN_CAPTURE_2026-07-11.md` | Run boundaries, preconditions, snapshot manifest |
| 3 | `2026-07-11_run_analysis.md` | Timeline, the eleven §6 read-side checks, root causes R1–R6, reproduction commands |
| 4 | `2026-07-11_goals_system_audit.md` | The commitment machinery post-Fix-2: rotation vs the value pump, avoidance orbit, credit mis-keying |
| 5 | `2026-07-11_deeper_pass.md` | QuadRF-loop anatomy, `write_exemplar` autopsy, Companion/Presence staged verification, memory + failure taxonomy |
| 6 | `2026-07-11_who_is_he.md` | The person-shaped read (note: the death-note advice line is a hardcoded template, `terminal.py:61`) |
| 7 | `2026-07-11_self_awareness_audit.md` | Second pass: every self-monitoring organ, store-cited — well-instrumented, narratively blind; 9 false recoveries, the "being stuck fades" mantra edge (92 % of reflections), stuck-monitor honored 17 %, QuadRF blindness quantified, wiring list C1–C11 |

Data: `data/` (brain/data snapshot), `goals_daemon/` (root data/), `artifacts_readable/`
(this run's memos), `logs/` (runtime + goal-progress + map-territory audit).

Headline numbers: committed-goal monopoly **92 %** (`self_understanding`);
`look_outward` 4,899 → **88 picks** (first visible learned-value kill);
production 443 attempts / 384 successes — **~93 % of it one memo rewritten 403×**;
reuse **2** (Run 5: 8); syntheses **0**; desyncs **0** (2nd clean run);
satiety meter fixed (**17**); `write_exemplar` dead all life (12× EACCES);
speech intents typed; presence notifications **3**/15.5 h.

Related fixes pending Run 7: `FETCH_REREAD_LOOP_FIX_2026-07-11.md` (built,
uncommitted, did not run in this life) + the credit-side items in the goals audit §8.
