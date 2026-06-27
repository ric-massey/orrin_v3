import { Fragment, useMemo } from "react";
import { useTelemetryState } from "@/App";
import { cn } from "@/lib/utils";
import { useStreamStale } from "@/lib/telemetry";
import { thoughtForFn, useStageLabel, useThought } from "@/lib/thoughts";

/**
 * Watch — the front door for someone who has never seen the runtime.
 *
 * Goal: a newcomer glances and instantly understands "this is an autonomous
 * runtime, processing on its own, right now." No input box, no dashboard. Three
 * reads, in order:
 *   1. it's RUNNING      → a breathing orb whose colour tracks its signal state
 *   2. it's PROCESSING   → one big plain-language thought line
 *   3. ON ITS OWN        → a fading stream of the steps just before this one
 */
export default function Watch() {
  const telemetry = useTelemetryState();
  const thought = useThought(telemetry);
  const stage = useStageLabel(telemetry.activeNode);
  const stale = useStreamStale(telemetry);
  const live = telemetry.connected && telemetry.source === "live" && !stale;

  const { valence, arousal, homeostasis } = telemetry.affect;
  const mood = moodWord(valence, arousal);
  // Signal → colour: warm gold on positive reward signal, cool slate on negative.
  // Activation sets the breathing speed; calm breathes slow, activated fast.
  const hue = Math.round(210 - clamp01(valence) * 165); // 210 (cool) → 45 (gold)
  const sat = Math.round(45 + clamp01(arousal) * 45); // calmer = softer colour
  const breath = (4 - clamp01(arousal) * 2).toFixed(2); // 4s (calm) → 2s (activated)
  const orb = `hsl(${hue} ${sat}% 62%)`;
  const orbDim = `hsl(${hue} ${sat}% 38%)`;

  // The workspace broadcast log: the deliberate steps just before this one,
  // newest first, fading with age — visible proof it's advancing by itself.
  const trail = useMemo(() => {
    const seen = new Set<string>();
    const out: { fn: string; key: string }[] = [];
    for (let i = telemetry.fnRecent.length - 1; i >= 0 && out.length < 6; i--) {
      const e = telemetry.fnRecent[i];
      if (!e?.fn || e.lane === "executive") continue;
      if (e.fn === telemetry.activeFn && out.length === 0) continue; // it's the headline now
      const key = `${e.fn}:${e.cycle ?? i}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ fn: e.fn, key });
    }
    return out;
  }, [telemetry.fnRecent, telemetry.activeFn]);

  return (
    <div className="relative flex h-[calc(100dvh-3.5rem)] flex-col items-center justify-center overflow-hidden bg-[#070a10] text-foreground sm:h-[calc(100dvh-4rem)]">
      {/* ambient wash — colour follows the signal state, drifts slowly */}
      <div
        className="pointer-events-none absolute inset-0 opacity-50 transition-all"
        style={{
          background: `radial-gradient(55% 55% at 50% 40%, ${orbDim}40, transparent 72%)`,
          transitionDuration: "2000ms",
        }}
      />
      {/* vignette — settles the eye toward the centre */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{ background: "radial-gradient(120% 90% at 50% 45%, transparent 55%, #04060a 100%)" }}
      />

      {/* top strip: who + live state, kept tiny */}
      <div className="absolute left-0 right-0 top-0 z-20 flex items-center justify-between px-6 py-4 text-xs text-white/50">
        <span className="font-semibold tracking-[0.18em] text-white/75">ORRIN</span>
        <span className="flex items-center gap-1.5 tabular-nums">
          <span className="relative flex h-1.5 w-1.5">
            {live && (
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-signal-ok opacity-75" />
            )}
            <span className={cn("relative inline-flex h-1.5 w-1.5 rounded-full", live ? "bg-signal-ok" : "bg-white/30")} />
          </span>
          {live ? `thinking · cycle ${telemetry.cycle}` : "waking…"}
        </span>
      </div>

      {/* THE ORB — breathing, mood-coloured, gently adrift */}
      <div
        className="relative flex items-center justify-center"
        style={{ width: 260, height: 260, animation: "orrinDrift 9s ease-in-out infinite" }}
      >
        {/* expanding ripples = pulses of activity (two, staggered) */}
        <span
          className="absolute rounded-full"
          style={{ width: 180, height: 180, background: orb, opacity: 0.16, animation: `orrinPing ${breath}s ease-out infinite` }}
        />
        <span
          className="absolute rounded-full"
          style={{ width: 180, height: 180, background: orb, opacity: 0.16, animation: `orrinPing ${breath}s ease-out infinite`, animationDelay: `${(Number(breath) / 2).toFixed(2)}s` }}
        />
        {/* slow rotating sheen behind the core */}
        <span
          className="absolute rounded-full"
          style={{
            width: 200,
            height: 200,
            background: `conic-gradient(from 0deg, transparent, ${orb}55, transparent 55%)`,
            opacity: 0.5,
            filter: "blur(3px)",
            animation: "orrinSpin 16s linear infinite",
          }}
        />
        {/* thin halo ring, breathing slightly out of phase with the core */}
        <span
          className="absolute rounded-full border transition-colors"
          style={{
            width: 176,
            height: 176,
            borderColor: `${orb}40`,
            transitionDuration: "1500ms",
            animation: `orrinBreath ${(Number(breath) * 1.25).toFixed(2)}s ease-in-out infinite`,
          }}
        />
        {/* the core itself */}
        <span
          className="absolute rounded-full transition-colors"
          style={{
            width: 152,
            height: 152,
            background: `radial-gradient(circle at 36% 32%, ${orb}, ${orbDim} 74%)`,
            boxShadow: `0 0 80px 14px ${orb}55, inset 0 0 40px ${orbDim}aa`,
            opacity: 0.6 + clamp01(homeostasis) * 0.4, // brighter when settled
            transitionDuration: "1500ms",
            animation: `orrinBreath ${breath}s ease-in-out infinite`,
          }}
        />
        <span className="relative z-10 text-[11px] font-medium uppercase tracking-[0.24em] text-white/85 drop-shadow">
          {stage}
        </span>
      </div>

      {/* THE THOUGHT — the headline, plain language */}
      <div className="z-10 mt-12 max-w-xl px-6 text-center">
        <p
          key={thought} /* re-key so each new thought fades in */
          className="animate-fade-in text-balance text-2xl font-medium leading-snug tracking-tight text-white sm:text-3xl"
        >
          {thought}
        </p>
        <div className="mt-4 flex items-center justify-center gap-2 text-sm text-white/45">
          <span
            className="h-1.5 w-1.5 rounded-full transition-colors"
            style={{ background: orb, transitionDuration: "1500ms" }}
          />
          <span>signal {mood}</span>
        </div>
      </div>

      {/* THE STREAM — recent thoughts, fading with age */}
      <div className="z-10 mt-10 flex min-h-[3.5rem] max-w-2xl flex-wrap items-center justify-center gap-x-1 gap-y-1 px-6 text-center">
        {trail.map((th, i) => (
          <Fragment key={th.key}>
            {i > 0 && <span className="select-none text-white/15">·</span>}
            <span
              className="px-1 text-xs text-white transition-opacity"
              style={{ opacity: 0.5 - i * 0.07 }}
            >
              {thoughtForFn(th.fn)}
            </span>
          </Fragment>
        ))}
      </div>

      {/* bottom: the one explanation */}
      <div className="absolute bottom-0 left-0 right-0 z-20 flex flex-col items-center gap-3 px-6 pb-6">
        <p className="max-w-md text-center text-xs leading-relaxed text-white/40">
          You're watching Orrin run on its own — the orb tracks its control-signal
          state, the line is the function executing this cycle.
        </p>
      </div>
    </div>
  );
}

function clamp01(n: number): number {
  return Math.max(0, Math.min(1, n));
}

// Engineering label for the current signal state (mirrors NarrativeStatusCard).
function moodWord(valence: number, arousal: number) {
  if (valence > 0.6 && arousal > 0.55) return "high +valence";
  if (valence > 0.6) return "+valence";
  if (valence < 0.4 && arousal > 0.55) return "high −valence";
  if (valence < 0.4) return "−valence";
  return "near setpoint";
}
