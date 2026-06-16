# README Critique — 2026-06-13

A critical review of the top-level `README.md` against the actual codebase. The README is
unusually well-written and **most of its concrete claims check out** (ports, arbiter paths,
LLM-as-tool gating, the two state trees, the `~7s` Executive interval, `reset_orrin.py`
flags, Apache 2.0). The issues below are the gaps, inaccuracies, and important things the
code does that the README never mentions. Findings are ordered by impact.

---

## High impact — things that will actually trip a user up

### 1. `SERPER_API_KEY` is undocumented but required for web search
The README lists "web search" as a flat capability (§"What Orrin actually does") and tells
the reader that the **only** key is `OPENAI_API_KEY` (which is "optional"). In reality:

- `brain/behavior/tools/toolkit.py:204` — web search uses Serper.dev and **requires
  `SERPER_API_KEY`**; without it, it logs `"[web_search] SERPER_API_KEY not set."` and returns
  an error.
- `brain/cognition/perception/look_outward.py:31` — with no `SERPER_API_KEY`, "looking
  outward" silently **redirects to `search_own_files`** instead of the web.

So a user following the README gets a degraded agent (no real web reach) with no explanation.
The README should document `SERPER_API_KEY` as an optional-but-needed-for-web key, and the
"web search / scrape / RSS" bullet should note the fallback behavior.

### 2. Only 4 of ~68 `ORRIN_*` environment variables are documented
The "Useful environment switches" table lists `ORRIN_UI`, `ORRIN_EXECUTIVE_DAEMON`,
`ORRIN_CYCLE_SLEEP`, `OPENAI_API_KEY`. The codebase reads **68 distinct `ORRIN_*` variables**.
Several are operationally important and undocumented, including:

- `ORRIN_LLM_TOOL_ONLY` — gates the LLM to tool-only use (it's set in the project's own `.env`).
- `ORRIN_STRICT` — strict fail-closed mode.
- `ORRIN_LLM_DAILY_TOKEN_BUDGET` — daily spend cap (cost control — users will want this).
- `ORRIN_DATA_DIR`, `ORRIN_GOALS_DIR`, `ORRIN_LOGS_DIR`, `ORRIN_REPO_ROOT`, `ORRIN_WORLD_ROOT`
  — relocate state (relevant to the Docker volume advice the README itself gives).
- `ORRIN_ONCE` / `ORRIN_BENCHMARK` — single-cycle / benchmark run modes (useful for testing).
- `ORRIN_FORGET_ON_START`, `ORRIN_BACKEND_HOST`, `ORRIN_BACKEND_PORT`, `ORRIN_UI_OPEN`,
  `ORRIN_EXECUTIVE_DAEMON_INTERVAL`, and a large `ORRIN_MEM_*` family for the memory daemon.

Documenting all 68 is overkill, but the table is currently misleading by omission — it reads
as if these four are the switches, when cost-control, strict-mode, path-relocation, and
run-mode switches all exist.

### 3. The Setup snippet never actually clones the repo
Step 1 is commented "Clone and enter the repo" but the command is just `cd orrin_v3` — there
is no `git clone <url>`. A new user copy-pasting the block lands in a non-existent directory.

---

## Medium impact — architectural ambiguity / drift

### 4. Two different goal daemons are conflated as one "Executive daemon"
The README presents a single goal-advancing daemon, but there are **two distinct subsystems**:

