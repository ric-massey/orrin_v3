import { useState } from "react";
import { Download, Eye, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { apiBase, getTransport } from "@/lib/transport";
import { usePolledJSON } from "@/lib/usePolled";
import { controlHeaders, postSettings, type SettingsStatus } from "./shared";
import { ToggleRow } from "./ToggleRow";

interface EgressFeed {
  services?: Record<string, { requests?: number; approx_tokens?: number; last_ts?: number }>;
  total_requests?: number;
}

interface Capability {
  key: string;
  label: string;
  why: string;
  state: "granted" | "denied" | "unknown" | "not_required";
  deep_link?: string;
  off_message?: string;
}
interface PermissionsFeed {
  platform?: string;
  capabilities?: Capability[];
}

// §10.6 — a capability's grant state as a short, honest badge.
function CapabilityState({ state }: { state: Capability["state"] }) {
  const map: Record<Capability["state"], { text: string; cls: string }> = {
    granted: { text: "On", cls: "text-signal-ok" },
    not_required: { text: "On", cls: "text-signal-ok" },
    denied: { text: "Off", cls: "text-destructive" },
    unknown: { text: "Ask when needed", cls: "text-muted-foreground" },
  };
  const { text, cls } = map[state];
  return <span className={cn("text-xs font-medium tabular-nums", cls)}>{text}</span>;
}

export function TrustSection({
  status,
  onChanged,
}: {
  status: SettingsStatus | null;
  onChanged: () => void | Promise<void>;
}) {
  const egress = usePolledJSON<EgressFeed>("/api/egress", 6000);
  const perms = usePolledJSON<PermissionsFeed>("/api/permissions", 10000);
  const capabilities = perms?.capabilities ?? [];
  const services = egress?.services ?? {};
  const rows = Object.entries(services);
  const nothingLeaves = (egress?.total_requests ?? 0) === 0;

  const toggle = async (key: "allow_finetune" | "allow_remote_viewing", value: boolean) => {
    await postSettings({ prefs: { [key]: value } });
    await onChanged();
  };

  const isBridge = getTransport().isBridge;
  const [diagNote, setDiagNote] = useState<string | null>(null);
  const exportDiagnostics = async () => {
    setDiagNote("Bundling logs…");
    try {
      const res = await fetch(`${apiBase()}/api/diagnostics`, { headers: controlHeaders() });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const name =
        res.headers.get("content-disposition")?.match(/filename="(.+)"/)?.[1] ||
        "orrin-diagnostics.zip";
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      a.click();
      URL.revokeObjectURL(url);
      setDiagNote("Saved — logs and state only, never its memory or interior content.");
    } catch {
      setDiagNote("Export failed (a control token may be required for a remote viewer).");
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Eye className="h-4 w-4" /> Privacy &amp; Trust
        </CardTitle>
        <CardDescription>Exactly what leaves this device — by count, never content.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div>
          <div className="mb-1.5 text-sm font-medium">Data leaving this device — last 24h</div>
          {rows.length > 0 ? (
            <div className="space-y-1">
              {rows.map(([svc, v]) => (
                <div key={svc} className="flex items-center justify-between text-sm">
                  <span className="capitalize">{svc}</span>
                  <span className="tabular-nums text-muted-foreground">
                    {v.requests ?? 0} requests
                    {v.approx_tokens ? ` · ~${v.approx_tokens.toLocaleString()} tokens` : ""}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="flex items-center gap-1.5 text-sm text-signal-ok">
              <ShieldCheck className="h-4 w-4" /> Nothing leaves your machine.
            </p>
          )}
          {!nothingLeaves && status?.symbolic_only && (
            <p className="mt-1 text-xs text-muted-foreground">
              With no keys set, Orrin runs fully on-device — nothing new leaves your machine.
            </p>
          )}
        </div>

        {capabilities.length > 0 && (
          <div className="border-t border-border pt-4">
            <div className="text-sm font-medium">What Orrin can reach</div>
            <p className="mt-0.5 mb-2 text-xs text-muted-foreground">
              The runtime asks your OS before it can see your screen or reach other apps.
              Anything off here just means that input is closed — it carries on without it.
            </p>
            <div className="space-y-2">
              {capabilities.map((c) => (
                <div key={c.key} className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-sm">{c.label}</div>
                    <div className="text-xs text-muted-foreground">{c.why}</div>
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-0.5">
                    <CapabilityState state={c.state} />
                    {c.state === "denied" && c.deep_link && (
                      <a
                        href={c.deep_link}
                        className="text-xs text-primary underline-offset-2 hover:underline"
                      >
                        Open System Settings
                      </a>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <ToggleRow
          label="Let Orrin fine-tune on its own conversations"
          warn="Uploads its best conversation traces (your words included) to OpenAI to train a private model, and spends on your account. Off by default."
          checked={!!status?.prefs?.allow_finetune}
          disabled={!status?.configured.openai || (status?.prefs?.llm_provider ?? "openai") !== "openai"}
          disabledNote={
            !status?.configured.openai
              ? "Requires an OpenAI key."
              : (status?.prefs?.llm_provider ?? "openai") !== "openai"
                ? "Fine-tuning is only available with the OpenAI provider."
                : undefined
          }
          onChange={(v) => toggle("allow_finetune", v)}
        />

        <ToggleRow
          label="Allow viewing from another device"
          warn="Opens a local network port so you can watch Orrin from your phone or another computer. Off means zero open ports. Takes effect on restart."
          checked={!!status?.prefs?.allow_remote_viewing}
          onChange={(v) => toggle("allow_remote_viewing", v)}
        />

        <div className="border-t border-border pt-4">
          <div className="text-sm font-medium">Diagnostics</div>
          <p className="mt-0.5 text-xs text-muted-foreground">
            If something goes wrong, export a bundle of recent logs and its state — logs
            only, never its memory or interior content. Nothing is sent automatically; you choose
            to share it.
          </p>
          {isBridge ? (
            <p className="mt-2 text-xs text-muted-foreground">
              Open Orrin in your browser to export diagnostics.
            </p>
          ) : (
            <Button
              size="sm"
              variant="outline"
              className="mt-2"
              onClick={() => void exportDiagnostics()}
            >
              <Download className="mr-1.5 h-4 w-4" /> Export diagnostics…
            </Button>
          )}
          {diagNote && <p className="mt-1.5 text-xs text-foreground">{diagNote}</p>}
        </div>
      </CardContent>
    </Card>
  );
}
