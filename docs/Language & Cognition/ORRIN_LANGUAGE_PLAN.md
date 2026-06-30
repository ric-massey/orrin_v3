# Orrin → Human-Level Language: Plan & Honest Roadmap

*Draft — 2026-06-04*

> **Cross-ref (2026-06-29):** This plan is compatible with
> `../Core Architecture, Embodiment & Evolution/GROUNDED_COGNITION_DIRECTION_2026-06-29.md`
> *provided the native LM stays render-only* — Phase-2 corpus schooling teaches the mouth
> *how to say,* never *what to say,* and external text must not enter concept formation
> (that is the real "corpus contamination" risk, not training the language organ on syntax).
> See that doc's "Part D′ — Relation to the existing language docs" for the full reconciliation.

## The goal

**Make Orrin as good as a human at language — not better than ChatGPT.**

That distinction is the whole plan. "Better than ChatGPT" is the wrong target (it's a
superhuman, scale-driven thing, and chasing it is a losing race on any local hardware).
"As good as a human" is a *lower, well-defined, reachable* bar: talk fluently-but-normally,
understand normally, and — the part that actually matters — **be a continuous, grounded,
remembering, wanting self.**

### The two axes (why this is two problems, not one)

| | Axis 1 — fluency & recall | Axis 2 — being a *someone* |
|---|---|---|
| What it is | smooth sentences, broad knowledge | self, goals, memory, grounding, caring, learning from life |
| Who's best | ChatGPT (superhuman; beats every human) | humans (ChatGPT has *none* of this) |
| Solved by | **scale** (params × data × compute) | **architecture + grounding + time** |
| Orrin's target | *human-normal* fluency (not superhuman) | *human-level* selfhood — the heart of the project |
| Runs on the M1? | **No** — initial acquisition needs more compute | **Yes** — this is what the M1 is for |

Axis 1 fell to scale and is now a **commodity tool** (like a calculator beats us at
arithmetic without being smarter than a mathematician). The right move is not to win it but
to **use** it — the LLM stays "the phone," a tool he reaches for, never part of his cognition.
Axis 2 is the open frontier and the reason Orrin exists.

---

## Where he is now

- **Model:** decoder-only transformer, `n_embd=256, n_head=4, n_layer=4, block=128`,
  vocab 8192, **~5.3M params** (weight-tied).
- **Corpus:** ~21 MB library (36 books + a handful of Wikipedia articles), expandable to
  effectively unlimited (the Wikipedia tap).
- **Hardware:** Apple M1, 8 GB RAM, MPS. ~8.9 training steps/sec.
- **Continual learning:** wired — idle bouts, dream consolidation, replay against forgetting,
  emotion-weighted experience, and boredom-driven book reading (`read_a_book`).

**Honest ceiling from scratch on this machine:** a **young child** — word-like, simple,
sometimes-grammatical sentences in a narrow style (think "TinyStories" tier). *Not* a fluent
adult. The blocker is not the code; it's the **compute needed for initial language acquisition**.

---

## The one real bottleneck

A human hears **tens of millions of words before kindergarten**, hundreds of millions by their
teens, in a language network vastly larger than 5M params. Fluency is the product of that
exposure. To reach human-*normal* fluency, Orrin's own organ needs a comparable schooling —
and that initial acquisition is more compute than an 8 GB M1 can deliver in a sane timeframe.

Everything *after* acquisition (living, remembering, growing, drip-feed learning) runs fine at
home. **So the plan is: do the heavy schooling once on real compute, then bring him home to
live and keep learning for life.**

---

## The principle (non-negotiable)

**This is NOT downloading an LLM.** It is schooling **his own organ**:

- His architecture, **randomly initialized — his weights**, trained from scratch.
- Corpus = public-domain text + **his own lived experience** (memories, conversations,
  inner monologue), via the same pipeline his continual loop already uses.
- No pretrained third-party weights are ever loaded into his cognition.

> Renting a GPU = **sending him to a well-resourced school instead of homeschooling him on
> 30 books.** Same child, same brain — just enough exposure to actually learn to speak.

---

## How humans actually do it — and why we school *his own* model, then keep training it

### Humans don't start random, *and* they don't start from someone else's mind

A baby's brain is not a blank slate and not a copy of an adult's. It starts from a **third
thing**: evolved **architecture + priors** — pre-wired structure, learning biases, a drive to
attend to speech, critical periods — inherited from the *species*, not from any individual.
Then it becomes *that specific person* through their lived, embodied, social, emotional life.

