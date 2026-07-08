# Scientific Foundations

Orrin's design borrows mechanisms from cognitive science, psychology, neuroscience-inspired
computational models, and AI-safety literature. The citations below live as comments in the code
itself — each section links the source work to the module(s) that implement the borrowed mechanism.

**Caveat:** the design is interpretive. Cognitive terms name engineering mechanisms; the literature
is cited for context and design lineage, not as formal validation that Orrin implements these
theories faithfully.

## Affect & control signals

| Source | Mechanism in Orrin | Code |
|---|---|---|
| Russell & Barrett (1999) core affect; Barrett (2017) *How Emotions Are Made* | Control signals as a low-dimensional affect state; "neutral" as absence of signal, not an emotion | [`control_signals/model.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/control_signals/model.py), [`update_signal_state.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/control_signals/update_signal_state.py), [`signal_dynamics.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/control_signals/signal_dynamics.py) |
| Cannon (1932) homeostasis | Signals decay toward per-signal setpoints; a single arbiter owns the state | [`setpoints.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/control_signals/setpoints.py), [`homeostasis.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/control_signals/homeostasis.py), [`arbiter.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/control_signals/arbiter.py) |
| Roseman (1996); Smith & Ellsworth (1985); Lazarus (1991) appraisal theory | Events are appraised along dimensions before they move signals | [`appraisal.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/control_signals/appraisal.py) |
| Gross (1998) emotion regulation; Aldao, Nolen-Hoeksema & Schweizer (2010) | Regulation strategies with bounded rate-of-change | [`regulation.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/control_signals/regulation.py) |
| Solomon & Corbit (1974) opponent process; Aston-Jones & Cohen (2005) phasic/tonic | Phasic bursts decay against tonic baselines | [`signal_dynamics.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/control_signals/signal_dynamics.py) |
| Brickman & Campbell (1971) hedonic treadmill | Baseline adaptation to sustained reward | [`signal_dynamics.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/control_signals/signal_dynamics.py) |

## Global workspace & conscious ignition

| Source | Mechanism in Orrin | Code |
|---|---|---|
| Baars (1988) Global Workspace Theory; Dehaene (2014) *Consciousness and the Brain* | One winner per cycle converges parallel processes into a single conscious content; ignition is all-or-none, and unconscious candidates are damped | [`cognition/global_workspace.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/cognition/global_workspace.py), [`loop/deliberate.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/loop/deliberate.py), [`loop/finalize.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/loop/finalize.py), [`think_utils/selection/boosts.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/think/think_utils/selection/boosts.py) |
| Top-down broadcast (the downward half of GWT) | The workspace winner writes back into substrate salience (decaying-only) | [`cognition/workspace_writeback.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/cognition/workspace_writeback.py) |

See [Workspace and Ignition](Workspace_and_Ignition) and
[Binding and Workspace Writeback](Binding_and_Workspace_Writeback) for the mechanism pages.

## Predictive processing & free energy

| Source | Mechanism in Orrin | Code |
|---|---|---|
| Friston (2010) free-energy principle / predictive processing | Predict internal state, score prediction error, treat large PE as a surprise signal | [`cognition/prediction.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/cognition/prediction.py), [`prediction_helpers.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/cognition/prediction_helpers.py), [`grounding/world_loop.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/cognition/grounding/world_loop.py) |
| Barrett & Simmons (2015) interoceptive prediction | Resource risk as interoceptive prediction error | [`cognition/resource_self_monitor.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/cognition/resource_self_monitor.py), [`cost_prediction.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/cognition/cost_prediction.py) |

## Causality

| Source | Mechanism in Orrin | Code |
|---|---|---|
| Pearl (2000) *Causality*; Pearl & Mackenzie (2018) Ladder of Causation; Granger (1969) | Causal edges score observation vs. intervention evidence (do(X) counts double); confounding checks per Pearl Ch. 3 | [`symbolic/causal_graph.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/symbolic/causal_graph.py) |
| Pearl's evidence levels applied to self-tests | Behavioural self-experiments logged as Level-1/Level-2 evidence | [`cognition/experimentation.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/cognition/experimentation.py) |

## Reinforcement learning & reward

