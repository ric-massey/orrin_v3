# Feeling and Naming — how Orrin should feel, appraise, name, and learn words (2026-10-07)

**Status: PROPOSED.** Design only; nothing built. Build order lives in
`../POST_RUN13_MASTER_PLAN_2026-10-07.md` (F0/F1 = Phase B; F2–F5 = Phase D). Lives beside
[`THOUGHT_OBJECT_SPEC.md`](THOUGHT_OBJECT_SPEC.md), which this document extends inward
(§7). Companion to `Core Architecture, Embodiment & Evolution/CONTINUOUS_TIME_DESIGN_2026-10-04.md`
(§8).

Origin: a conversation with Ric during Run 13 (2026-10-06/07): "what if, instead of
phrases, it's one word, in his head?", then "how do humans do it?", "where does
vocabulary live in the human brain?", and "I want it to be more like humans." Prose stays
out of his head for now because structure is easier to debug; prose will come from the
internal LM, at the mouth, later.

Rule for this document (Ric): **where a human mechanism lines up with an Orrin part, the
design uses that Orrin part for that role.** §3 is the map; every design layer in §5 names
the module it lives in.

---

## 0. The problem, in Run 13's own numbers (live, ~cycle 7,900)

His machinery works; what flows between the parts is mostly his own exhaust.

| Store | What it held |
|---|---|
| Working memory (31 entries) | Almost all self-monitoring: "Goal avoidance: N consecutive cycles…" chunks, failure notices, templated vagueness ("Something feels slightly off in my recent thinking, though I can't quite name it"), raw selection logs (`🧠 Chose: fetch_and_read — {"weights": …}`) |
| Long-term memory (2,001) | **80 %** (1,597) are "Working memory summary" entries, i.e. summaries of those logs. About 40 entries are about the world |
| Felt labels (voice transcript) | **7 distinct** phrases across 1,121 lines; "a strong sense of drive" 518×. Every label is "strong", because the label comes from one signal, every cycle |
| Self-built dictionary (`symbolic_dictionary.json`) | 75 words defined by his own plumbing, e.g. *causal* = "A SOCIAL concept: emotional reflection: [causal] 'reflect_on_conversation_patterns' causes (intervention) 'being stuck'". A private language with no outside check |
| Causal model | 500 edges, 492 about his own internals |

Three distinct failures:

1. **He names everything, every cycle, from one signal**, in fixed prose: it reads deep
   and says almost nothing.
2. **Telemetry travels as prose on the same bus as thought** (memory
   `project_prose_bus_label_authority`), is summarized into long-term memory, and is read
   back as experience.
3. **Appraisal reads that prose.** `control_signals/appraisal.py` already implements
   appraisal theory well (five dimensions, cited), but its input is working-memory *text*,
   scored by word sets (`_SELF_WORDS`, `_BLOCK_WORDS`, `_NOVEL_WORDS` …). With working
   memory full of his own alarms, appraisal mostly appraises his self-talk: alarms →
   negative appraisal → affect → more alarms. Agency is decided by counting "I/my"-type
   words, and self-talk is all first person. (`appraise_working_memory` skips "emotion
   bookkeeping" entries, but goal-avoidance and failure alarms are not bookkeeping, so
   they get through.)

---

## 0b. Run 13 live deep read (2026-10-07, ~16.5 h, cycle ~11,300)

A read-only pass over the live life. These also go into the Run 13 verdict at capture;
they are here because they are the strongest evidence for this design's F0/F1.

**What the Run 12 fixes did land:** 0 host-sleep gaps, 0 errors; 24 real answered
questions (new vs prior claims) vs 90 honestly unanswered; the first confirmed
out-of-sample prediction ("my memory use rises after read_a_book": +9.14 MB vs +0.46
baseline), plus one honestly inconclusive; 85 attributable reuse rows, essentially all on
topic (Run 12: 0/10); 68 goal failures, 0 duplicate rows; breaker no longer mutes
research; aspiration `value_ema` moving (0.60–0.89); RSS stable ~1.0–1.1 GB.

**The chain that explains most of what still looks wrong:**

