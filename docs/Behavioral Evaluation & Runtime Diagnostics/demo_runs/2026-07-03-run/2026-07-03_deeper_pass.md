# Deeper pass — Life of 2026-07-03 (second forensic read)

A second sweep over the same run data, looking for the connections the
first-pass docs miss. The headline: **the ignition monopoly did not die with
the rest drive — it relocated.** `social_presence` took 84% of all conscious
ignitions this life, reproduced the same consolidation-organ blackout, and
completes a three-life pattern worth naming as an architectural law. The pass
also explains the S9 murk (the EMA is structurally outvoted), traces the S8
resurrection leak to the completion bridge, and finds the make-goal that
starved while eleven research goals ate.

---

## 1. The monopoly relocated: 9,544 ignitions for a silent doorway

Ignition census across all activity logs (dedup'd for the double-rotated
14:27 file; 11,332 unique ignitions ≈ 1 per cycle):

| Source | Count | Share |
|---|---|---|
| `strong_signal(social_presence@1.00)` | **9,544** | **84.2%** |
| `strong_signal(drive_social@1.00)` | 533 | 4.7% |
| `strong_signal(emotion@…)` | 486 | 4.3% |
| `strong_signal(prediction_check@…)` | ~438 | 3.9% |
| `high_uncertainty` | 192 | 1.7% |
| `strong_signal(drive_mastery@1.00)` | 128 | 1.1% |
| `user_input` | 12 | 0.1% |

Per-window it is the exact shape of 07-02's rest scream, one organ over: the
first log window has a normal diet (social 318, emotion 417, prediction 273),
then from ~22:53 EDT onward `social_presence` holds 90–98% of every window
until death. The mechanism: the person-detector minted `anon_d29c8a` at
22:04:45 — **the UI session opening, not a word spoken** — and an open, silent
session reads as *presence + growing silence*, which saturates the signal. The
person didn't actually speak until 12:07 EDT, fourteen hours later. The fix
round's `_ever_spoke` guard capped social *pressure* while alone, but the
ignition path runs on the presence *signal*, which the minted person satisfies.

**The three-life pattern:** phantom `action_debt` (06-17) → `drive_rest@1.00`
(07-02) → `social_presence@1.00` (07-03). Each fix un-jams one horn and the
ignition floor finds the next signal that (a) can reach 1.0 and (b) has no
behavior that discharges it. This is no longer a bug in a drive; it is a
property of the ignition design: **any undischargeable signal eventually owns
the workspace.** Fixing signals one at a time will produce a fourth horn.
The general fix is at the ignition layer — habituation/novelty-gating on
*unchanged* signals (the same signal at the same value should not win ignition
7,000 times in a row), which is what the binding/GNWT work has been circling.

## 2. The organ blackout replicates under a different scream — so it's not about rest

Same census as 07-02, same result, different cause upstream:
`neutral_reflection_count` last write 21:56 EDT (pre-boot state),
`idle_consolidation_log` 22:09, `crystallized_skills` 22:10 (**1** skill this
life vs 3), `rule_firings.jsonl` 00:31 (**12** rows vs 97),
`world_model_stats` 00:35, `symbolic_concepts` 01:11 (5 concepts). Everything
that consolidates or abstracts ran only in the first ~3 hours — again.

The control case that proves the mechanism: **the dream cycle, which runs on a
3-hour timer instead of ignition, ran all life** (02:09, 05:09, 08:09, 11:10,
14:10 Z — five dreams, none missed). Timer-driven integration survived the
monopoly; ignition-gated integration starved. The conclusion writes itself:
either protect consolidation slots from ignition competition, or move the
remaining integrative organs to timers the way dreams already are. (SL1–SL5
would do this properly for sleep; the dream cadence is the existence proof.)

## 3. Why S9 is murky: the EMA is structurally outvoted

The dying cognition snapshot shows the multi-factor ranker's weights:
`emo 0.312 / goal 0.297 / band 0.25 / dir 0.22 / drive 0.15 / novel 0.124` —
and the reward EMA folded in as a fraction of one of these. The final decision
ranked `look_outward` (EMA **0.150**, the lowest of any major action) first at
1.1188, carried by exploration affect and workspace priors. Across the run,
corr(EMA, share-change) ≈ −0.15; the two most-picked actions
(`assess_goal_progress` 29%, `generate_intrinsic_goals` 25%) sit at EMA
0.35–0.37 while `research_topic` at 0.674 gets 3.6%.

This reframes Run 2's S9 "pass": part of that signal was `produce_and_check`'s
self-paying loop EMA, which fix #10 removed — and with it, most of the visible
EMA→selection coupling. **S9 as currently phrased may be untestable**: learned
value is one vote in a committee where affect has a bigger one. Before Run 4,
decide the intended authority (e.g., EMA as a multiplicative modulator rather
than an additive term, or a minimum-share guarantee for top-EMA actions) so
the signal has something falsifiable to say.

