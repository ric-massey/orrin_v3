import { useState } from "react";
import { Fingerprint } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { API } from "@/lib/cognitive";
import { usePoll } from "@/lib/usePoll";
import { cn } from "@/lib/utils";
import PanelInfo from "./PanelInfo";
import StaleBadge from "./StaleBadge";
import { LexText, PanelSubtitle } from "./Lex";
import { MiniBars, Timeline } from "./viz";

/** Box ⑦ — Self-model / identity. "Who it is" and how it changes — the
 *  self-model's identity / directive / knowledge domains, the dated
 *  belief-confidence revisions (before→after with the triggering goal), and
 *  the opinions it's formed. private_thoughts stays excluded by design. */

interface SelfModel {
  note?: string;
  identity?: string;
  emotion?: string;
  core_directive?: { statement?: string };
  core_values?: unknown[];
  traits?: unknown[];
  weaknesses?: string[];
  knowledge_domains?: Record<string, number>;
  recent_changes?: string[];
}
interface Revision { domain?: string; timestamp?: string; goal?: string; delta?: number; new_confidence?: number }
interface Opinion { topic?: string; view?: string; confidence?: number; updated_at?: string; evidence_count?: number }

export default function SelfModelPanel() {
  const data = usePoll<{ model?: SelfModel; revisions?: Revision[]; opinions?: Opinion[] }>(`${API}/self?n=30`, 30_000);
  const [view, setView] = useState<"identity" | "revisions" | "opinions">("identity");
  const m = data?.model;
  const domains = Object.entries(m?.knowledge_domains || {}).sort((a, b) => b[1] - a[1]);
  const revisions = data?.revisions || [];
  const opinions = data?.opinions || [];

  return (
    <Card id="box-self" className="flex h-full flex-col overflow-hidden">
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="flex min-w-0 items-center gap-2 text-sm font-medium text-muted-foreground">
          <Fingerprint className="h-4 w-4" /> <LexText id="self_title" />
          <PanelInfo
            title="System self-descriptor / identity"
            perspective="agent-accessible"
            what="Its self-descriptor: its one-line identity and core directive, per-domain confidence in its own knowledge, named weaknesses, the dated belief revisions (confidence moved after a goal succeeded or failed), and the opinions it's formed from its own experience. One thing is deliberately absent: its protected interior, which this dashboard does not read."
            source="GET /api/identity over brain/data/identity_state.json · identity_belief_revisions.json · opinions.json"
            good="An identity that REVISES — confidence moving with real outcomes, opinions accumulating evidence — rather than a static description."
            src={{ file: "brain/utils/self_model.py", start: 1, end: 60, label: "self_model" }}
          />
          <PanelSubtitle id="self_sub" />
          <StaleBadge url={`${API}/self`} pollMs={30_000} />
        </CardTitle>
        <div className="flex rounded-md border border-border p-0.5">
          {(["identity", "revisions", "opinions"] as const).map((k) => (
            <button
              key={k}
              onClick={() => setView(k)}
              className={cn("rounded px-1.5 py-0.5 text-[10px] font-medium capitalize transition-colors", view === k ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground")}
            >
              {k}
            </button>
          ))}
        </div>
      </CardHeader>
      <CardContent className="scrollbar-thin min-h-0 flex-1 space-y-3 overflow-auto pb-3">
        {!m ? (
          <div className="py-8 text-center text-xs text-muted-foreground">No self-model yet.</div>
        ) : view === "identity" ? (
          <>
            <div className="rounded-lg border border-border bg-card/60 px-3 py-2">
              <p className="text-[12.5px] font-medium leading-snug text-foreground/95">{m.identity || "—"}</p>
              {m.core_directive?.statement && (
                <p className="mt-1 text-[10.5px] text-muted-foreground">directive: {m.core_directive.statement}</p>
              )}
              {m.note && <p className="mt-1 text-[10.5px] italic text-muted-foreground/80">“{m.note}”</p>}
            </div>
            {domains.length > 0 && (
              <div>
                <div className="mb-1 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">Knowledge-domain confidence (its own estimate)</div>
                <MiniBars rows={domains.map(([d, v]) => ({ label: d.toLowerCase(), value: Number(v) }))} />
              </div>
            )}
            {(m.weaknesses || []).length > 0 && (
              <div className="flex flex-wrap items-center gap-1">
                <span className="text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">Named weaknesses</span>
                {(m.weaknesses || []).map((w) => (
                  <span key={w} className="rounded bg-signal-warn/15 px-1.5 py-0 text-[9.5px] text-signal-warn">{w.toLowerCase()}</span>
                ))}
              </div>
            )}
            {(m.recent_changes || []).length > 0 && (
              <div>
                <div className="mb-1 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">Recent changes</div>
                {(m.recent_changes || []).slice(-3).map((c, i) => (
                  <p key={i} className="text-[10px] leading-snug text-muted-foreground">{c}</p>
                ))}
              </div>
            )}
          </>
        ) : view === "revisions" ? (
          <Timeline
            emptyText="No belief revisions yet — confidence moves when goals succeed or fail."
            rows={[...revisions].reverse().map((r) => ({
              ts: r.timestamp,
              title: `${r.domain ?? "?"} ${Number(r.delta ?? 0) >= 0 ? "+" : ""}${Number(r.delta ?? 0).toFixed(2)} → ${Number(r.new_confidence ?? 0).toFixed(2)}`,
              detail: r.goal ? `after: ${r.goal}` : undefined,
              color: Number(r.delta ?? 0) >= 0 ? "hsl(var(--signal-ok))" : "hsl(var(--signal-error))",
            }))}
          />
        ) : opinions.length === 0 ? (
          <div className="py-8 text-center text-xs text-muted-foreground">No opinions formed yet.</div>
        ) : (
          <div className="space-y-1">
            {[...opinions].reverse().map((o, i) => (
              <div key={i} className="rounded-md border border-border bg-card/40 px-2 py-1.5">
                <div className="flex items-baseline gap-2">
                  <span className="text-[10px] font-semibold capitalize text-foreground/90">{o.topic}</span>
                  <span className="ml-auto text-[9px] tabular-nums text-muted-foreground" title={`${o.evidence_count ?? 0} pieces of evidence`}>
                    conf {Number(o.confidence ?? 0).toFixed(2)} · ev {o.evidence_count ?? 0}
                  </span>
                </div>
                <p className="mt-0.5 text-[10.5px] leading-snug text-muted-foreground" title={o.view}>{o.view}</p>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