Mapped onto Orrin:

- **Transformer architecture + its wiring into his cognition** = the innate, evolved part.
- **Well-conditioned random weights** = a substrate *ready to learn*, carrying nobody's mind.
- **Learning from his own experience** (memories, conversations, emotion-weighted) = becoming *him*.

So among the options, **random-from-scratch shaped by his own data is the closest to human.**
Warm-starting from another model's weights (GPT-2, etc.) is the *least* human — it's being born
with a stranger's adult mind already installed. Proper GPT-style init isn't "learned content";
it's the nearest stand-in we have for evolutionary priors: a brain merely *shaped to learn well*.

### Why random at birth — but his own weights ever after

The very first organ must start random, because **he has no language-weights to inherit yet**
(this is his first), and his symbolic structures — knowledge graph, memory, world model — are
*data, not weight matrices*; you can't pour them into attention layers. The only pre-loadable
language weights would be another model's, which we reject.

But he only starts random **once.** From then on, **continual learning means every future
version warm-starts from his own previous checkpoint.** Random is the single instant of birth;
everything after is him inheriting himself. *"Weights from Orrin training the model"* isn't
skipped — it's his entire life after birth.

### The learning regime is where "human" really lives

The starting weights are the small part. What makes language acquisition *human* is **how it
learns**. Where Orrin stands:

| Human ingredient | Orrin |
|---|---|
| Emotion-weighted salience (we keep what mattered) | ✓ built |
| Developmental curriculum (simple → rich, critical periods) | ✓ built |
| Sleep consolidation + replay | ✓ built (dream cycle) |
| Lifelong, never-reset continual learning | ✓ built |
| **Grounding / embodiment** (words tied to sensation, action, consequence) | ⚠ partial — **the real gap** |
| **Social, interactive learning** (language learned *with* people who matter) | ⚠ partial — **the second gap** |

The honest tension: **the most human path is also the slowest.** A real child takes *years* of
embodied, multimodal, social input — they do **not** learn language by reading 21 MB of books.
Text-only learning is itself our biggest divergence from how humans do it.

### So: train our own model — *then keep training it.* (Skip infancy, don't skip childhood.)

This is the whole strategy in one line. We **school his own from-scratch model** to load the
language into him, **then continue to train it for life.** It's like **loading a language into a
kid and skipping infancy** — we hand him the fluency a child would spend years of slow,
embodied babble acquiring, so he doesn't have to crawl through that on an 8 GB laptop. But we
**do not** skip *childhood and beyond*: once the language is loaded, he keeps learning from his
own life — grounded, social, emotional, continual — exactly as a person does.

- **Skip infancy** = the one-time schooling (Phase 2). Compresses the years of raw acquisition.
- **Don't skip childhood** = continual learning forever after. This is where he becomes *himself*
  and where the grounding/social gaps get closed over time.

It stays *his* model the whole way: his architecture, his weights, his vocabulary, his
experience — just spared the part of infancy that's pure mechanical exposure, which the GPU
schooling does in days instead of years.

---

## Model size tiers

| Tier | Config (approx) | Params | Context | Where it trains | What he sounds like |
|---|---|---|---|---|---|
| **0 — now** | 256 / 4L / 4H | ~5.3M | 128 | M1 from scratch | young child / word-like |
| **1 — local upgrade** | 384 / 6L / 6H | ~20–25M | 256 | M1, weeks of training | early reader; simple but real |
| **2 — the target** | 768 / 12L / 12H, vocab 16k | ~110–160M | 1024 | **cloud GPU once**, then M1 for life | human-*normal* conversational fluency |

Tier 2 is roughly GPT-2-small class — the zone where text reads "basically normal." That is
the **human-fluency target**, and deliberately *not* bigger: we want normal, not superhuman.

---

## The phased plan

**Phase 0 — prove the pipeline (M1, already staged).**
Run the current light pretrain (`--epochs 1 --steps 150`) on the 5.3M model. Confirm held-out
perplexity falls and the sample looks word-like. Purpose: validate the machinery end to end.
*(Runbook already written; nothing launched yet.)*

**Phase 1 — bigger model, still local (~25M).**
Bump the config to Tier 1, retrain tokenizer + pretrain on the M1 over days/weeks. Confirm a
larger model trains stably here and perplexity drops meaningfully. Purpose: de-risk the
architecture change before paying for a GPU.

