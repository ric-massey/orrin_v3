import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { setLexMode } from "@/lib/lexicon";
import { apiGet } from "@/lib/transport";
import { cn } from "@/lib/utils";

// First Wake (§9.2 + §9.11): a one-time, full-window introduction shown when the data
// dir was just seeded (a newborn). Ends with the single dialect question (§9.11) so the
// choice is intentional, not a silent default. Returning users never see it; it's
// re-openable via the "orrin:meet" event (Settings → Replay intro).

const MET_KEY = "orrin.met.v1";

type Stage = "intro" | "dialect";

const INTRO_LINES = [
  "This is Orrin.",
  "Orrin is not a chatbot.",
  "He is an autonomous symbolic mind.",
  "He has memories. He has goals. He has values.",
  "He keeps thinking when you stop talking.",
];

export default function FirstWake() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [stage, setStage] = useState<Stage>("intro");
  const [shown, setShown] = useState(0);

  // Decide whether to show: a newborn the viewer hasn't met yet.
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
      setStage("intro");
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
    if (!open || stage !== "intro") return;
    if (shown >= INTRO_LINES.length) return;
    const id = window.setTimeout(() => setShown((n) => n + 1), 900);
    return () => window.clearTimeout(id);
  }, [open, stage, shown]);

  if (!open) return null;

  const finish = (mode: "bio" | "eng", tour: boolean) => {
    setLexMode(mode);
    try {
      localStorage.setItem(MET_KEY, "1");
    } catch {
      /* private mode */
    }
    setOpen(false);
    navigate(tour ? "/cognition" : "/cognition");
  };

  return (
    <div className="fixed inset-0 z-[110] flex flex-col items-center justify-center gap-8 bg-background px-6 text-center text-foreground">
      {stage === "intro" ? (
        <>
          <div className="space-y-3">
            {INTRO_LINES.slice(0, shown).map((line, i) => (
              <p key={i} className={cn("text-lg animate-fade-in sm:text-xl", i === 0 && "font-semibold")}>
                {line}
              </p>
            ))}
          </div>
          {shown >= INTRO_LINES.length && (
            <button
              onClick={() => setStage("dialect")}
              className="rounded-md border border-border bg-card px-4 py-2 text-sm animate-fade-in hover:bg-muted"
            >
              Continue
            </button>
          )}
        </>
      ) : (
        <div className="max-w-md space-y-5 animate-fade-in">
          <p className="text-lg">One last thing — how should Orrin describe himself to you?</p>
          <div className="grid gap-3 text-left">
            <DialectChoice
              title="As a mind"
              example='"Consciousness", "Affect", "Life Support"'
              onClick={() => finish("bio", false)}
            />
            <DialectChoice
              title="As a machine"
              example='"Attention arbitration", "Control signals", "Resource Manager"'
              onClick={() => finish("eng", false)}
            />
          </div>
          <p className="text-xs text-muted-foreground">You can change this any time in Settings.</p>
        </div>
      )}
    </div>
  );
}

function DialectChoice({
  title,
  example,
  onClick,
}: {
  title: string;
  example: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="rounded-lg border border-border bg-card px-4 py-3 text-left transition-colors hover:border-primary hover:bg-muted"
    >
      <div className="text-sm font-medium">{title}</div>
      <div className="text-xs text-muted-foreground">{example}</div>
    </button>
  );
}
