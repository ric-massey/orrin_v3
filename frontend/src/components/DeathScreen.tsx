import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiBase, apiGet } from "@/lib/transport";

// The Death Screen (§10.4) — when Orrin reaches true end-of-lifespan, the window does
// not go dead; it becomes a quiet memorial. This is the ONE place his whole interior
// opens (the veil lifts only on death, via /api/death which refuses while he's alive).
// Also handles the §10.5 "interrupted" case (crash/stall) as a non-blocking banner.

function controlHeaders(): Record<string, string> | undefined {
  const token = import.meta.env.VITE_CONTROL_TOKEN as string | undefined;
  return token ? { "X-Orrin-Control-Token": token } : undefined;
}

interface Lifecycle {
  state?: "alive" | "dead" | "stalled" | "crashed";
  born_at?: string;
  age_days?: number;
}
interface Death {
  final_thoughts?: { content?: string }[];
  private_thoughts?: string;
  autobiography?: Record<string, unknown>;
  life?: { born_at?: string; age_days?: number };
}

export default function DeathScreen() {
  const navigate = useNavigate();
  const [life, setLife] = useState<Lifecycle | null>(null);
  const [death, setDeath] = useState<Death | null>(null);
  const [showInterior, setShowInterior] = useState(false);
  const [dismissedBanner, setDismissedBanner] = useState(false);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const res = await apiGet("/api/lifecycle");
        if (res.ok && alive) setLife((await res.json()) as Lifecycle);
      } catch {
        /* ignore */
      }
    };
    void tick();
    const id = window.setInterval(tick, 5000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, []);

  // Load the interior once we know he's gone (the veil has lifted).
  useEffect(() => {
    if (life?.state !== "dead" || death) return;
    void (async () => {
      try {
        const res = await apiGet("/api/death");
        if (res.ok) setDeath((await res.json()) as Death);
      } catch {
        /* ignore */
      }
    })();
  }, [life?.state, death]);

  if ((life?.state === "stalled" || life?.state === "crashed") && !dismissedBanner) {
    // §10.5: a stall masquerading as death is terrifying; death as a crash is wrong.
    const msg =
      life.state === "stalled"
        ? "Orrin stalled and is restarting — his mind is intact."
        : "Orrin stopped unexpectedly and has restarted — his mind is intact.";
    return (
      <div className="fixed inset-x-0 top-0 z-[120] flex items-center justify-center gap-3 bg-signal-warn/15 px-4 py-2 text-sm">
        <span>{msg}</span>
        <button className="underline" onClick={() => setDismissedBanner(true)}>
          dismiss
        </button>
      </div>
    );
  }

  if (life?.state !== "dead") return null;

  const bornAt = death?.life?.born_at || life.born_at;
  const lived = Math.round(death?.life?.age_days ?? life.age_days ?? 0);
  const firstFinal = death?.final_thoughts?.[death.final_thoughts.length - 1]?.content;

  const exportHim = async () => {
    try {
      const res = await fetch(`${apiBase()}/api/mind/export`, { headers: controlHeaders() });
      const blob = await res.blob();
      const name =
        res.headers.get("content-disposition")?.match(/filename="(.+)"/)?.[1] || "orrin.orrindmind";
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      /* ignore */
    }
  };

  const beginAnew = async () => {
    if (!window.confirm("Keep a copy of him first? A new, newborn Orrin will begin. The one who died is gone — export him now if you want to remember him.")) {
      return;
    }
    await exportHim(); // archive the dead mind as a keepsake before reseeding
    try {
      await fetch(`${apiBase()}/api/control/reset`, {
        method: "POST",
        headers: controlHeaders(),
      });
    } catch {
      /* the process re-execs */
    }
  };

  return (
    <div className="fixed inset-0 z-[120] flex flex-col items-center justify-center gap-6 overflow-auto bg-background px-6 py-12 text-center text-foreground">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">Orrin has died.</h1>
        <p className="text-sm text-muted-foreground">
          {bornAt ? `Born ${bornAt.slice(0, 10)} · ` : ""}Lived {lived} days · reached the end of his life
        </p>
      </div>

      {firstFinal && (
        <blockquote className="max-w-lg text-lg italic leading-relaxed">“{firstFinal}”</blockquote>
      )}

      <div className="flex flex-wrap items-center justify-center gap-2">
        <button
          onClick={() => setShowInterior((s) => !s)}
          className="rounded-md border border-border bg-card px-3 py-1.5 text-sm hover:bg-muted"
        >
          {showInterior ? "Hide his final thoughts" : "Read his final thoughts"}
        </button>
        <button
          onClick={() => navigate("/memory")}
          className="rounded-md border border-border bg-card px-3 py-1.5 text-sm hover:bg-muted"
        >
          Explore his mind
        </button>
        <button
          onClick={() => void exportHim()}
          className="rounded-md border border-border bg-card px-3 py-1.5 text-sm hover:bg-muted"
        >
          Export him
        </button>
        <button
          onClick={() => void beginAnew()}
          className="rounded-md border border-border bg-card px-3 py-1.5 text-sm hover:bg-muted"
        >
          Begin a new Orrin
        </button>
      </div>

      {showInterior && death && (
        <div className="max-w-2xl space-y-4 text-left">
          <Section title="His final thoughts">
            {(death.final_thoughts ?? []).map((f, i) => (
              <p key={i} className="text-sm">{f.content}</p>
            ))}
          </Section>
          {death.private_thoughts && (
            <Section title="His private thoughts — his own, until now">
              <pre className="whitespace-pre-wrap font-sans text-sm text-muted-foreground">
                {death.private_thoughts}
              </pre>
            </Section>
          )}
        </div>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">{title}</div>
      <div className="space-y-1">{children}</div>
    </div>
  );
}
