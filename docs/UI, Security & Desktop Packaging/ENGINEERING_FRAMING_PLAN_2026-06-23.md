# Engineering Framing Plan

Date: 2026-06-23

## Purpose

Orrin already has a biological/engineering terminology toggle, but the engineering framing is only partial. This plan finishes the translation layer so a company, reviewer, or infrastructure-minded engineer can understand Orrin first as a stateful agent runtime instead of as a speculative "mind" project.

The goal is not to remove Orrin's deeper research ontology. The goal is to make the product boundary bilingual:

- Biological mode: the Orrin-native research/personhood vocabulary.
- Engineering mode: infrastructure vocabulary for agent runtime, state, governance, observability, and resource scheduling.

## Current State

What already works:

- `frontend/src/lib/lexicon.ts` defines `bio` and `eng` labels.
- `frontend/src/components/Header.tsx` exposes the Biological / Engineering toggle.
- `frontend/src/pages/settings/LanguageSection.tsx` lets the user choose a dialect.
- `frontend/src/components/FirstWake.tsx` asks whether Orrin should describe himself "As a mind" or "As a machine".
- Many panel titles and subtitles already translate through `LexText`, `PanelSubtitle`, or `useLexicon()`.

What does not fully work:

- Engineering mode does not cover all authored UI copy.
- Some high-visibility pages still hardcode "mind", "felt", "consciousness", "he", "him", "brain", and "keepsake" language.
- Panel info popovers use fixed biological copy in many places.
- Backup/import/export flows still use "Export Mind" and "Restore Mind" even in engineering mode.
- The default fallback in `getLexMode()` is currently biological mode, so a first-time reviewer may see the poetic framing before the infrastructure framing.

## Core Decision

Do not rename the whole codebase.

Internal names such as `mind_archive`, `selfhood`, `metabolism`, `nervous_system`, and `consciousness` can remain where they are accurate to the architecture. Renaming them would create churn without improving the external perception problem.

Instead, finish the presentation boundary:

- User-facing UI copy should be dialect-aware.
- Company-facing docs should lead with engineering terms.
- Code comments may keep research vocabulary unless they are surfaced in the UI.
- API paths can stay stable unless a new public API is being designed.

## Target External Positioning

Use this as the company-facing baseline:

> Orrin is an experimental stateful agent runtime with durable memory, goal persistence, policy gates, observability, restart continuity, resource-aware scheduling, and controlled self-extension.

Avoid leading company-facing pages with:

> Orrin is a mind / organism / selfhood system.

The second framing can remain available as the research explanation after the engineering framing has established credibility.

## Translation Rules

Use consistent vocabulary in engineering mode:

| Biological phrase | Engineering phrase |
| --- | --- |
| Mind | Runtime state |
| Brain | Runtime dashboard |
| Consciousness | Attention arbitration |
| Stream of consciousness | Workspace broadcast log |
| Affect | Control signals |
| Felt state | Internal state estimate |
| Felt time | Internal clock estimate |
| Metabolism | Resource cadence policy |
| Nervous system | Health telemetry sampler |
| Body | Host/process resource budget |
| Life support | Resource manager |
| Selfhood | Identity and policy state |
| Moral override | Policy gate |
| Wants / drives | Priority weights |
| Dreams | Idle consolidation |
| Export Mind | Export State Archive |
| Restore Mind | Restore State Archive |
| Keepsake | Backup |

## Engineering Audience Rules

For company-facing and reviewer-facing surfaces, the first sentence should answer:

- What subsystem is this?
- What state does it read or write?
- What decision does it make?
- What evidence proves it is working?
- What remains experimental?

Avoid leading with inner-life interpretation when the reader is still trying to establish whether the mechanism is real. In Engineering mode, "why this matters" should be framed as risk reduction, reliability, auditability, or runtime control.

Examples:

