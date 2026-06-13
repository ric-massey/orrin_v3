import { HeartPulse } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { API } from "@/lib/cognitive";
import { usePoll } from "@/lib/usePoll";
import PanelInfo from "./PanelInfo";
import { LexText, PanelSubtitle } from "./Lex";
import StaleBadge from "./StaleBadge";

/** Box ⑪ — System health (the ops view). health_state + the record_failure
 *  ledger (failures.jsonl — per-site counts, the creator's "what is quietly
 *  broken" table) + recent incidents with what self-repair saw. Replaces
 *  tailing four log files; pairs with Fix 10.5's live failure stream. */

interface FailSite { site: string; count: number; last_error?: string; last_ts?: string }
interface Incident { id?: string; ts?: string; phase?: string; type?: string; msg?: string }

export default function HealthPanel() {
  const data = usePoll<{
    health?: { status?: string; streak?: number; sick_streak?: number; total_healthy_cycles?: number; cycle?: number };
    failing_sites?: FailSite[];
    failure_lines?: number;
    incidents?: Incident[];
  }>(`${API}/health?n=8`, 15_000);
  const h = data?.health;
  const status = String(h?.status || "unknown");
  const ok = ["healthy", "nominal", "ok"].includes(status);
  const sites = data?.failing_sites || [];
  const incidents = data?.incidents || [];

  return (
    <Card id="box-health" className="flex h-full flex-col overflow-hidden">
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          <HeartPulse className="h-4 w-4" /> <LexText id="health_title" />
          <PanelInfo
            title="System health (ops)"
            what="Is the organism healthy: the watchdog's overall status and healthy streak, the per-site failure counts from the record_failure ledger (every guarded subsystem that's been quietly erroring), and recent incidents with their exception type."
            source="brain/data/health_state.json · failures.jsonl · incidents.jsonl"
            good="Status nominal with a growing streak, an EMPTY failing-sites table, and no fresh incidents. Failures here also stream live into the console's ERROR filter (Fix 10.5)."
            src={{ file: "brain/utils/failure_counter.py", start: 52, end: 120, label: "record_failure" }}
          />
          <PanelSubtitle id="health_sub" />
          <StaleBadge url={`${API}/health`} pollMs={15_000} />
        </CardTitle>
        <span
          className="rounded px-1.5 py-0.5 text-[10px] font-semibold capitalize"
          style={{
            background: ok ? "hsl(var(--signal-ok) / 0.15)" : "hsl(var(--signal-error) / 0.15)",
            color: ok ? "hsl(var(--signal-ok))" : "hsl(var(--signal-error))",
          }}
        >
          {status}
        </span>
      </CardHeader>
      <CardContent className="scrollbar-thin min-h-0 flex-1 space-y-3 overflow-auto pb-3">
        {h && (
          <div className="grid grid-cols-3 gap-2 text-center">
            <div>
              <div className="text-lg font-semibold tabular-nums">{h.streak ?? "—"}</div>
              <div className="text-[9px] uppercase tracking-wide text-muted-foreground">healthy streak</div>
            </div>
            <div>
              <div className="text-lg font-semibold tabular-nums" style={{ color: Number(h.sick_streak ?? 0) > 0 ? "hsl(var(--signal-error))" : undefined }}>
                {h.sick_streak ?? "—"}
              </div>
              <div className="text-[9px] uppercase tracking-wide text-muted-foreground">sick streak</div>
            </div>
            <div>
              <div className="text-lg font-semibold tabular-nums">{h.total_healthy_cycles ?? "—"}</div>
              <div className="text-[9px] uppercase tracking-wide text-muted-foreground">healthy cycles</div>
            </div>
          </div>
        )}

        <div>
          <div className="mb-1 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">
            Top failing sites {data?.failure_lines ? `(${data.failure_lines} ledger lines)` : ""}
          </div>
          {sites.length === 0 ? (
            <div className="rounded-md border border-border bg-card/40 px-2 py-1.5 text-[10.5px] text-muted-foreground">
              Nothing quietly broken — the failure ledger is clean.
            </div>
          ) : (
            <div className="space-y-1">
              {sites.map((s) => (
                <div key={s.site} className="rounded-md border border-border bg-card/40 px-2 py-1" title={s.last_error}>
                  <div className="flex items-baseline gap-2">
                    <span className="min-w-0 flex-1 truncate font-mono text-[10px] text-foreground/85">{s.site}</span>
                    <span className="text-[10px] font-semibold tabular-nums text-signal-error">×{s.count}</span>
                  </div>
                  {s.last_error && <p className="truncate text-[9px] text-muted-foreground">{s.last_error}</p>}
                </div>
              ))}
            </div>
          )}
        </div>

        {incidents.length > 0 && (
          <div>
            <div className="mb-1 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">Recent incidents</div>
            <div className="space-y-1">
              {[...incidents].reverse().map((inc, i) => (
                <div key={inc.id || i} className="rounded-md border border-border bg-card/40 px-2 py-1">
                  <div className="flex gap-2 text-[10px]">
                    <span className="font-mono font-semibold text-signal-warn">{inc.type || "?"}</span>
                    <span className="text-muted-foreground">{inc.phase}</span>
                    <span className="ml-auto text-[9px] text-muted-foreground/70">{String(inc.ts || "").slice(0, 19).replace("T", " ")}</span>
                  </div>
                  {inc.msg && <p className="truncate text-[10px] text-foreground/80" title={inc.msg}>{inc.msg}</p>}
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
