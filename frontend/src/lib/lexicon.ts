import { useCallback, useEffect, useState } from "react";
import { readLocalStorage } from "./useLocalStorage";

/**
 * Fix 12 — the biological ↔ engineering terminology toggle.
 *
 * One table holds every display string the UI authors, in BOTH dialects, so
 * they cannot drift. The biological vocabulary stays the default (it is honest
 * about what the architecture models); engineering mode re-labels the same
 * data as mechanism for readers who hear "Consciousness" as mysticism.
 *
 * HARD RULE — translate the chrome, never the mind. Orrin's own output
 * (conscious content, goal titles, log messages, memory summaries, speech) is
 * DATA and renders verbatim in both modes. Only labels the UI authors carry
 * both dialects here.
 */

export type LexMode = "bio" | "eng";

const KEY = "orrin.terminology.v1";
const EVENT = "orrin:lexicon";

export const LEX = {
  // ── Panel titles ──────────────────────────────────────────────────────────
  sphere_title: { bio: "Cognitive Sphere", eng: "Function-call graph" },
  consciousness_title: { bio: "Consciousness", eng: "Attention arbitration" },
  affect_title: { bio: "Affect Telemetry", eng: "Control-signal state" },
  metrics_title: { bio: "System Metrics", eng: "System Metrics" },
  memory_title: { bio: "Memory Inspector", eng: "Store & op inspector" },
  goals_title: { bio: "Goals", eng: "Goals" },
  console_title: { bio: "Live Console", eng: "Live Console" },
  benchmarks_title: { bio: "Benchmarks", eng: "Benchmarks" },
  goalhealth_title: { bio: "Goal health", eng: "Goal-closure metrics" },
  innerweather_title: { bio: "Inner weather", eng: "Clock & state summary" },
  symbolic_title: { bio: "Symbolic mind", eng: "Rule engine" },
  predictions_title: { bio: "Predictions", eng: "Calibration" },
  drives_title: { bio: "Drives & body", eng: "Priority weights & budget" },
  learning_title: { bio: "Learning", eng: "Reward statistics" },
  tensions_title: { bio: "Tensions & will", eng: "Conflict & retry state" },
  health_title: { bio: "System health", eng: "System health" },
  self_title: { bio: "Self-model", eng: "System self-descriptor" },
  people_title: { bio: "Relationships", eng: "Person models" },
  dreams_title: { bio: "Dreams", eng: "Idle consolidation" },
  language_title: { bio: "Language organ", eng: "Native language model" },

  // ── Plain-language subtitles (Fix 11 step 3) ──────────────────────────────
  sphere_sub: { bio: "his mind's map; the lights are what's running now", eng: "registered functions; highlights are executing now" },
  consciousness_sub: { bio: "what he's paying attention to right now", eng: "highest-salience broadcast this cycle" },
  affect_sub: { bio: "how he feels right now", eng: "signal levels vs. their setpoints" },
  metrics_sub: { bio: "how he's felt over time", eng: "signal history over time" },
  memory_sub: { bio: "what he remembers — the live ops and the real stores", eng: "op ticker (sampled) + persistent store browser" },
  goals_sub: { bio: "what he's trying to do", eng: "task tree + plan state" },
  console_sub: { bio: "everything his subsystems report, live", eng: "structured log stream" },
  benchmarks_sub: { bio: "is he actually working? five hard checks", eng: "B1–B5 acceptance checks" },
  goalhealth_sub: { bio: "do his goals close instead of piling up", eng: "closure rates; population should stay bounded" },
  innerweather_sub: { bio: "how time and mood feel to him", eng: "internal clock skew + smoothed state" },
  symbolic_sub: { bio: "what he can think without the LLM", eng: "no-LLM inference share + learned rules" },
  predictions_sub: { bio: "what he expected vs. what happened", eng: "forecast accuracy + Brier score" },
  drives_sub: { bio: "what he wants, and what thinking costs him", eng: "drive weights + per-call cost model" },
  learning_sub: { bio: "which thoughts pay off for him", eng: "per-function reward EMAs + bandit state" },
  tensions_sub: { bio: "what he's wrestling with", eng: "open conflict flags + retry loops" },
  health_sub: { bio: "is the organism healthy", eng: "failure counters + incident log" },
  self_sub: { bio: "who he thinks he is, and how that revises", eng: "identity state + confidence revisions" },
  people_sub: { bio: "who he knows, and how he holds them", eng: "interlocutor + internal-peer models" },
  dreams_sub: { bio: "what he consolidates while idle", eng: "offline write-back + recombination job" },
  language_sub: { bio: "the language he's growing from scratch", eng: "from-scratch LM + phrase banks" },

  // ── Consciousness panel sections ──────────────────────────────────────────
  conscious_now: { bio: "Conscious now", eng: "Broadcast winner (this cycle)" },
  executive_lane: { bio: "Executive lane (autopilot)", eng: "Background task runner" },
  breakthroughs: { bio: "Breakthroughs offered", eng: "Interrupt requests (offered)" },
  watchdog: { bio: "Watchdog", eng: "Stall detector" },
  verdicts_label: { bio: "Honored vs quieted", eng: "Dismissal recalibration" },
  workspace_tagline: { bio: "Global Workspace · dual-process", eng: "priority-arbitrated broadcast bus" },

  // ── Affect rings ──────────────────────────────────────────────────────────
  valence_label: { bio: "Valence", eng: "Hedonic score" },
  valence_hint: { bio: "negative ↔ positive", eng: "reward sign − ↔ +" },
  arousal_label: { bio: "Arousal", eng: "Activation" },
  arousal_hint: { bio: "calm ↔ activated", eng: "low ↔ high activation" },
  homeostasis_label: { bio: "Homeostasis", eng: "Setpoint proximity" },
  homeostasis_hint: { bio: "agitated ↔ settled", eng: "far ↔ near setpoints" },

  // ── KPI strip ─────────────────────────────────────────────────────────────
  kpi_stage: { bio: "Active stage", eng: "Pipeline stage" },
  kpi_cycle: { bio: "Cycle", eng: "Cycle" },
  kpi_stream: { bio: "Stream", eng: "Telemetry socket" },
  kpi_longterm: { bio: "Long-term memories", eng: "Persistent store records" },
  kpi_memops: { bio: "Memory ops (live)", eng: "Store ops (this session)" },

  // ── Misc chrome ───────────────────────────────────────────────────────────
  sphere_empty: { bio: "Mapping his mind…", eng: "Loading the function catalog…" },
  exec_idle: { bio: "Idle — no step advancing this cycle.", eng: "Idle — no task step ran this tick." },

  // ── Named rooms (§9.1 navigation) ─────────────────────────────────────────
  nav_watch: { bio: "Watch", eng: "Watch" },
  nav_face: { bio: "Face", eng: "Face" },
  nav_cognition: { bio: "Cognition", eng: "Cognition" },
  nav_life: { bio: "Life Support", eng: "Resource Manager" },
  nav_memory: { bio: "Memory", eng: "Memory" },
  nav_timeline: { bio: "Timeline", eng: "Activity log" },
  nav_learning: { bio: "Learning", eng: "Behavior changes" },
  nav_brain: { bio: "Brain", eng: "Brain" },
  nav_settings: { bio: "Settings", eng: "Settings" },

  // ── Cognition view (§9.3) ─────────────────────────────────────────────────
  cog_focus: { bio: "Current focus", eng: "Active function (this cycle)" },
  cog_goal: { bio: "Current goal", eng: "Active goal + step" },
  cog_competing: { bio: "Competing thoughts", eng: "Workspace candidates (ranked)" },
  cog_winner: { bio: "What took his attention", eng: "Broadcast winner" },
  cog_peers: { bio: "Inner voices", eng: "Active peer models" },
  cog_drives: { bio: "Drive pressure", eng: "Priority weights" },
  cog_symbolic: { bio: "Symbolic activity", eng: "Rules firing" },
  cog_private: { bio: "His private thoughts stay his own.", eng: "Protected interior (not exposed by the API)." },

  // ── Life Support (§9.10) ──────────────────────────────────────────────────
  life_cpu: { bio: "Headroom to think", eng: "CPU available" },
  life_mem: { bio: "Working-memory headroom", eng: "RAM available" },
  life_disk: { bio: "Room left to grow his mind", eng: "Disk free (data dir)" },
  life_rate: { bio: "How fast he's thinking", eng: "Cycles/min" },
  life_age: { bio: "How long he's been alive", eng: "Uptime since born_at" },
  life_remaining: { bio: "Life he feels he has left", eng: "Est. days remaining (felt)" },
  life_interests: { bio: "What he cares about right now", eng: "Top active goals" },
} as const;