- Weak for engineers: "Orrin remembers because his mind persists."
- Stronger: "Orrin persists runtime state through WAL-backed memory stores, goal snapshots, and full state archives."
- Weak for engineers: "Orrin feels strain when thinking costs too much."
- Stronger: "Orrin tracks predicted vs actual function cost and uses the gap as a control signal for resource-aware scheduling."
- Weak for engineers: "Orrin has private thoughts."
- Stronger: "The UI does not expose protected internal records; generated speech/logs and stored memories are separate data channels."

## Authored Copy Boundary

Engineers implementing this plan need a clear line between text that should be translated and text that must remain verbatim.

Translate these:

- Page headings, subheadings, descriptions, empty states, cards, modals, toasts, tooltips, button labels, confirmation dialogs, and onboarding copy.
- Panel-info `title`, `what`, and `good` text.
- UI-authored status summaries such as the live thought/status line in `frontend/src/lib/thoughts.ts`.
- Documentation intended for reviewers or companies.

Do not translate these:

- Orrin-generated speech.
- Goal titles, memory summaries, log lines, thought records, conscious-stream records, and event payloads generated by the runtime.
- API route names, JSON field names, file paths, function names, and source-code references.
- Internal module names unless they are being surfaced as product copy.

When in doubt, ask whether the text was authored by the UI or produced by the running system. UI-authored text should be dialect-aware. Runtime-produced text should be shown as evidence and should remain exact.

## Phase 1 - Complete The Lexicon Boundary

### Tasks

- Expand `frontend/src/lib/lexicon.ts` beyond panel titles/subtitles into high-visibility page copy.
- Add keys for page headings, hero copy, button labels, confirmations, empty states, and panel-info text.
- Keep Orrin-generated data verbatim. Only translate UI-authored copy.
- Add a small helper for translated paragraphs so components do not manually branch on `mode`.

### Candidate helper APIs

- `LexText` for short inline labels.
- `LexBlock` for paragraphs or descriptions.
- `lexCopy(id)` for non-React confirm strings and imperative messages.
- `PanelInfoLex` or `PanelInfo` props that accept `{ bio, eng }` copy objects.

### Recommended Type Contract

Prefer one shared text shape instead of one-off `mode === "eng"` branches scattered through components:

```ts
export type DialectText = string | { bio: string; eng: string };

export function resolveDialectText(text: DialectText, mode: LexMode): string {
  return typeof text === "string" ? text : text[mode];
}
```

Recommended component changes:

- `PanelInfo` should accept `DialectText` for `title`, `what`, and `good`.
- `LexBlock` should render `DialectText` paragraphs and subscribe to `useLexicon()`.
- `lexCopy(id)` should return the current dialect for imperative browser APIs such as `window.confirm()`.
- Any helper used outside React must read the same mode source as `getLexMode()` so dialogs and buttons cannot disagree.

Avoid duplicating local dialect types. `frontend/src/lib/thoughts.ts` currently defines its own `Dialect` shape; future work should reuse the shared type once it exists.

### Acceptance Criteria

- Switching to Engineering changes all chrome and authored explanatory copy on the main surfaces.
- Orrin's generated speech, logs, goal titles, memory summaries, and thoughts remain unchanged.
- No page should require a reader to understand "mind/personhood" framing when Engineering mode is active.

## Phase 2 - Fix High-Visibility Pages

### Files To Prioritize

- `frontend/src/pages/Face.tsx`
- `frontend/src/pages/Brain.tsx`
- `frontend/src/pages/Cognition.tsx`
- `frontend/src/pages/Life.tsx`
- `frontend/src/pages/Memory.tsx`
- `frontend/src/pages/Learning.tsx`
- `frontend/src/pages/Watch.tsx`
- `frontend/src/components/DeathScreen.tsx`
- `frontend/src/components/FirstWake.tsx`

### Known Hardcoded Leaks

