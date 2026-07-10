import { TelemetryState } from "./types";

/**
 * The live "what is it doing right now" line — two registers, one table.
 *
 * Sibling to lib/lexicon.ts: that table translates the UI's static *chrome*
 * (panel titles, subtitles); this one derives the moving status line — the
 * single sentence that says what the runtime is doing this instant.
 *
 * Each entry carries both registers (Companion & Presence plan §2 C4):
 * - `fn`    — engineering voice, "call signature · clinical gloss". Watch, Face
 *             and every workshop room render this. Unchanged behavior.
 * - `plain` — companion voice, a fresh rewrite (NOT a mechanical strip of the
 *             gloss). Only companion surfaces (/orrin) render it; deep rooms
 *             never see it. This is deliberately not a global toggle that
 *             re-skins the Brain room — that's the deleted-dialect mistake the
 *             lexicon comment warns about.
 *
 * HARD RULE (shared with lexicon.ts): translate the chrome, never the mind.
 * This line is a UI-authored status label. The runtime's own selected content /
 * goal titles / speech are DATA and render verbatim.
 */

export interface Thought {
  /** Engineering register: "fn() · clinical gloss". */
  fn: string;
  /** Companion register: plain human phrasing of the same act. */
  plain: string;
}

// ── Per-function thoughts ─────────────────────────────────────────────────────
// Keyed by the cognitive-function name the loop reports as `active_fn`.
export const THOUGHTS: Record<string, Thought> = {
  // Goals & agency
  generate_intrinsic_goals: {
    fn: "generate_intrinsic_goals() · surfacing self-set goals from drives",
    plain: "deciding what he wants next",
  },
  run_intrinsic_motivation: {
    fn: "run_intrinsic_motivation() · intrinsic-reward goal drive",
    plain: "following his curiosity",
  },
  pursue_committed_goal: {
    fn: "pursue_committed_goal() · advancing the active plan",
    plain: "working on what he set out to do",
  },
  assess_goal_progress: {
    fn: "assess_goal_progress() · scoring plan progress",
    plain: "checking how it's going",
  },
  adapt_subgoals: {
    fn: "adapt_subgoals() · surgical sub-plan revision",
    plain: "adjusting the plan as he goes",
  },
  attend_goal: {
    fn: "attend_goal() · selecting the focus goal",
    plain: "choosing what to focus on",
  },
  redirect_goal_plan: {
    fn: "redirect_goal_plan() · re-planning around a block",
    plain: "finding a way around a block",
  },
  abandon_goal: {
    fn: "abandon_goal() · retiring an unproductive goal",
    plain: "letting go of something that isn't working",
  },

  // Reflection & self-model
  reflection: {
    fn: "reflection() · re-evaluating the recent trace",
    plain: "thinking over what just happened",
  },
  narrative_update: {
    fn: "narrative_update() · revising the run-history narrative",
    plain: "updating the story of his day",
  },
  update_latent_identity: {
    fn: "update_latent_identity() · identity-vector revision",
    plain: "reconsidering who he is",
  },
  propose_value_revision: {
    fn: "propose_value_revision() · proposing a value change",
    plain: "questioning what matters to him",
  },
  audit_reflective_claims: {
    fn: "audit_reflective_claims() · verifying self-claims",
    plain: "double-checking what he believes about himself",
  },
  audit_map_territory: {
    fn: "audit_map_territory() · model-vs-world consistency check",
    plain: "checking his picture of the world against the world",
  },
  review_failures: {
    fn: "review_failures() · post-mortem over failed attempts",
    plain: "learning from what went wrong",
  },
  reflect_on_cognition_rhythm: {
    fn: "reflect_on_cognition_rhythm() · meta-cadence review",
    plain: "noticing the rhythm of his own thinking",
  },

  // Control signals
  update_signal_state: {
    fn: "update_signal_state() · stepping the control-signal model",
    plain: "feeling out how he's doing",
  },
  reflect_on_affect: {
    fn: "reflect_on_affect() · introspecting current signal state",
    plain: "noticing how he feels",
  },
  reflect_on_emotion_model: {
    fn: "reflect_on_emotion_model() · reviewing the signal model",
    plain: "thinking about his own feelings",
  },
  investigate_unexplained_emotions: {
    fn: "investigate_unexplained_emotions() · tracing signal anomalies",
    plain: "wondering why he feels this way",
  },
  check_affect_drift: {
    fn: "check_affect_drift() · setpoint-drift detection",
    plain: "noticing a slow shift in his mood",
  },
  attempt_regulation: {
    fn: "attempt_regulation() · setpoint self-regulation",
    plain: "settling himself down",
  },
  apply_signal_feedback: {
    fn: "apply_signal_feedback() · folding signals into control",
    plain: "letting how he feels guide him",
  },
  signal_driven_mode_shift: {
    fn: "signal_driven_mode_shift() · signal-gated mode switch",
    plain: "shifting gears",
  },

  // Memory
  detect_memory_contradictions: {
    fn: "detect_memory_contradictions() · consistency scan",
    plain: "noticing memories that don't line up",
  },
  repair_contradictions: {
    fn: "repair_contradictions() · resolving memory conflicts",
    plain: "straightening out his memories",
  },
  run_forgetting_cycle: {
    fn: "run_forgetting_cycle() · salience-weighted decay",
    plain: "letting unimportant things fade",
  },

  // Perception / environment
  look_around: {
    fn: "look_around() · sampling the local environment",
    plain: "looking around",
  },
  look_outward: {
    fn: "look_outward() · external-source perception",
    plain: "looking out at the wider world",
  },
  survey_environment: {
    fn: "survey_environment() · environment sweep",
    plain: "taking stock of his surroundings",
  },
  check_user_presence: {
    fn: "check_user_presence() · presence probe",
    plain: "checking if you're there",
  },
  read_clipboard: {
    fn: "read_clipboard() · clipboard ingest",
    plain: "glancing at the clipboard",
  },

  // Curiosity / experimentation
  run_active_experiment: {
    fn: "run_active_experiment() · executing an active test",
    plain: "trying something to see what happens",
  },
  run_symbolic_experiments: {
    fn: "run_symbolic_experiments() · symbolic trial batch",
    plain: "playing out what-ifs",
  },
  assess_innovation_outcomes: {
    fn: "assess_innovation_outcomes() · scoring novel attempts",
    plain: "judging how his experiments went",
  },
  run_embodied_observation: {
    fn: "run_embodied_observation() · host-coupled outcome capture",
    plain: "watching what his actions changed",
  },
  run_embodied_cycle: {
    fn: "run_embodied_cycle() · act-observe loop",
    plain: "acting, then watching what happens",
  },

  // Symbolic / no-LLM reasoning
  symbolic_route: {
    fn: "symbolic_route() · rule-engine inference",
    plain: "reasoning it through",
  },
  run_symbolic_prediction_cycle: {
    fn: "run_symbolic_prediction_cycle() · symbolic forecast",
    plain: "predicting what comes next",
  },
  run_rule_compression: {
    fn: "run_rule_compression() · rule-set compaction",
    plain: "tidying up what he knows",
  },
  run_symbolic_consolidation: {
    fn: "run_symbolic_consolidation() · offline symbolic recombination",
    plain: "connecting things he's learned",
  },

  // Self-improvement / self-code
  run_self_improvement: {
    fn: "run_self_improvement() · self-tuning pass",
    plain: "working on himself",
  },
  write_cognitive_function: {
    fn: "write_cognitive_function() · authoring a new function",
    plain: "teaching himself a new skill",
  },
  write_tool: {
    fn: "write_tool() · authoring a new tool",
    plain: "building himself a new tool",
  },
  delete_own_code: {
    fn: "delete_own_code() · pruning own code",
    plain: "pruning a part of himself he's outgrown",
  },
  search_own_files: {
    fn: "search_own_files() · introspecting own source",
    plain: "looking inward at his own code",
  },
  list_own_code: {
    fn: "list_own_code() · enumerating own modules",
    plain: "taking inventory of himself",
  },

  // Files / tools
  grep_files: {
    fn: "grep_files() · pattern search",
    plain: "searching through files",
  },
  search_files: {
    fn: "search_files() · file search",
    plain: "looking for a file",
  },
  list_directory: {
    fn: "list_directory() · directory listing",
    plain: "seeing what's in a folder",
  },

  // Expression / notes
  notify_user: {
    fn: "notify_user() · user notification",
    plain: "getting your attention",
  },
  announce_to_dashboard: {
    fn: "announce_to_dashboard() · dashboard broadcast",
    plain: "posting an update",
  },
  leave_note: {
    fn: "leave_note() · persisting a note",
    plain: "writing something down",
  },
  save_note: {
    fn: "save_note() · note write",
    plain: "saving a note",
  },
  write_desktop_note: {
    fn: "write_desktop_note() · desktop note write",
    plain: "leaving a note for you",
  },
  mark_private: {
    fn: "mark_private() · flagging interior content private",
    plain: "keeping a thought to himself",
  },

  // Continuity / control
  thread_continue: {
    fn: "thread_continue() · resuming a thought thread",
    plain: "picking up where he left off",
  },
  metacog_flush: {
    fn: "metacog_flush() · flushing the metacognition queue",
    plain: "clearing his head",
  },
  update_stagnation_signal_escalation: {
    fn: "update_stagnation_signal_escalation() · stall escalation",
    plain: "noticing he's stuck",
  },
  run_benchmark: {
    fn: "run_benchmark() · self-acceptance checks",
    plain: "testing himself",
  },
};

