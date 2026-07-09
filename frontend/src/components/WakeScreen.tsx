import { useEffect, useRef, useState } from "react";
import { Check, Loader2, X } from "lucide-react";
import { apiGet } from "@/lib/transport";

// Watch Orrin wake up (§9.7): a truthful boot checklist driven by real startup
// milestones (GET /api/boot), shown only on a COLD launch and dissolving into the
// app once cognition is live. A warm reopen (brain already up) never shows it.

interface BootStep { step: string; ok: boolean; note?: string }
interface BootFeed { events?: BootStep[]; ready?: boolean }

type Phase = "checking" | "waking" | "done";

export default function WakeScreen() {
  const [phase, setPhase] = useState<Phase>("checking");
  const [events, setEvents] = useState<BootStep[]>([]);
  const startedAt = useRef(Date.now());

  useEffect(() => {
    let alive = true;
    let timer = 0;

    const poll = async () => {
      let feed: BootFeed | null = null;
      try {
        const res = await apiGet("/api/boot");
        if (res.ok) feed = (await res.json()) as BootFeed;
      } catch {
        /* backend not up yet — keep checking briefly */
      }
      if (!alive) return;

      if (feed) {
        setEvents(feed.events ?? []);
        // Decide on the FIRST response: if already ready and the first poll is fast,
        // it's a warm reopen → never flash the screen.
        if (phaseRef.current === "checking") {
          if (feed.ready && Date.now() - startedAt.current < 1500) {
            setPhase("done");
            return;
          }
          setPhase("waking");
        }
        if (feed.ready && phaseRef.current === "waking") {
          // Let "Orrin has awakened." land for a beat, then dissolve.
          window.setTimeout(() => alive && setPhase("done"), 1400);
          return;
        }
      }
      // Safety: never trap the window on the wake screen. If the backend answers
      // but no boot milestone ever appears, nothing is booting (viewing a stopped
      // brain) — bail fast instead of holding a 30s "waking up" overlay.
      const cap = feed && (feed.events?.length ?? 0) === 0 ? 5000 : 30000;
      if (Date.now() - startedAt.current > cap) {
        setPhase("done");
        return;
      }
      timer = window.setTimeout(poll, 500);
    };
    void poll();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, []);

  // Keep a ref of phase for the async loop (avoids stale closure).
  const phaseRef = useRef(phase);
  phaseRef.current = phase;

  if (phase === "done" || phase === "checking") return null;

  const ready = events.length > 0 && phase === "waking" && events.every((e) => e.ok);

  return (
    <div className="fixed inset-0 z-[100] flex flex-col items-center justify-center gap-6 bg-background text-foreground animate-fade-in">
      <div className="text-sm uppercase tracking-[0.2em] text-muted-foreground">Orrin is waking up</div>
      <ul className="w-72 space-y-2">
        {events.map((e, i) => (
          <li key={i} className="flex items-center justify-between gap-3 text-sm">
            <span className="flex items-center gap-2">
              {e.ok ? (
                <Check className="h-4 w-4 text-signal-ok" />
              ) : (
                <X className="h-4 w-4 text-destructive" />
              )}
              {e.step}
            </span>
            {e.note && <span className="text-xs tabular-nums text-muted-foreground">{e.note}</span>}
          </li>
        ))}
        {!ready && (
          <li className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            {events.length === 0 ? "Starting cognition…" : "…"}
          </li>
        )}
      </ul>
      {ready && <div className="text-base font-medium animate-fade-in">Orrin has awakened.</div>}
    </div>
  );
}
