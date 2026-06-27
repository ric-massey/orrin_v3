import { useState } from "react";
import { Download, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { apiBase } from "@/lib/transport";
import { controlHeaders, postSettings, type SettingsStatus } from "./shared";
import { ToggleRow } from "./ToggleRow";

interface UpdateInfo {
  checked?: boolean;
  available?: boolean;
  current?: string;
  latest?: string;
  url?: string;
  error?: string;
}

export function UpdatesSection({
  status,
  onChanged,
}: {
  status: SettingsStatus | null;
  onChanged: () => void | Promise<void>;
}) {
  const version = status?.version || "—";
  const autoCheck = !!status?.prefs?.auto_update_check;
  const [info, setInfo] = useState<UpdateInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const checkNow = async () => {
    setBusy(true);
    setNote(null);
    try {
      const res = await fetch(`${apiBase()}/api/update?force=1`, { headers: controlHeaders() });
      setInfo((await res.json()) as UpdateInfo);
    } catch {
      setInfo({ error: "Couldn't reach the update check." });
    } finally {
      setBusy(false);
    }
  };

  const backUpAndGet = async () => {
    setBusy(true);
    setNote("Exporting the state archive as a backup first…");
    try {
      const res = await fetch(`${apiBase()}/api/update/prepare`, {
        method: "POST",
        headers: controlHeaders(),
      });
      const j = (await res.json()) as { ok?: boolean; backup?: string };
      if (j.ok) {
        setNote("State archive backed up. Opening the download…");
        if (info?.url) window.open(info.url, "_blank");
      } else {
        setNote("Backup failed — not opening the download.");
      }
    } catch {
      setNote("Backup failed — not opening the download.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Sparkles className="h-4 w-4" /> Updates
        </CardTitle>
        <CardDescription>
          Orrin is version {version}. Before any update, the whole runtime state is exported
          as a backup and carried forward — you're never one update away from losing it.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <ToggleRow
          label="Check for new versions automatically"
          warn="Periodically asks GitHub whether a newer Orrin is published. Off by default — nothing checks the network until you turn this on."
          checked={autoCheck}
          onChange={async (v) => {
            await postSettings({ prefs: { auto_update_check: v } });
            await onChanged();
          }}
        />
        <div className="flex flex-wrap items-center gap-3">
          <Button size="sm" variant="outline" disabled={busy} onClick={() => void checkNow()}>
            Check now
          </Button>
          {info?.checked && !info.available && !info.error && (
            <span className="text-xs text-signal-ok">You're up to date.</span>
          )}
          {info?.error && <span className="text-xs text-signal-warn">{info.error}</span>}
        </div>
        {info?.available && (
          <div className="rounded-md border border-ring bg-accent/30 p-3 text-sm">
            <div className="font-medium">A new Orrin is available — v{info.latest}</div>
            <p className="mt-0.5 text-xs text-muted-foreground">
              The current runtime state is exported first, then carried forward. If a version
              needs a fresh start, the old state is kept as that export.
            </p>
            <Button size="sm" variant="outline" className="mt-2" disabled={busy} onClick={() => void backUpAndGet()}>
              <Download className="mr-1.5 h-4 w-4" /> Back up &amp; get the update
            </Button>
          </div>
        )}
        {note && <p className="text-xs text-foreground">{note}</p>}
      </CardContent>
    </Card>
  );
}