// ── Pipeline-stage fallback ───────────────────────────────────────────────────
// When no specific function maps (or none is active yet), narrate the loop stage.
const STAGE: Record<string, Thought> = {
  perceive: { fn: "perceive · sampling inputs", plain: "taking in what's around him" },
  reflect: { fn: "reflect · evaluating state", plain: "thinking it over" },
  plan: { fn: "plan · action selection", plain: "deciding what to do next" },
  act: { fn: "act · executing the chosen function", plain: "doing it" },
};

/**
 * Resolve the live thought line for the given telemetry (engineering register).
 * Priority: the running function (most specific) → the pipeline stage →
 * the raw backend narrative (last resort).
 */
export function thoughtFor(state: TelemetryState): string {
  const fn = state.activeFn;
  if (fn && THOUGHTS[fn]) return THOUGHTS[fn].fn;

  const node = state.activeNode ?? "";
  if (STAGE[node]) return STAGE[node].fn;

  // A function ran that we don't have a label for yet — show it cleanly
  // (the call form) rather than the jargon-y raw string.
  if (fn) return `${fn}()`;

  return state.narrative || "Idle";
}

/**
 * Translate a single function name (e.g. a recent-thought trail entry) to its
 * engineering label. Unlike thoughtFor() this takes no pipeline stage — it's
 * the thought for *that* function alone.
 */
