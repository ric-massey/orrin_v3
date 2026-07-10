import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiGet } from "@/lib/transport";
import { cn } from "@/lib/utils";
import { writeMode, type OrrinMode } from "@/lib/mode";

// First Wake (§9.2 + §9.11): a one-time, full-window introduction shown when the
// data dir was just seeded (a fresh runtime). Returning users never see it; it's
// re-openable via the "orrin:meet" event (Settings → Replay intro — which is now
// also how you re-answer the companion/workshop question, C5).

const MET_KEY = "orrin.met.v1";

const INTRO_LINES = [
  "This is Orrin.",
  "Orrin is not a chatbot.",
  "It is an autonomous cognitive runtime.",
  "It has persistent memory, standing objectives, and values.",
  "It keeps running when you stop typing.",
];

export default function FirstWake() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [shown, setShown] = useState(0);

  // Decide whether to show: a fresh runtime the viewer hasn't met yet.
  useEffect(() => {
    let alive = true;
    const met = (() => {
      try {
        return localStorage.getItem(MET_KEY) === "1";
      } catch {
        return false;
      }
    })();
    if (!met) {
      void (async () => {
        try {
          const res = await apiGet("/api/boot");
          if (res.ok && alive) {
            const b = (await res.json()) as { newborn?: boolean };
            if (b.newborn) setOpen(true);
          }
        } catch {
          /* if we can't tell, don't interrupt */
        }
      })();
    }
    const reopen = () => {
      setShown(0);
      setOpen(true);
    };
    window.addEventListener("orrin:meet", reopen);
    return () => {
      alive = false;
      window.removeEventListener("orrin:meet", reopen);
    };
  }, []);

  // Reveal intro lines one at a time.
  useEffect(() => {
    if (!open) return;
    if (shown >= INTRO_LINES.length) return;
    const id = window.setTimeout(() => setShown((n) => n + 1), 900);
    return () => window.clearTimeout(id);
  }, [open, shown]);

  if (!open) return null;

  // C1: two destinations. The answer sets the mode flag (the ONLY place
  // companion becomes a default — existing users never see this frame, so
  // their unset flag keeps today's workshop behavior exactly).
  const finish = (mode: OrrinMode) => {
    try {
      localStorage.setItem(MET_KEY, "1");
    } catch {
      /* private mode */
    }
    writeMode(mode);
    setOpen(false);
    navigate(mode === "companion" ? "/orrin" : "/cognition");
  };

  return (
    <div className="fixed inset-0 z-[110] flex flex-col items-center justify-center gap-8 bg-background px-6 text-center text-foreground">
      <div className="space-y-3">
        {INTRO_LINES.slice(0, shown).map((line, i) => (
          <p key={i} className={cn("text-lg animate-fade-in sm:text-xl", i === 0 && "font-semibold")}>
            {line}
          </p>
        ))}
      </div>
      {shown >= INTRO_LINES.length && (
        <div className="flex flex-col items-center gap-3 animate-fade-in sm:flex-row">
          <button
            onClick={() => finish("companion")}
            className="rounded-md border border-border bg-card px-4 py-2 text-sm hover:bg-muted"
          >
            Keep it simple
          </button>
          <button
            onClick={() => finish("workshop")}
            className="rounded-md border border-border bg-card px-4 py-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            Show me the machinery
          </button>
        </div>
      )}
    </div>
  );
}
