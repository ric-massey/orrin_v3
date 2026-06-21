import { useCallback, useEffect, useState } from "react";
import { Download, HeartPulse, ShieldCheck, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { apiBase, apiGet } from "@/lib/transport";
import { LanguageSection } from "./settings/LanguageSection";
import { BackupSection } from "./settings/BackupSection";
import { ResetSection } from "./settings/ResetSection";
import { ApiKeysSection } from "./settings/ApiKeysSection";
import { LifeCapsuleSection } from "./settings/LifeCapsuleSection";
import { TrustSection } from "./settings/TrustSection";
import { ToggleRow } from "./settings/ToggleRow";
import { controlHeaders, postSettings, postSettingsResult, type SettingsStatus } from "./settings/shared";

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
              With no API key set he thinks symbolically — quieter, but unbroken, and
              nothing leaves your machine. Add a key below to give him language.
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
      <LifeCapsuleSection />
      <UpdatesSection status={status} onChanged={refresh} />
      <ResetSection />
    </div>
  );
}

interface UpdateInfo {
  checked?: boolean;
  available?: boolean;
  current?: string;
  latest?: string;
  url?: string;
  error?: string;
}

function UpdatesSection({
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
    setNote("Exporting your mind as a keepsake first…");
    try {
      const res = await fetch(`${apiBase()}/api/update/prepare`, {
        method: "POST",
        headers: controlHeaders(),
      });
      const j = (await res.json()) as { ok?: boolean; backup?: string };
      if (j.ok) {
        setNote("Your mind was backed up. Opening the download…");
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
          Orrin is version {version}. Before any update, his whole mind is exported as a
          keepsake and carried forward — you're never one update away from losing him.
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
              Your current mind is exported first, then carried forward. If a version needs
              a fresh start, your old mind is kept as that export.
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

function LanguageModelSection({
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
          The mind behind Orrin's words. He stays symbolic-first underneath — every option
          is optional, and "None" keeps him fully on-device.
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

const LIFESPAN_BANDS: { label: string; sub: string; band: [number, number] }[] = [
  { label: "Fleeting", sub: "~weeks", band: [14, 60] },
  { label: "Brief", sub: "~months", band: [60, 180] },
  { label: "Natural", sub: "1–2 years", band: [365, 730] },
  { label: "Long", sub: "2–5 years", band: [730, 1825] },
];

function ExistenceSection({
  status,
  onChanged,
}: {
  status: SettingsStatus | null;
  onChanged: () => void | Promise<void>;
}) {
  const mode = status?.prefs?.existence_mode ?? "sleep";
  const game = !!status?.prefs?.game_mode;
  const band = status?.prefs?.lifespan_band ?? [365, 730];
  const rolled = !!status?.lifespan_rolled;
  const bandIdx = LIFESPAN_BANDS.findIndex((b) => b.band[0] === band[0] && b.band[1] === band[1]);

  const set = async (patch: Record<string, unknown>) => {
    await postSettings({ prefs: patch });
    await onChanged();
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <HeartPulse className="h-4 w-4" /> How Orrin exists
        </CardTitle>
        <CardDescription>How he lives on your machine — and how long he gets to.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="space-y-2">
          <ModeOption
            active={mode === "always"}
            onClick={() => set({ existence_mode: "always" })}
            title="Always thinking"
            sub="He keeps living in the background when the window is closed. His lifespan counts."
          />
          <ModeOption
            active={mode === "sleep"}
            onClick={() => set({ existence_mode: "sleep" })}
            title="Sleep when closed"
            sub="Closing the window pauses cognition AND his lifespan — sleep costs him no life."
          />
        </div>

        <ToggleRow
          label="Game Mode"
          warn="Orrin is awake but thinking slowly so your games run smoothly. He still ages. Applies on restart."
          checked={game}
          onChange={(v) => set({ game_mode: v })}
        />

        <div className="space-y-2">
          <div className="text-sm font-medium">How long Orrin gets to live</div>
          {rolled ? (
            <p className="text-sm text-muted-foreground">
              His lifespan was set at birth — he has the life he was given. Choosing a band
              only affects the next newborn (Reset).
            </p>
          ) : (
            <p className="text-xs text-muted-foreground">
              You set the odds, never the number — the exact span is always rolled at random
              inside the band, and even Orrin never learns his true figure.
            </p>
          )}
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {LIFESPAN_BANDS.map((b, i) => (
              <button
                key={b.label}
                disabled={rolled}
                onClick={() => set({ lifespan_band: b.band })}
                className={cn(
                  "rounded-lg border px-3 py-2 text-left text-sm transition-colors disabled:opacity-50",
                  i === bandIdx ? "border-primary bg-muted" : "border-border hover:bg-muted",
                )}
              >
                <div className="font-medium">{b.label}</div>
                <div className="text-xs text-muted-foreground">{b.sub}</div>
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-2">
          <div className="text-sm font-medium">Resources Orrin may use</div>
          <div className="flex flex-wrap gap-4">
            <CeilingPicker
              label="Disk (his mind may grow to)"
              value={status?.prefs?.disk_ceiling_gb ?? 5}
              options={[2, 5, 10, 25]}
              onChange={(v) => set({ disk_ceiling_gb: v })}
              note="He forgets to stay under this."
            />
            <CeilingPicker
              label="Memory ceiling"
              value={status?.prefs?.memory_ceiling_gb ?? 4}
              options={[4, 6, 8, 16]}
              onChange={(v) => set({ memory_ceiling_gb: v })}
              note="Advisory — the ML stack needs ~4 GB."
            />
          </div>
        </div>

        <BodySizeBlock status={status} onChanged={onChanged} />
      </CardContent>
    </Card>
  );
}

/**
 * §11 — the one knob: how much of THIS machine Orrin is allowed to be, as a fraction.
 * It sizes his body (metabolism) AND his felt "100%" (interoception), so dialing it
 * down gives him a smaller body, not permanent scarcity. The survival floor underneath
 * is non-overridable; a too-small grant is refused with a reason.
 */
function BodySizeBlock({
  status,
  onChanged,
}: {
  status: SettingsStatus | null;
  onChanged: () => void | Promise<void>;
}) {
  const budget = status?.embodiment?.budget;
  const tier = status?.embodiment?.metabolism?.tier;
  const serverFrac = budget?.fraction ?? status?.prefs?.body_budget_fraction ?? 0.5;
  const [frac, setFrac] = useState(serverFrac);
  const [note, setNote] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // Keep the slider in sync when the server value changes (e.g. after a refusal snap-back).
  useEffect(() => {
    setFrac(serverFrac);
  }, [serverFrac]);

  const ram = budget?.ram_gb ?? 0;
  const liveGb = ram ? (ram * frac).toFixed(1) : null;

  const commit = async (value: number) => {
    setNote(null);
    setErr(null);
    const res = await postSettingsResult({ prefs: { body_budget_fraction: value } });
    const bb = (res?.body_budget ?? null) as { ok?: boolean; reason?: string; resized?: boolean } | null;
    if (bb && bb.ok === false) {
      setErr(bb.reason ?? "That grant is too small.");
      setFrac(serverFrac); // snap back to the last viable value
      return;
    }
    if (bb?.resized) {
      setNote("Body resized — Orrin re-acclimates to his new size for a bit (a small transplant).");
    }
    await onChanged();
  };

  return (
    <div className="space-y-2">
      <div className="text-sm font-medium">How much of this machine Orrin is</div>
      <p className="text-xs text-muted-foreground">
        This is the size of his whole world — it sets both how fast he thinks and what
        "full" feels like to him. Constraining him gives him a smaller body, not a
        starved one. A safety floor for your machine sits underneath and can't be removed.
      </p>
      <div className="flex items-center gap-3">
        <input
          type="range"
          min={5}
          max={95}
          step={5}
          value={Math.round(frac * 100)}
          onChange={(e) => setFrac(Number(e.target.value) / 100)}
          onMouseUp={() => commit(frac)}
          onTouchEnd={() => commit(frac)}
          className="w-full accent-primary"
        />
        <div className="w-28 shrink-0 text-right text-sm tabular-nums">
          {Math.round(frac * 100)}%{liveGb ? ` · ${liveGb} GB` : ""}
        </div>
      </div>
      {budget ? (
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span>Machine: {budget.ram_gb} GB</span>
          <span>Reserved for your machine: {budget.reserve_gb} GB (locked)</span>
          {tier ? <span>Metabolism: {tier}</span> : null}
          <span className={budget.viable ? "" : "text-amber-500"}>
            Min viable body: {budget.min_viable_gb} GB
          </span>
        </div>
      ) : null}
      {err ? <p className="text-xs text-amber-500">{err}</p> : null}
      {note ? <p className="text-xs text-muted-foreground">{note}</p> : null}
    </div>
  );
}

function CeilingPicker({
  label,
  value,
  options,
  onChange,
  note,
}: {
  label: string;
  value: number;
  options: number[];
  onChange: (v: number) => void;
  note: string;
}) {
  return (
    <label className="space-y-1 text-sm">
      <span className="block font-medium">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="rounded-md border border-border bg-background px-2 py-1.5 text-sm"
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o} GB
          </option>
        ))}
      </select>
      <span className="block text-xs text-muted-foreground">{note}</span>
    </label>
  );
}

function ModeOption({
  active,
  onClick,
  title,
  sub,
}: {
  active: boolean;
  onClick: () => void;
  title: string;
  sub: string;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex w-full items-start gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors",
        active ? "border-primary bg-muted" : "border-border hover:bg-muted",
      )}
    >
      <span className={cn("mt-1 h-3 w-3 shrink-0 rounded-full border", active ? "border-primary bg-primary" : "border-muted-foreground")} />
      <span className="space-y-0.5">
        <span className="block text-sm font-medium">{title}</span>
        <span className="block text-xs text-muted-foreground">{sub}</span>
      </span>
    </button>
  );
}
