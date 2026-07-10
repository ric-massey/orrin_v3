import { DecisionMoment } from "./types";

/**
 * R4 — chrome translation for the live decision moment. The component keys are
 * the selector's scoring terms (selection/score_actions.py); both registers
 * live here so the Cognition card (engineering) and the companion home (plain)
 * read from one table. Translate the chrome, never the mind: these label the
 * UI's sentence, the picked function/goal names render verbatim.
 */

export const FACTOR_LABEL: Record<string, string> = {
  dir: "directive fit",
  goal: "goal fit",
  emo: "affect routing",
  novel: "novelty",
  band: "cadence band",
  drive: "drive pressure",
  attn: "attention mode",
  energy: "energy state",
  help: "helpfulness",
  emo_route: "signal routing",
  chain: "learned chain",
  neuro: "neuromodulator boost",
  emo_mode: "signal mode",
  outward: "outward bias",
  goal_recruit: "goal recruitment",
  goal_lens: "goal lens",
  explore: "exploration value",
  exploit: "exploitation value",
  satiety: "satiety",
  value: "learned value",
};

const FACTOR_PLAIN: Record<string, string> = {
  dir: "it matched what he set out to do",
  goal: "it served the goal he's on",
  emo: "it fit how he feels",
  novel: "it was something new",
  band: "it was due",
  drive: "the pull was strongest there",
  attn: "it fit where his attention is",
  energy: "he had the energy for it",
  help: "it seemed most helpful",
  emo_route: "his mood pointed there",
  chain: "it usually follows what he just did",
  neuro: "his state primed it",
  emo_mode: "it fit the mode he's in",
  outward: "it faced outward",
  goal_recruit: "a goal recruited it",
  goal_lens: "it kept him on task",
  explore: "he wanted to see something new",
  exploit: "it's been working",
  satiety: "he'd had enough of the alternatives",
  value: "it's been paying off",
};

export function factorLabel(key: string): string {
  return FACTOR_LABEL[key] ?? key;
}

/** Plain one-liner for companion surfaces: why the last pick won. */
export function decisionPlainWhy(d: DecisionMoment | null): string {
  if (!d || !d.top_factor) return "";
  return FACTOR_PLAIN[d.top_factor] ?? "";
}
