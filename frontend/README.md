# Orrin UI — frontend

Vite + React + TypeScript + Tailwind. Two views sharing one telemetry stream: the
**Public Face** (calm chat) and the **Core Brain** (dark research dashboard). See
the top-level [`UI_README.md`](../UI_README.md) for the full system overview.

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
├── App.tsx                  # shared layout, theme switch, telemetry provider
├── index.css                # Tailwind layers + design tokens (Face light / Brain dark)
├── lib/
│   ├── types.ts             # telemetry data contracts (mirror of server/schema.py)
│   ├── telemetry.ts         # useTelemetry() WebSocket hook (reconnect + demo fallback)
│   └── utils.ts             # cn(), small helpers
├── components/
│   ├── ui/                  # shadcn-style primitives (button, card, input, badge, …)
│   ├── Header.tsx           # persistent Public Face ⇋ Core Brain toggle
│   ├── face/                # NarrativeStatusCard
│   └── brain/               # CognitiveGraph, AffectRings, MemoryInspector, LiveConsole, MetricsStrip
└── pages/
    ├── Face.tsx
    └── Brain.tsx
```

Config via `.env.local` — see [`.env.example`](.env.example).
