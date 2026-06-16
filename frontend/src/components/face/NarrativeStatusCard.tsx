import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { TelemetryState } from "@/lib/telemetry";
import { useLexicon } from "@/lib/lexicon";
import { useStageLabel, useThought } from "@/lib/thoughts";

/**
 * Translates the backend cognitive loop into a single, calm human-readable line.
 * No jargon, no metrics — just what Orrin is "doing" right now. The line, the
 * stage badge and the mood word all obey the bio↔eng terminology toggle (the
 * visual is identical in both dialects; only the words change).
 */
export default function NarrativeStatusCard({ telemetry }: { telemetry: TelemetryState }) {
  const { mode } = useLexicon();
  const thought = useThought(telemetry);
  const label = useStageLabel(telemetry.activeNode);
  const [dots, setDots] = useState("");

  useEffect(() => {
    const id = window.setInterval(() => setDots((d) => (d.length >= 3 ? "" : d + "·")), 450);
    return () => window.clearInterval(id);
  }, []);

  const mood = moodWord(telemetry.affect.valence, telemetry.affect.arousal, mode);

  return (
    <div className="mx-auto w-full max-w-2xl">
      <div className="flex items-center justify-between rounded-2xl border bg-card/60 px-5 py-3.5 shadow-sm animate-fade-in">
        <div className="flex items-center gap-3">
          <span className="relative flex h-2.5 w-2.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-signal-accent/60" />
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-signal-accent" />
          </span>
          <div>
            <div className="text-sm font-medium tracking-tight">
              {thought || `${label}…`}
              <span className="ml-0.5 inline-block w-4 text-left text-muted-foreground">{dots}</span>
            </div>
            <div className="text-xs text-muted-foreground">
              {label} · {mode === "eng" ? "affect" : "feeling"} {mood}
            </div>
          </div>
        </div>
        <MiniMeter value={telemetry.affect.homeostasis} />
      </div>
    </div>
  );
}

function MiniMeter({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  return (
    <div className="hidden items-center gap-2 sm:flex" title="Inner balance">
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-secondary">
        <div
          className={cn("h-full rounded-full transition-all duration-700", barColor(value))}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-8 text-right text-xs tabular-nums text-muted-foreground">{pct}%</span>
    </div>
  );
}

function barColor(v: number) {
  if (v > 0.66) return "bg-signal-ok";
  if (v > 0.4) return "bg-signal-warn";
  return "bg-signal-error";
}

// Same affect state, two dialects: a felt mood word (bio) vs. the signed
// valence/arousal quadrant it comes from (eng).
function moodWord(valence: number, arousal: number, mode: "bio" | "eng") {
  if (valence > 0.6 && arousal > 0.55) return mode === "eng" ? "high +valence" : "energized";
  if (valence > 0.6) return mode === "eng" ? "+valence" : "content";
  if (valence < 0.4 && arousal > 0.55) return mode === "eng" ? "high −valence" : "unsettled";
  if (valence < 0.4) return mode === "eng" ? "−valence" : "subdued";
  return mode === "eng" ? "near setpoint" : "steady";
}
