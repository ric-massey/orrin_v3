/**
 * The UI's authored chrome strings — engineering vocabulary, single language.
 *
 * One table holds every display string the UI authors, so they cannot drift.
 * (This used to carry a biological ↔ engineering toggle; the biological dialect
 * was removed — engineering is the only language now.)
 *
 * HARD RULE — translate the chrome, never the mind. Orrin's own output
 * (selected content, goal titles, log messages, memory summaries, speech) is
 * DATA and renders verbatim. Only labels the UI authors live here.
 */

export const LEX = {
  // ── Panel titles ──────────────────────────────────────────────────────────
  sphere_title: "Function-call graph",
  consciousness_title: "Attention arbitration",
  affect_title: "Control-signal state",
  metrics_title: "System Metrics",
  memory_title: "Store & op inspector",
  goals_title: "Goals",
  console_title: "Live Console",
  benchmarks_title: "Benchmarks",
  goalhealth_title: "Goal-closure metrics",
  innerweather_title: "Clock & state summary",
  symbolic_title: "Rule engine",
  predictions_title: "Calibration",
  drives_title: "Priority weights & budget",
  learning_title: "Reward statistics",
  tensions_title: "Conflict & retry state",
  health_title: "System health",
  self_title: "System self-descriptor",
  people_title: "Person models",
  dreams_title: "Idle consolidation",
  language_title: "Native language model",

  // ── Plain-language subtitles ──────────────────────────────────────────────
  sphere_sub: "registered functions; highlights are executing now",
  consciousness_sub: "highest-salience broadcast this cycle",
  affect_sub: "signal levels vs. their setpoints",
  metrics_sub: "signal history over time",
  memory_sub: "op ticker (sampled) + persistent store browser",
  goals_sub: "task tree + plan state",
  console_sub: "structured log stream",
  benchmarks_sub: "B1–B5 acceptance checks",
  goalhealth_sub: "closure rates; population should stay bounded",
  innerweather_sub: "internal clock skew + smoothed state",
  symbolic_sub: "no-LLM inference share + learned rules",
  predictions_sub: "forecast accuracy + Brier score",
  drives_sub: "priority weights + per-call cost model",
  learning_sub: "per-function reward EMAs + bandit state",
  tensions_sub: "open conflict flags + retry loops",
  health_sub: "failure counters + incident log",
  self_sub: "identity state + confidence revisions",
  people_sub: "interlocutor + internal-peer models",
  dreams_sub: "offline write-back + recombination job",
  language_sub: "from-scratch LM + phrase banks",

  // ── Attention panel sections ──────────────────────────────────────────────
  conscious_now: "Broadcast winner (this cycle)",
  executive_lane: "Background task runner",
  breakthroughs: "Interrupt requests (offered)",
  watchdog: "Stall detector",
  verdicts_label: "Dismissal recalibration",
  workspace_tagline: "priority-arbitrated broadcast bus",

  // ── Control-signal rings ──────────────────────────────────────────────────
  valence_label: "Hedonic score",
  valence_hint: "reward sign − ↔ +",
  arousal_label: "Activation",
  arousal_hint: "low ↔ high activation",
  homeostasis_label: "Setpoint proximity",
  homeostasis_hint: "far ↔ near setpoints",

  // ── KPI strip ─────────────────────────────────────────────────────────────
  kpi_stage: "Pipeline stage",
  kpi_cycle: "Cycle",
  kpi_stream: "Telemetry socket",
  kpi_longterm: "Persistent store records",
  kpi_memops: "Store ops (this session)",

  // ── Misc chrome ───────────────────────────────────────────────────────────
  sphere_empty: "Loading the function catalog…",
  exec_idle: "Idle — no task step ran this tick.",

  // ── Named rooms (navigation) ──────────────────────────────────────────────
  nav_watch: "Watch",
  nav_face: "Face",
  nav_cognition: "Cognition",
  nav_life: "Resource Manager",
  nav_memory: "Memory",
  nav_timeline: "Activity log",
  nav_learning: "Behavior changes",
  nav_brain: "Runtime",
  nav_settings: "Settings",

  // ── Cognition view ────────────────────────────────────────────────────────
  cog_focus: "Active function (this cycle)",
  cog_goal: "Active goal + step",
  cog_competing: "Workspace candidates (ranked)",
  cog_winner: "Broadcast winner",
  cog_peers: "Active peer models",
  cog_drives: "Priority weights",
  cog_symbolic: "Rules firing",
  cog_private: "Protected interior (not exposed by the API).",

  // ── Resource Manager ──────────────────────────────────────────────────────
  life_cpu: "CPU available",
  life_mem: "RAM available",
  life_disk: "Disk free (data dir)",
  life_rate: "Cycles/min",
  life_age: "Uptime since start",
  life_remaining: "Est. runtime remaining",
  life_interests: "Top active goals",
} as const;

export type LexId = keyof typeof LEX;

/** Resolve an id to its engineering string (for non-React code). */
export function lex(id: LexId): string {
  return LEX[id];
}

/**
 * Hook: returns a translator `t`. (`tip` is retained as an inert no-op so the
 * panel call sites that still pass `title={tip(id)}` keep compiling; the
 * biological-counterpart glossary it used to provide is gone.)
 */
export function useLexicon(): {
  t: (id: LexId) => string;
  tip: (id: LexId) => string | undefined;
} {
  return {
    t: (id: LexId) => LEX[id],
    tip: () => undefined,
  };
}
