import { useState } from "react";
import { ChevronDown, FlaskConical } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { API } from "@/lib/cognitive";
import { usePoll } from "@/lib/usePoll";
import { cn } from "@/lib/utils";
import PanelInfo from "./PanelInfo";
import { LexText, PanelSubtitle } from "./Lex";
import StaleBadge from "./StaleBadge";
import { Sparkline, statusColor } from "./viz";

/** Box ① — Benchmarks (B1–B5). The headline "is he actually working" answer,
 *  previously visible only by reading benchmark_results.json. Fail and not_run
 *  states render first-class — a box that only looks right when everything
 *  passes is the same class of dishonesty Fixes 1–2 removed. */

interface Bench {
  title?: string;
  tests?: string;
  success?: string;
  status?: string; // pass | fail | not_run
  required_cycles?: number;
  curve?: [number, number][];
  hint?: string;
  [k: string]: unknown;
}

const META_KEYS = new Set(["title", "tests", "kind", "required_cycles", "how", "success", "status", "curve", "hint", "note"]);

function benchStatus(s?: string): { color: string; label: string } {
  if (s === "pass") return { color: statusColor("ok"), label: "PASS" };
  if (s === "fail") return { color: statusColor("err"), label: "FAIL" };
  return { color: statusColor("off"), label: s === "not_run" ? "NOT RUN" : (s || "?").toUpperCase() };
}

export default function BenchmarkPanel() {
  const data = usePoll<{ evaluated_at?: string; sample_count?: number; benchmarks?: Record<string, Bench> }>(`${API}/benchmarks`, 30_000);
  const [open, setOpen] = useState<string | null>(null);
  const benches = Object.entries(data?.benchmarks || {}).sort(([a], [b]) => a.localeCompare(b));
  const passed = benches.filter(([, b]) => b.status === "pass").length;

  return (
    <Card id="box-benchmarks" className="flex h-full flex-col overflow-hidden">
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          <FlaskConical className="h-4 w-4" /> <LexText id="benchmarks_title" />
          <PanelInfo
            title="Benchmarks (B1–B5)"
            what="Five standing capability benchmarks evaluated from real run data: memory boundedness, affect-driven switching, offline (no-LLM) planning, satiety-based goal closure, and self-repair. This is the honest scoreboard — fails and not-yet-run benchmarks are shown as such."
            source="brain/data/benchmark_results.json (evaluator: brain/benchmarks/__init__.py)"
            good="All five green. A FAIL is information, not embarrassment — e.g. B1 failing means long-term memory is still growing instead of plateauing."
            src={{ file: "brain/benchmarks/__init__.py", start: 1, end: 80, label: "benchmark evaluator" }}
          />
          <PanelSubtitle id="benchmarks_sub" />
          <StaleBadge url={`${API}/benchmarks`} pollMs={30_000} />
        </CardTitle>
        <span className="text-[11px] text-muted-foreground/60">
          {benches.length ? `${passed}/${benches.length} passing` : "—"}
        </span>
      </CardHeader>
      <CardContent className="scrollbar-thin min-h-0 flex-1 space-y-1 overflow-auto pb-3">
        {benches.length === 0 && (
          <div className="py-8 text-center text-xs text-muted-foreground">No benchmark results yet (run the suite to populate benchmark_results.json).</div>
        )}
        {benches.map(([key, b]) => {
          const st = benchStatus(b.status);
          const isOpen = open === key;
          const extras = Object.entries(b).filter(([k, v]) => !META_KEYS.has(k) && (typeof v === "number" || typeof v === "string" || typeof v === "boolean"));
          return (
            <div key={key} className="rounded-md border border-border bg-card/40">
              <button onClick={() => setOpen(isOpen ? null : key)} className="flex w-full items-center gap-2 px-2 py-1.5 text-left">
                <span className="w-7 font-mono text-[11px] font-semibold text-foreground/80">{key}</span>
                <span className="min-w-0 flex-1 truncate text-[11px] text-foreground/85" title={b.tests}>{b.title || "—"}</span>
                <span className="rounded px-1.5 py-0.5 text-[9px] font-bold tracking-wide" style={{ background: `${st.color}22`, color: st.color }}>
                  {st.label}
                </span>
                <ChevronDown className={cn("h-3 w-3 text-muted-foreground transition-transform", isOpen && "rotate-180")} />
              </button>
              {isOpen && (
                <div className="space-y-1.5 border-t border-border/60 px-2 py-2 text-[10.5px]">
                  {b.tests && <p className="leading-snug text-foreground/85">{b.tests}</p>}
                  {b.success && (
                    <p className="leading-snug text-muted-foreground"><span className="font-semibold text-foreground/70">Pass when:</span> {b.success}</p>
                  )}
                  {Array.isArray(b.curve) && b.curve.length > 1 && (
                    <div className="flex items-center gap-2">
                      <Sparkline points={b.curve.map((p) => p[1])} width={150} height={32} color={st.color} />
                      <span className="text-[9.5px] leading-snug text-muted-foreground">
                        entries vs cycle — the proof is a plateau, not a line
                      </span>
                    </div>
                  )}
                  {extras.length > 0 && (
                    <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
                      {extras.map(([k, v]) => (
                        <div key={k} className="flex justify-between gap-2">
                          <span className="truncate text-muted-foreground">{k.replace(/_/g, " ")}</span>
                          <span className="font-mono tabular-nums text-foreground/85">{String(v)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  {b.hint && <p className="leading-snug text-muted-foreground/80">↳ {b.hint}</p>}
                </div>
              )}
            </div>
          );
        })}
        {data?.evaluated_at && (
          <div className="pt-1 text-[9px] text-muted-foreground/60">
            evaluated {String(data.evaluated_at).slice(0, 19).replace("T", " ")} · {data.sample_count ?? "?"} samples
          </div>
        )}
      </CardContent>
    </Card>
  );
}
