import { useState } from "react";
import { Network } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { API } from "@/lib/cognitive";
import { usePoll } from "@/lib/usePoll";
import { cn } from "@/lib/utils";
import PanelInfo from "./PanelInfo";
import { LexText, PanelSubtitle } from "./Lex";
import StaleBadge from "./StaleBadge";
import { Gauge, MiniBars, MiniGraph } from "./viz";

/** Box ③ — Symbolic mind. The no-LLM reasoning engine is the project's
 *  strongest claim and had no window: the ratio of queries answered without the
 *  LLM, the learned rule base, the causal graph, and per-domain rule coverage.
 *  Honesty caveat rendered first-class: when llm_calls == 0 the ratio is
 *  trivially 1.0 — the gauge says "LLM off" instead of a meaningless 100%. */

interface Rule {
  id?: string;
  conditions?: string[];
  conclusion?: string;
  confidence?: number;
  hits?: number;
  source?: string;
}
interface Edge { cause?: string; effect?: string; strength?: number; causal_score?: number; evidence_count?: number }
interface Progress {
  symbolic_ratio?: number; llm_calls?: number; symbolic_hits?: number; rules_total?: number;
  rules_added_today?: number; crystallized_today?: number; meta_rule_applications?: number;
  causal_graph_density?: number; avg_rule_depth?: number; top_meta_rule?: string;
}