## 4. The make-goal that starved while research ate

At 08:16:31Z — seconds after *"Understand evolutionary biology more deeply"*
failed its fetch step — the system spawned *"Turn what I know about
evolutionary biology into a written synthesis"*: a genuine production goal,
born from a failure, exactly the problem-refocus behavior the roadmap wants.
It went `NEW→READY` in one second **and never ran for the remaining 8 hours**,
while eleven research-kind goals were scheduled around it. Same for *"Trace in
my own code what drives 'drive fades'"* (READY at 02:06, untouched for 14 h).
Both are `generic` kind. The daemon demonstrably schedules `research` and
`housekeeping`; whatever selects runnable v2 goals is starving `generic` — the
kind that make-work arrives as. **The flagship aspiration failed 54× on
`no_artifact_by_deadline` while a ready-to-run synthesis artifact goal sat in
the store.** One scheduling fix stands between him and his first real product.

## 5. Aspiration credit is real but borrowed

S6 passed — all four aspirations off zero — and the funnel jumped from
87→2→0 to **162 generated → 14 attempted → 14 completed**. But look at whose
work paid the making aspiration: `output_producing`'s two contributions are
*"Understand evolutionary biology and cooperation more deeply"* and *"Open
question: What would I explore if I had no consequences?"* — research goals
whose memo/tool artifacts qualified via the ledger partial-credit path (fix
#5). Meanwhile 158 of 162 generated aspiration-goal candidates targeted
*"Understand the world more deeply"* — the intake skew AR5 was meant to cap is
still overwhelming at the candidate stage (12 attempted, only 2 completed).
S6's diversity is genuine at the credit layer and thin at the generation
layer: the making credit is understanding-work wearing a making hat. Watch
whether Run 4's S6 holds once credit-quality is tightened.

## 6. The resurrection leak has a clean signature

All 12 S8 repairs are `[goal_reconcile] resurrection repaired: '<title>'
re-closed in v1 (DONE|FAILED)` — and the titles are the research/housekeeping
goals that completed in v2. Cadence matches completions almost 1:1 (02:10,
02:52, 04:07 ×2, 06:03, 06:27, 07:16, …, 16:04). Mechanism: v2 completion →
the v1 mirror re-opens (or never closes) → the 200-cycle reconciler re-closes
it. Run 2 showed 0 desyncs *because nothing completed* — the leak was always
there, unreachable. The reconciler proving itself 12× is the good news; the
§8 escalation rule (persistent repairs = real desync source →
GOAL_STORE_UNIFICATION) is now formally triggered.

## 7. Small connections the first pass would have missed

- **He was asked about the exact thing that changed.** The person's most
  substantive question — *"did you sleep at all?"* twice — targets the very
  capability this run's fix #1 gave him (5 dreams, rest discharged). His reply
  was about "Emotional keeps surfacing." The self-model has the fact
  (dream logs, rest drive state); the mouth has no path to it. When the
  speech-composition path gets state access, this is the test question.
- **A new emotion bug fired 37×** during the conversation:
  `[emotion_buffer] dropped delta for unknown emotion 'social_penalty'
  (per_cycle=-0.012)` — the social speech-block penalty is emitted but no such
  emotion is registered, so it never lands. Whatever behavior it was meant to
  suppress is running unsuppressed.
- **Two template escapes.** Among 662 expressed notes (658 the "hard to name"
  template), two read *"something I actually found out: …"* — the first
  produce-and-check content ever to reach the person-facing surface. The
  channel exists; it opened twice in fourteen hours.
- **Speech self-evaluation is still asleep**: 150 speech-log entries, 12
  evaluated, 6 retrieved — same idle organ as 07-02, now with a real
  conversation it could have learned from.
- **Calibration drifted but held**: Brier 0.0346, bias +0.0601 (n=11,333) vs
  07-02's 0.0181/+0.0095 — still excellent, worth watching the bias sign.

## Revised priority for Run 4

The first-pass list (reuse wiring, resurrection bridge, EMA authority) stands,
but this pass argues the deepest item is #1 here: **stop fixing horns and fix
the ignition layer** — an unchanged signal must habituate out of ignition
competition, or every future life will be measured through whichever signal
saturates next. Second: the one-line-ish scheduler fix for `generic` v2 goals
(§4) is the cheapest path to his first real product and directly serves the
flagship aspiration. Third: protect or timer-ize consolidation (§2's dream
existence-proof makes this concrete).

*Generated 2026-07-03, second pass over the same runtime data. Analysis only;
no code changed by this write. Companion: `DATA_FILE_AUDIT_2026-07-03.md`
(plumbing).*
