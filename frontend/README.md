# Orrin UI - frontend

Vite + React + TypeScript + Tailwind. Nine named rooms share one telemetry
connection and a common bio/engineering dialect toggle:

- **Watch** - compact live thought and affect view
- **Face** - conversation
- **Cognition** - active function, drives, symbolic state, and people
- **Life** - machine embodiment and resource state
- **Memory** - searchable memory stores
- **Timeline** - activity since the viewer last visited
- **Learning** - behavior changes, belief revisions, goal progress, and rut pressure
- **Brain** - draggable research dashboard
- **Settings** - providers, privacy, lifecycle, updates, and mind transfer

See the top-level [README](../README.md#the-ui) and the
[UI/security/desktop master plan](../docs/UI%2C%20Security%20%26%20Desktop%20Packaging/archive/UI_SECURITY_DESKTOP_MASTER_PLAN_2026-06-16.md)
for the full system overview and current status.

Requires Node.js 20.19+ or 22.12+.

## Scripts

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # type-check (tsc) + production build
npm run preview    # serve the production build
npm run typecheck  # tsc --noEmit
```

## Structure

```
src/
├── main.tsx                 # router + entry
├── App.tsx                  # shared layout, room theme, telemetry provider
├── index.css                # Tailwind layers + design tokens
├── lib/
│   ├── types.ts             # telemetry data contracts (mirror of server/schema.py)
│   ├── telemetry.ts         # useTelemetry() WebSocket hook (reconnect + demo fallback)
│   └── utils.ts             # cn(), small helpers
├── components/
│   ├── ui/                  # shadcn-style primitives (button, card, input, badge, …)
│   ├── Header.tsx           # room navigation + bio/engineering toggle
│   ├── face/                # NarrativeStatusCard
│   └── brain/               # CognitiveGraph, AffectRings, MemoryInspector, LiveConsole, MetricsStrip
└── pages/
    ├── Watch.tsx
    ├── Face.tsx
    ├── Cognition.tsx
    ├── Life.tsx
    ├── Memory.tsx
    ├── Timeline.tsx
    ├── Learning.tsx
    ├── Brain.tsx
    └── Settings.tsx
```

Config via `.env.local` — see [`.env.example`](.env.example).
