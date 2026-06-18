# UI Ideas — Making Learning Visible (and Three Perspectives)

**Date:** 2026-06-16
**Status:** Historical idea capture. Priority items A, B+C, E, H, I, J, and the
three-perspective labeling were built on 2026-06-17. Current status lives in
`UI_SECURITY_DESKTOP_MASTER_PLAN_2026-06-16.md`; the remaining K-N ideas require
new causal/provenance tracking and are not implied by the current UI.

---

## The through-line

Almost every idea below is the same complaint stated many ways:

> The dashboard is good at **stocks** (how many beliefs, goals, facts, rewards exist
> *right now*) and weak at **flows** (what *changed*, and *because of what*).

A learning system has to occasionally say: *"I used to do X. Now I do Y. Because
experience showed Y works better."* The current panels can almost never say that
sentence out loud. They show the present state of the machinery; they rarely show a
**before → after + reason** triple. That triple is the thing worth building toward.

So the test for every idea here is not "is this data interesting?" but **"does it
show a change and its cause?"**

---

## What already exists (so we don't rebuild it)

The Brain dashboard already has a lot. Relevant to these ideas:

| Existing panel / source | What it already covers |
|---|---|
| **LearningPanel** (`/learning` ← `decision_stats`, `bandit_state`, `reward_trace`) | Per-function pick count, avg reward, current suppressions, raw reward trace. The bandit's view of "which cognition is paying off." |
| **PredictionsPanel** (`/predictions` ← `predictions`, `prediction_domain_stats`, `calibration_state`, `introspection_trust`) | Recent hit/miss strip, per-domain accuracy, a single current **Brier score**, and a felt-vs-behaved "introspection trust" per domain. |
| **SelfModelPanel** (`/self` ← `self_model`, `self_belief_revisions`, `opinions`) | A **revisions** tab: dated belief-confidence changes (old → new, with the triggering goal). An **opinions** tab: view + confidence + `evidence_count` + `updated_at`. Knowledge-domain confidence. |
| **SymbolicMindPanel** (`/symbolic` ← `symbolic_progress`, `symbolic_rules`, `causal_graph`, `world_model_stats`) | `rules_total`, `rules_added_today`, `crystallized_today`, symbolic-answer ratio, causal graph, per-domain rule coverage. Rules are added *and* forgotten. |
| **GoalsPanel** (`/goals`) | Full goal tree: status, tier, milestones (with `met` / `met_at`), plan steps, history events, created/updated timestamps. |
| **GoalHealthPanel** (`/outcomes` ← `outcome_metrics`) | Daily: active-goal count, average goal age, completion vs abandonment rate, and which **closure path** ended each goal (completed / retired / satiety / abandoned). |
| **ConsciousnessPanel** (`/consciousness`) | The Global-Workspace winner this cycle, the ranked runners-up that lost, the conscious stream, monitor breakthroughs, executive lane. |
| **Watch page** + `lexicon.ts` / `thoughts.ts` | The agent-experience view: a plain-language "what he's thinking" line and mood orb, with a live bio↔eng toggle that turns raw numbers into felt language. |
| **Backend engines (no panel yet)** | `behavioral_adaptation.py` (turns metacog insight into drive/bias/suppression changes), `exploration_value.py` + `habituation.py` (explore/exploit + outcome-novelty satiety). The *machinery* for several ideas below already runs — it's just not surfaced. |

---

## The ideas, audited

Grouped, deduped, and judged. Verdict legend:
**BUILD** = genuinely missing and worth it ·
**PARTIAL** = data or a weaker version exists, needs a real view ·
**HAVE** = already covered, don't rebuild.

### A. Behavior change caused by learning — *"the one number"*  → **BUILD**
> Before: `stagnation → reflect_on_self`. After: `stagnation → wikipedia_search`.
> Reason: prediction success +22%. … Last 7 days: 37 behavior changes.

This is the headline ask and the single most valuable missing piece. The **engine
exists** (`behavioral_adaptation.py` already suppresses overused functions and shifts
action-vs-reflect bias in response to metacog patterns), but **nothing renders the
diff.** We never show "policy for situation X moved from Y to Z, here's why." Today
the closest thing is the bandit's reward bars, which show *which function pays off*
but not *that the response to a situation was rewritten*.
What's needed that we don't store yet: a log of policy edits as
`{situation, old_action, new_action, reason, evidence, when}`. This is the one that
answers the whole "is it learning?" question, so it's worth doing even though it's
the most work.

