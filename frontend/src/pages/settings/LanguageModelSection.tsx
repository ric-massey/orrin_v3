import { useState } from "react";
import { ShieldCheck, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { apiBase } from "@/lib/transport";
import { controlHeaders, postSettings, type SettingsStatus } from "./shared";

export function LanguageModelSection({
  status,
  onChanged,
}: {
  status: SettingsStatus | null;
  onChanged: () => void | Promise<void>;
}) {
  const providers = status?.llm?.providers ?? [];
  const selected = status?.prefs?.llm_provider ?? status?.llm?.selected ?? "openai";
  const meta = providers.find((p) => p.id === selected);
  const model = status?.prefs?.llm_model ?? "";
  const baseUrl = status?.prefs?.llm_base_url ?? "";
  const [keyValue, setKeyValue] = useState("");
  const [test, setTest] = useState<{ ok: boolean; message: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const set = async (patch: Record<string, unknown>) => {
    setTest(null);
    await postSettings({ prefs: patch });
    await onChanged();
  };

  const saveKey = async () => {
    if (!meta?.secret || !keyValue.trim()) return;
    setBusy(true);
    await postSettings({ [`${meta.secret}_api_key`]: keyValue.trim() });
    setKeyValue("");
    await onChanged();
    setBusy(false);
  };

  const runTest = async () => {
    setBusy(true);
    setTest(null);
    try {
      const res = await fetch(`${apiBase()}/api/llm/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(controlHeaders() || {}) },
        body: "{}",
      });
      const j = (await res.json()) as { ok: boolean; message: string };
      setTest(j);
    } catch {
      setTest({ ok: false, message: "Couldn't reach the test endpoint." });
    } finally {
      setBusy(false);
    }
  };

  const keyConfigured = !!(meta?.secret && status?.configured?.[meta.secret]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Sparkles className="h-4 w-4" /> Language model
        </CardTitle>
        <CardDescription>
          The model behind Orrin's words. It stays symbolic-first underneath — every option
          is optional, and "None" keeps it fully on-device.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1.5">
          {providers.map((p) => (
            <label
              key={p.id}
              className={cn(
                "flex cursor-pointer items-center gap-3 rounded-md border px-3 py-2 text-sm",
                selected === p.id ? "border-ring bg-accent/40" : "border-border",
              )}
            >
              <input
                type="radio"
                name="llm_provider"
                className="h-4 w-4"
                checked={selected === p.id}
                onChange={() => void set({ llm_provider: p.id })}
              />
              <span className="flex-1">{p.label}</span>
              {p.local && (
                <span className="inline-flex items-center gap-1 text-xs text-signal-ok">
                  <ShieldCheck className="h-3.5 w-3.5" /> on-device
                </span>
              )}
            </label>
          ))}
        </div>

        {meta && meta.id !== "none" && (
          <div className="space-y-3 rounded-md border border-border bg-card/50 p-3">
            {meta.models.length > 0 ? (
              <label className="block text-sm">
                <span className="mb-1 block font-medium">Model</span>
                <select
                  className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-1 focus:ring-ring"
                  value={model || meta.default_model}
                  onChange={(e) => void set({ llm_model: e.target.value })}
                >
                  {meta.models.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <label className="block text-sm">
                <span className="mb-1 block font-medium">Model</span>
                <input
                  // key by provider so switching remounts the field with the current
                  // value instead of keeping the previously-typed (stale) text.
                  key={`model-${selected}`}
                  className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-1 focus:ring-ring"
                  placeholder="model name (e.g. llama3.1)"
                  defaultValue={model}
                  onBlur={(e) => void set({ llm_model: e.target.value.trim() })}
                />
              </label>
            )}

            {meta.needs_base_url && (
              <label className="block text-sm">
                <span className="mb-1 block font-medium">Endpoint URL</span>
                <input
                  className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-1 focus:ring-ring"
                  placeholder="http://localhost:11434/v1"
                  defaultValue={baseUrl}
                  onBlur={(e) => void set({ llm_base_url: e.target.value.trim() })}
                />
              </label>
            )}

            {meta.secret && (
              <div className="space-y-1.5 text-sm">
                <span className="font-medium">
                  API key{" "}
                  <span className={cn("text-xs", keyConfigured ? "text-signal-ok" : "text-muted-foreground")}>
                    {keyConfigured ? "· saved in keychain" : "· not set"}
                  </span>
                </span>
                <div className="flex gap-2">
                  <input
                    type="password"
                    autoComplete="off"
                    spellCheck={false}
                    value={keyValue}
                    placeholder={keyConfigured ? "•••••••• (saved)" : "paste key"}
                    onChange={(e) => setKeyValue(e.target.value)}
                    className="min-w-0 flex-1 rounded-md border border-border bg-background px-3 py-1.5 outline-none focus:ring-1 focus:ring-ring"
                  />
                  <Button size="sm" variant="outline" disabled={busy || !keyValue.trim()} onClick={() => void saveKey()}>
                    Save
                  </Button>
                </div>
              </div>
            )}

            <div className="flex items-center gap-3">
              <Button size="sm" variant="outline" disabled={busy} onClick={() => void runTest()}>
                Test connection
              </Button>
              {test && (
                <span className={cn("text-xs", test.ok ? "text-signal-ok" : "text-signal-warn")}>
                  {test.message}
                </span>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
