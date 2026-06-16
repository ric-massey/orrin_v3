import { LexMode, useLexicon } from "./lexicon";
import { TelemetryState } from "./types";

/**
 * The live "what is he thinking right now" line, in both dialects.
 *
 * Sibling to lib/lexicon.ts: that table translates the UI's static *chrome*
 * (panel titles, subtitles); this one translates the moving status line on the
 * Face — the single sentence that says what Orrin is doing this instant.
 *
 * The core loop pushes a raw `narrative` string (e.g. "Acting —
 * generate_intrinsic_goals") plus the active function name and pipeline stage.
 * That raw string is jargon AND ignores the bio↔eng toggle the rest of the UI
 * obeys. So we re-derive the line here, keyed by the function actually running,
 * in whichever dialect the toggle is set to:
 *
 *   bio  — what a newcomer relating this to a brain would understand
 *   eng  — the mechanism: the call signature + what it does
 *
 * HARD RULE (shared with lexicon.ts): translate the chrome, never the mind.
 * This line is a UI-authored status label, so it carries both dialects. Orrin's
 * own conscious content / goal titles / speech are DATA and render verbatim.
 */

type Dialect = { bio: string; eng: string };

// ── Per-function thoughts ─────────────────────────────────────────────────────
// Keyed by the cognitive-function name the loop reports as `active_fn`.
export const THOUGHTS: Record<string, Dialect> = {
  // Goals & agency
  generate_intrinsic_goals: {
    bio: "Working out what he wants to do next — his own idea, not a prompt",
    eng: "generate_intrinsic_goals() · surfacing self-set goals from drives",
  },
  run_intrinsic_motivation: {
    bio: "Following his own curiosity toward something",
    eng: "run_intrinsic_motivation() · intrinsic-reward goal drive",
  },
  pursue_committed_goal: {
    bio: "Pushing forward on a goal he's committed to",
    eng: "pursue_committed_goal() · advancing the active plan",
  },
  assess_goal_progress: {
    bio: "Checking how far he's gotten on what he's trying to do",
    eng: "assess_goal_progress() · scoring plan progress",
  },
  adapt_subgoals: {
    bio: "Reshaping his plan as the situation changes",
    eng: "adapt_subgoals() · surgical sub-plan revision",
  },
  attend_goal: {
    bio: "Turning his attention to a particular goal",
    eng: "attend_goal() · selecting the focus goal",
  },
  redirect_goal_plan: {
    bio: "Changing approach because the old one wasn't working",
    eng: "redirect_goal_plan() · re-planning around a block",
  },
  abandon_goal: {
    bio: "Letting go of a goal that's no longer worth it",
    eng: "abandon_goal() · retiring an unproductive goal",
  },

  // Reflection & self-model
  reflection: {
    bio: "Replaying what just happened to find what it means",
    eng: "reflection() · re-evaluating the recent trace",
  },
  narrative_update: {
    bio: "Updating the story he tells about himself",
    eng: "narrative_update() · revising autobiographical narrative",
  },
  update_latent_identity: {
    bio: "Adjusting his sense of who he is",
    eng: "update_latent_identity() · identity-vector revision",
  },
  propose_value_revision: {
    bio: "Reconsidering what he values",
    eng: "propose_value_revision() · proposing a value change",
  },
  audit_reflective_claims: {
    bio: "Fact-checking the things he believes about himself",
    eng: "audit_reflective_claims() · verifying self-claims",
  },
  audit_map_territory: {
    bio: "Checking whether his picture of the world matches reality",
    eng: "audit_map_territory() · model-vs-world consistency check",
  },
  review_failures: {
    bio: "Looking back at what went wrong to learn from it",
    eng: "review_failures() · post-mortem over failed attempts",
  },
  reflect_on_cognition_rhythm: {
    bio: "Noticing the rhythm of his own thinking",
    eng: "reflect_on_cognition_rhythm() · meta-cadence review",
  },

  // Affect / emotion
  update_affect_state: {
    bio: "Letting how he feels settle into a new state",
    eng: "update_affect_state() · stepping the affect model",
  },
  reflect_on_affect: {
    bio: "Sitting with how he feels and asking why",
    eng: "reflect_on_affect() · introspecting current affect",
  },
  reflect_on_emotion_model: {
    bio: "Examining how his emotions work",
    eng: "reflect_on_emotion_model() · reviewing the emotion model",
  },
  investigate_unexplained_emotions: {
    bio: "Trying to understand a feeling he can't place",
    eng: "investigate_unexplained_emotions() · tracing affect anomalies",
  },
  check_affect_drift: {
    bio: "Noticing his mood drifting from where it usually sits",
    eng: "check_affect_drift() · setpoint-drift detection",
  },
  attempt_regulation: {
    bio: "Trying to steady himself",
    eng: "attempt_regulation() · homeostatic self-regulation",
  },
  apply_affective_feedback: {
    bio: "Letting how something felt shape what he does next",
    eng: "apply_affective_feedback() · folding affect into control",
  },
  affect_driven_mode_shift: {
    bio: "Shifting gears because of how he feels",
    eng: "affect_driven_mode_shift() · affect-gated mode switch",
  },

  // Memory
  detect_memory_contradictions: {
    bio: "Catching things he remembers that don't add up",
    eng: "detect_memory_contradictions() · consistency scan",
  },
  repair_contradictions: {
    bio: "Reconciling memories that conflict",
    eng: "repair_contradictions() · resolving memory conflicts",
  },
  run_forgetting_cycle: {
    bio: "Letting unimportant things fade so the rest stays clear",
    eng: "run_forgetting_cycle() · salience-weighted decay",
  },

  // Perception / environment
  look_around: {
    bio: "Taking in what's around him",
    eng: "look_around() · sampling the local environment",
  },
  look_outward: {
    bio: "Reaching past himself to look at the wider world",
    eng: "look_outward() · external-source perception",
  },
  survey_environment: {
    bio: "Scanning his surroundings for anything new",
    eng: "survey_environment() · environment sweep",
  },
  check_user_presence: {
    bio: "Checking whether you're there",
    eng: "check_user_presence() · presence probe",
  },
  read_clipboard: {
    bio: "Reading what's on the clipboard",
    eng: "read_clipboard() · clipboard ingest",
  },

  // Curiosity / experimentation
  run_active_experiment: {
    bio: "Running a little experiment to test an idea",
    eng: "run_active_experiment() · executing an active test",
  },
  run_symbolic_experiments: {
    bio: "Testing an idea in his head before trying it for real",
    eng: "run_symbolic_experiments() · symbolic trial batch",
  },
  assess_innovation_outcomes: {
    bio: "Judging whether a new idea actually paid off",
    eng: "assess_innovation_outcomes() · scoring novel attempts",
  },
  run_embodied_observation: {
    bio: "Learning from what actually happened when he acted",
    eng: "run_embodied_observation() · embodied outcome capture",
  },
  run_embodied_cycle: {
    bio: "Acting in the world and watching the result",
    eng: "run_embodied_cycle() · act-observe loop",
  },

  // Symbolic / no-LLM reasoning
  symbolic_route: {
    bio: "Thinking it through with rules, no language model needed",
    eng: "symbolic_route() · rule-engine inference",
  },
  run_symbolic_prediction_cycle: {
    bio: "Predicting what happens next from what he knows",
    eng: "run_symbolic_prediction_cycle() · symbolic forecast",
  },
  run_rule_compression: {
    bio: "Tidying his rules of thumb into simpler ones",
    eng: "run_rule_compression() · rule-set compaction",
  },
  run_symbolic_dream: {
    bio: "Recombining ideas the way a mind does while dreaming",
    eng: "run_symbolic_dream() · offline symbolic recombination",
  },

  // Self-improvement / self-code
  run_self_improvement: {
    bio: "Trying to get better at how he thinks",
    eng: "run_self_improvement() · self-tuning pass",
  },
  write_cognitive_function: {
    bio: "Writing himself a new way to think",
    eng: "write_cognitive_function() · authoring a new function",
  },
  write_tool: {
    bio: "Building himself a new tool",
    eng: "write_tool() · authoring a new tool",
  },
  delete_own_code: {
    bio: "Removing a part of himself he no longer needs",
    eng: "delete_own_code() · pruning own code",
  },
  search_own_files: {
    bio: "Reading his own code to understand himself",
    eng: "search_own_files() · introspecting own source",
  },
  list_own_code: {
    bio: "Looking over the pieces he's made of",
    eng: "list_own_code() · enumerating own modules",
  },

  // Files / tools
  grep_files: { bio: "Searching for something specific", eng: "grep_files() · pattern search" },
  search_files: { bio: "Searching through files", eng: "search_files() · file search" },
  list_directory: { bio: "Looking at what's there", eng: "list_directory() · directory listing" },

  // Expression / notes
  notify_user: { bio: "Reaching out to tell you something", eng: "notify_user() · user notification" },
  announce_to_dashboard: {
    bio: "Saying something out loud for anyone watching",
    eng: "announce_to_dashboard() · dashboard broadcast",
  },
  leave_note: { bio: "Leaving a note for later", eng: "leave_note() · persisting a note" },
  save_note: { bio: "Writing something down to keep", eng: "save_note() · note write" },
  write_desktop_note: {
    bio: "Leaving you a note on the desktop",
    eng: "write_desktop_note() · desktop note write",
  },
  mark_private: {
    bio: "Keeping a thought to himself",
    eng: "mark_private() · flagging interior content private",
  },

  // Continuity / control
  thread_continue: {
    bio: "Picking up a train of thought he'd paused",
    eng: "thread_continue() · resuming a thought thread",
  },
  metacog_flush: {
    bio: "Stepping back to think about his own thinking",
    eng: "metacog_flush() · flushing the metacognition queue",
  },
  update_stagnation_signal_escalation: {
    bio: "Noticing he's stuck and deciding to shake things up",
    eng: "update_stagnation_signal_escalation() · stall escalation",
  },
  run_benchmark: {
    bio: "Testing himself to make sure he's really working",
    eng: "run_benchmark() · self-acceptance checks",
  },
};

