# Why Orrin Isn't Learning Well — Diagnosis (2026-06-16)

**Question:** the activity report shows his most-used cognitive functions are also his
lowest-reward ones (`look_outward` 1043× @ 0.11, `look_around` 1002× @ 0.14,
`generate_intrinsic_goals` 1050× @ 0.29), while higher-reward functions
(`attempt_regulation` 0.40, `dream_cycle` 0.37, `seek_novelty` 0.35) are used far less.
Why isn't learning correcting this?

**Answer in one line:** He *is* learning correctly — the value estimates are right — but
the learned value barely influences what he actually *picks*. Selection is dominated by
hardcoded emotion priors that point at the worst functions, so the learning gets
overruled every cycle.

---

## 1. The learning works. The ranking it produces is correct.

The contextual bandit (`brain/think/bandit/contextual_bandit.py`) buckets context into four
affect states and keeps UCB1 sample-mean value estimates (`q`) per action. In the
`exploration_drive` bucket — where he spends most of his time — here is what he *learned*
versus how often he *chose* each arm (`brain/data/bandit_state.json`):

| function | learned value `q` | times picked (this bucket) |
|---|---|---|
| `look_outward` | **0.109** (worst) | **819** (most) |
| `look_around` | 0.141 | 801 |
| `generate_intrinsic_goals` | 0.285 | 805 |
| `seek_novelty` | **0.338** | 149 |
| `grep_files` | 0.308 | 90 |
| `research_topic` (in `stable`) | **0.593** | ~0 here |
| `dream_cycle` (in `stable`) | **0.673** | — |

The ranking is **inverted**: he has correctly learned that `look_outward` is worth ~0.11
and that `seek_novelty`/`research_topic` are worth 3–5× more, and then picks `look_outward`
5× as often. This is not a broken learner. It is a broken *selector*.

**Confirmation that he can learn:** in the `stable` bucket — where the priors below don't
fire — behavior is healthy: `dream_cycle` (q=0.67), `learn_from_reading` (0.66),
`research_topic` (0.59) dominate. So the breakage is specific to the prior-driven
`exploration_drive` state, not the learning machinery.

---

## 2. Why the learned value gets overruled

The actual pick is **not** the bandit's choice. In `select_function.py` the chosen function
is `chosen = scored[0][0]` (line ~1820): the argmax of a **weighted sum of ~16 components**.
The learned reward is only one term:

- **Bandit hint** (learned value via `get_scores()`): weight `SELECTOR_W_BAND = 0.25`,
  clamped to [0,1] — a "hint," not the decider.
- **Emotion prior** (hardcoded `_SEMANTIC_PRIORS` table): weight `SELECTOR_W_EMO = 0.26`.

The hardcoded `exploration_drive` prior assigns:

```
search_own_files 0.88, look_outward 0.85, look_around 0.75, generate_intrinsic_goals 0.72
```

Those are **exactly the four low-reward functions.** Meanwhile `seek_novelty` and
`research_topic` — the genuinely higher-reward explorers — are **absent** from that prior,
so they get zero lift.

### Decisive comparison (recomputed from live state)

`look_outward` vs `seek_novelty`, emotion + bandit terms only:

| component | `look_outward` | `seek_novelty` |
|---|---|---|
| emotion prior `0.26 × (0.85·0.85)` | **+0.188** | +0.000 (not in prior) |
| bandit hint `0.25 × UCB` | +0.040 | +0.113 |
| **net** | **+0.227** | +0.113 |

The static prior's +0.188 advantage *is the entire margin*. The bandit's learned correction
(+0.07 toward `seek_novelty`) is real but too small to overcome it — every cycle. And
`look_outward` is *additionally* in `_USER_HELPFUL`, `_OUTWARD_MED`, `_BLIND_EXPLORE`, and
the `wonder`/`stagnation`/`positive_valence` priors. It is structurally over-privileged by
~5 separate static tables firing at once. No amount of low reward can dig out from under
that.

---

## 3. Three compounding factors

1. **His own anti-rut safety valve is dead code.** `contextual_bandit.choose()` has a
   stagnation-epsilon boost that *did* detect this rut (top-3 arms = **81.6%** of picks in
   the bucket, over the 80% trip threshold). But the wrapper that calls it
   (`_bandit_pick_with_info`) has **zero call sites** — selection uses only `get_scores()`
   as a hint and runs its own argmax. The breaker designed for exactly this situation never
   fires.