### B. Belief revision history (last 24h feed)  → **PARTIAL**
> Belief, old conf → new conf, evidence (N successes / failures).

A real version of this **exists but is fragmented and buried**: self-belief revisions
live in a SelfModel sub-tab, opinions in another, symbolic-rule churn in yet another
panel. The idea is right; the gap is a **single chronological "what beliefs moved"
feed** across all belief types (self-beliefs, opinions, symbolic rules) with old→new
confidence and the evidence count, prominent enough that an empty feed for days is an
obvious red flag. This is mostly a *consolidation + promotion* job, not new plumbing.

### C. Belief churn (created / revised / discarded counts)  → **PARTIAL**
The "too low = dogmatic, too high = unstable" framing is valuable. For **symbolic
rules** we already have add/forget counts (`rules_added_today`, forgetting). For
self-beliefs and opinions we have the raw revision events but no rolled-up
created/revised/discarded tallies. Small add on top of (B): three counters per belief
class. Do it as part of B, not separately.

### D. Knowledge provenance (click a belief → where it came from)  → **PARTIAL**
> Created date, source goal, evidence count, supporting vs contradicting predictions,
> confidence.

Opinions already carry `evidence_count`; goals already carry IDs and history. The
missing link is **stitching them**: a belief doesn't currently point back to the goal
that spawned it or the predictions that support/contradict it. Genuinely useful for
debugging Orrin specifically, but it depends on provenance being *recorded at write
time*. Medium effort; lower urgency than A/B.

### E. Long-term goal progress / parent-goal advancement  → **PARTIAL**
> Top-level objectives only, with age and a real progress %. (Ideas #3 and #13 are the
> same ask.)

We have the goal tree, milestones (`met`/`met_at`), and ages — so a progress % is
**derivable** (met milestones ÷ total) but **not computed or shown**, and the tree
view mixes parents with subgoals/actions. The need: a **short list of just the
long-lived top objectives**, each with age and a progress bar that moves. This is a
focused view over data we already have. High value, modest effort.

### F. Goal survival curve (lifetime histogram)  → **PARTIAL**
> <10 cycles 41% · 10–50 32% · 50–200 18% · 200+ 9%.

GoalHealth gives average age and completion/abandonment *rates*, but not the
**distribution** of lifetimes. The histogram answers a different question (can he
*carry* objectives across time, or do they all die young?) that the average hides.
Nice-to-have; cheap if goal close-times are already logged.

### G. Self-model accuracy  → **PARTIAL (data already started!)**
> Predicted: reflection reduces uncertainty. Observed: no change. Error high. …
> Self-model accuracy 61% → 78% over time.

