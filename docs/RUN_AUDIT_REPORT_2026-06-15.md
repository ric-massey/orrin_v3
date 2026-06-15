# Run Audit Report — 2026-06-15

**Scope:** Analysis of all run telemetry from the 2026-06-14 20:18 → 2026-06-15 08:31 session
(the first run on the new Phase 0–5 symbolic-first code, post fourth blank-slate reset).

**Data examined:**
- `brain/logs/orrin_runtime.log` (365 lines)
- `brain/logs/crash.log`
- `brain/logs/map_territory_audit.jsonl`
- `brain/data/incidents.jsonl` (10 incidents)
- `brain/data/error_log.txt` (78 lines)
- `data/goals/wal.log` + `data/goals/state.jsonl`
- `outbox/notes.json`

---

## Summary

| # | Severity | Issue | Status |
|---|----------|-------|--------|
| 1 | **Critical** | `NameError: _goal_from_recent_research is not defined` crashed the brain thread on every boot | **Fixed in working tree** (uncommitted) |
| 2 | Medium | `detect_affect` GPT/JSON path runs even when LLM is unavailable → 62 spurious JSON salvage failures + affect silently returns `neutral` | Open |
| 3 | Low | Calibrated reward channels trip a false "not a registered cognitive function" warning | Open |
| 4 | Low | Boot schema errors: `long_memory.json` / `working_memory.json` were dicts, reinitialised | Self-healed |
| 5 | Low | `reflection_log.json` / `chat_log.json` failed list-type load | Open (latent) |
| 6 | Config | `SERPER_API_KEY` not set → web search disabled the whole run | Open (config) |
| 7 | Info | Self-audit flagged a comment/constant mismatch in `acquisition.py` | Likely false positive |

The headline: **the brain crashed on startup 15 times between 20:18 and 01:43** before the
fix in #1 was applied, after which it ran cleanly for ~6.5 hours (goals, notes, and knowledge-graph
activity continued to 08:31).

---

## 1. Critical — `NameError: _goal_from_recent_research is not defined`

**Evidence:** 5 `[CRITICAL] UNCAUGHT EXCEPTION in thread 'orrin-brain'` in `orrin_runtime.log`;
10 entries in `incidents.jsonl`; 10 in `error_log.txt`; 15 session restarts in `crash.log`
between `2026-06-14T20:18` and `2026-06-15T01:43`.

```
File "brain/cognition/intrinsic_goals.py", line 931, in _varied_symbolic_goal
    rg = _goal_from_recent_research(long_mem)
NameError: name '_goal_from_recent_research' is not defined
```

**Root cause:** In the committed (`HEAD`) version of `brain/cognition/intrinsic_goals.py`,
`_varied_symbolic_goal()` called `_goal_from_recent_research()` but that function was never
defined. Goal generation (`generate_intrinsic_goals`) is invoked early in the cognitive loop,
so the exception propagated through `_invoke_cognition` → `route_exception` and killed the
`orrin-brain` thread on every cycle. The brain could not stay alive.

**Status — FIXED in working tree (not yet committed):** `git diff` shows 51 lines added to
`intrinsic_goals.py` defining `_goal_from_recent_research()` (now at line 931, before its
caller at line 972). The module parses cleanly. The run telemetry confirms recovery — after
~01:43 there are no further `NameError` incidents and the brain produced goals/notes through 08:31.

**Action:** Commit the working-tree fix so the repo no longer ships a brain that crashes on boot.

---

## 2. Medium — `detect_affect` JSON path runs with the LLM disabled

**Evidence:** 62 × `[DEBUG] utils.json_utils: salvage failed: Expecting property name enclosed
in double quotes ... caller=affect.py:199 (detect_affect)`, spanning 23:49 → 08:10 (i.e. the
entire healthy run).

**Root cause:** `brain/affect/affect.py:detect_affect()` falls back to a GPT path when the
keyword path finds nothing (`kw.intensity == 0`). In symbolic-first mode the LLM is unavailable,
so `generate_response()` returns **symbolic narrative text** (e.g. `"Drawing from a past case
[analogy/GENERAL] [CAUSES] Similar situation (score=0.327)..."`). Line 199
(`data = extract_json(result.strip()) if result and "{" in result else {}`) then tries to
JSON-parse that prose, fails, and falls through to `{"emotion": "neutral", "intensity": 0.0}`.