| Source | Mechanism in Orrin | Code |
|---|---|---|
| Rescorla & Wagner (1972) | Prediction-error-scaled updates throughout (affect, confidence, causal weights) | [`cognition/prediction.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/cognition/prediction.py), [`grounding/grounded_concept.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/cognition/grounding/grounded_concept.py), [`symbolic/causal_graph.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/symbolic/causal_graph.py) |
| Pearce & Hall (1980) associability; Mackintosh (1975); Sutton (1992) IDBD | Adaptive per-action learning rates driven by unsigned prediction error | [`reward_signals/action_reward_ema.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/control_signals/reward_signals/action_reward_ema.py) |
| Schultz, Dayan & Montague (1997) TD reward prediction error; Sutton (1988) TD learning | Reward engine and PE→emotion coupling | [`reward_signals/reward_engine.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/control_signals/reward_signals/reward_engine.py), [`think/loop_helpers.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/think/loop_helpers.py) |
| Yu & Dayan (2005) uncertainty and learning | Learning-rate gain gating; volatile contexts learn faster | [`think/bandit/contextual_bandit.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/think/bandit/contextual_bandit.py) |
| Gershman (2018) directed vs. random exploration | Uncertainty-seeking exploration bonus in action scoring | [`selection/score_actions.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/think/think_utils/selection/score_actions.py) |
| Auer, Cesa-Bianchi & Fischer (2002) UCB1; Langford & Zhang (2007) epoch-greedy; Agrawal & Goyal (2012) Thompson sampling | Bandit machinery for function and depth selection | [`utils/bandit.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/utils/bandit.py), [`think/depth_bandit.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/think/depth_bandit.py) |
| Hebb (1949) | Post-cycle emotion→function reinforcement and spreading activation | [`runtime_coupling/adaptation.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/runtime_coupling/adaptation.py) |

## Intrinsic motivation & exploration

| Source | Mechanism in Orrin | Code |
|---|---|---|
| Oudeyer & Kaplan (2007); Gottlieb & Oudeyer (2018); Berlyne (1960) | Epistemic vs. diversive curiosity in intrinsic reward | [`reward_signals/reward_signals.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/control_signals/reward_signals/reward_signals.py), [`cognition/exploration_value.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/cognition/exploration_value.py) |
| Loewenstein (1994) information-gap theory | Curiosity peaks where a topic is partially known | [`cognition/intrinsic_generators.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/cognition/intrinsic_generators.py) |

## Memory

