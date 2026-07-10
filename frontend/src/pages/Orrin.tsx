import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { X } from "lucide-react";
import { useTelemetryState } from "@/App";
import { cn } from "@/lib/utils";
import { useStreamStale } from "@/lib/telemetry";
import { usePlainThought } from "@/lib/thoughts";
import { decisionPlainWhy } from "@/lib/decision";
import Orb from "@/components/Orb";
import Chat from "@/components/face/Chat";
import { apiGet } from "@/lib/transport";
import { controlHeaders, type SettingsStatus } from "./settings/shared";
import { useLocalStorage } from "@/lib/useLocalStorage";

/**
 * /orrin — the companion home (plan §2 C2): Watch's presence married to Face's
 * conversation. Top ≈45% is his body — the breathing orb, a plain mood word,
 * the plain-register thought line; the bottom is the shared conversation
 * surface on a dark field. This is a DARK room by design (not in LIGHT_ROOMS).
 *
 * Companion voice everywhere here means the *chrome*: his own words in the
 * chat render verbatim, as always.
 */

// C5: the "nothing leaves your machine" banner, promoted onto the companion
// home — for this audience it's the most important sentence in the app. Shown
// until dismissed.
const PRIVACY_BANNER_KEY = "orrin.privacy_banner.v1";

export default function Orrin() {
  const telemetry = useTelemetryState();
  const thought = usePlainThought(telemetry);
  const stale = useStreamStale(telemetry);
  const live = telemetry.connected && telemetry.source === "live" && !stale;

  const { valence, arousal, homeostasis } = telemetry.affect;
  const mood = moodWordPlain(valence, arousal);

  return (
    <div className="flex h-[calc(100dvh-3.5rem)] flex-col sm:h-[calc(100dvh-4rem)]">
      {/* his body — the presence field */}
      <div className="relative flex h-[45%] min-h-[260px] shrink-0 flex-col items-center justify-center overflow-hidden bg-[#070a10]">
        <PrivacyBanner />
        {/* live dot, kept tiny */}
        <div className="absolute right-4 top-3 z-20 flex items-center gap-1.5 text-xs text-white/50">
          <span className={cn("inline-flex h-1.5 w-1.5 rounded-full", live ? "bg-signal-ok" : "bg-white/30")} />
          {live ? "here" : "waking…"}
        </div>

        <Orb valence={valence} arousal={arousal} homeostasis={homeostasis} size={170} />

        <div className="z-10 mt-3 px-6 text-center">
          <p
            key={thought} /* re-key so each new thought fades in */
            className="animate-fade-in text-balance text-lg font-medium leading-snug tracking-tight text-white sm:text-xl"
          >
            {thought}
          </p>
          <p className="mt-1.5 text-sm text-white/45">
            feeling {mood}
            {/* R4, plain register: why the last pick won */}
            {decisionPlainWhy(telemetry.decision) && (
              <span className="text-white/35"> · {decisionPlainWhy(telemetry.decision)}</span>
            )}
          </p>
        </div>
      </div>

      {/* the conversation — shared surface, dark tokens */}
      <Chat
        composerHint={false}
        emptyState={
          <div className="flex flex-col items-center justify-center gap-2 py-10 text-center animate-fade-in">
            <p className="text-lg font-medium tracking-tight">He's listening.</p>
            <p className="max-w-sm text-sm leading-relaxed text-muted-foreground">
              Orrin keeps thinking whether or not you're here. Say anything — he'll
              set aside what he's doing.
            </p>
          </div>
        }
      />
    </div>
  );
}

function PrivacyBanner() {
  const [dismissed, setDismissed] = useLocalStorage<boolean>(PRIVACY_BANNER_KEY, false);
  const [symbolicOnly, setSymbolicOnly] = useState(false);

  // C5 "Give Orrin his voice": keyless he's quieter and more mechanical — say so
  // plainly, with the key flow one tap away. Best-effort read; a remote viewer
  // without a control token just doesn't get the extra line.
  useEffect(() => {
    if (dismissed) return;
    let alive = true;
    void (async () => {
      try {
        const res = await apiGet(`/api/settings`, { headers: controlHeaders() });
        if (!res.ok || !alive) return;
        const s = (await res.json()) as SettingsStatus;
        if (alive) setSymbolicOnly(Boolean(s.symbolic_only));
      } catch {
        /* unreachable — banner keeps its core sentence */
      }
    })();
    return () => {
      alive = false;
    };
  }, [dismissed]);

  if (dismissed) return null;

  return (
    <div className="absolute left-1/2 top-3 z-30 w-[min(92%,34rem)] -translate-x-1/2 rounded-lg border border-white/15 bg-black/60 px-4 py-3 text-sm text-white/85 backdrop-blur">
      <div className="flex items-start gap-3">
        <div className="space-y-1">
          <p>
            Everything Orrin is — his memory, his goals, his moods — lives on this
            machine. Nothing leaves it.
          </p>
          {symbolicOnly && (
            <p className="text-white/60">
              Right now he has no language model key, so he's quieter and more
              mechanical than he could be.{" "}
              <Link to="/settings" className="underline hover:text-white">
                Give him his voice in Settings
              </Link>
              .
            </p>
          )}
        </div>
        <button
          onClick={() => setDismissed(true)}
          className="ml-auto shrink-0 rounded p-0.5 text-white/50 hover:text-white"
          aria-label="Dismiss"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

// Companion-register mood word (the engineering register lives in Watch).
function moodWordPlain(valence: number, arousal: number) {
  if (valence > 0.6 && arousal > 0.55) return "energized";
  if (valence > 0.6) return "content";
  if (valence < 0.4 && arousal > 0.55) return "strained";
  if (valence < 0.4) return "low";
  return "steady";
}