- `Face.tsx`: "a mind that perceives, reflects, plans, and acts"
- `Brain.tsx`: "This is Orrin's brain, live", "show me the mind", and orientation bullets using consciousness/feels/private thoughts language
- `Life.tsx`: "his mind is...", "he feels..."
- `Learning.tsx`: "How his behaviour is changing"
- `Memory.tsx`: "Watching him forget keeps his mind finite and real"
- `DeathScreen.tsx`: "his mind is intact", "export him"
- `Watch.tsx`: ambient "mind thinking" framing

### Acceptance Criteria

- In Engineering mode, these pages describe modules, state, runtime behavior, logs, and resource budgets.
- Biological mode still keeps the current tone where it is useful.
- FirstWake explains the choice as a terminology preference, not a change in behavior.

### Example Rewrites

Use examples like these when converting hardcoded copy:

| Current biological copy | Engineering-mode copy |
| --- | --- |
| "You're speaking with Orrin - a mind that perceives, reflects, plans, and acts in a continuous loop." | "You're connected to Orrin - a stateful agent runtime with perception, reflection, planning, and action stages running in a continuous loop." |
| "This is Orrin's brain, live." | "This is Orrin's runtime dashboard, live." |
| "Got it - show me the mind" | "Got it - show me the runtime" |
| "Watching him forget keeps his mind finite and real." | "The forgetting ledger shows bounded memory behavior instead of unbounded store growth." |
| "How his behaviour is changing" | "Behavior-change log" |
| "Nothing actively pulling at him right now." | "No active priority signal right now." |

## Phase 3 - Translate Panel Info Popovers

Many `PanelInfo` calls currently pass biological wording directly. These popovers are important because they are where technical reviewers learn what each subsystem does.

### Files To Prioritize

- `frontend/src/components/brain/ConsciousnessPanel.tsx`
- `frontend/src/components/brain/CognitiveSphere.tsx`
- `frontend/src/components/brain/AffectRings.tsx`
- `frontend/src/components/brain/DrivesPanel.tsx`
- `frontend/src/components/brain/SymbolicMindPanel.tsx`
- `frontend/src/components/brain/SelfModelPanel.tsx`
- `frontend/src/components/brain/InnerWeatherPanel.tsx`
- `frontend/src/components/brain/MemoryInspector.tsx`
- `frontend/src/components/brain/GoalsPanel.tsx`
- `frontend/src/components/brain/LearningPanel.tsx`
- `frontend/src/components/brain/HealthPanel.tsx`
- `frontend/src/components/brain/BenchmarkPanel.tsx`

### Implementation Option

Update `PanelInfo` to accept either strings or dialect objects:

```ts
type DialectText = string | { bio: string; eng: string };
```

Then translate `title`, `what`, `good`, and potentially `source` where useful. Source paths usually do not need translation.

### Acceptance Criteria

- In Engineering mode, every info popover explains the subsystem using infrastructure language.
- Code references remain visible and honest.
- The popover copy does not overclaim production readiness.

## Phase 4 - Fix Settings, Backup, And Control Copy

These flows are sensitive because they describe destructive actions, persistence, and trust.

### Files To Prioritize

- `frontend/src/pages/settings/BackupSection.tsx`
- `frontend/src/pages/settings/UpdatesSection.tsx`
- `frontend/src/pages/settings/ResetSection.tsx`
- `frontend/src/pages/settings/ExistenceSection.tsx`
- `frontend/src/pages/settings/TrustSection.tsx`
- `frontend/src/pages/settings/LanguageModelSection.tsx`
- `frontend/src/components/Header.tsx`

### Required Engineering Labels

- "Export Mind" -> "Export State Archive"
- "Restore Mind" -> "Restore State Archive"
- "Preparing his mind" -> "Preparing state archive"
- "Restore replaces Orrin's current mind" -> "Restore replaces Orrin's current runtime state"
- "Erase this mind" -> "Erase runtime state"
- "his body asks your OS" -> "the runtime requests OS permissions"

### Acceptance Criteria