| Source | Mechanism in Orrin | Code |
|---|---|---|
| Ebbinghaus (1885) forgetting curve; Anderson & Schooler (1991) | Memory strength decay; rule forgetting | [`memory/strength.py`](https://github.com/ric-massey/orrin_v3/blob/main/memory/strength.py), [`symbolic/rule_forgetting.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/symbolic/rule_forgetting.py) |
| Baddeley & Hitch (1974) working memory | Central-executive gating; load narrows capacity | [`cog_memory/working_memory.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/cog_memory/working_memory.py) |
| Tulving (1972, 1983) episodic→semantic; Tulving (2002) autonoetic consciousness | Episode-to-knowledge consolidation; temporal self-location | [`cognition/knowledge_formation.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/cognition/knowledge_formation.py), [`knowledge_graph_extract.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/cognition/knowledge_graph_extract.py), [`temporal_state.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/cognition/temporal_state.py) |
| McGaugh (2000) consolidation; Levine & Pizarro (2004) emotion & memory | Emotion-weighted consolidation | [`control_signals/consolidation.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/control_signals/consolidation.py) |
| Diekelmann & Born (2010) sleep & memory; Tononi & Cirelli (2014) synaptic homeostasis (SHY) | Idle/sleep consolidation cycles enrich rather than just prune | [`idle_consolidation/consolidation_cycle.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/cognition/idle_consolidation/consolidation_cycle.py) |

## Symbolic reasoning & knowledge representation

| Source | Mechanism in Orrin | Code |
|---|---|---|
| Anderson (1983) ACT-R; Anderson (1982) procedural compilation; Schank (1982) case-based reasoning | Rule structure, synthesis, and compilation of specific episodes into general rules | [`symbolic/rule_engine.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/symbolic/rule_engine.py), [`rule_synthesis.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/symbolic/rule_synthesis.py) |
| Johnson-Laird (1983) mental models; Baader et al. (2003) description logic; Gärdenfors (2000) conceptual spaces | World-model inference: subsumption, model search, similarity as shared-feature overlap | [`symbolic/inference.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/symbolic/inference.py), [`cognition/world_model.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/cognition/world_model.py) |
| Bartlett (1932) schemas | Parent schemas inherit from abstracted children | [`symbolic/rule_abstraction.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/symbolic/rule_abstraction.py) |
| Mitchell et al. (1986) explanation-based learning | Breakthrough distillation in metacognition | [`cognition/metacog.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/cognition/metacog.py) |

## Attention, effort & cognitive control

| Source | Mechanism in Orrin | Code |
|---|---|---|
| Kahneman (1973) *Attention and Effort*; Kahneman (2011) System 1/2 | Attention as a limited resource; experiencing-self depletion | [`cognition/attention.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/cognition/attention.py), [`temporal_state.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/cognition/temporal_state.py) |
| Botvinick et al. (2001) conflict monitoring | Conflict-gated deliberation | [`think/think_module.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/think/think_module.py) |
| Shenhav, Botvinick & Cohen (2013) Expected Value of Control | Learned cost predictions become a depletion-scaled penalty on candidate actions | [`cognition/cost_prediction.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/cognition/cost_prediction.py) |
| Yerkes & Dodson (1908) inverted-U arousal curve | Energy orientation: reactive over-peak vs. proactive band | [`motivation/energy_orientation.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/motivation/energy_orientation.py) |

## Metacognition & calibration

| Source | Mechanism in Orrin | Code |
|---|---|---|
| Nelson & Narens (1990) metamemory; Fleming & Lau (2014) measuring metacognition; Brier (1950) probability scoring | Confidence calibrated against outcomes with a recency-weighted Brier score | [`cognition/calibration.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/cognition/calibration.py) |

## Behavioral adaptation & control theory

| Source | Mechanism in Orrin | Code |
|---|---|---|
| Carver & Scheier (1982) control-systems theory; Powers (1973) perceptual control theory; Bandura (1977) self-efficacy; Tolman (1932) latent learning | Pattern-specific corrective interventions: ruts trigger exploration, oscillation triggers commitment, goal avoidance triggers action | [`cognition/behavioral_adaptation.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/cognition/behavioral_adaptation.py) |
| Thompson & Spencer (1966) habituation | Repeated stimuli lose salience | [`cognition/habituation.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/cognition/habituation.py) |
| Nolen-Hoeksema (1991); Treynor, Gonzalez & Nolen-Hoeksema (2003) rumination/brooding | Detecting and breaking passive self-focused loops | [`cognition/rumination.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/cognition/rumination.py) |

## Social cognition

| Source | Mechanism in Orrin | Code |
|---|---|---|
| Friston-style generative-model theory of mind; Baron-Cohen; Feldman (synchrony); Buckner | Peer models commit to predictions, score PE, and blend confidence from accuracy + synchrony | [`cognition/theory_of_mind.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/cognition/theory_of_mind.py), [`theory_of_mind_infer.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/cognition/theory_of_mind_infer.py) |
| Hatfield, Cacioppo & Rapson (1993) emotional contagion | Peer affect leaks into Orrin's signals, bounded | [`cognition/contagion.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/cognition/contagion.py) |
| Heinrichs et al. (2003) social buffering | Speech as a social-penalty regulator | [`behavior/speech_gate.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/behavior/speech_gate.py) |

## Goodhart's law & specification gaming (quality standard)

| Source | Mechanism in Orrin | Code |
|---|---|---|
| Goodhart (1975); Strathern (1997); Manheim & Garrabrant (2018) | Why Orrin cannot edit his own quality bar | [`cognition/quality_standard/`](https://github.com/ric-massey/orrin_v3/blob/main/brain/cognition/quality_standard/__init__.py) |
| Amodei et al. (2016) *Concrete Problems in AI Safety*; Krakovna et al. (2020); Skalse et al. (2022); Everitt et al. (2021) reward tampering | Human-ratified loosening only; the standard evolves from demonstrated-good work | [`quality_standard/proposer.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/cognition/quality_standard/proposer.py) |

## Language

| Source | Mechanism in Orrin | Code |
|---|---|---|
| Keskar et al. (2019) CTRL repetition penalty | Sampling-time repetition control in the native LM | [`cognition/language/native_lm.py`](https://github.com/ric-massey/orrin_v3/blob/main/brain/cognition/language/native_lm.py) |

## Finding citations in the source

Most modules carry their references as a header comment block. To list them all:

```bash
grep -rn "([12][089][0-9][0-9])" --include="*.py" brain/ goals/ memory/ | grep -iE "et al|&|[A-Z][a-z]+ \("
```

## Caveats

- The design is interpretive; the wiki cites literature for context, not formal validation.
- Cognitive terms name engineering mechanisms (see
  [`CLAUDE.md`](https://github.com/ric-massey/orrin_v3/blob/main/CLAUDE.md) golden rule 4) — the
  citations document where a mechanism's *shape* came from, not a claim of equivalence.