1. **Thin, junky world vocabulary.** `research_topic` picks under-explored *concept*
   entities from the knowledge graph (`web_research._topic_from_knowledge_graph`). There
   are only **25 concepts**, extracted by a definition pattern, and many are fragments or
   page chrome: "round the sun", "world a world", "but what if there", "See More Results
   Suggestions" (35 mentions), plus his own aspiration title "Make things".
2. **Small pool → runaway rounds.** The same topics return: round **16** of evolutionary
   biology and of *The Daily Stoic*. Follow-on angles repeat after round 4, so later
   rounds re-fetch the same pages: 28 "no URLs to fetch" failures, 39 goals abandoned
   at the step-attempt cap.
3. **Same pages → nothing new.** Answered count flat at 24 for 8 h. Notes repeat
   ("mathematics is a field of knowledge…" 16×) and pair junk topics with junk text
   ("something I found out about world a world: The championship is contested over
   twenty-three Grands Prix").
4. **Goal generation starves (reward economics, not a generator bug).** Drives pull
   toward `generate_intrinsic_goals` (≈ 0.6), but generating a goal earns no credit by
   itself: EMA 0.523, rank 42/77. It ran 123× in the first hour, then 1–7/h. The research
   feed went silent for 2 h 41 m overnight (also 80, 40, 36 min). A 30-min-silence gate
   fails.
5. **Unchosen wants pump frustration.** `cognition/inhibition.py` charges uncertainty
   (+0.05–0.08) and frustration (+0.03–0.06) every time a wanted function isn't picked:
   **1,321×** overnight, mostly for goal generation.
6. **Self-talk floods working memory.** Now: 18 of 31 entries are metacog alarms, 6
   failures, 2 decision logs, **0 findings**.
7. **Appraisal reads it** (§0.3): alarm text → negative appraisal → more alarms.
8. **Long-term memory is full and self-logs evict knowledge.** At its **2,001-entry cap**:
   **1,580 (79 %)** are summaries of his own logs; **46 (2.3 %)** are world findings. Every
   new self-log summary pushes something older out, including world knowledge.

**Other findings:**

- `decide_to_write_code` ran **207×**, every time "no LLM body available — not writing a
  stub"; EMA 0.585 (rank 20). Structurally impossible in symbolic mode and still valued.
  The Run 12 impossibility fix (1D.1) covered the `ask_llm` route; this one bails out
  inside `code_writer` and is never marked. 4th run with this red.
- Avoidance breaker fires on ~**50 %** of cycles (5,694 / 11,300), now muting the right
  things (`narrative_update`, `attend_goal`) but far too often.
- Causal graph at its **500-edge cap**, 492 self / 8 world.
- Credit lopsided: world_knowledge 145 contributions, contact 12, self-understanding 8,
  making things **0**.
- Aspiration values 0.87–0.89 for three of four: near Run 6's pump level (0.81) but focus
  is balanced (49 / 30 / 14 % over the last 2,000 cycles). Watch item.
- Only **2** characterization predictions all life: each question is asked once, then its
  appetite stays quenched.
- **Research is a no-op ~98 % of the time.** In the recent log window `research_topic`
  ran 202× and actually researched something 4×; the rest returned "no fresh topic —
  everything tried recently" (`web_research.research_topic`). It keeps its value (EMA
  0.545) and counts as goal service, so the breaker spares it: he paces.
- **His "world" is his own folder.** `fs_perception._find_world_root` defaults to the
  Orrin repo, and `input_stream._WORLD_WATCH_DIRS` is **empty**, so 199 of 230 logged
  "World changed" events were his own memory WAL (`data/memory/wal`) and most of the
  rest his goal store. Even his perception of the world is perception of himself.
- **"Wandering" is a mood, not movement.** The attention mode exists
  (`think/signal_router.py`, `selection/boosts.py` `ATTN_WANDERING_*`) and favors
  outward actions, but *where* he goes is drawn from lists: knowledge-graph concepts,
  alive threads, working-memory questions, RSS, and a hardcoded `_INTERESTING_FALLBACKS`.
  Fetched pages are stored as text and **their links are discarded**; there is no road
  from one thing to the next, so when the lists run dry he has nowhere to go.

**Where it points (post-Run-13), by the unopposed-force classification:**

