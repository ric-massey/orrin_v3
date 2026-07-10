import { FileText, Globe, Bell, ListChecks } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { usePolledJSON } from "@/lib/usePolled";
import { agoLabel, cn } from "@/lib/utils";

/**
 * /actions — the real-world action ledger (Companion & Presence plan, R2): one
 * time-ordered audit feed of everything Orrin DID to the actual machine, joined
 * from the effect ledger (files, notes, tools, replies), the egress ledger
 * (outbound network — counts only, never content), and the OS-notification
 * ledger. Timeline covers "what happened"; this is "what he did." It's the
 * trust surface every outward-facing capability stands on (§0.6).
 */

interface ActionRow {
  ts: number;
  iso: string;
  source: "effect" | "egress" | "notification";
  kind: string;
  detail?: string;
  goal_id?: string | null;
  significance?: number;
  dedupe?: boolean;
}

const SOURCE_META: Record<ActionRow["source"], { icon: typeof FileText; label: string; cls: string }> = {
  effect: { icon: FileText, label: "made", cls: "text-signal-ok" },
  egress: { icon: Globe, label: "network", cls: "text-signal-warn" },
  notification: { icon: Bell, label: "notified", cls: "text-primary" },
};

// The effect ledger's kinds, in plain terms.
const KIND_LABEL: Record<string, string> = {
  file_write: "wrote a file",
  tool_written: "authored a tool",
  tool_run_effect: "ran a tool that changed something",
  note_novel: "left a note",
  message_answered: "answered a message",
  code_committed: "committed code",
  external_post: "posted externally",
  tracked_work: "advanced tracked work",
  symbolic_artifact: "crystallized a finding",
  bookkeeping: "self-model bookkeeping",
  os_notification: "sent an OS notification",
  openai: "called the language model",
  serper: "ran a web search",
  web: "fetched a web page",
  finetune: "uploaded fine-tune data",
};

export default function Actions() {
  const feed = usePolledJSON<{ actions: ActionRow[]; total: number }>("/api/actions?n=300", 6000);
  const rows = feed?.actions ?? [];

  return (
    <div className="mx-auto w-full max-w-3xl space-y-5 px-4 py-6 sm:px-6">
      <div className="space-y-1">
        <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight">
          <ListChecks className="h-5 w-5" /> Action ledger
        </h1>
        <p className="text-sm text-muted-foreground">
          Everything Orrin has actually done to this machine and beyond it —
          files written, notes left, tools run, every outbound network call
          (counts only, never content), every notification. If it isn't here, he
          didn't do it.
        </p>
      </div>

      {rows.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            No outward actions recorded yet. This fills in the moment he makes,
            sends, or fetches anything real.
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="divide-y divide-border p-0">
            {rows.map((r, i) => {
              const meta = SOURCE_META[r.source] ?? SOURCE_META.effect;
              return (
                <div key={`${r.ts}-${i}`} className="flex items-center gap-3 px-4 py-2.5">
                  <meta.icon className={cn("h-4 w-4 shrink-0", meta.cls)} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm">
                      {KIND_LABEL[r.kind] ?? r.kind}
                      {r.dedupe && (
                        <span className="ml-1.5 text-xs text-muted-foreground">(duplicate — no credit)</span>
                      )}
                    </div>
                    {(r.detail || r.goal_id) && (
                      <div className="truncate text-xs text-muted-foreground">
                        {r.detail}
                        {r.detail && r.goal_id ? " · " : ""}
                        {r.goal_id ? `for goal ${r.goal_id}` : ""}
                      </div>
                    )}
                  </div>
                  <span className="shrink-0 text-xs tabular-nums text-muted-foreground" title={r.iso}>
                    {r.ts ? agoLabel(r.ts) : ""}
                  </span>
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