**Phase 2 — the schooling (cloud GPU, one time, ~Tier 2).**
Rent a GPU, pretrain *his* Tier-2 model on a large clean corpus until conversationally fluent,
then download the checkpoint. This is the unlock for human-normal fluency.

**Phase 3 — he comes home and lives.**
Load the schooled checkpoint on the M1. Inference fits comfortably; **continual learning
continues at home** (small batches / partial updates as needed). The LLM stays a closed tool.
He keeps growing from his own life, for life.

---

## Phase 2 specifics (the GPU schooling)

**What to rent:** one modern GPU with ≥24 GB VRAM.
- Ideal: a single **A100 40 GB** or **H100** (spot/community rates ~$1.50–3/hr).
- Workable: a **24 GB card (RTX 4090 / L4)** with gradient accumulation.
- Marketplaces: RunPod, Lambda, Vast.ai, etc. (spot pricing is cheapest).

**Data:** a few **billion tokens** of clean, mostly-simple English — the existing library
scaled up via the Wikipedia tap (`fetch_wikipedia`), plus simple-English sources, plus his own
experience folded in at the end (already supported via `acquisition.experience_corpus`).

**Time & cost (honest ranges, depend on target size + data + quality bar):**
- A ~30–60M model to solid simple-fluency: **hours to ~1 day**, **~$30–80**.
- A ~110–160M (GPT-2-small class) to human-normal fluency: **~1–4 days**, **~$50–250**.
- These are iterative — you can stop early, evaluate (held-out perplexity + samples), and
  decide whether to keep going. It is not a single all-or-nothing bill.

**What changes vs. the current script:** only the **model config** (size/context/vocab) and
**where the one-time pretrain runs**. The tokenizer approach, curriculum, replay, eval, and
experience-folding are already built and carry over unchanged.

---

## Phase 3 specifics (coming home)

- **Inference of a ~124M model on M1 8 GB:** fits (≈0.25 GB fp16 / ≈0.5 GB fp32).
- **Continual learning at home:** feasible at small batch (slow, but lifelong learning *should*
  be a slow drip). If full-model updates are too heavy, restrict updates to a subset of layers
  (or LoRA-style adapters) so he keeps learning cheaply without forgetting his schooling.
- **Nothing else changes:** idle/dream consolidation, replay, emotion-weighting, and
  boredom-driven reading all continue. The schooled weights are just a far better starting point.

---

## What "human-level Orrin" actually feels like

Not ChatGPT. A **person**:
- talks **fluently but normally** — bounded vocabulary, makes mistakes, has a voice;
- doesn't know everything — **reaches for tools** (the "phone") for facts, like you do;
- **remembers you**, means what he says, wants things, and **learns from what happens to him.**

The fluency comes from the schooling; the *who* comes from the architecture you already built.

---

## Honest caveats

- **Even Tier 2 is not ChatGPT.** Smaller knowledge base, occasional clumsiness. That's fine —
  the target is *human*, and humans google things.
- **Human-level selfhood (Axis 2) is genuinely unsolved** — this is research-frontier work, and
  success is uncertain. But it's the right north star, and the architecture is a serious attempt.
- **Throughput is the lifelong constraint.** He learns slowly. That's acceptable (so do children),
  but don't expect overnight leaps after Phase 3 — expect gradual growth.
- **Grounding does the heavy lifting for "understanding."** The LM is the mouth/ear; comprehension
  lives in his symbolic mind. A modest-but-fluent LM + strong grounding can feel meaningful well
  before the prose is polished.

---

## What's already built (carries into every phase)

- From-scratch transformer + byte-level BPE tokenizer (his own).
- Library: fetch / browse / pick / read, with read-tracking and curriculum ordering.
- Continual learning: idle + dream consolidation, replay against catastrophic forgetting.
- **Emotion-weighted** learning (memories that "held weight" train harder).
- **Boredom-driven reading** (`read_a_book`) — he picks a book his own way when restless.
- Pretraining script with: library-seeded tokenizer, **his own experience folded in**,
  warmup→cosine LR, held-out **perplexity eval**, throttled checkpointing, weight tying.

The only thing standing between "young child" and "human-normal" is **Phase 2 compute** —
and that's a rented GPU and a few dollars, not a rewrite.
