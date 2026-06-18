// Shared catalogue of chartable signals + their *meaning* (UI_FIXES Fix 6):
// a deep explanation, definitions of the terms involved, how the value is
// actually measured, and a pointer to the real source code that computes it.
// Extracted from MetricsStrip so AffectRings (and future panels) reuse the
// same definitions instead of duplicating copy.
//
// UNIT: every value is shown as a 0-100 "level" - normalized intensity. 0 =
// none, 100 = full. For bipolar signals (Valence, Arousal) 50 = neutral.

export type SrcRef = { file: string; start: number; end: number; label: string };
export type PerspectiveLayer = "dev-only" | "agent-accessible" | "in-attention";
export type MetricDef = {
  key: string;
  label: string;
  color: string;
  desc: string;
  lo: string;
  hi: string;
  bipolar?: boolean;
  long: string;
  terms?: { t: string; d: string }[];
  measure: string;
  perspective: PerspectiveLayer;
  src?: SrcRef;
};

export const METRICS: MetricDef[] = [
  {
    key: "valence_raw", label: "Raw valence", color: "hsl(348 83% 55%)", bipolar: true,
    desc: "Uncompressed pleasant-unpleasant signal.", lo: "unpleasant", hi: "pleasant",
    perspective: "dev-only",
    long: "The direct -1 to +1 valence emitted by the affect system, without the Face's centered 0 to 1 presentation mapping.",
    measure: "Direct affect_state.valence telemetry; no centering or compression.",
    src: { file: "brain/ORRIN_loop.py", start: 194, end: 250, label: "_emit_affect" },
  },
  {
    key: "impasse_raw", label: "Raw impasse", color: "hsl(0 84% 50%)",
    desc: "Direct unresolved-goal distress signal.", lo: "clear", hi: "blocked",
    perspective: "agent-accessible",
    long: "The direct impasse signal, shown separately from aggregate distress so a blocked goal cannot be hidden by normalization.",
    measure: "Direct core_signals.impasse_signal telemetry, clamped only to 0 to 1.",
    src: { file: "brain/ORRIN_loop.py", start: 194, end: 250, label: "_emit_affect" },
  },
  {
    key: "valence", label: "Valence", color: "hsl(217 91% 60%)", bipolar: true,
    desc: "His overall pleasant–unpleasant tone.", lo: "unpleasant", hi: "pleasant",
    perspective: "agent-accessible",
    long: "Valence is the pleasant↔unpleasant axis of core affect (Russell's circumplex). It's not one feeling — it's the net hedonic sign of everything he's feeling at once.",
    terms: [
      { t: "Core affect", d: "The always-on background feeling, summarized on two axes: valence (pleasant↔unpleasant) and arousal (calm↔activated)." },
      { t: "Hedonic sign", d: "Whether the blend of active signals leans good (+) or bad (−)." },
    ],
    measure: "Intensity-weighted average of every active affect signal × its valence coefficient (positive_valence +0.9, wonder +0.55 … impasse −0.6, conflict −0.75), clamped to −1…+1, then mapped so 50 = neutral.",
    src: { file: "brain/affect/affect_dynamics.py", start: 157, end: 242, label: "compute_valence_activation_level + _VALENCE table" },
  },
  {
    key: "arousal", label: "Arousal", color: "hsl(262 83% 62%)", bipolar: true,
    desc: "How activated vs. calm his state is.", lo: "calm", hi: "activated",
    perspective: "agent-accessible",
    long: "Arousal is the activation↔deactivation axis of core affect — how energized/alert his whole system is, independent of whether it feels good or bad. High arousal + positive = excited; high arousal + negative = stressed.",
    terms: [
      { t: "Activation", d: "Mobilization/alertness — body and mind keyed up (threat, excitement, drive)." },
      { t: "Deactivation", d: "Low-energy, settled states (reflection, calm, melancholy)." },
    ],
    measure: "Intensity-weighted average of active signals × their activation coefficient (conflict +0.9, threat +0.8, positive +0.65 … reflective −0.1, melancholy −0.35), clamped to −1…+1.",
    src: { file: "brain/affect/affect_dynamics.py", start: 181, end: 242, label: "_ACTIVATION_LEVEL table + compute" },
  },
  {
    key: "homeostasis", label: "Homeostasis", color: "hsl(142 71% 45%)",
    desc: "How close his whole affect sits to rest.", lo: "agitated", hi: "settled",
    perspective: "agent-accessible",
    long: "A single 'is he settled?' reading: how far his entire affect vector currently sits from its resting setpoints. 100 = everything near its baseline (at peace); it dips when signals deviate (agitation, saturation) and recovers as they decay back.",
    terms: [
      { t: "Setpoint", d: "The resting value each signal drifts back toward when nothing pushes it (e.g. impasse rests at ~0, motivation at ~0.5)." },
      { t: "Deviation", d: "Distance of a signal from its setpoint right now; summed across the vector." },
    ],
    measure: "1 − (mean |signal − setpoint| over all core signals) × 1.6, clamped to 0–1. Computed when affect is pushed to the UI.",
    src: { file: "brain/ORRIN_loop.py", start: 178, end: 216, label: "_emit_affect — homeostasis + metric push" },
  },
  {
    key: "energy", label: "Energy", color: "hsl(38 92% 50%)",
    desc: "Capacity vs. fatigue (1 − resource deficit).", lo: "depleted", hi: "fresh",
    perspective: "agent-accessible",
    long: "His available cognitive capacity right now — the opposite of fatigue. Sustained hard cognition (recursion, long goal pushes, heavy reflection) accumulates a 'resource deficit' (ego-depletion; Baumeister 1998); rest and easy cycles let it recover. Energy = 1 − that deficit.",
    terms: [
      { t: "Capacity", d: "Headroom for effortful, deliberate work. High capacity → he can plan, reason, persist. Low → he defaults to easy/automatic actions." },
      { t: "Fatigue (resource_deficit)", d: "An accumulating drain. It ticks up a little every cycle (+0.002) and faster when he over-uses effortful functions; it decays toward a 0.15 baseline (faster, ×0.06, once severely depleted >0.75 — active recovery)." },
    ],
    measure: "energy = 1 − resource_deficit. resource_deficit accumulates per cycle and decays toward an allostatic setpoint; recovery accelerates when exhausted.",
    src: { file: "brain/affect/update_affect_state.py", start: 629, end: 640, label: "resource_deficit accumulation + recovery" },
  },
  {
    key: "fatigue", label: "Fatigue", color: "hsl(18 58% 50%)",
    desc: "The accumulating resource deficit he's carrying.", lo: "rested", hi: "depleted",
    perspective: "agent-accessible",
    long: "The raw drain itself — the exact mirror of Energy, charted directly so you can watch depletion *climb*. Every cycle adds a little load; effortful, deliberate cognition (recursion, long goal pushes, heavy reflection) adds more (ego-depletion; Baumeister 1998). Rather than relaxing back to a fixed baseline, it now settles toward an *allostatic setpoint* — a target the system moves ahead of need (Sterling 2012): it tolerates more deficit under user/critical demand and forces recovery when allostatic load has built up.",
    terms: [
      { t: "Resource deficit", d: "The accumulating drain. Ticks up ~+0.002 every cycle, faster under effortful function use; high values bias him toward easy/automatic actions over deliberate ones." },
      { t: "Allostatic setpoint (τ)", d: "The deficit target he relaxes toward — not fixed. ~0.12 idle, 0.15 neutral, 0.30 under user demand, 0.40 critical: he runs hotter when it matters, then forces recovery as load accrues (predictive regulation, not reactive)." },
      { t: "EVC pacing", d: "Expected Value of Control (Shenhav 2013): predicted effort cost is weighed before spending it, so he paces hard cognition instead of over-drawing — though never gating speaking/responding (corrigibility)." },
    ],
    measure: "fatigue = resource_deficit. Accumulates per cycle (+~0.002, more under effortful use), decays toward a context-dependent allostatic setpoint τ; recovery accelerates (×0.06) once severely depleted (>0.75) and during dream rest.",
    src: { file: "brain/cognition/interoception.py", start: 229, end: 255, label: "allostatic_setpoint — predictive deficit target (τ + load + smoothing)" },
  },
  {
    key: "motivation", label: "Motivation", color: "hsl(330 80% 62%)",
    desc: "Drive to act on and pursue goals.", lo: "listless", hi: "driven",
    perspective: "agent-accessible",
    long: "His appetitive drive — how strongly he wants to act, pursue, and finish. It's lifted by reward (completing things, value-aligned actions) and a flow bonus for sustained action, and decays toward a 0.5 baseline so it doesn't pin at the ceiling.",
    terms: [
      { t: "Appetitive drive", d: "The 'go' signal — wanting to move toward goals (vs. avoid)." },
      { t: "Flow bonus", d: "Repeated action-oriented choices lift motivation/confidence a little (being in flow is itself rewarding)." },
    ],
    measure: "A core signal: raised by reward writes + flow, pulled back toward its 0.50 setpoint each cycle (per-call homeostatic decay).",
    src: { file: "brain/affect/setpoints.py", start: 27, end: 101, label: "setpoints + CORE_BASELINES (resting values)" },
  },
  {
    key: "confidence", label: "Confidence", color: "hsl(190 85% 50%)",
    desc: "Self-trust in his current footing.", lo: "unsure", hi: "assured",
    perspective: "agent-accessible",
    long: "How much he trusts his current understanding/plan. It rises with successful, well-predicted actions and falls on surprise (prediction error) and contradiction. Confidence feeds regulation (high confidence → stay the course; low → reflect/verify).",
    terms: [
      { t: "Prediction error", d: "Gap between what he expected and what happened. Big errors cut confidence (and raise curiosity)." },
      { t: "Cross-inhibition", d: "When threat is high it actively pulls confidence down, and vice-versa — they can't both be maxed." },
    ],
    measure: "A core signal: lifted by confirmed predictions/flow, cut by surprise; decays toward a 0.45 setpoint; antagonistic with threat/uncertainty.",
    src: { file: "brain/affect/homeostasis.py", start: 30, end: 95, label: "ANTAGONISTS + cross-inhibition" },
  },
  {
    key: "curiosity", label: "Curiosity", color: "hsl(280 70% 66%)",
    desc: "Exploration drive — the pull toward the new.", lo: "incurious", hi: "curious",
    perspective: "agent-accessible",
    long: "His exploration drive: the pull toward novel/uncertain things. It's the same signal that, when high, makes him spawn investigation sub-goals on his own. Driven by novelty (how unlike anything known), uncertainty (poor coverage), and prediction error.",
    terms: [
      { t: "Novelty", d: "How unlike anything in memory a thing is (inverse structural-analogy score)." },
      { t: "Information gap (uncertainty)", d: "How poorly his rules/knowledge cover a topic — Loewenstein's curiosity sits in that gap." },
    ],
    measure: "exploration_drive core signal; the autonomous explore-score = 0.45·novelty + 0.35·uncertainty + 0.20·prediction_error.",
    src: { file: "brain/symbolic/intrinsic_motivation.py", start: 42, end: 115, label: "novelty / uncertainty / exploration_drive_score" },
  },
  {
    key: "distress", label: "Distress", color: "hsl(0 72% 56%)",
    desc: "Aggregate negative load — frustration, threat.", lo: "at ease", hi: "distressed",
    perspective: "agent-accessible",
    long: "A single 'how much is he struggling' reading — the summed weight of his negative signals (impasse/frustration, threat, conflict, risk, rejection). High distress shortens his regulation cadence (he works harder to calm down) and biases him toward regulation functions.",
    terms: [
      { t: "Negative load", d: "Weighted sum of the active distress signals, so one big or several small all register." },
      { t: "Regulation", d: "When load is high he picks calming strategies (grounding, reappraisal) more often." },
    ],
    measure: "negative_load(affect) — weighted sum of impasse/threat/conflict/risk/etc. — normalized to 0–1 for display.",
    src: { file: "brain/affect/observers.py", start: 44, end: 95, label: "negative_load" },
  },
  {
    key: "stability", label: "Stability", color: "hsl(160 60% 46%)",
    desc: "How settled vs. volatile his emotions are.", lo: "volatile", hi: "steady",
    perspective: "agent-accessible",
    long: "How steady vs. churning his emotions are right now. High when affect is calm and consistent; it drops when negatives dominate or he ping-pongs between states. Stability gates regulation success (it's easier to calm down when you're already fairly steady).",
    terms: [
      { t: "Volatility", d: "Rapid swings / contradictory states — destabilizing (e.g. A↔B↔A cognitive indecision)." },
      { t: "Affect velocity", d: "How much the whole vector moved this cycle; capped so one chaotic cycle can't lurch everything." },
    ],
    measure: "1 − avg_negative × 2 + avg_positive × 0.25, clamped to 0–1; further cut by indecision/ping-pong patterns.",
    src: { file: "brain/affect/update_affect_state.py", start: 525, end: 542, label: "new_stability computation" },
  },
  {
    key: "learning", label: "Learning", color: "hsl(48 95% 55%)",
    desc: "Share of his recent predictions that came true.", lo: "missing", hi: "on target",
    perspective: "dev-only",
    long: "Whether his model of the world is actually getting things right: the fraction of his recently-resolved predictions that came true. This is the live readout of the agency-based learning loop — he predicts effects of his actions, checks them, and the confirmed ones crystallize into rules.",
    terms: [
      { t: "Prediction", d: "A falsifiable expectation he commits to (e.g. 'after pursue_goal, impasse falls')." },
      { t: "Resolved", d: "A prediction that's been checked against what actually happened (correct / not)." },
    ],
    measure: "hits / resolved over his last ~40 predictions, refreshed every few seconds.",
    src: { file: "brain/ORRIN_loop.py", start: 219, end: 242, label: "_learning_pulse" },
  },
];

/** Look up a metric definition by its telemetry key (e.g. "homeostasis"). */
export function metricDef(key: string): MetricDef | undefined {
  return METRICS.find((m) => m.key === key);
}