This overlaps an existing-but-quiet signal: `introspection_trust.json` already tracks
**felt-vs-behaved agreement per domain** ("has his introspection earned the right to
be believed"). That's exactly the seed of self-model accuracy. The gap is a
**time-trend** and a plain framing ("how well does he understand himself, and is it
improving?"). Build on the existing file rather than starting fresh.

### H. Prediction calibration over time  → **PARTIAL**
> Brier 0.32 → 0.28 → 0.24 → 0.19 across weeks.

We show the **current** Brier prominently, but `calibration_state.json` is a snapshot —
there's **no history series**, so we can't draw the downward trend that is the
cleanest single "the world model is improving" picture. Needs a periodic Brier
snapshot to a history file, then a sparkline. Low effort, high signal.

### I. Cognitive rut detector (quantitative)  → **PARTIAL**
> reflect_on_self: 27 consecutive uses · rut score 0.71.

The **machinery exists** (`behavioral_adaptation` detects ruts/oscillation and reacts;
habituation tracks satiety) but there's **no quantitative rut readout** — consecutive-
use counts and a single rut score. Cheap to surface from data the loop already
computes, and it pairs naturally with A (rut detected → policy changed).

### J. Novelty vs exploitation ratio  → **PARTIAL**
> Novel 38% / known-useful 62% — too far either way is a failure mode.

`exploration_value.py` already computes explore/exploit value per action; we don't
**aggregate it into one ratio** for display. Single gauge over existing signals. Easy,
and a good health indicator (wandering vs stuck).

### K. Recovery from failure (the funnel)  → **BUILD**
> Failures 48 → retried 41 → alternative strategy 33 → succeeded after failure 18.

Not currently surfaced as a funnel, and the "succeeded *after* failure" step isn't
tracked as such. This is a strong intelligence signal (recovery, not failure-
avoidance) and conceptually distinct from everything above. Needs failure→retry→
outcome to be linked when it happens. Medium effort, high conceptual value.

### L. Strategy diversity per goal  → **BUILD**
> Goal "investigate uncertainty": tried reflection, wikipedia, research_topic,
> memory_search, hypothesis_generation = 5. Stuck goal stuck at 1 strategy = problem.

Goal history records *events* but we don't roll up **distinct strategy count per
goal**. Cheap to derive if plan/history records which function attacked each goal;
pairs with E and K (a stalling goal with strategy-count 1 is the alarm).

### M. Knowledge reuse  → **BUILD (needs new tracking)**
> Facts learned today 47 · reused later 29 · reuse rate 61%.

"Learning is retrieval and application, not storage." We don't track **whether a
stored fact is ever retrieved again**. Requires instrumenting retrieval to credit the
source fact. Real plumbing; defer until A/B land, but it's a clean idea.

### N. Memory impact score  → **BUILD (needs new tracking)**
> Retrieved 8432 · changed a decision 731 · impact 8.7%. "Else memory is a scrapbook."

Same family as M but harder: it needs **causal attribution** of a retrieval to a
decision change, which we don't capture. Highest-plumbing, do last — but the framing
("is memory load-bearing or decorative?") is worth keeping on the list.

### O. Compression (observations → rules → accuracy)  → **HAVE**
> 500 observations → 12 rules → 83% rule accuracy.

This is essentially what **SymbolicMindPanel already shows** (rule counts, crystallized
rules, per-domain coverage, causal graph). If anything's missing it's a single explicit
**compression ratio** line (observations ÷ rules) and rule predictive-accuracy front
and center — a small label add, not a new panel.

---

## The perspective problem (separate, and important)

The dashboard mixes three layers without labeling them, which makes behavior
genuinely ambiguous to debug:

1. **Developer perspective** — ground-truth state (Valence = 54, Uncertainty = 95).
   Implementation detail; exists for the math.
2. **Agent-accessible perspective** — what Orrin *can* introspect ("I feel a pull
   toward exploration," "something feels unresolved").
3. **Agent-attention perspective** — what's in his active workspace *right now*
   (current goals, live thoughts, predictions, concerns, memories in awareness).

Why it matters: when Orrin does something surprising, the explanation is completely
different depending on which layer knew what —
(a) he knew and ignored it, (b) he knew and chose otherwise, or
(c) **the architecture knew, but he never had access to the number at all.**
Today the dashboard makes (c) look like (a), because the developer can see Uncertainty
= 95 and assumes Orrin could too.

**What partly exists already:** the **Watch page** is a pure agent-experience view, and
the `lexicon.ts` bio↔eng toggle already compresses raw numbers into felt language —
that's the seed of layer 2. The **ConsciousnessPanel** is essentially layer 3 (what's
in the workspace). What's **missing is explicit labeling on the Brain dashboard**: each
metric should declare whether it's dev-only, agent-accessible, or currently-in-
attention — so you can tell at a glance whether a number is something Orrin *has*, or
just something the machine has. This isn't a new panel; it's a **classification +
visual marker** applied to existing metrics (e.g. a small badge: "Orrin can feel this"
vs "implementation only" vs "in awareness now").

This may be more valuable than any single metric above, because it changes how you
*read everything else.*

---

## What you actually need (the distilled shortlist)

If the point is "prove learning is happening and changing behavior," build in this
order:

1. **Behavior-change log (A)** — the one number. *"I used to do X, now I do Y, because
   Z."* The engine already changes behavior; capture and show the diffs. **Highest value.**
2. **Unified belief-revision feed (B+C)** — consolidate the revisions/opinions/rule-
   churn we already compute into one prominent "what changed" feed with old→new +
   evidence. **Mostly consolidation, not new plumbing.**
3. **Perspective labeling (the three layers)** — tag every dashboard metric as
   dev-only / agent-accessible / in-attention. Changes how you read the whole UI.
4. **Two cheap trend lines we're one snapshot away from:** calibration-over-time (H)
   and a novelty/exploit gauge (J) — both ride on data the loop already produces.
5. **Top-level goal progress (E)** + **rut readout (I)** — focused views over existing
   data; together they show persistence and stuckness.

Defer (good ideas, real new plumbing): recovery funnel (K), strategy diversity (L),
knowledge reuse (M), memory impact (N), provenance stitching (D), survival-curve
histogram (F). Already covered: compression (O — SymbolicMindPanel).

The unifying principle for all of it: **stop adding stocks, start showing changes and
their causes.** A panel that can render *before → after → because* is worth more than
ten panels that render a current count.
