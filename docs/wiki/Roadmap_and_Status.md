# Roadmap & Project Status

Orrin is an **experimental research prototype** under active single-developer development. This page
is the honest status: what works today, what's experimental, and what's out of scope. It mirrors the
README's claims-and-evidence framing; the authoritative, dated status lives in
`docs/MASTER_STATUS_*` and the run reports.

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

## Known limitations

- Internal APIs still change quickly.
- Desktop builds are unsigned (expect OS trust prompts).
- No first-class low-resource install profile yet.
- Some capabilities are evidence *targets*, not settled claims.

## Where to follow along

- [Releases](https://github.com/ric-massey/orrin_v3/releases) — tagged checkpoints
- `docs/MASTER_STATUS_*` — the current dated status
- Run reports — the behavioral evidence trail