**Impact:** Two problems — (a) log noise (62 DEBUG lines this run), and (b) **affect detection
silently degrades to `neutral`** for every text the keyword path can't classify, because the
fallback can never succeed without an LLM. This is a symbolic-first-conversion oversight: the
GPT branch should be gated on LLM availability the way other call sites are (cf. the
`self_model_conflicts` "LLM unavailable — skipping" guard).

**Recommendation:** Gate the GPT branch on an LLM-availability check (skip it when symbolic-first),
and/or return early after the keyword path. At minimum, suppress the `extract_json` attempt when
the result is clearly non-JSON narrative.

---

## 3. Low — Calibrated reward channels trip a false "unknown action" warning

**Evidence:** `[WARNING] affect.reward_signals.action_reward_ema: action_reward_ema: first reward
for action 'prediction_hit', which is not a registered cognitive function — possible typo'd
action name` (1×).

**Root cause:** `reward_calibrator._release()` deliberately passes the reward-channel name as
`action_type` ("so each calibrated channel learns its own expectation") for the channels
`goal_closure`, `user_validation`, `prediction_hit`, `contradiction_resolved`,
`retrieval_auxiliary`. But `action_reward_ema._flag_unknown_action()` only whitelists `"cycle"`,
so any channel name that isn't a registered cognitive function logs a "possible typo" warning on
first use. These are intended pseudo-actions, not typos.

**Recommendation:** Add the five calibrated reward-channel names to the `_flag_unknown_action`
whitelist alongside `"cycle"` (or have the calibrator submit them under a known namespace prefix).

---

## 4. Low — Boot schema errors (self-healed)

**Evidence:** `error_log.txt`, 00:18:36 (first boot):
```
[boot] SCHEMA ERROR: long_memory.json should be list, got dict. Reinitialising to safe default.
[boot] SCHEMA ERROR: working_memory.json should be list, got dict. Reinitialising to safe default.
```

**Assessment:** Likely a leftover-state artifact from the blank-slate reset (a dict-shaped seed
where a list was expected). The loader self-healed by reinitialising to `[]` — current files are
both lists. No recurrence after the first boot. **Action:** confirm the reset/seed writer emits
list-typed `long_memory.json` / `working_memory.json` so a fresh boot starts clean.

---

## 5. Low — `reflection_log.json` / `chat_log.json` list-type load failures

**Evidence:**
```
[2026-06-15T01:55:43Z] Error loading brain/data/reflection_log.json: does not contain a list.
[2026-06-15T04:15:15Z] Error loading brain/data/chat_log.json: does not contain a list.
```

**Assessment:** Same class as #4 — a loader expecting a list got another shape. These did not
crash the run (logged and skipped) but indicate either a malformed seed or a writer that can
emit a non-list shape. **Action:** verify the writers for these two files and the reset seed.

---

## 6. Config — `SERPER_API_KEY` not set, web search disabled all run

**Evidence:** 10 × `[web_search] SERPER_API_KEY not set.` in `error_log.txt` (06:49 → 09:53).
`SERPER_API_KEY` is commented out in both `.env` and `.env.example`.

**Assessment:** Not a code bug, but materially limits the run: `look_outward` / research goals
cannot actually fetch from the web. Note this directly undercuts the feature behind #1 —
`_goal_from_recent_research()` follows up on research findings that web search would have
produced. With no key, that origination source is starved. **Action:** set `SERPER_API_KEY`
if outward research is intended this run, or document that web search is intentionally off.

---

## 7. Info — Self-audit comment/constant flag (likely false positive)

**Evidence:** `map_territory_audit.jsonl` (Orrin's own self-audit, 03:50):
> `cognition/language/acquisition.py:44 — _NARRATE_MIN_INTERVAL_S=90.0 but its comment says 10 s`

**Assessment:** The comment reads `# throttle so a 10s cycle can't flood the corpus` — the "10s"
refers to the **cycle cadence**, not the narrate interval (90s). The constant and its use at
line 426 are consistent. This appears to be a false positive from the self-audit's keyword
matching rather than a real defect. Optionally reword the comment to remove the ambiguity that
tripped the audit.

---

## Recommended order of work

1. **Commit the #1 fix** — highest priority; the repo currently ships a brain that crashes on boot.
2. **Fix #2** — gate `detect_affect`'s GPT path on LLM availability (correctness + noise).
3. **Fix #3** — whitelist calibrated reward channels (cheap; removes false alarms).
4. **Investigate #4/#5** — audit reset seeds / writers for `long_memory`, `working_memory`,
   `reflection_log`, `chat_log` file shapes.
5. **Decide #6** — set `SERPER_API_KEY` or document web search as off.
6. **Optional #7** — reword the `acquisition.py:44` comment.