2. **Reward scale is compressed and flat.** Everything in exploration mode scores 0.1–0.35.
   With a UCB sample-mean frozen over 800+ pulls, `look_outward`'s `q` is pinned at 0.11 and
   *cannot drop further* to signal "stop." Habituation can't push it negative.

3. **Context is coarse (4 buckets).** The one bucket without a miscalibrated prior
   (`stable`) behaves well. The damage is concentrated in the `exploration_drive` state.

---

## 4. Relation to human cognition

This failure mode has clean analogues in human decision neuroscience, and they sharpen the
diagnosis rather than just decorate it.

- **Habitual (model-free) control overriding goal-directed (model-based) control.** The
  bandit is Orrin's model-free, dopaminergic value learner (basal-ganglia analogue): it
  tracks reward-prediction error and gets the values right. The hardcoded emotion priors act
  like **Pavlovian/instinctive drives** — innate appetitive pulls toward a salient cue
  ("when curious, look outward"). When a Pavlovian cue overrides instrumental value, you get
  exactly this signature: *a known-low-value action chosen because a state-cue makes it
  salient.* In humans this is **Pavlovian-instrumental transfer** and sign-tracking. Orrin's
  "look_outward reflex under curiosity" is a sign-tracker.

- **Insensitivity to outcome devaluation** — the hallmark of a habit. A behavior is
  *habitual* (not goal-directed) precisely when it persists after its outcome stops being
  valuable. `look_outward`'s frozen q=0.11 and continued dominance is the computational
  picture of a devalued action that the system keeps emitting. The reward signal *says*
  "this is no longer paying off"; the controller isn't reading it.

- **Diversive vs. epistemic curiosity (Berlyne).** `look_outward`/`look_around` are
  **diversive** curiosity — cheap, low-yield, restless scanning for any stimulation.
  `research_topic`/`seek_novelty` are **epistemic/specific** curiosity — effortful,
  directed, high-yield knowledge-seeking. Orrin is trapped in diversive curiosity: the drive
  fires, but it's wired to the cheap satisfier, so it never matures into the effortful kind
  that actually closes knowledge gaps. Healthy curiosity should *transfer* from diversive
  arousal to epistemic pursuit; his prior table blocks that transfer.

- **State-dependent arbitration; stress/arousal shifts control toward habit.** Humans under
  acute arousal shift from model-based to model-free control (Otto et al., 2013). Orrin
  mirrors this *structurally*: in the calm `stable` bucket he is "model-based" and picks
  high-value functions; in the aroused `exploration_drive` bucket the prior dominates and he
  goes "habitual." The arbitration weight is mis-set so the aroused state never hands control
  back to the value learner.

- **Missing metacognitive override (ACC/cognitive-control analogue).** The dead stagnation
  breaker is the absent piece: in humans, anterior-cingulate conflict/rut monitoring detects
  "I keep doing the same unrewarding thing" and recruits prefrontal control to switch. Orrin
  *computes* that signal (81.6% concentration, threshold crossed) but it is disconnected from
  the actuator — he notices the rut and does nothing about it.

The through-line: a correct reward learner sitting underneath an over-strong set of innate
drives, with the metacognitive "break the habit" override unplugged. That is a recognizable,
specific dysfunction — not vague "he doesn't learn."

---

## 5. Fixes, in order of impact

1. **Realign the `exploration_drive` prior** to the functions he is actually rewarded for
   (`seek_novelty`, `research_topic`, `wikipedia_search`) and shrink/drop
   `look_outward`/`look_around`. *(Lowest risk — a data/table edit. Note:
   `exploration_value.py` was meant to retire the `look_outward` clock; this prior table is
   the piece still feeding it.)* — **turns diversive curiosity into epistemic.**
2. **Let learned value gate the priors**, not just add to them: multiply each prior by a
   factor that decays as a function's avg_reward falls below its peers, so a prior cannot
   keep boosting an arm the agent has proven is bad. — **restores outcome-devaluation
   sensitivity / model-based override of habit.**
3. **Wire the real pick through the stagnation-epsilon breaker** (call it, or replicate the
   concentration check in `select_function`). — **reconnects the metacognitive rut monitor
   to the actuator.**

---

### Verification notes

- Numbers above pulled live from `brain/data/bandit_state.json`,
  `brain/data/action_reward_ema.json`, and weights in `brain/config/tuning.py`.
- Real pick path confirmed: `chosen = scored[0][0]` (weighted-sum argmax);
  `_bandit_pick_with_info` (holding the breaker) has **0 call sites** in `think/`.
- Decisive `look_outward` vs `seek_novelty` margin (+0.227 vs +0.113) and the 81.6%
  concentration recomputed directly from state.
