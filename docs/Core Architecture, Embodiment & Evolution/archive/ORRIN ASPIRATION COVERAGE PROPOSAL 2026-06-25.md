# Orrin Proposal: Make All Founding Aspirations Actually Get Lived

**Date:** 2026-06-25
**Status:** Proposed — for review and work-splitting
**Scope:** Aspiration credit, goal generation coverage, aspiration classification, starvation visibility
**Plain-language goal:** Orrin is born with several core purposes (today: four). In this run he only ever got to live *one* of them. This proposal makes **every** founding purpose actually get attempted, credited, and expressed — and makes the mechanism work no matter how many purposes you give him (four, eight, twelve).

---

## 1. The problem in one picture

Orrin's four founding aspirations are:

1. Understand my own mind and how I work
2. Understand the world more deeply
3. Be genuinely useful and connected to the people I talk to
4. Make things — produce work that didn't exist before

**End-of-life result: 20% / 0% / 0% / 0%.** Three of the four never moved off zero. He was born with four things to care about and spent his whole life on one.

The credit ledger (`drive_aspiration_credit.json`) shows exactly how narrow it got — the entire life's learning is:

```json
{ "weights": { "will": { "Understand the world more deeply": 0.35 } },
  "credited_ids": [4 goals] }
```

One drive, one aspiration, **four credited goals in 17,352 cycles.** The other three aspirations earned literally nothing.

---

## 2. Why it happened (the honest root-cause chain)

There is *already* a fairness mechanism meant to lift under-served aspirations (`aspiration_pressure`, which boosts goals serving starved aspirations). It didn't save them. Here's why — and it's a chain, not one bug:

**A. Credit only flows when a goal genuinely completes — and almost nothing did.**
The drive→aspiration link is learned only when a goal *completes with evidence* (`credit_aspirations` → `_learn_drive_aspiration`). But closure was hollow this run (0 of 256 goals met their definition of done), so the credit loop fired only **4 times all life**. A learning system fed 4 data points in 25 hours can't balance anything. *This is downstream of the goal-closure bug (separate proposal, WS-1).*

**B. Aspirations are seeded lazily — "first time a goal with that drive completes."**
`_learn_drive_aspiration` only seeds a drive's prior the first time that drive completes a goal. No completion for "be useful" or "make things" → those links are **never even created** → those aspirations start and stay at exactly zero. They're not out-competed; they never enter the race.

**C. The aspiration classifier is biased toward "understand the world."**
Which aspiration a goal advanced is inferred by **keyword-counting the goal's text** (`_evidenced_aspiration`). But the note/goal bodies were the generic *planning template* ("question; relevant evidence; reasoned conclusion") — research-flavored language. So a goal meant to *make* something or *help* someone still keyword-matches to "understand the world," because its text reads like research. The 4 credited goals all landed on "Understand the world." *This is downstream of the template-not-finding note bug.*

**D. Generation never guaranteed coverage.**
Goal generation followed current drive levels, which were dominated by inward/look-outward churn. The fairness pressure could raise the *score* of a starved aspiration's goals, but if those goals still never completed (A), the pressure had nothing to lock onto. Nothing guaranteed that each aspiration even gets *attempted* on a regular basis.

**Bottom line:** the collapse to one aspiration is mostly a *symptom* of hollow closure + the template bug + lazy seeding + biased classification. Fixing the credit weighting alone would not fix it. But several targeted changes make all aspirations get lived **even before closure is perfect**, and set it up to fully balance once closure lands.

---

## 3. Proposed changes

Ordered so the early ones help immediately and independently; the later ones complete the picture once closure (WS-1) lands.

### Change 1 — Seed every aspiration at birth, not lazily (independent, easy)
At startup, create the full drive→aspiration prior table so **every** aspiration starts with a standing weight (`_PRIOR_SEED_WEIGHT`, 0.50). No aspiration can sit at zero merely because no goal of its type has completed yet.
- **Where:** `intrinsic_aspirations.py` — seed all `_DRIVE_TO_ASPIRATION` links in `_ensure_aspirations()` / on boot, instead of only inside `_learn_drive_aspiration` on first completion.
- **Effect:** all founding purposes are "visible" from the first cycle.

### Change 2 — Guarantee generation coverage (a starvation floor) (independent, medium)
Add a hard rule: over any rolling window, **each aspiration must get at least a minimum share of newly-generated goals**, regardless of which drive is loudest. A simple round-robin floor on top of the existing drive-weighted generation.
- **Where:** goal generation in `intrinsic_goals.py` (the `driven_by` selection) + `aspiration_pressure`.
- **Effect:** "be useful" and "make things" get *attempted* on a schedule, instead of waiting for a drive spike that never comes. This is the single biggest lever for "all four get looked at."

