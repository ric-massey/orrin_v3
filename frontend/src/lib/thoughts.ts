import { TelemetryState } from "./types";

/**
 * The live "what is it doing right now" line — engineering vocabulary.
 *
 * Sibling to lib/lexicon.ts: that table translates the UI's static *chrome*
 * (panel titles, subtitles); this one derives the moving status line on the
 * Face — the single sentence that says what the runtime is doing this instant.
 *
 * The core loop pushes a raw `narrative` string (e.g. "Acting —
 * generate_intrinsic_goals") plus the active function name and pipeline stage.
 * That raw string is jargon, so we re-derive the line here, keyed by the
 * function actually running: the call signature + what it does.
 *
 * HARD RULE (shared with lexicon.ts): translate the chrome, never the mind.
 * This line is a UI-authored status label. The runtime's own selected content /
 * goal titles / speech are DATA and render verbatim.
 */

// ── Per-function thoughts ─────────────────────────────────────────────────────
// Keyed by the cognitive-function name the loop reports as `active_fn`.
export const THOUGHTS: Record<string, string> = {
  // Goals & agency
  generate_intrinsic_goals: "generate_intrinsic_goals() · surfacing self-set goals from drives",
  run_intrinsic_motivation: "run_intrinsic_motivation() · intrinsic-reward goal drive",
  pursue_committed_goal: "pursue_committed_goal() · advancing the active plan",
  assess_goal_progress: "assess_goal_progress() · scoring plan progress",
  adapt_subgoals: "adapt_subgoals() · surgical sub-plan revision",
  attend_goal: "attend_goal() · selecting the focus goal",
  redirect_goal_plan: "redirect_goal_plan() · re-planning around a block",
  abandon_goal: "abandon_goal() · retiring an unproductive goal",

  // Reflection & self-model
  reflection: "reflection() · re-evaluating the recent trace",
  narrative_update: "narrative_update() · revising the run-history narrative",
  update_latent_identity: "update_latent_identity() · identity-vector revision",
  propose_value_revision: "propose_value_revision() · proposing a value change",
  audit_reflective_claims: "audit_reflective_claims() · verifying self-claims",
  audit_map_territory: "audit_map_territory() · model-vs-world consistency check",
  review_failures: "review_failures() · post-mortem over failed attempts",
  reflect_on_cognition_rhythm: "reflect_on_cognition_rhythm() · meta-cadence review",

  // Control signals
  update_affect_state: "update_affect_state() · stepping the control-signal model",
  reflect_on_affect: "reflect_on_affect() · introspecting current signal state",
  reflect_on_emotion_model: "reflect_on_emotion_model() · reviewing the signal model",
  investigate_unexplained_emotions: "investigate_unexplained_emotions() · tracing signal anomalies",
  check_affect_drift: "check_affect_drift() · setpoint-drift detection",
  attempt_regulation: "attempt_regulation() · setpoint self-regulation",
  apply_affective_feedback: "apply_affective_feedback() · folding signals into control",
  affect_driven_mode_shift: "affect_driven_mode_shift() · signal-gated mode switch",

  // Memory
  detect_memory_contradictions: "detect_memory_contradictions() · consistency scan",
  repair_contradictions: "repair_contradictions() · resolving memory conflicts",
  run_forgetting_cycle: "run_forgetting_cycle() · salience-weighted decay",

  // Perception / environment
  look_around: "look_around() · sampling the local environment",
  look_outward: "look_outward() · external-source perception",
  survey_environment: "survey_environment() · environment sweep",
  check_user_presence: "check_user_presence() · presence probe",
  read_clipboard: "read_clipboard() · clipboard ingest",

  // Curiosity / experimentation
  run_active_experiment: "run_active_experiment() · executing an active test",
  run_symbolic_experiments: "run_symbolic_experiments() · symbolic trial batch",
  assess_innovation_outcomes: "assess_innovation_outcomes() · scoring novel attempts",
  run_embodied_observation: "run_embodied_observation() · host-coupled outcome capture",
  run_embodied_cycle: "run_embodied_cycle() · act-observe loop",

  // Symbolic / no-LLM reasoning
  symbolic_route: "symbolic_route() · rule-engine inference",
  run_symbolic_prediction_cycle: "run_symbolic_prediction_cycle() · symbolic forecast",
  run_rule_compression: "run_rule_compression() · rule-set compaction",
  run_symbolic_dream: "run_symbolic_dream() · offline symbolic recombination",

  // Self-improvement / self-code
  run_self_improvement: "run_self_improvement() · self-tuning pass",
  write_cognitive_function: "write_cognitive_function() · authoring a new function",
  write_tool: "write_tool() · authoring a new tool",
  delete_own_code: "delete_own_code() · pruning own code",
  search_own_files: "search_own_files() · introspecting own source",
  list_own_code: "list_own_code() · enumerating own modules",

  // Files / tools
  grep_files: "grep_files() · pattern search",
  search_files: "search_files() · file search",
  list_directory: "list_directory() · directory listing",

  // Expression / notes
  notify_user: "notify_user() · user notification",
  announce_to_dashboard: "announce_to_dashboard() · dashboard broadcast",
  leave_note: "leave_note() · persisting a note",
  save_note: "save_note() · note write",
  write_desktop_note: "write_desktop_note() · desktop note write",
  mark_private: "mark_private() · flagging interior content private",

  // Continuity / control
  thread_continue: "thread_continue() · resuming a thought thread",
  metacog_flush: "metacog_flush() · flushing the metacognition queue",
  update_stagnation_signal_escalation: "update_stagnation_signal_escalation() · stall escalation",
  run_benchmark: "run_benchmark() · self-acceptance checks",
};

// ── Pipeline-stage fallback ───────────────────────────────────────────────────
// When no specific function maps (or none is active yet), narrate the loop stage.
const STAGE: Record<string, string> = {
  perceive: "perceive · sampling inputs",
  reflect: "reflect · evaluating state",
  plan: "plan · action selection",
  act: "act · executing the chosen function",
};

/**
 * Resolve the live thought line for the given telemetry.
 * Priority: the running function (most specific) → the pipeline stage →
 * the raw backend narrative (last resort).
 */
export function thoughtFor(state: TelemetryState): string {
  const fn = state.activeFn;
  if (fn && THOUGHTS[fn]) return THOUGHTS[fn];

  const node = state.activeNode ?? "";
  if (STAGE[node]) return STAGE[node];

  // A function ran that we don't have a label for yet — show it cleanly
  // (the call form) rather than the jargon-y raw string.
  if (fn) return `${fn}()`;

  return state.narrative || "Idle";
}

/**
 * Translate a single function name (e.g. a recent-thought trail entry) to its
 * label. Unlike thoughtFor() this takes no pipeline stage — it's the thought
 * for *that* function alone.
 */
export function thoughtForFn(fn: string): string {
  if (THOUGHTS[fn]) return THOUGHTS[fn];
  return `${fn}()`;
}

/** Hook form: live thought line. */
export function useThought(state: TelemetryState): string {
  return thoughtFor(state);
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
