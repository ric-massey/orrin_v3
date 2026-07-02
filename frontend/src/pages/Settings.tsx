import { useCallback, useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";
import { apiGet } from "@/lib/transport";
import { UpdatesSection } from "./settings/UpdatesSection";
import { LanguageModelSection } from "./settings/LanguageModelSection";
import { ApiKeysSection } from "./settings/ApiKeysSection";
import { TrustSection } from "./settings/TrustSection";
import { ExistenceSection } from "./settings/ExistenceSection";
import { LanguageSection } from "./settings/LanguageSection";
import { BackupSection } from "./settings/BackupSection";
import { LifeCapsuleSection } from "./settings/LifeCapsuleSection";
import { ResetSection } from "./settings/ResetSection";
import { RunConfigSection } from "./settings/RunConfigSection";
import { controlHeaders, type SettingsStatus } from "./settings/shared";

export default function Settings() {
  const [status, setStatus] = useState<SettingsStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await apiGet(`/api/settings`, { headers: controlHeaders() });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setStatus((await res.json()) as SettingsStatus);
      setError(null);
    } catch (e) {
      setError(
        "Couldn't read settings. On a remote viewer this needs a control token; the native window doesn't.",
      );
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <div className="mx-auto w-full max-w-2xl space-y-5 px-4 py-6 sm:px-6">
      <div className="space-y-1">
        <h1 className="text-xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Orrin's keys, privacy, and a fresh start — all stored on this device.
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-signal-warn/40 bg-signal-warn/10 px-4 py-3 text-sm text-foreground">
          {error}
        </div>
      )}

      {status?.symbolic_only && (
        <div className="flex items-start gap-2.5 rounded-lg border bg-card px-4 py-3 text-sm">
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-signal-ok" />
          <div>
            <span className="font-medium">Orrin is running fully on-device.</span>{" "}
            <span className="text-muted-foreground">
              With no API key set it runs symbolically — quieter, but unbroken, and
              nothing leaves your machine. Add a key below to give it language.
            </span>
          </div>
        </div>
      )}

      <LanguageModelSection status={status} onChanged={refresh} />
      <ApiKeysSection status={status} onChanged={refresh} />
      <TrustSection status={status} onChanged={refresh} />
      <ExistenceSection status={status} onChanged={refresh} />
      <LanguageSection />
      <BackupSection />
      <RunConfigSection />
      <LifeCapsuleSection />
      <UpdatesSection status={status} onChanged={refresh} />
      <ResetSection />
    </div>
  );
}
