# Face & Brain UI

`frontend/` is a Vite + React + TypeScript app that exposes the runtime as named **rooms** instead
of hiding behavior in a chat transcript. It reads the telemetry stream from `backend/` (see
[Backend & Telemetry](Backend_Telemetry.md)); in the packaged desktop app it runs in a native
pywebview window over an in-process bridge with no open port.

![The Learning room, showing belief and behavior changes as before→after→because diffs](images/orrin_learning_ui.png)

## The rooms (`frontend/src/pages/`)

| Room | What it shows |
|------|---------------|
| **Face** | The person-facing surface: conversation and expressions composed through the [expression membrane](Expression_Membrane.md) |
| **Brain** | The live internals: workspace/thought stream, control-signal rings, demands, attention, goals, internal state |
| **Cognition** | Function-selection stats, per-function EMAs, thinking cost (tokens/cache), deliberation activity |
| **Memory** | The memory inspector: working memory, long-term retrievals, consolidation activity |
| **Learning** | Behavior changes and belief revisions as before→after→because diffs |
| **Life** | The existence view: runtime-lifetime phase, restoration, and run history |
| **Timeline** | The event timeline across the run |
| **Watch** | A passive observation screen built around the live thought line |
| **Settings** | Provider/API-key management (keys go to the OS keychain), RAM budget, runtime options |

## The thought line is the workspace, not a log

The live "what it's thinking" line is the output of the global-workspace bottleneck — the winning
content each cycle — not a printout of internal logs (see
[Workspace and Ignition](Workspace_and_Ignition.md)). Hysteresis keeps it continuous rather than
flickering.

It is also **bilingual**: `frontend/src/lib/thoughts.ts` (sibling to `lexicon.ts`) renders the
status line in either Orrin's own developing vocabulary or plain English, toggleable in the UI.

## Panels

`frontend/src/components/brain/` holds the panel library: control-signal rings, demands, attention,
goals + goal health, internal state, memory inspector, learning, language, predictions,
relationships, self-model, symbolic-model, tensions, resource signs, live console, and the
cognitive-sphere visualization.

## Type safety across the wire

The telemetry schema is defined once in `backend/server/schema.py`; `generate_telemetry_ts.py`
generates the frontend's TypeScript types from it (`make telemetry-types`), so the two sides cannot
silently drift.

## Modes

- **Native window** (default): pywebview over the built `frontend/dist`, no browser, no port.
- **Developer** (`ORRIN_UI_DEV=1`): Vite dev server on `:5173` with hot reload, backend on `:8800`.
- **Headless** (`ORRIN_UI=0`): no UI at all.