export type LexId = keyof typeof LEX;

export function getLexMode(): LexMode {
  return readLocalStorage<LexMode>(KEY, "bio", {
    sanitize: (raw) => (raw === "eng" ? "eng" : "bio"),
  });
}

export function setLexMode(mode: LexMode): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(mode));
  } catch {
    /* private mode — the toggle just won't persist */
  }
  window.dispatchEvent(new Event(EVENT));
}

/** Resolve an id in the CURRENT mode without subscribing (for non-React code). */
export function lex(id: LexId): string {
  return LEX[id][getLexMode()];
}

/**
 * Hook: returns the live mode, a translator `t`, and `tip` — the counterpart
 * dialect for a hover tooltip ("Attention arbitration — biological:
 * Consciousness"), so the toggle doubles as a glossary.
 */
export function useLexicon(): {
  mode: LexMode;
  t: (id: LexId) => string;
  tip: (id: LexId) => string | undefined;
} {
  const [mode, setMode] = useState<LexMode>(getLexMode);
  useEffect(() => {
    const on = () => setMode(getLexMode());
    window.addEventListener(EVENT, on);
    return () => window.removeEventListener(EVENT, on);
  }, []);
  const t = useCallback((id: LexId) => LEX[id][mode], [mode]);
  const tip = useCallback(
    (id: LexId) => {
      const other: LexMode = mode === "bio" ? "eng" : "bio";
      const counterpart = LEX[id][other];
      if (counterpart === LEX[id][mode]) return undefined;
      return `${other === "bio" ? "biological" : "engineering"}: ${counterpart}`;
    },
    [mode],
  );
  return { mode, t, tip };
}
