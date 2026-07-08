# Getting Started

Your first hour with Orrin: install it, run it, and understand what you're looking at. No API key is
required — Orrin runs fully in symbolic-only mode out of the box.

## Install

```bash
git clone https://github.com/ric-massey/orrin_v3.git
cd orrin_v3

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # optional — an empty .env is fine
./run_orrin.sh
```

Requirements: Python 3.10+. The full install is heavy (it pulls PyTorch and spaCy-related packages
for embeddings/NLP), but steady-state runtime is light. Prefer not to install all that? See
[Running with Docker](Running_with_Docker).

## Run

```bash
python main.py                 # native desktop window (pywebview), no browser, no port
ORRIN_UI_DEV=1 python main.py  # developer: Vite dev server :5173 + backend :8800, hot reload
ORRIN_UI=0 python main.py      # headless, no UI
```

By default Orrin opens the **Face & Brain UI** itself. It boots, rolls a lifetime budget on first
run, and starts its cognitive loop immediately — you don't prompt it.

## What you're looking at

The UI is organized as **rooms**, not a chat window ([Face & Brain UI](Face_and_Brain_UI)):

| Room | Watch this to see… |
|------|--------------------|
| **Brain** | The live thought stream, control-signal rings, demands, attention, goals |
| **Cognition** | Which functions are being selected and what "thinking" is costing |
| **Memory** | Working memory and what's being retrieved/consolidated |
| **Learning** | Behavior changes as before→after→because diffs |
| **Life** | Lifetime phase and run history |
| **Face** | Person-facing conversation |

Start in the **Brain** room and just watch the thought line for a minute — that line is the winner
of the global-workspace competition each cycle ([Workspace and Ignition](Workspace_and_Ignition)),
not a log.

## What "working" looks like

- The thought stream updates continuously and stays on a coherent topic for a while (hysteresis),
  rather than flickering randomly.
- Control-signal rings drift and respond to events rather than sitting flat.
- Goals appear, advance through steps, and occasionally close or fail.
- Over a longer run, the **Learning** room shows belief/behavior changes and the **effect ledger**
  accrues produced artifacts ([Production and the Effect Ledger](Production_and_Effect_Ledger)).

## Add capabilities (optional)

Edit `.env` to unlock tools — each is optional and each degrades gracefully:

```bash
# OPENAI_API_KEY=sk-...   # enables the LLM tool (symbolic-only without it)
# SERPER_API_KEY=...      # enables live web search (local-file fallback without it)
```

You can also pick a provider (OpenAI / Anthropic / Gemini / local) in the UI **Settings** room; keys
are stored in your OS keychain, not on disk. See [LLM Integration](LLM_Integration).

## Next steps

- Understand the mechanism → [The Cognitive Loop](The_Cognitive_Loop)
- Something looks wrong → [Troubleshooting](Troubleshooting)
- Configure or deploy it → [Configuration Reference](Configuration_Reference)
- Reset and start fresh → [Existence and Lifecycle](Existence_and_Lifecycle)