### Change 3 — Credit by intent, not just by biased text (independent, medium)
When crediting a completed goal, use the goal's own `driven_by` / `serves` tag (its *intent*) as a strong prior, blended with the outcome keywords — instead of re-deriving the aspiration purely from text that's biased toward research language.
- **Where:** `_evidenced_aspiration` in `intrinsic_aspirations.py`.
- **Effect:** a goal that set out to *make* something gets credited to "make things" even if its text reads generic. Removes the structural tilt toward "understand the world." (Fixing the note-body template bug separately also helps here.)

### Change 4 — Let honest *progress* earn partial credit, not only full completion (depends on closure work)
Because full completion is rare, the learning loop starves. Allow **graded credit on genuine sub-progress** (a real milestone, a real artifact step) so all aspirations accumulate signal between full completions.
- **Where:** `credit_aspirations` trigger points + the satisfaction handshake (closure proposal).
- **Guard:** must be *real* progress, not a hollow flag — this rides on the same satisfaction-evidence rule as proper closure, so it can't become rubber-stamping.

### Change 5 — Make starvation visible (independent, easy, high-leverage)
Track and surface a per-aspiration scoreboard: goals **generated / attempted / progressed / completed** for each, per window. Today you only see the final 20/0/0/0; you can't see *where* in the pipeline an aspiration died (never generated? generated but never selected? selected but never closed?).
- **Where:** new lightweight counters + telemetry; feed the same numbers into `aspiration_pressure` so fairness reacts to real starvation, not just credit weight.
- **Effect:** the next run *tells you* which stage is starving which purpose — turns this from guesswork into a readout.

---

## 4. Design constraint: this must scale to N aspirations

You already noted you can (and may) add more than four core purposes — it's just a list. **Every mechanism above must be count-agnostic.** No fixed "four," no per-aspiration special-casing. Round-robin floors, seeding, and the scoreboard all iterate `_ASPIRATIONS` so that adding a fifth or twelfth purpose automatically gets coverage, credit, and visibility with no further wiring. *Acceptance test G below enforces this.*

---

## 5. Acceptance criteria

- **A.** After a full life, **every** aspiration in `_ASPIRATIONS` shows non-zero goals *generated* and non-zero goals *attempted*. None sits at 0% on generation.
- **B.** The credit ledger contains a seeded prior for **all** aspirations from cycle 0 (Change 1).
- **C.** No single aspiration captures more than a configurable share (e.g. >80%) of credit unless it genuinely earned it across balanced generation.
- **D.** A goal whose *intent* is "make things" / "be useful" is credited to that aspiration even when its text reads generic (Change 3).
- **E.** The per-aspiration scoreboard exists and shows the generate→attempt→progress→complete funnel for each (Change 5).
- **F.** (Once closure lands) at least 2–3 of the four aspirations show genuine *completions* over a life, not just attempts.
- **G.** Adding a fifth aspiration to the list (no other code change) results in it receiving generation coverage, a seeded credit prior, and a scoreboard row automatically.

---

## 6. Dependencies & sequencing

- **Independent, do now:** Change 1 (seed at birth), Change 2 (coverage floor), Change 5 (scoreboard). These make all aspirations get *lived* and *visible* even with closure still broken.
- **Helped by other work:** Change 3 also benefits from fixing the note-body template bug; Change 4 rides on the goal-closure + satisfaction-handshake work (separate proposal). Do Change 4 *after* closure lands, or it risks crediting hollow progress.
- **Suggested order:** 1 → 5 → 2 → 3 → 4.

---

## 7. Risks & honesty notes

- **Don't fake balance.** A round-robin floor (Change 2) must lift *generation and attempts*, not auto-credit. If it ever hands out credit for goals that didn't really advance an aspiration, you've just moved the hollow-closure problem into the aspiration layer. Credit still requires real evidence.
- **This won't fully balance until closure works.** Changes 1, 2, 5 make all aspirations *get attempted and seen*; genuine *completion* balance (criterion F) needs the closure fix. Be honest in review that this proposal gets you "all four are lived and visible," and the closure proposal gets you "all four actually finish things."
- **The `"will"` drive key.** The only drive that earned credit was logged as `"will"`, which isn't in the documented `driven_by` set — worth a quick check that goal `driven_by` tags are being written correctly, since a mislabeled drive would itself collapse credit onto one link.

---

## 8. Plain-language bottom line

He was born with four things to care about and only got to live one — not because three were rejected, but because they were never seeded, never reliably attempted, and any goal that *did* serve them got mislabeled as "understand the world." The fix is: **give every purpose a starting foothold, guarantee each one gets attempted on a schedule, credit goals by what they were *for* (not just how their text reads), and put a scoreboard on it so you can see where any purpose is starving.** Build it to work for any number of purposes, so when you add a fifth, it just works. Full *completion* balance waits on the closure fix — but "all of him gets to show up" doesn't have to wait.