- Engineering mode uses precise persistence/security language.
- Confirmation dialogs are clear about risk and reversibility.
- Biological mode can preserve current tone if desired.

## Phase 5 - Make Reviewer Mode Easy To Reach

Engineering mode should be the easiest mode for external evaluation.

### Options

- Add `VITE_DEFAULT_LEX_MODE=eng` for reviewer/company builds.
- Support a URL param such as `?lex=eng` or `?mode=eng`.
- Add a "Reviewer mode" button or command that sets Engineering mode and opens the Brain/Runtime dashboard.
- Consider changing `getLexMode()` fallback from `"bio"` to `"eng"` only if this is intended for all fresh installs.

### Recommended Path

Use an environment-controlled default first:

- Local/personal build can default to biological.
- Demo/reviewer/company build can default to engineering.
- The user's saved choice still wins once set.

### Default Mode Precedence

Use a deterministic precedence order so reviewers can reproduce what they saw:

1. Explicit URL parameter, for example `?lex=eng`.
2. Saved user preference in local storage.
3. Build-time default, for example `VITE_DEFAULT_LEX_MODE`.
4. Hardcoded fallback.

Recommended implementation:

- Keep local/personal installs free to default to biological if that is the intended experience.
- Set reviewer/demo builds to engineering with `VITE_DEFAULT_LEX_MODE=eng`.
- If `?lex=eng` or `?lex=bio` is present, store that choice immediately so refreshes stay consistent.
- Add a visible "Engineering" state in the header so screenshots make the active framing obvious.

### Acceptance Criteria

- A reviewer can open Orrin directly in Engineering mode without hunting through Settings.
- The toggle remains visible so the deeper biological vocabulary is discoverable.

## Phase 6 - Add Company-Facing Documentation

Create or update docs that describe Orrin as infrastructure first.

### Recommended Files

- Add `docs/Capability, Benchmarks & Evidence/ORRIN_RUNTIME_CAPABILITIES.md`
- Add a README section: "Engineering Translation"
- Link this plan from `docs/README.md`

### Suggested Structure

- What Orrin is in engineering terms
- Current implemented mechanisms
- What is prototype vs production-ready
- Known gaps
- How Orrin compares to agent runtimes/frameworks without overclaiming
- Evidence from code and benchmarks

### Claims-To-Code Table

The company-facing capability doc should use a claims table so engineers can verify the architecture quickly:

| Claim | Engineering wording | Evidence to cite |
| --- | --- | --- |
| LLM is optional/tool-like | Gated LLM tool, symbolic route first | `brain/utils/generate_response.py`, `brain/utils/llm_gate.py`, `brain/cognition/tools/ask_llm.py` |
| Restart continuity | Runtime state survives restarts unless explicitly reset | `main.py`, `brain/utils/mind_archive.py`, `memory/wal.py`, `goals/store.py` |
| Goal persistence | Durable goal and step state with replay/snapshots | `goals/model.py`, `goals/store.py`, `goals/wal.py`, `goals/goals_daemon.py` |
| Host-resource awareness | Process and host vitals feed runtime pacing/control | `observability/nervous_system.py`, `reaper/host_resources.py`, `brain/cognition/body_sense.py`, `brain/cognition/host_interoception.py` |
| Observable adaptation | Behavior changes are logged as before/after/reason records | `brain/cognition/behavioral_adaptation.py`, `backend/server/routers/cognition.py` |
| Policy/governance | Policy gates and capability routing constrain actions | `brain/cognition/selfhood/ethics.py`, `brain/cognition/selfhood/values_check.py`, `brain/think/think_utils/selection/text.py` |
| Controlled extension | Generated helpers/tools are sandboxed and loaded from a controlled self-code area | `brain/agency/self_code.py`, `brain/agency/code_writer.py`, `tests/brain/test_self_code_location.py` |

