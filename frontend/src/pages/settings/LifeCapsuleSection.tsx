import { useCallback, useEffect, useState } from "react";
import { Archive, Download, FileText, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { apiBase, getTransport } from "@/lib/transport";
import { controlHeaders } from "./shared";

interface CapsuleEntry {
  run_id: string;
  file: string;
  size_bytes: number;
  built_at?: string;
  build_reason?: string;
  table_row_counts?: Record<string, number>;
}

interface CapsuleClaim {
  claim_id: string;
  claim: string;
  status: string;
}

interface CapsuleSummary {
  run_id: string;
  executive_summary_md?: string;
  run_summary?: {
    cycles_recorded?: number;
    outward_action_count?: number;
    outward_action_rate?: number;
  };
  artifact_summary?: { logged?: number; credited_novel?: number; dedupe_rate?: number };
  claims?: CapsuleClaim[];
}

// The evidence export (Part IX) — list sealed run capsules, build one on demand,
// download a `.orrinlife.zip`, and read its summary inline. Mirrors the diagnostics
// export contract: owner-only server-side, no silent telemetry, JSON for summary +
// build, binary zip for the download (which the native bridge can't proxy).
export function LifeCapsuleSection() {
  const [capsules, setCapsules] = useState<CapsuleEntry[] | null>(null);
  const [summary, setSummary] = useState<CapsuleSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const isBridge = getTransport().isBridge;

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase()}/api/life/capsules`, { headers: controlHeaders() });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const j = (await res.json()) as { capsules: CapsuleEntry[] };
      setCapsules(j.capsules);
    } catch {
      setNote("Couldn't list capsules (a control token may be required for a remote viewer).");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const build = async () => {
    setBusy(true);
    setNote("Sealing a capsule from the current run…");
    try {
      const res = await fetch(`${apiBase()}/api/life/capsule/build`, {
        method: "POST",
        headers: controlHeaders(),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setNote("Capsule sealed.");
      await load();
    } catch {
      setNote("Build failed.");
    } finally {
      setBusy(false);
    }
  };

  const view = async (run: string) => {
    setNote(null);
    try {
      const res = await fetch(`${apiBase()}/api/life/capsule/summary?run=${encodeURIComponent(run)}`, {
        headers: controlHeaders(),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setSummary((await res.json()) as CapsuleSummary);
    } catch {
      setNote("Couldn't read that capsule's summary.");
    }
  };

  const download = async (run: string) => {
    setNote("Preparing the capsule…");
    try {
      const res = await fetch(`${apiBase()}/api/life/capsule?run=${encodeURIComponent(run)}`, {
        headers: controlHeaders(),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const name =
        res.headers.get("content-disposition")?.match(/filename="(.+)"/)?.[1] ||
        `orrin_life_capsule_${run}.orrinlife.zip`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      a.click();
      URL.revokeObjectURL(url);
      setNote("Downloaded.");
    } catch {
      setNote("Download failed.");
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Archive className="h-4 w-4" /> Run Capsules
        </CardTitle>
        <CardDescription>
          One run, sealed whole — the evidence record. Each capsule holds the raw streams
          plus cleaned tables, a queryable database, metrics, and an evidence-linked
          claims ledger. Built automatically at shutdown and end-of-run; you can also
          seal one now.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="outline" disabled={busy} onClick={() => void build()}>
            <Archive className="mr-1.5 h-4 w-4" /> Seal a capsule now
          </Button>
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => void load()}>
            <RefreshCw className="mr-1.5 h-4 w-4" /> Refresh
          </Button>
        </div>

        {capsules && capsules.length === 0 && (
          <p className="text-xs text-muted-foreground">
            No capsules yet — seal one now, or one will appear when Orrin next shuts down.
          </p>
        )}

        {capsules && capsules.length > 0 && (
          <div className="space-y-1.5">
            {capsules.map((c) => (
              <div
                key={c.file}
                className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border bg-card/50 px-3 py-2 text-sm"
              >
                <div className="min-w-0">
                  <div className="font-medium tabular-nums">{c.run_id}</div>
                  <div className="text-xs text-muted-foreground">
                    {c.build_reason ?? "—"} · {(c.size_bytes / 1024 / 1024).toFixed(1)} MB
                    {c.table_row_counts?.cycles != null ? ` · ${c.table_row_counts.cycles} cycles` : ""}
                  </div>
                </div>
                <div className="flex shrink-0 gap-1.5">
                  <Button size="sm" variant="ghost" onClick={() => void view(c.run_id)}>
                    <FileText className="mr-1 h-3.5 w-3.5" /> View
                  </Button>
                  {!isBridge && (
                    <Button size="sm" variant="outline" onClick={() => void download(c.run_id)}>
                      <Download className="mr-1 h-3.5 w-3.5" /> Download
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {isBridge && capsules && capsules.length > 0 && (
          <p className="text-xs text-muted-foreground">
            Open Orrin in your browser to download a capsule file.
          </p>
        )}

        {summary && (
          <div className="space-y-2 rounded-md border border-ring bg-accent/20 p-3">
            <div className="flex items-center justify-between">
              <div className="text-sm font-medium">Run {summary.run_id}</div>
              <button
                className="text-xs text-muted-foreground hover:text-foreground"
                onClick={() => setSummary(null)}
              >
                Close
              </button>
            </div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-3">
              <SummaryStat label="cycles" value={summary.run_summary?.cycles_recorded} />
              <SummaryStat
                label="outward rate"
                value={summary.run_summary?.outward_action_rate}
              />
              <SummaryStat label="effects" value={summary.artifact_summary?.logged} />
              <SummaryStat label="credited" value={summary.artifact_summary?.credited_novel} />
              <SummaryStat label="dedupe" value={summary.artifact_summary?.dedupe_rate} />
            </div>
            {summary.claims && summary.claims.length > 0 && (
              <div className="space-y-1 border-t border-border pt-2">
                <div className="text-xs font-medium text-muted-foreground">Claims</div>
                {summary.claims.map((cl) => (
                  <div key={cl.claim_id} className="flex items-start justify-between gap-2 text-xs">
                    <span className="min-w-0">{cl.claim}</span>
                    <span
                      className={cn(
                        "shrink-0 font-medium",
                        cl.status === "supported"
                          ? "text-signal-ok"
                          : cl.status === "refuted"
                            ? "text-signal-warn"
                            : "text-muted-foreground",
                      )}
                    >
                      {cl.status}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {note && <p className="text-xs text-foreground">{note}</p>}
      </CardContent>
    </Card>
  );
}

function SummaryStat({ label, value }: { label: string; value?: number }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <span className="tabular-nums font-medium">{value ?? "—"}</span>
      <span className="text-muted-foreground">{label}</span>
    </div>
  );
}