export default function SymbolicModelPanel() {
  const data = usePoll<{
    progress?: Progress; llm_off?: boolean; rules_total?: number; rules?: Rule[];
    causal_total?: number; causal?: Edge[]; domains?: Record<string, { rule_total?: number; rule_hits?: number }>;
  }>(`${API}/symbolic?n=8`, 20_000);
  const [view, setView] = useState<"rules" | "causal">("rules");
  const p = data?.progress;
  const domains = Object.entries(data?.domains || {});

  return (
    <Card id="box-symbolic" className="flex h-full flex-col overflow-hidden">
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          <Network className="h-4 w-4" /> <LexText id="symbolic_title" />
          <PanelInfo
            title="Rule engine / knowledge"
            perspective="agent-accessible"
            what="The no-LLM reasoning engine: queries answered purely by its learned symbolic rules, the rule base itself (conditions → conclusion with confidence), and the causal graph built from its own interventions and observations."
            source="brain/data/symbolic_progress.json · symbolic_rules.json · causal_graph.json · world_model_stats.json"
            good="A high share answered without the LLM while rules keep being added AND forgotten (a living rule base). Note: in an LLM-off run the ratio is trivially 100%, so the gauge is suppressed."
            src={{ file: "brain/symbolic/rule_engine.py", start: 1, end: 70, label: "rule_engine" }}
          />
          <PanelSubtitle id="symbolic_sub" />
          <StaleBadge url={`${API}/symbolic`} pollMs={20_000} />
        </CardTitle>
        <span className="text-[11px] text-muted-foreground/60">{data?.rules_total ?? "—"} rules · {data?.causal_total ?? "—"} causal edges</span>
      </CardHeader>
      <CardContent className="scrollbar-thin min-h-0 flex-1 space-y-3 overflow-auto pb-3">
        {!p ? (
          <div className="py-8 text-center text-xs text-muted-foreground">No symbolic progress recorded yet.</div>
        ) : (
          <>
            <div className="flex items-center gap-3">
              {data?.llm_off ? (
                <Gauge value={1} text="LLM off" label="symbolic share" color="hsl(var(--muted-foreground))" size={70} />
              ) : (
                <Gauge value={Number(p.symbolic_ratio ?? 0)} label="without the LLM" color="hsl(var(--signal-ok))" size={70} />
              )}
              <div className="grid flex-1 grid-cols-2 gap-x-3 gap-y-1 text-[10.5px]">
                <Stat k="symbolic answers" v={p.symbolic_hits} />
                <Stat k="LLM calls" v={p.llm_calls} />
                <Stat k="rules added today" v={p.rules_added_today} />
                <Stat k="crystallized today" v={p.crystallized_today} />
                <Stat k="meta-rule uses" v={p.meta_rule_applications} />
                <Stat k="causal density" v={p.causal_graph_density} />
              </div>
            </div>
            {data?.llm_off && (
              <div className="rounded-md border border-border bg-muted/30 px-2 py-1 text-[9.5px] leading-snug text-muted-foreground">
                LLM-off run: every query is answered symbolically by definition, so the share gauge is suppressed rather than showing a meaningless 100%.
              </div>
            )}

            {domains.length > 0 && (
              <div>
                <div className="mb-1 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">Rule coverage by domain (hits / total)</div>
                <MiniBars
                  rows={domains.map(([d, s]) => ({
                    label: d.toLowerCase(),
                    value: s.rule_total ? (s.rule_hits || 0) / s.rule_total : 0,
                    title: `${s.rule_hits ?? 0} of ${s.rule_total ?? 0} rules have fired`,
                  }))}
                  color="hsl(var(--signal-accent))"
                />
              </div>
            )}

            <div>
              <div className="mb-1 flex items-center gap-2">
                {(["rules", "causal"] as const).map((k) => (
                  <button
                    key={k}
                    onClick={() => setView(k)}
                    className={cn("rounded px-1.5 py-0.5 text-[10px] font-medium transition-colors", view === k ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground")}
                  >
                    {k === "rules" ? "Top rules" : "Causal edges"}
                  </button>
                ))}
              </div>
              {view === "rules" ? (
                <div className="space-y-1">
                  {(data?.rules || []).map((r, i) => (
                    <div key={r.id || i} className="rounded-md border border-border bg-card/40 px-2 py-1.5 text-[10px]">
                      <div className="leading-snug text-foreground/85">
                        <span className="text-muted-foreground">{(r.conditions || []).join(" ∧ ") || "(no conditions)"}</span>
                        <span className="mx-1 text-muted-foreground/60">→</span>
                        <span className="font-medium">{r.conclusion || "—"}</span>
                      </div>
                      <div className="mt-0.5 flex gap-2 text-[9px] text-muted-foreground">
                        <span>conf {(Number(r.confidence ?? 0)).toFixed(2)}</span>
                        <span>{r.hits ?? 0} hits</span>
                        {r.source && <span className="ml-auto">{r.source}</span>}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="space-y-1">
                  {/* The causal graph as a graph (MiniGraph) — the edge list below is the detail. */}
                  {(data?.causal || []).length > 1 && (
                    <div className="rounded-md border border-border bg-card/40 px-1 pt-1">
                      <MiniGraph
                        edges={(data?.causal || [])
                          .filter((e) => e.cause && e.effect)
                          .map((e) => ({ from: String(e.cause), to: String(e.effect), weight: Number(e.causal_score ?? e.strength ?? 0) }))}
                      />
                    </div>
                  )}
                  {(data?.causal || []).map((e, i) => (
                    <div key={i} className="flex items-center gap-1.5 rounded-md border border-border bg-card/40 px-2 py-1 text-[10px]">
                      <span className="truncate font-mono text-foreground/85">{e.cause}</span>
                      <span className="text-muted-foreground/60">→</span>
                      <span className="min-w-0 flex-1 truncate text-foreground/85">{e.effect}</span>
                      <span className="tabular-nums text-muted-foreground" title={`evidence ${e.evidence_count ?? 0}`}>
                        {(Number(e.causal_score ?? e.strength ?? 0)).toFixed(2)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function Stat({ k, v }: { k: string; v: unknown }) {
  return (
    <div className="flex justify-between gap-2">
      <span className="truncate text-muted-foreground">{k}</span>
      <span className="font-mono tabular-nums text-foreground/85">{v == null ? "—" : String(v)}</span>
    </div>
  );
}