- **Executive daemon** — `brain/cognition/planning/executive.py`, in-process, advances goal
  steps every ~7s, toggled by `ORRIN_EXECUTIVE_DAEMON`. This is what the "At a glance" diagram
  box ("Executive daemon — goal steps") and §"What it is" ("a separate Executive daemon that
  advances goal steps") describe.
- **Goals daemon** — `goals/goals_daemon.py` (`GoalsDaemon`), a separate durable subsystem
  with its own WAL + snapshots, launched from `main.py:408`. The repo-layout table calls
  `goals/` the "Goals daemon — goal lifecycle, planning, and **step execution**."

So "step execution" is attributed to both, and the diagram shows only one box. A reader can't
tell there are two goal-related daemons or how they divide responsibility. This should be
disambiguated — e.g. Executive (in-loop scheduler) vs. Goals daemon (durable lifecycle store).

### 5. Version string is stale / inconsistent
The header says **"Version 3.0"**, but the repo's own artifacts are at **3.30**
(`orrin_v3.30.zip`, dated 2026-06-12). Either the README is behind or the versioning is
informal — worth reconciling so the badge isn't misleading.

### 6. The Architecture "Convergence layer" note describes branch-only work as settled
The "Convergence layer" bullet (single affect writer, lock-guarded proposal inbox) describes
the `convergence-layer` feature branch this README currently lives on — it is **not yet on
`main`**. Presenting it in the steady-state architecture section is fine *if* the README ships
with the merge, but as written on a feature branch it documents behavior `main` doesn't have
yet. Confirm the README and the merge land together.

---

## Lower impact — omissions & small inaccuracies

### 7. spaCy is described as "optional" in two different senses
§Requirements says "...and optionally spaCy," but `requirements.txt` lists `spacy>=3.7`
**unconditionally** — it is always installed. What's actually optional is the *language model*
(`en_core_web_sm`), which has a regex fallback. The wording conflates the package with the
model and undersells the install footprint (spaCy is always pulled in).

### 8. Runtime communication dirs `inbox/` and `outbox/` are missing from the repo layout
`outbox/notes.json` is where Orrin's outward notes / desktop communication are written (the
README's own "leave notes on your desktop" claim), and `inbox/` is a sibling input dir. Both
are top-level directories absent from the "Repository layout" table.

### 9. `watchdogs.py` (the actual reaper wiring) isn't in the layout table
The README describes the reaper conceptually and lists the `reaper/` package, but the
top-level `watchdogs.py` — which assembles the `HealthBus`/`NervousSystem` and all the guards
(heartbeat, lifespan, no-goals, memory health, repeat-loop) — is undocumented. It's the file
that actually composes the liveness subsystem the README praises.

### 10. Remote-access path is entirely undocumented
`expose_orrin.command` + `tunnel_url.txt` implement single-tunnel remote access (the Vite dev
server proxies both `/ws` and `/api` to the backend on 8800, frontend derives URLs from page
origin). This is a real, shipped capability with no mention in the README — notable given the
README spends a full section on the UI.

### 11. `reset_orrin.py --no-snapshot` flag is undocumented
The README shows `--dry-run` and `--hard`, but `reset_orrin.py:155` also defines
`--no-snapshot` (skip the automatic pre-reset snapshot). Minor, but it's the one flag that
changes the "a reset is recoverable" guarantee the README leans on.

### 12. The screenshot placeholder is still empty
The HTML comment block reserving space for the Face & Brain UI screenshot
(`docs/images/face_and_brain.png`) is unfilled. For a project whose pitch is "watch a digital
mind," shipping without the hero image leaves the strongest selling point invisible.

---

## Structural / polish notes (no factual error)

- **No table of contents** for a ~315-line README — navigation is purely scroll-based.
- **No Troubleshooting section** — the most likely first-run failures (npm not on PATH, ports
  8800/9100/5173 already bound, what "symbolic-only mode" actually looks like, missing
  `SERPER_API_KEY`) are exactly the things a Troubleshooting block should pre-empt.
- **No CONTRIBUTING / contribution guidance**, despite an Apache-2.0 open-source framing.
- The `docs/` pointer is good but doesn't surface the most useful current doc,
  `docs/BENCHMARKS.md`, by name where benchmarks are mentioned.

---

## What the README gets right (verified)
For balance — these claims were checked and hold:
- Ports: backend `:8800` (`backend/server/config.py:47`), Prometheus `:9100` (`main.py:148`),
  frontend `:5173` (`config.py:51`). ✔
- Arbiter files exist: `brain/affect/arbiter.py`, `brain/think/action_arbiter.py`. ✔
- `brain/cognition/tools/ask_llm.py` exists; LLM is gated/fail-closed
  (`brain/utils/llm_gate.py`, `generate_response.py:120`). ✔
- LLM provider is OpenAI (`gpt-4.1` / `gpt-4o-mini`, `brain/core/config/settings.py`);
  `OPENAI_API_KEY` truly is optional (symbolic-only fallback via `llm_stub.py`). ✔
- Two state trees (`brain/data/` vs root `data/`) match the description. ✔
- Executive advances every ~7s (`executive.py:389`, default `"7"`). ✔
- `reset_orrin.py --hard` clears `bandit_state.json` / `decision_stats.json` as claimed. ✔
- Python ≥3.10 consistent with `pyproject.toml` (`requires-python = ">=3.10"`). ✔
- Apache 2.0 license header confirmed. ✔
