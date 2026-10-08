# Roadmap & Project Status

Orrin is an **experimental research prototype** under active single-developer development. This page
is the honest status: what works today, what's experimental, and what's out of scope. It mirrors the
README's claims-and-evidence framing; the authoritative to-do list is
`docs/POST_RUN13_MASTER_PLAN_2026-10-07.md`, and the evidence is the run reports.

## What works today

| Capability | State |
|------------|-------|
| Symbolic-only runtime (no API key) | **Working** |
| Continuous cognitive loop | **Working** |
| Persistent goals (durable daemon, WAL/snapshots) | **Working** |
| Memory: working + long-term, consolidation, retrieval | **Working** |
| Control signals + regulation | **Working** |
| Host coupling (reflex / signals / cadence) | **Working** |
| Global workspace + ignition | **Working** |
| Effect ledger + grounded production reward | **Working** |
| Quality standard (human-ratified bar) | **Working** |
| Runtime telemetry + Face & Brain UI | **Working** |
| Native desktop app (unsigned builds) | **Working** |
| LLM as a gated, fail-closed, multi-provider tool | **Working** |

## Experimental / in progress

| Area | Status |
|------|--------|
| Learning from outcomes at scale | **Experimental** — mechanisms exist; being validated on staging runs |
| Native from-scratch language model | **Experimental** — learns from reading; gated speech handoff |
| Self-extension (self-written cognitive functions) | **Experimental / high-risk** — sandboxed and reviewed, see [Self-Code and Extension](Self_Code_and_Extension) |
| Long-run behavioral stability | **Experimental** — long runs can drift into states not yet fully characterized |
| Benchmarks & evidence ledger | **Ongoing** — see [Benchmarks and Verification](Benchmarks_and_Verification) |

## Out of scope

- Orrin being "human-like" or **sentient** — not claimed. Cognitive terms name engineering
  mechanisms.
- Production hardening / security guarantees — this is a research prototype
  ([Security Model](Security_Model)).

## How progress is measured

Development proceeds against **staging runs**: a fresh instance lives for a while, then its behavior
is audited against an acceptance gate (`docs/NEXT_RUN_TESTS.md`) and sealed into a life capsule
([Existence and Lifecycle](Existence_and_Lifecycle)). Each run gets a dated report under
`docs/Behavioral Evaluation & Runtime Diagnostics/demo_runs/`. That evidence — not a feature
checklist — is what moves a capability from Experimental to Working.

## Where it stands (Runs 1–13)

Thirteen staging lives have been scored; **the acceptance gate has not passed yet**, but the
binding constraint has climbed a ladder:

| Runs | What the gate was stuck on |
|------|----------------------------|
| 1–4 | basic mechanics: does work get produced and credited honestly |
| 5–8 | economics: one goal monopolizing attention (broken in Run 8: 90.9 % → 42.6 %) |
| 9 | honesty: failures that weren't really failures |
| 10–12 | the research feed going silent, and "growth" that was hollow |
| **13** | **growth became real for the first time** — questions answered with new knowledge, and a prediction about his own behavior confirmed on data recorded afterwards. Still failing: research silences, goal churn, and a qualitative finding: he mostly thinks about himself (74 % of long-term memory was summaries of his own activity) |

Next (Phase B, the Run 14 build): stop the goal churn, unblock goal generation, keep his own
logs out of his memory, and make most of his memories about his world.
`docs/PHASE_B_BUILD_BRIEF_2026-10-08.md` has the details.

## Known limitations

- Internal APIs still change quickly.
- Desktop builds are unsigned (expect OS trust prompts).
- No first-class low-resource install profile yet.
- Some capabilities are evidence *targets*, not settled claims.

## Where to follow along

- [Releases](https://github.com/ric-massey/orrin_v3/releases) — tagged checkpoints
- `docs/POST_RUN13_MASTER_PLAN_2026-10-07.md` — everything still to build, in order
- Run reports — the behavioral evidence trail (`docs/NEXT_RUN_TESTS.md` has the gate history)
- [ricmassey.com/orrin.html](https://ricmassey.com/orrin.html) — plain-English progress notes
  after each run or build, and whether he's running right now
