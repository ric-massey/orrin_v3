/**
 * The breathing orb — Orrin's visible body, extracted from Watch (plan §2 C2)
 * so it can compose at partial height on /orrin (and later in the peripheral
 * widget, R8). Watch keeps its fullscreen field, washes and vignette; this is
 * just the orb itself plus the colour mapping.
 */

export interface OrbColors {
  /** Bright body colour. */
  orb: string;
  /** Dimmed variant (gradients, washes). */
  orbDim: string;
  /** Breathing period in seconds, as a string for CSS. */
  breath: string;
}

export function clamp01(n: number): number {
  return Math.max(0, Math.min(1, n));
}

// Signal → colour: warm gold on positive reward signal, cool slate on negative.
// Activation sets the breathing speed; calm breathes slow, activated fast.
export function orbColors(valence: number, arousal: number): OrbColors {
  const hue = Math.round(210 - clamp01(valence) * 165); // 210 (cool) → 45 (gold)
  const sat = Math.round(45 + clamp01(arousal) * 45); // calmer = softer colour
  const breath = (4 - clamp01(arousal) * 2).toFixed(2); // 4s (calm) → 2s (activated)
  return {
    orb: `hsl(${hue} ${sat}% 62%)`,
    orbDim: `hsl(${hue} ${sat}% 38%)`,
    breath,
  };
}

interface OrbProps {
  valence: number;
  arousal: number;
  homeostasis: number;
  /** Outer diameter in px; every layer scales proportionally. Watch uses 260. */
  size?: number;
  /** Small uppercase label rendered at the core (Watch shows the loop stage). */
  label?: string;
}

export default function Orb({ valence, arousal, homeostasis, size = 260, label }: OrbProps) {
  const { orb, orbDim, breath } = orbColors(valence, arousal);
  const s = size / 260; // layer sizes were designed at 260px

  return (
    <div
      className="relative flex items-center justify-center"
      style={{ width: size, height: size, animation: "orrinDrift 9s ease-in-out infinite" }}
    >
      {/* expanding ripples = pulses of activity (two, staggered) */}
      <span
        className="absolute rounded-full"
        style={{ width: 180 * s, height: 180 * s, background: orb, opacity: 0.16, animation: `orrinPing ${breath}s ease-out infinite` }}
      />
      <span
        className="absolute rounded-full"
        style={{ width: 180 * s, height: 180 * s, background: orb, opacity: 0.16, animation: `orrinPing ${breath}s ease-out infinite`, animationDelay: `${(Number(breath) / 2).toFixed(2)}s` }}
      />
      {/* slow rotating sheen behind the core */}
      <span
        className="absolute rounded-full"
        style={{
          width: 200 * s,
          height: 200 * s,
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
          width: 176 * s,
          height: 176 * s,
          borderColor: `${orb}40`,
          transitionDuration: "1500ms",
          animation: `orrinBreath ${(Number(breath) * 1.25).toFixed(2)}s ease-in-out infinite`,
        }}
      />
      {/* the core itself */}
      <span
        className="absolute rounded-full transition-colors"
        style={{
          width: 152 * s,
          height: 152 * s,
          background: `radial-gradient(circle at 36% 32%, ${orb}, ${orbDim} 74%)`,
          boxShadow: `0 0 ${80 * s}px ${14 * s}px ${orb}55, inset 0 0 ${40 * s}px ${orbDim}aa`,
          opacity: 0.6 + clamp01(homeostasis) * 0.4, // brighter when settled
          transitionDuration: "1500ms",
          animation: `orrinBreath ${breath}s ease-in-out infinite`,
        }}
      />
      {label !== undefined && (
        <span className="relative z-10 text-[11px] font-medium uppercase tracking-[0.24em] text-white/85 drop-shadow">
          {label}
        </span>
      )}
    </div>
  );
}