Each row should include a status: `Implemented`, `Partial`, `Experimental`, or `Roadmap`. Do not describe a mechanism as solved unless there is a test, benchmark, or run report behind it.

### Acceptance Criteria

- A company reader can understand what is valuable without buying the "mind" framing first.
- Claims are explicitly separated into Implemented, Partially Implemented, and Roadmap.
- The document names the exact code modules behind each claim.

## Phase 7 - QA And Regression Checks

### Static Checks

Run searches for remaining UI-authored biological language:

```sh
rg -n "his mind|a mind|felt|consciousness|personhood|Export Mind|Restore Mind|keepsake|he feels|his body|him" frontend/src -S
```

Expected result:

- Remaining matches should either be in biological lexicon entries, comments, Orrin-generated data paths, or intentionally untranslated research-mode copy.

### Manual Checks

- Open the UI in Engineering mode.
- Visit Watch, Face, Cognition, Life, Memory, Timeline, Learning, Brain, Settings.
- Open every major panel info popover.
- Trigger Backup, Restore, Reset, Stop, and Update confirmation copy.
- Confirm no engineering-mode copy makes consciousness/personhood claims.

### Build Checks

Run the frontend checks available in the repo:

```sh
cd frontend
npm run typecheck
npm run lint
npm run build
```

These scripts currently map to:

- `npm run typecheck`: `tsc --noEmit`
- `npm run lint`: `eslint .`
- `npm run build`: `tsc --noEmit && vite build`

Run `npm run build` even if `typecheck` passes, because it verifies the Vite production bundle and catches import/path issues that static typechecking alone can miss.

### Screenshot Checks

For a reviewer-facing UI change, verify both modes visually:

- Engineering mode, desktop width.
- Engineering mode, narrow/mobile width.
- Biological mode, desktop width.

For each screenshot pass, check Face, Brain, Life, Learning, Memory, and Settings. The main goal is not pixel perfection; it is confirming that the visible copy matches the selected dialect and does not mix framings in the same panel.

## Implementation Risks

- Inconsistent mode sources: React labels, browser confirmations, and transport callbacks can drift if they read different mode sources.
- Over-translation: runtime data should remain exact, even if it contains biological phrasing generated earlier.
- Type churn: adding too many separate copy helper shapes will make the lexicon harder to maintain.
- Hidden copy: `title` attributes, `aria-label`s, confirmation dialogs, and empty states are easy to miss.
- Claim inflation: engineering copy should sound concrete, not more grandiose. "State archive" is better than "production-grade continuity" unless production evidence exists.

## Suggested PR Sequence

1. Add shared `DialectText` helpers and default-mode precedence.
2. Convert high-visibility pages and settings/control dialogs.
3. Convert `PanelInfo` popovers.
4. Add reviewer/company documentation.
5. Run static searches, frontend checks, and screenshot review.

Keeping this in separate commits or PRs makes regressions easier to isolate.

## Non-Goals

- Do not rename internal Python modules just for optics.
- Do not remove biological mode.
- Do not rewrite Orrin's generated memories, thoughts, logs, or speech.
- Do not hide experimental status.
- Do not claim production-grade reliability unless benchmarks and deployment evidence support it.

## Definition Of Done

This work is done when:

- Engineering mode is complete enough that a company reviewer sees Orrin as infrastructure first.
- Biological mode still exists as the deeper Orrin-native interpretation.
- All high-visibility UI copy is dialect-aware.
- Backup/reset/security flows use precise engineering language in Engineering mode.
- Company-facing docs describe implemented mechanisms without hype.
- Static searches show no unintended biological framing leaks in Engineering mode.

## Recommended First Implementation Slice

Start with a narrow, high-impact slice:

1. Add lexicon keys for Face, Brain orientation, Backup, Life, Learning, and DeathScreen copy.
2. Convert those files to use the lexicon.
3. Add an environment-controlled default mode.
4. Build the frontend.
5. Re-run the framing search.

This will make the biggest visible difference without touching core architecture.
