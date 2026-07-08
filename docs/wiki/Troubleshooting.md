# Troubleshooting

Symptom → likely cause → fix, for the problems people actually hit. For memory-specific issues see
[Debugging Memory Issues](Debugging_Memory_Issues); for signal pathologies see
[Control Signals: Deep Dive](Control_Signals_Deep_Dive).

## Startup

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| UI window doesn't open | pywebview unavailable | Orrin falls back to a browser tab and prints the URL; or use `ORRIN_UI_DEV=1`, or `ORRIN_UI=0` for headless |
| Heavy/slow first launch | Embedding + NLP deps (PyTorch/spaCy) loading | Expected once; steady-state is light. Consider [Docker](Running_with_Docker) |
| Restart wedges / won't come back | The Vite frontend process group holds a pipe | Kill the Vite process group as well as the loop when restarting the dev path |
| Import error mentioning `paths` before conftest | A module imported `brain.paths` before env overrides were set | Only relevant in tests — resolve state via `brain/paths.py`, never `__file__`-relative |

## LLM / tools

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| LLM calls do nothing | No provider key, or caller not allow-listed | Expected in symbolic-only mode. Set a key in Settings; only allow-listed callers may use the LLM (`ORRIN_LLM_TOOL_ONLY`) |
| LLM "stops working" mid-run | Circuit breaker opened after repeated errors | Check `llm_failure_counts.json`; fix the provider/key — it degrades to symbolic-only by design |
| Web search errors | No `SERPER_API_KEY` | Expected — "looking outward" falls back to local file search |
| Fabricated-looking output on error | — | Shouldn't happen: the gate fails closed. File a bug with the trace |

## Behavior

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Same function picked over and over | A rut / reward collapse | The rut-breaker and Reward Auditor peer should intervene; check the Cognition room's per-function EMAs |
| "Makes nothing" for a long time | Reward was churning on intake | Grounded by the [effect ledger](Production_and_Effect_Ledger); confirm artifacts are being recorded under `brain/data/effect_artifacts/` |
| Thought stream flickers randomly | Hysteresis/binding not engaging | Check `ORRIN_IGNITION_GATE`/`ORRIN_WORKSPACE_PRIOR` aren't disabled |
| Control signals thrash | Velocity budget too loose, or two writers | See [Tuning Control Signals](Tuning_Control_Signals); ensure writes go through the arbiter |

## State & disk

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Data files growing unbounded | — | Shouldn't happen: logs are capped, history windowed, memory decays. If not, check `docs/CONFIGURATION.md` "How state stays bounded" |
| Want a clean slate | — | `python reset_orrin.py` (snapshots first; `--dry-run` to preview). See [Existence and Lifecycle](Existence_and_Lifecycle) |
| Corrupted / weird state after a crash | Interrupted write | Daemons recover from WAL + snapshot; a reset restores from the pre-reset snapshot |

## Remote / UI access

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Can't reach UI from another device | Backend bound to loopback | Set `ORRIN_BACKEND_HOST=0.0.0.0`, pin the port, or use `expose_orrin.command`. See [Remote Access & Tunneling](Remote_Access_Tunneling) |
| Anyone with the URL can control it | No control token set | Set `ORRIN_CONTROL_TOKEN` before exposing. See [Security Model](Security_Model) |

## Still stuck?

Grab evidence — relevant lines from `brain/logs/`, a run report, or a life capsule — and open an
issue (no secrets/tokens, please). See [Contributing](Contributing).