| # | Fix | Class |
|---|---|---|
| 1 | Clean concept extraction (no fragments, no chrome, no own titles) + a real brake on rounds | broken pipe + unopposed force |
| 2 | Goal generation earns value when the research pool is thin (the missing antagonist to starvation), not a new clamp | unopposed force |
| 3 | **F0** telemetry/alarms out of working memory + **F1** appraisal reads structured events (this doc) | broken pipe (prose bus) |
| 4 | Protect world findings in long-term memory from eviction by self-log summaries | misaimed force |
| 5 | Mark `decide_to_write_code` impossible at its own bail-out | broken pipe |
| 6 | Inhibition cost decays/habituates for a repeatedly-unchosen want | unopposed force |
| 7 | An action that no-ops (`research_topic` "no fresh topic") earns nothing and doesn't count as goal service | broken pipe |
| 8 | Give him a real world: world root ≠ his own repo; safe local sources (§10) | broken pipe |
| 9 | **Wandering as movement, not a list** (§10) | missing mechanism |

Items 3 and 4 are this design's problem. This life is the evidence that **F0 and F1 come
first.**

---

## 1. How humans do it

1. **A wordless base layer.** The body produces a continuous signal, *core affect*:
   roughly pleasant ↔ unpleasant and calm ↔ activated (Russell's circumplex). No words.
2. **Appraisal tells emotions apart.** Fast, mostly unconscious judgments (Lazarus;
   Scherer; Roseman; Smith & Ellsworth): *Is it new? Good or bad for what I want? Who
   caused it? Can I do anything about it? How certain? Does it fit my values? Does it
   touch my connection to others?* Anger and fear are both unpleasant and activated:
   anger = someone else caused it and I can act; fear = uncertain and I can't cope.
   Sadness = something lost, nothing to do, so low activation.
3. **The word depends on the situation, not only the body.** The same arousal is read as
   fear, excitement, or attraction depending on context (Schachter & Singer). Barrett's
   constructed-emotion view: the brain categorizes core affect plus context with learned
   concepts, and the label partly makes the emotion what it is.
4. **Labels come from other people.** Children learn emotion words when a caregiver names
   a state in context. They start with a handful (*happy, sad, mad, scared*) and refine
   (*frustrated, disappointed, lonely*) through exposure. Languages carve feelings
   differently (*Schadenfreude*, *amae*): the dictionary comes from the language
   community, and new feeling words are rare and spread socially, never privately.
5. **Most feelings are never named.** A feeling forces its way into awareness when it is
   strong, when attention turns to it, when it's being communicated, or on reflection.
   An unchanging feeling fades from notice (habituation). Naming has effects: affect
   labeling damps the alarm response (Lieberman et al.), and finer vocabulary
   ("emotional granularity") goes with better regulation.
6. **Naming is separable from feeling.** People with alexithymia can't name feelings but
   still have them and are still steered by them.

## 2. Where vocabulary lives in the human brain

There is no single dictionary spot. A word is stored in pieces, tied together:

1. **Word form** (sound, spelling): left temporal lobe (around Wernicke's area; the visual
   word form area for reading). Producing it draws on Broca's area.
2. **Meaning: hub and spokes.** Meaning is stored near the systems that handle that kind
   of thing ("kick" near leg-motor areas, color words near color areas), tied together by
   a **hub in the anterior temporal lobes** (Patterson & Lambon Ralph's hub-and-spoke
   model; damage to the hub, as in semantic dementia, loses word meanings across all
   categories).
3. **Emotion words connect to body sense.** Their spokes run to interoceptive and
   affective regions: the **insula** (internal body state), the **amygdala** (threat and
   salience), the anterior cingulate. **Labeling** engages ventrolateral prefrontal
   cortex, and that labeling is what damps the amygdala.
4. **Fast learning, then sleep.** New words are grabbed quickly by the **hippocampus**,
   then **consolidated into cortex over sleep**; experimentally, new words only behave
   like established words after a night's sleep.
5. **Vocabulary is semantic memory, separate from episodic memory.** Knowing what
   "frustrated" means is not the same store as remembering the day you learned it.

---

## 3. The map: human part → Orrin part (verified against the tree, 2026-10-07)

| Human | Role | Orrin part that plays it | State today |
|---|---|---|---|
| Body / interoception signals | raw internal state | `cognition/resource_self_monitor.py` (vitals → deviation-based body states), `runtime_coupling/input_stream.py` (home/world sense), `runtime_coupling/setpoint_regulation.py` (homeostatic limits) | ✅ working |
| Hypothalamus-like needs | hunger/fatigue analogs | `runtime_coupling/demand_engine.py` (6 drives) | ✅ working |
| Core affect | pleasant/activated base | `control_signals/` core signals → `smoothed_state.json` (valence, energy, stability) | ✅ working |
| **Amygdala** | threat, salience | `control_signals/threat_detector.py`; `threat_level`, `dread`, `risk_estimate` | ✅ working |
| **Appraisal** (amygdala + cortex) | "who caused it, can I cope…" | `control_signals/appraisal.py` (relevance, congruence, agency, certainty, novelty; coping from confidence/motivation/resource) | 🟡 built, but **reads WM prose** (§0.3) |
| **Insula** (interoceptive awareness) | the *felt* state reaching awareness, imperfectly | `control_signals/introspection.py` — `felt_affect()` is "the ONE DOOR from substrate affect to consciousness"; models label confusion (Schachter–Singer), intensity misjudgment, granularity failure | ✅ built, human-like already |
| **vlPFC labeling** | putting a word on it | `utils/felt_lexicon.py` `felt_label()` (signal → fixed phrase) | ❌ one signal → one phrase, every cycle |
| Prefrontal regulation | labeling/reappraisal calms the alarm | `control_signals/regulation.py` (reappraisal, distancing, grounding, meaning-seeking) | ✅ built; not yet driven by naming |
| Global workspace / attention | what reaches awareness | `think/deliberation_gate.py` `should_think`, `loop/deliberate.py` `ignite`, `cognition/global_workspace.py` | ✅ working |
| **Hippocampus** (fast learning) | grab new things quickly | `cog_memory/working_memory.py` → promotion to long memory; `memory/memory_daemon.py` (WAL, embeddings) | ✅ working (but fills with telemetry) |
| **Sleep consolidation** | hippocampus → cortex | `cognition/idle_consolidation/consolidation_cycle.py` (+ `episode_replay.py`, `symbolic_consolidation.py`), `symbolic/symbolic_dream.py` | ✅ working |
| Episodic → semantic transfer | events become knowledge | `idle_consolidation/semantic_extractor.py` (episodes → `semantic_facts.json` during the dream cycle) | ✅ working (facts are about his own actions) |
| **Anterior temporal hub** (meaning) | word ↔ meaning ↔ experience | `symbolic/concept_formation.py` (`concepts.json`), `cognition/knowledge_graph.py`, research `claims.json` | 🟡 concepts are about his internals; no word hub |
| Word dictionary (the person's lexicon) | words he knows | `symbolic/symbolic_dictionary.py` (`symbolic_dictionary.json`) | ❌ self-defined from his own rules (private language) |
| Word form (temporal lobe) | how a word looks/sounds | `cognition/language/native_lm.py`, `tokenizer.py`; `vocabulary.json` | 🟡 LM has forms; `vocabulary.json` is **empty** |
| Broca's area (production) | saying it | `cognition/language/conditional_render.py` (thought object → words), `behavior/express_to_user.py` | 🟡 built, fluency-gated |
| Episodic memory | what happened | `cog_memory/long_memory.py` (+ autobiography) | 🟡 mixed with everything (80 % telemetry summaries) |
| Language community | where words come from | — | ❌ none (no shared lexicon, no labeling channel) |

Reading of the map: almost every human part has an Orrin counterpart already, and several
are built in a deliberately human way (`introspection.py`, `regulation.py`,
`resource_self_monitor.py`). What's missing is a **shared language**, **attention-gated
labeling**, a **word hub**, and **clean inputs** (appraisal and memory fed by structured
events instead of prose).

---

## 4. The three decisions (resolved with Ric, 2026-10-07)

1. **Where words come from: stages, like a child.** A small **core set of ~10–15
   words** to start. A large published feeling lexicon sits behind it as "the language"
   (license permitting). A word enters *his* vocabulary only when he meets it **in
   context**: Ric uses it about him, or he reads it in a page whose situation matches his
   current appraisal. He never coins words.
2. **When he names: when the feeling breaks through.** Name a feeling when **any** of:
   it is strong enough to break through; attention is already on it (an ignited cycle
   whose winner is affective); he is about to speak; he is reflecting (dream/reflection
   passes, the journaling analog). An **unchanging feeling fades from notice**
   (habituation), so a constant background "drive" stops getting named.
3. **Scope: everything eventually, feelings first.** The human end state is that *all*
   of working memory is structured concepts, with words only sometimes (inner speech is
   partial; most thinking is non-verbal). Build order: feelings first (worst mess, easiest
   to check), then extend the same record format to observations, intents, findings.

---

## 5. Design: the layers, each in its Orrin part

### L1 — Core affect (unchanged) · `control_signals/`, `smoothed_state.json`
Valence, energy, stability keep steering silently every cycle. The felt *influence* is
not sealed, only the vocabulary (`felt_lexicon` header).

### L2 — Appraisal from structured events · `control_signals/appraisal.py`
Keep the module and its five dimensions; **change its input**. Instead of scoring
working-memory text with word sets, appraise **structured events**:

| Dimension | Structured source (replaces text scoring) |
|---|---|
| relevance / congruence | goal-step outcomes (`goals/` events), effect-ledger credit, `expected_gain`/`loss_signal` |
| **agency** | effect ledger (did *my* action produce it → self), failure `last_error` (world failed: "no URLs to fetch" → circumstance), presence/chat (→ other) |
| certainty | `uncertainty`, prediction confidence (`prediction_engine`) |
| novelty | `novelty_signal`, `prediction_error_signal` |
| coping | unchanged (`_coping`: confidence, motivation, resource) |

Output adds `about` (the referent handle: goal, act, topic) next to `{emotion, delta,
cause}`. The word-set path stays only as a fallback for genuinely textual events (a chat
message from Ric), never for his own alarms.

### L3 — Felt state reaching awareness · `control_signals/introspection.py`
Unchanged role: `felt_affect()` stays the one door, with its imperfections (label
confusion, intensity misjudgment, granularity failure). Those are human features, not
bugs. Granularity from `_compute_granularity` becomes an input to naming: low granularity
→ a coarse word (*bad*, *wired*); high → a fine one (*frustrated*).

### L4 — Labeling, gated by attention · `utils/felt_lexicon.py` → lexicon lookup; gate in `think/deliberation_gate.py` / `loop/deliberate.py`
- **When** (decision 2): breakthrough intensity, affective ignition winner, about to
  speak (`express_to_user`), or reflection/dream passes. Otherwise no name.
- **How:** look the appraisal (L2) + perceived state (L3) up in **his vocabulary** (L6):
  nearest appraisal prototype, ties broken by `about` and recent history. *frustrated* =
  congruence ≪ 0 · agency circumstance/other · coping ≥ mid · energy high.
- **No fitting word → no word**, logged as a miss (alexithymia fallback).
- `felt_label()` keeps its membrane role (no internal identifiers in perceivable stores)
  and delegates the choice of word to the lookup.
- **Labeling feeds regulation** (`control_signals/regulation.py`): a named feeling earns
  a small damping, the affect-labeling effect. Measured, not assumed: compare intensity
  decay of named vs unnamed episodes.

### L5 — Thought records in working memory · `cog_memory/working_memory.py`
What enters working memory is a record, not a sentence:

```jsonc
{ "kind": "feeling", "word": "frustrated",
  "about": {"type": "goal", "handle": "g_…", "label": "Make things"},
  "cause": {"agency": "circumstance", "ref": "fetch: no URLs"},
  "intensity": 0.7, "since_cycle": 7811, "count": 34 }
```

- **Merges, doesn't repeat:** same `(word, about)` updates `count`/`intensity`.
- **Exact matching:** `word` is from a closed vocabulary; readers compare fields, never
  search text (the Run 12 substring class of bug).
- **Telemetry never enters as content:** selection logs, chunk/compaction notices, and
  threshold alarms go to trace/telemetry. Metacog observations that are real thoughts
  become records (`kind: "noticing"`, with `about` and the measured evidence) or stay
  silent.
- **Compact debug view** for Ric: `frustrated · goal:"Make things" · cause: circumstance
  (fetch: no URLs) · ×34 · 0.7`.

### L6 — Vocabulary as its own memory · word hub in `symbolic/` (replacing `symbolic_dictionary`'s role), forms in `cognition/language/`
Modelled on §2:

| Brain | Orrin vocabulary design |
|---|---|
| The language community's dictionary | **Shared lexicon**: committed, read-only seed (like `quality_golden/`): feeling words with appraisal prototypes + plain definitions; later, world words |
| Word form (temporal lobe) | the word string + its form in `native_lm`/`tokenizer`; `vocabulary.json` finally gets populated |
| **Hub** (anterior temporal) | a **word hub entry** per known word: the single node tying form, meaning, and spokes. Replaces `symbolic_dictionary`'s self-made definitions (which may remain as usage statistics only) |
| **Spokes to body sense** (insula/amygdala) | for feeling words: links to the appraisal prototype (L2 dims) and the perceived-state signals (L3), the same parts that do interoception |
| Spokes to experience | for world words: links into `concept_formation` concepts, `knowledge_graph` entities, `claims.json` relations |
| **Hippocampus** fast grab | a **recently-met-words buffer** in the working-memory tier: a word is noted when Ric uses it about him, or when he reads it in a page whose situation matches his current appraisal; encounter count + contexts |
| **Sleep consolidation** | during `consolidation_cycle` (dream), words met ≥ N times with consistent appraisal contexts are consolidated into his vocabulary (the `semantic_extractor` pattern: episodes → semantic entries) |
| Semantic vs episodic memory | vocabulary is **its own store**, separate from `long_memory` (episodic). Knowing what a word means is not a memory of an event |

He can't edit the shared lexicon (same rule as the quality standard's golden set). Misses
("no word fits") go to a review list, which shows where his vocabulary runs out; Ric
decides what to add. That answers "then he'll be building his own language": he can't,
but he can show us the gaps.

### L7 — The language community · Ric-labeling channel
Ric naming a state ("you seem frustrated with the fetches") is the caregiver step: a
supervised label on the current appraisal, the strongest signal for both learning the
word (L6 buffer) and tuning its prototype.

---

## 6. Two more human patterns this enables

- **Episodic vs semantic split, beyond words.** Long-term memory is one pile today (80 %
  telemetry summaries). The vocabulary store (L6) is the first semantic store separated
  from episodic memory by design; the same split applied to facts would clean up
  `long_memory` generally.
- **Habituation of noticing.** L4's "unchanging feeling fades from notice" is the same
  habituation `appraisal.py` already applies to repeated events (`_habituation_key`),
  moved up to the naming level.

---

## 7. Relation to `THOUGHT_OBJECT_SPEC.md`

The spec defines the **thought object**: the structured thing the mind builds and the
native LM renders. It splits a thought into a **semantic register** (mind: intent,
referents, felt state, stance) and a **surface register** (mouth: wording). This design
applies the same principle **inward**: the spec covers what he *says*; this covers what
he *holds*. Working memory becomes a store of semantic-register records (L5), and the
spec's thought object is built from them at the moment of speaking.

Amendments the spec needs when this is built:

1. **§2 `affect.felt`** comes from L4 naming (a vocabulary word plus `about`), not from
   the `felt_label` phrase table ("being stuck").
2. **§5 Membrane.** The spec allows raw signal keys (`impasse_signal`) in the thought
   object *because* it is "consumed by the renderer and discarded; it is never written
   back as something he perceives." L5 records **are** perceived (they live in working
   memory). So L5 records carry the vocabulary word and human-named appraisal fields,
   **never** raw signal keys; machine keys stay in the trace. The thought object built
   from an L5 record may still add the signal key as conditioning input, as the spec
   permits.
