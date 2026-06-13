import { useState } from "react";
import { Waves } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { API } from "@/lib/cognitive";
import { usePoll } from "@/lib/usePoll";
import { cn } from "@/lib/utils";
import PanelInfo from "./PanelInfo";
import { LexText, PanelSubtitle } from "./Lex";
import StaleBadge from "./StaleBadge";

/** Box ⑩ — Tensions, rumination & second-order volition. The "is anything
 *  wrong / what is he wrestling with" view — and the volition timeline (what he
 *  wants to WANT: stance · desire · statement), the most philosophically
 *  interesting artifact in brain/data. */

interface Tension { id?: string; title?: string; description?: string; status?: string; source?: string; cycles_active?: number; created?: string }
interface Loop { content?: string; mode?: string; charge?: number; return_count?: number; suppressed_count?: number }
interface Volition { ts?: number; stance?: string; desire?: string; statement?: string }

const STANCE_COLOR: Record<string, string> = {
  own: "hsl(var(--signal-ok))",
  endorse: "hsl(var(--signal-ok))",
  disown: "hsl(var(--signal-error))",
  resist: "hsl(var(--signal-error))",
  neutral: "hsl(var(--muted-foreground))",
};

export default function TensionsPanel() {
  const data = usePoll<{ tensions?: Tension[]; rumination?: Loop[]; volition?: Volition[] }>(`${API}/tensions?n=20`, 20_000);
  const [view, setView] = useState<"now" | "volition">("now");
  const tensions = (data?.tensions || []).filter((t) => (t.status || "active") !== "resolved");
  const loops = data?.rumination || [];
  const volition = data?.volition || [];

  return (
    <Card id="box-tensions" className="flex h-full flex-col overflow-hidden">
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          <Waves className="h-4 w-4" /> <LexText id="tensions_title" />
          <PanelInfo
            title="Tensions, rumination & second-order volition"
            what="What he's wrestling with: unresolved tensions (with how long they've been active), rumination loops that keep returning (brooding, problem-solving…), and the second-order volition timeline — periodic reflections where he owns or disowns the desire currently driving him."
            source="brain/data/tensions.json · rumination_loops.json · second_order_volition.json"
            good="Tensions that RESOLVE rather than accumulate, loops whose return counts fall, and volition statements that show real stance-taking — not all 'neutral'."
            src={{ file: "brain/cognition/selfhood/second_order_volition.py", start: 1, end: 70, label: "second_order_volition" }}
          />
          <PanelSubtitle id="tensions_sub" />
          <StaleBadge url={`${API}/tensions`} pollMs={20_000} />
        </CardTitle>
        <div className="flex rounded-md border border-border p-0.5">
          {(["now", "volition"] as const).map((k) => (
            <button
              key={k}
              onClick={() => setView(k)}
              className={cn("rounded px-2 py-0.5 text-[10px] font-medium capitalize transition-colors", view === k ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground")}
            >
              {k === "now" ? `Now · ${tensions.length}` : "What he wants to want"}
            </button>
          ))}
        </div>
      </CardHeader>
      <CardContent className="scrollbar-thin min-h-0 flex-1 space-y-3 overflow-auto pb-3">
        {view === "now" ? (
          <>
            {tensions.length === 0 && loops.length === 0 && (
              <div className="py-8 text-center text-xs text-muted-foreground">Nothing he's wrestling with right now.</div>
            )}
            {tensions.length > 0 && (
              <div>
                <div className="mb-1 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">Active tensions</div>
                <div className="space-y-1">
                  {tensions.map((t, i) => {
                    const long = Number(t.cycles_active ?? 0) >= 200;
                    return (
                      <div key={t.id || i} className={cn("rounded-md border px-2 py-1.5", long ? "border-signal-warn/50 bg-signal-warn/10" : "border-border bg-card/40")}>
                        <p className="text-[11px] leading-snug text-foreground/90" title={t.description}>{t.description || t.title}</p>
                        <div className="mt-0.5 flex gap-2 text-[9px] text-muted-foreground">
                          {t.source && <span>{t.source}</span>}
                          <span className={cn("ml-auto tabular-nums", long && "font-semibold text-signal-warn")}>
                            {t.cycles_active ?? 0} cycles active
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
            {loops.length > 0 && (
              <div>
                <div className="mb-1 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">Rumination loops</div>
                <div className="space-y-1">
                  {loops.map((l, i) => (
                    <div key={i} className="rounded-md border border-border bg-card/40 px-2 py-1.5">
                      <p className="truncate text-[10.5px] text-foreground/85" title={l.content}>{l.content}</p>
                      <div className="mt-0.5 flex gap-2 text-[9px] text-muted-foreground">
                        {l.mode && <span className="italic">{l.mode}</span>}
                        <span>returned ×{l.return_count ?? 0}</span>
                        {Number(l.suppressed_count ?? 0) > 0 && <span>quieted ×{l.suppressed_count}</span>}
                        <span className="ml-auto tabular-nums">charge {(Number(l.charge ?? 0)).toFixed(2)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        ) : volition.length === 0 ? (
          <div className="py-8 text-center text-xs text-muted-foreground">No second-order reflections yet (he reflects every ~20 cycles).</div>
        ) : (
          <div className="space-y-1">
            {[...volition].reverse().map((v, i) => {
              const color = STANCE_COLOR[(v.stance || "").toLowerCase()] || STANCE_COLOR.neutral;
              return (
                <div key={i} className="rounded-md border border-border bg-card/40 px-2 py-1.5" style={{ borderLeft: `3px solid ${color}` }}>
                  <p className="text-[11px] italic leading-snug text-foreground/90">“{v.statement}”</p>
                  <div className="mt-0.5 flex gap-2 text-[9px] text-muted-foreground">
                    <span style={{ color }}>{v.stance || "—"}</span>
                    <span>desire: {v.desire || "—"}</span>
                    {v.ts && <span className="ml-auto">{new Date(Number(v.ts) * 1000).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</span>}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
