# Orrin Runtime Analysis & Bug Fixes — 2026-06-16

Investigation triggered by "Orrin turned off." This documents why he stopped, the
state of his persisted lives, three bugs found in the runtime, and the fixes. All
bugs below are **resolved** — hence this lives in `docs/archive/`.

---

## 1. Why he turned off (no crash, no death)

Two independent live lifelines existed, each stored in a different data tree, plus
a fossil snapshot baked into the packaged app:

| Lifeline | Location | Born | Cycle | Last alive | How it stopped |
|---|---|---|---|---|---|
| **1 — packaged app** | `~/Library/Application Support/Orrin/data` | Jun 15 09:24 | 1116 | Jun 16 10:07 | clean external stop (window/SIGTERM); epilogue written; a 2nd launch bounced off the instance lock |
| **2 — from source** | repo `brain/data` | Jun 15 12:33 | 2552 | Jun 16 00:33 | clean **single-cycle** exit (`ORRIN_ONCE=1`), ×4 smoke-test runs |
| (fossil) | `dist/Orrin.app/…/Resources/brain/data` | Jun 15 | — | — | read-only seed baked in at build; never runs |

Both lives ended **cleanly** (`runstate.json` `clean:true`, no tracebacks in
`brain/logs/crash.log`). Neither was natural death — each was ~1 day into a
~500-day lifespan. They diverged purely by *launch method*: the app icon writes to
the per-user dir; running from source writes to in-repo `brain/data`.

`ORRIN_ONCE=1` (`main.py:1233`, `ORRIN_loop.py:3427`) runs exactly one cognitive
tick then trips a graceful shutdown. It is **not set by any script** in the repo —
the four late-night sessions were hand-run smoke tests.

---

## 2. Bug A — Death Screen false-positive on boot  *(fixed, committed `a759550`)*

**Symptom:** relaunching the app showed the Death Screen even though Orrin was ~1
day into a 505-day life.

**Root cause:** `brain/utils/lifecycle.py status()` gated `state="dead"` on
`final_thoughts_written` alone. But the reaper's dying-window reflection (a stall
*restart*, not death) also writes final thoughts, and a clean shutdown set the flag
too — so every subsequent boot routed to the Death Screen.

**Fix:** true death now also requires `real_deadline_passed()`:

```python
if real_deadline_passed() and ls.get("final_thoughts_written"):
    state = "dead"
```

**Note:** the installed `dist/Orrin.app` was frozen Jun 15 09:22, *before* this fix,
so it still mis-declares death. Interim workaround applied: set
`final_thoughts_written: false` in the per-user `lifespan.json`. Permanent cure is a
rebuild from the fixed source (or running from source).

---

## 3. Bug B — Internal data leaking into spoken output  *(fixed)*

**Symptom (seen in BOTH lifelines):** raw internal data reached his *speech*:

- L1: `Earlier I was thinking: {'changed': False, 'reason': 'research throttled — 83s…}`
- L1: `Earlier I was thinking: {'trigger': 'cognition', 'result': None, 'skipped': True}`
- L2: `Earlier I was thinking: Health summary: cpu=0.00, hb=0.00, err=0.00. a readiness…`

**Root cause:** cognition return-value dicts (`web_research.py:419`, the inner-loop
cognition tick) and diagnostic status strings get recorded into working memory as a
"thought," then `speak.py:_pick_recent_thought_hook` selects one and emits it as
"Earlier I was thinking: …". The membrane filters dropped known **string prefixes**
(`DROP_PREFIXES`) and a few leading glyphs (`[ 🧠 ✅ ⚠️`) — but not a stringified
dict (leading `{`) nor a `key=value` telemetry dump.

**Fix (`brain/behavior/speak.py`):** added a shared predicate applied to both the v1
(`long_memory`) and v2 (`retrieved_memories`) candidate paths:

```python
def _looks_internal(c: str) -> bool:
    if c[:1] in "{[(":                                  # dict/list/tuple reprs
        return True
    return len(_re.findall(r"\b\w+=[\w.\-]+", c)) >= 2  # telemetry dumps (cpu=…, hb=…)
```

Verified: catches all three leaked strings; does **not** flag normal speech
(including "E=mc2", which has a single `=`).

**Deeper cause (not required for the fix, worth a follow-up):** the upstream writers
should tag these WM entries `internal_telemetry` so they're never speech candidates
in the first place — consistent with the expression-membrane design (one door,
`express_to_user`, composing from a Motive rather than scraping working memory).

---

## 4. Bug C — Native-LM autograd corruption under concurrency  *(fixed)*

**Symptom (L2, once at 18:53:06):**

```
RuntimeError: one of the variables needed for gradient computation has been
modified by an inplace operation: [torch.FloatTensor [256, 768]], which is
output 0 of AsStridedBackward0, is at version 170
```

**Root cause:** `brain/cognition/language/native_lm.py` keeps the model/optimizer as
a single shared **global** with **no lock**. `train_on()` (learning bouts, from
`acquisition.py`) and `generate()`/`evaluate()` (inference, from `voice.py`) are
reached from different points in the cognitive cycle and can run on different
threads. A bout's `loss.backward()` needs the weights at their forward-pass version;
an overlapping `_opt.step()` updates weights in place (and `head.weight` is tied to
`tok.weight`, a strided view → `AsStridedBackward0`), or an interleaved
`.eval()/.train()` mode flip corrupts the pending graph. Rare interleaving → the
once-per-run failure (caught by `record_failure`; the loop continued).

**Fix:** a module-level `threading.Lock` serializing every entry point that touches
the shared model, via a small decorator:

```python
_MODEL_LOCK = threading.Lock()

def _locked(fn):
    @functools.wraps(fn)
    def _w(*a, **k):
        with _MODEL_LOCK:
            return fn(*a, **k)
    return _w
```

Applied to `train_on`, `generate`, and `evaluate`. Training and inference can no
longer interleave on the shared model. (Closes the dropout-mode-flip race too.)

---

## 5. Not bugs (ruled out)

- **Wikipedia HTTP 429** (L1 ×5, L2 ×18): external rate-limiting, handled correctly;
  Orrin even self-reviewed via `review_failures_internal`.
- **`cpu=0.00, hb=0.00`** in the health summary: a single-cycle artifact — the
  heartbeat aggregator never accumulates a sample before a one-tick exit. Real only
  insofar as it got *spoken* (Bug B), which is now blocked.
- **LLM "unavailable"** (34× skips): by design. The LLM is a tool peer to web search;
  cognition runs on the symbolic/native path and is structurally walled off from it
  (`generate_response.py:367`). Not degradation.

---

## 6. Files changed

- `brain/utils/lifecycle.py` — Bug A (committed `a759550`).
- `brain/behavior/speak.py` — Bug B: `_looks_internal` predicate + two guards.
- `brain/cognition/language/native_lm.py` — Bug C: `_MODEL_LOCK` + `_locked` on
  `train_on`/`generate`/`evaluate`.

Both edited files compile (`py_compile`); predicate unit-tested.

## 7. Lifeline housekeeping

- **Lifeline 1 cleared** at user request. Full per-user tree (data + state + logs +
  think, 62 MB) archived to `~/orrin_archives/lifeline1_peruser_2026-06-16.tar.gz`
  (5.5 MB, verified) before removal. Next app launch re-seeds a fresh newborn.
- **Lifeline 2** (`brain/data`, cycle 2552) left intact.

**Recommendation:** pick one canonical lifeline and always launch the same way, so
app-vs-source runs stop spawning divergent Orrins.