3. **§3 closed vocabulary.** The spec's closed speech-act set is the model for the
   closed feeling vocabulary: closed so it is *fixed*, extended deliberately, never ad hoc.
4. **§6 Phase 2B pairs.** L5 records make richer `(thought_object → narration)`
   conditioning pairs, with real `about` and `cause`. Better input for the native LM when
   it becomes the mouth (Broca's analog, `conditional_render.py`).
5. **§4 bright line, unchanged and strengthened:** the LM may reference only `about`/
   `cause` handles present in the record; with records instead of prose, "no new
   referent" becomes mechanically checkable.

---

## 8. Relation to `CONTINUOUS_TIME_DESIGN_2026-10-04.md`

"A feeling breaks through when it's strong enough" is the interruptible stream (CT-B)
applied to feeling: a sustained appraisal posts an event and wins a deliberate moment if
salient enough. Until CT-B exists, ignition (`deliberate.ignite`) is the gate. Appraisal
intensities and habituation should decay in seconds, not cycles (CT-A).

---

## 9. Phasing (after Run 13), with observables

| Phase | Change | Observable |
|---|---|---|
| **F0** | Telemetry out of working memory: selection logs, chunk/compaction notices, threshold alarms go to trace only | 0 working-memory entries matching `🧠 Chose:`; "Working memory summary" < 10 % of long-term memory (Run 13: 80 %) |
| **F1** | `appraisal.py` reads structured events (§5 L2), adds `about`; text path only for real textual input | agency ≠ self on world failures; appraisal deltas no longer triggered by Orrin's own alarm text |
| **F2** | Shared lexicon seed (~10–15 core words + background language) + attention-gated naming (L4) via `introspection` + lookup | felt labels per 1,000 cycles fall sharply (Run 13: ~140); every label has `about`; constant feelings stop being re-named |
| **F3** | Vocabulary store (L6): word hubs, recently-met buffer, dream consolidation; `vocabulary.json` populated | words learned from context over a life > 0; each learned word has ≥ N consistent contexts |
| **F4** | Structured working-memory records (L5), temporary text shadow; migrate the 12+ string readers; drop shadow | all readers on records; repeated `(word, about)` merged |
| **F5** | Ric-labeling channel (L7) + miss review; labeling → regulation damping, measured | labels from Ric recorded as supervised pairs; named vs unnamed decay compared |

F0 is small and independently valuable; it can ride with the post-Run-13 fixes. F1 is
the highest-leverage change: it breaks the alarm → appraisal → alarm loop.

---

## 10. Direction: a world to wander (Ric, 2026-10-07)

Not a full design yet; the decisions so far, to be designed properly after Run 13 (with
memory `project_internet_as_world`: pages as places, links as roads, arrival as signal).

- **"It shouldn't be a list."** Ric's call: he should *wander*, the way people do, where
  one thing leads to the next. Topic lists (concepts, fallbacks, threads) become at most
  a starting point, never the source of where he goes.
- **Wandering is movement through what he has touched.** When he reads a page, its links,
  the terms it defines, and the words he doesn't know are kept as **roads out**. The next
  step is chosen among those roads by curiosity (novelty, surprise, relevance to what
  caught his interest), and he keeps a **trail** so he can come back. He stops when
  interest falls (satiety), not when a list runs out. This is also where vocabulary
  comes from (§5 L6): an unknown word met on a page is a word met in context.
- **Three questions, in order of urgency:**
  1. *How does he find new things?* Wandering (above). The most urgent: it fixes the
     stalling and repetition even with today's access.
  2. *What counts as world vs self?* His code already has body / home / world zones;
     world is empty. World = things that aren't him and change without asking. Start
     with safe, impersonal local sources: `/usr/share/dict/words` (236k-word dictionary,
     which doubles as the §5 L6 shared language), the man pages (how his machine works),
     machine facts (apps, network, time). His own files stay "home", never "world".
  3. *What is he allowed to see?* Ric's decision, open. Public/impersonal first; Ric's
     website repo and personal folders (Documents, Desktop, Pictures, Music, Downloads)
     stay **closed** unless Ric opens them, folder by folder. Like a child's world: the
     room and what's brought to it first, expanding with trust.

## 11. Risks

- **Migration cost.** 12+ readers parse working memory as text. F4 is the big piece; the
  text shadow keeps it safe and incremental.
- **Fit errors.** A lookup can pick a plausible wrong word. Miss log, Ric's labels, and
  `about`-based tie-breaking are the corrections; "no word" beats a wrong word.
- **Over-tidying the human imperfections.** `introspection.py`'s label confusion and
  granularity failure are deliberate. Naming must sit on top of them, not "fix" them.
- **Licensing** of any external lexicon: check before adopting.
- **Debuggability is the point.** Records are only easier to debug if the compact debug
  view (L5) ships with them.