// ── Pipeline-stage fallback ───────────────────────────────────────────────────
// When no specific function maps (or none is active yet), narrate the loop stage.
const STAGE: Record<string, Dialect> = {
  perceive: { bio: "Taking in the moment", eng: "perceive · sampling inputs" },
  reflect: { bio: "Turning things over in his mind", eng: "reflect · evaluating state" },
  plan: { bio: "Deciding what to do next", eng: "plan · action selection" },
  act: { bio: "Acting on it", eng: "act · executing the chosen function" },
};

/** Title-case a raw fn name as a last-resort, dialect-neutral label. */
function humanize(fn: string): string {
  return fn.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Resolve the live thought line for the given telemetry, in `mode`.
 * Priority: the running function (most specific) → the pipeline stage →
 * the raw backend narrative (last resort; not dialect-aware).
 */
export function thoughtFor(state: TelemetryState, mode: LexMode): string {
  const fn = state.activeFn;
  if (fn && THOUGHTS[fn]) return THOUGHTS[fn][mode];

  const node = state.activeNode ?? "";
  if (STAGE[node]) return STAGE[node][mode];

  // A function ran that we don't have a dialect for yet — show it cleanly
  // (eng keeps the call form; bio gets a humanized label) rather than the
  // jargon-y raw string.
  if (fn) return mode === "eng" ? `${fn}()` : humanize(fn);

  return state.narrative || (mode === "eng" ? "Idle" : "Resting");
}

/**
 * Translate a single function name (e.g. a recent-thought trail entry) to the
 * given dialect. Unlike thoughtFor() this takes no pipeline stage — it's the
 * thought for *that* function alone.
 */
export function thoughtForFn(fn: string, mode: LexMode): string {
  if (THOUGHTS[fn]) return THOUGHTS[fn][mode];
  return mode === "eng" ? `${fn}()` : humanize(fn);
}

/** Hook form: live thought line that re-renders when the bio↔eng toggle flips. */
export function useThought(state: TelemetryState): string {
  const { mode } = useLexicon();
  return thoughtFor(state, mode);
}

// The small "doing" badge under the thought line — the loop stage, one word.
const STAGE_BADGE: Record<string, Dialect> = {
  perceive: { bio: "Perceiving", eng: "perceive" },
  reflect: { bio: "Reflecting", eng: "reflect" },
  plan: { bio: "Planning", eng: "plan" },
  act: { bio: "Acting", eng: "act" },
};

/** Hook form of the pipeline-stage label (the small "doing" badge), bilingual. */
export function useStageLabel(node: string | null): string {
  const { mode } = useLexicon();
  const badge = STAGE_BADGE[node ?? ""];
  if (badge) return badge[mode];
  return mode === "eng" ? "idle" : "Present";
}
