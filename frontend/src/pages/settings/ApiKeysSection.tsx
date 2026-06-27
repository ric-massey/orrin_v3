import { useState } from "react";
import { KeyRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { apiPost } from "@/lib/transport";
import { controlHeaders, type SettingsStatus } from "./shared";

export function ApiKeysSection({
  status,
  onChanged,
}: {
  status: SettingsStatus | null;
  onChanged: () => void | Promise<void>;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <KeyRound className="h-4 w-4" /> API keys
        </CardTitle>
        <CardDescription>
          Stored in your operating system's keychain — never in a file or in Orrin's
          program folder. Both keys are optional.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <KeyRow
          label="OpenAI"
          field="openai_api_key"
          placeholder="sk-…"
          configured={!!status?.configured.openai}
          help="Gives Orrin language (its LLM tool). Create one at platform.openai.com."
          onChanged={onChanged}
        />
        <KeyRow
          label="Serper"
          field="serper_api_key"
          placeholder="your Serper key"
          configured={!!status?.configured.serper}
          help="Lets Orrin search the web. Create one at serper.dev."
          onChanged={onChanged}
        />
      </CardContent>
    </Card>
  );
}

function KeyRow({
  label,
  field,
  placeholder,
  configured,
  help,
  onChanged,
}: {
  label: string;
  field: "openai_api_key" | "serper_api_key";
  placeholder: string;
  configured: boolean;
  help: string;
  onChanged: () => void | Promise<void>;
}) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const save = async (clear: boolean) => {
    if (busy) return;
    setBusy(true);
    setNote(null);
    try {
      const res = await apiPost(
        `/api/settings`,
        { [field]: clear ? "" : value.trim() },
        { headers: controlHeaders() },
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setValue("");
      setNote(clear ? "Removed." : "Saved — Orrin's language is active.");
      await onChanged();
    } catch {
      setNote("Couldn't save (a control token may be required for a remote viewer).");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label className="text-sm font-medium">{label}</label>
        <span
          className={cn(
            "inline-flex items-center gap-1.5 text-xs",
            configured ? "text-signal-ok" : "text-muted-foreground",
          )}
        >
          <span className={cn("h-1.5 w-1.5 rounded-full", configured ? "bg-signal-ok" : "bg-muted-foreground/50")} />
          {configured ? "Connected (key in keychain)" : "Not configured"}
        </span>
      </div>
      <div className="flex gap-2">
        <input
          type="password"
          autoComplete="off"
          spellCheck={false}
          value={value}
          placeholder={configured ? "•••••••• (saved)" : placeholder}
          onChange={(e) => setValue(e.target.value)}
          className="min-w-0 flex-1 rounded-md border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-1 focus:ring-ring"
        />
        <Button size="sm" onClick={() => void save(false)} disabled={busy || !value.trim()}>
          {busy ? "Saving…" : "Save"}
        </Button>
        {configured && (
          <Button size="sm" variant="outline" onClick={() => void save(true)} disabled={busy}>
            Disconnect
          </Button>
        )}
      </div>
      <p className="text-xs text-muted-foreground">{help}</p>
      {note && <p className="text-xs text-foreground">{note}</p>}
    </div>
  );
}