export function thoughtForFn(fn: string): string {
  if (THOUGHTS[fn]) return THOUGHTS[fn].fn;
  return `${fn}()`;
}

/** Companion-register thought line (C4). Only companion surfaces render this. */
export function plainThoughtFor(state: TelemetryState): string {
  const fn = state.activeFn;
  if (fn && THOUGHTS[fn]) return THOUGHTS[fn].plain;

  const node = state.activeNode ?? "";
  if (STAGE[node]) return STAGE[node].plain;

  return "thinking";
}

/** Companion-register label for a single function name. */
export function plainThoughtForFn(fn: string): string {
  if (THOUGHTS[fn]) return THOUGHTS[fn].plain;
  return "thinking";
}

/** Hook form: live thought line (engineering register). */
export function useThought(state: TelemetryState): string {
  return thoughtFor(state);
}

/** Hook form: live thought line (companion register). */
export function usePlainThought(state: TelemetryState): string {
  return plainThoughtFor(state);
}

// The small "doing" badge under the thought line — the loop stage, one word.
const STAGE_BADGE: Record<string, string> = {
  perceive: "perceive",
  reflect: "reflect",
  plan: "plan",
  act: "act",
};

/** Hook form of the pipeline-stage label (the small "doing" badge). */
export function useStageLabel(node: string | null): string {
  return STAGE_BADGE[node ?? ""] ?? "idle";
}
