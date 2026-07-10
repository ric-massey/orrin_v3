import { useTelemetryState } from "@/App";
import NarrativeStatusCard from "@/components/face/NarrativeStatusCard";
import Chat from "@/components/face/Chat";

/**
 * Face — the calm light conversation room. Status card on top, then the shared
 * conversation surface (components/face/Chat.tsx, also composed into /orrin).
 */
export default function Face() {
  const telemetry = useTelemetryState();

  return (
    <div className="flex h-[calc(100dvh-3.5rem)] flex-col sm:h-[calc(100dvh-4rem)]">
      {/* Narrative status — always present, calm and human */}
      <div className="px-3 pt-3 sm:px-4 sm:pt-5">
        <NarrativeStatusCard telemetry={telemetry} />
      </div>

      <Chat
        emptyState={
          <div className="flex flex-col items-center justify-center gap-3 py-16 text-center animate-fade-in sm:py-24">
            <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">How are you, really?</h1>
            <p className="max-w-sm text-[15px] leading-relaxed text-muted-foreground">
              You're speaking with Orrin — a runtime that perceives, reflects, plans, and acts in
              a continuous loop. Say anything.
            </p>
          </div>
        }
      />
    </div>
  );
}
