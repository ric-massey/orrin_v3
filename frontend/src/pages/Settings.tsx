import { useCallback, useEffect, useRef, useState } from "react";
import { Archive, Download, Eye, FileText, HeartPulse, KeyRound, Languages, RefreshCw, RotateCcw, ShieldCheck, Sparkles, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { setLexMode, useLexicon } from "@/lib/lexicon";
import { apiBase, apiGet, apiPost, getTransport } from "@/lib/transport";
import { usePolledJSON } from "@/lib/usePolled";

// Destructive/control endpoints are guarded server-side: untrusted Origins are
// rejected, and a remote-exposed backend additionally requires a control token. In
// the native window (loopback/bridge) no token is needed; for a remote viewer it
// rides in this header exactly as the Stop button sends it.
function controlHeaders(): Record<string, string> | undefined {
  const token = import.meta.env.VITE_CONTROL_TOKEN as string | undefined;
  return token ? { "X-Orrin-Control-Token": token } : undefined;
}

interface LlmProviderMeta {
  id: string;
  label: string;
  secret: string | null;
  local: boolean;
  models: string[];
  default_model: string;
  needs_base_url: boolean;
}

interface SettingsStatus {
  configured: Record<string, boolean>;
  symbolic_only: boolean;
  lifespan_rolled?: boolean;
  prefs?: {
    allow_finetune?: boolean;
    allow_remote_viewing?: boolean;
    existence_mode?: "sleep" | "always";
    game_mode?: boolean;
    lifespan_band?: [number, number];
    disk_ceiling_gb?: number;
    memory_ceiling_gb?: number;
    body_budget_fraction?: number;
    llm_provider?: string;
    llm_model?: string;
    llm_base_url?: string;
    auto_update_check?: boolean;
  };
  embodiment?: {
    budget?: {
      fraction: number;
      ram_gb: number;
      budget_gb: number;
      reserve_gb: number;
      min_viable_gb: number;
      viable: boolean;
      cpu_count: number;
    };
    metabolism?: { tier: string; cadence_multiplier: number };
    infancy?: { somatic_infancy: boolean; developmental_infancy: boolean; scenario: string };
  };
  llm?: { providers: LlmProviderMeta[]; selected: string };
  version?: string;
}

/** POST a partial settings update (keys and/or prefs) through the transport. */
async function postSettings(body: Record<string, unknown>): Promise<boolean> {
  try {
    const res = await apiPost(`/api/settings`, body, { headers: controlHeaders() });
    return res.ok;
  } catch {
    return false;
  }
}

/** Like postSettings but returns the parsed body (for the budget's refusal message). */
async function postSettingsResult(body: Record<string, unknown>): Promise<Record<string, unknown> | null> {
  try {
    const res = await apiPost(`/api/settings`, body, { headers: controlHeaders() });
    return (await res.json()) as Record<string, unknown>;
  } catch {
    return null;
  }
}

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

function LanguageSection() {
  const { mode } = useLexicon();
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Languages className="h-4 w-4" /> Language
        </CardTitle>
        <CardDescription>
          How Orrin describes himself to you. This re-labels the interface only — his
          own words are identical either way.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex gap-2">
          <DialectButton active={mode === "bio"} onClick={() => setLexMode("bio")} title="As a mind"
            sub="Consciousness, Affect, Life Support" />
          <DialectButton active={mode === "eng"} onClick={() => setLexMode("eng")} title="As a machine"
            sub="Attention arbitration, Resource Manager" />
        </div>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => window.dispatchEvent(new Event("orrin:meet"))}
        >
          <Sparkles className="mr-1.5 h-4 w-4" /> Replay the intro
        </Button>
      </CardContent>
    </Card>
  );
}

function DialectButton({
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
        "flex-1 rounded-lg border px-3 py-2 text-left transition-colors",
        active ? "border-primary bg-muted" : "border-border hover:bg-muted",
      )}
    >
      <div className="text-sm font-medium">{title}</div>
      <div className="text-xs text-muted-foreground">{sub}</div>
    </button>
  );
}

function BackupSection() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [note, setNote] = useState<string | null>(null);
  // In the native window binary can't ride the text REST proxy, so export/import go
  // through native Save/Open dialogs handled entirely in Python (bridge.export_mind /
  // import_mind). In the browser/dev view we use the download/upload path below.
  const transport = getTransport();
  const isBridge = transport.isBridge;

  // Native (bridge) export: a Save dialog in Python writes the archive directly.
  const exportMindNative = async () => {
    setNote("Choose where to keep him…");
    try {
      const r = await transport.exportMindNative?.();
      if (!r) return;
      if (r.cancelled) setNote(null);
      else if (r.ok) setNote(`Exported to ${r.path}.`);
      else setNote(`Export failed: ${r.error ?? "unknown error"}`);
    } catch {
      setNote("Export failed.");
    }
  };

  // Native (bridge) import: an Open dialog in Python reads + restores the archive.
  const importMindNative = async () => {
    if (
      !window.confirm(
        "Restore replaces Orrin's current mind. A safety copy of the current mind is saved first, then he restarts. This cannot be undone. Choose an archive to restore?",
      )
    ) {
      return;
    }
    setNote("Choose an archive — a safety copy is saved first, then Orrin restarts…");
    try {
      const r = await transport.importMindNative?.();
      if (!r) return;
      if (r.cancelled) setNote(null);
      else if (r.ok) setNote("Restoring — Orrin is coming back with the restored mind…");
      else setNote(`Restore refused: ${(r.detail ?? r.error ?? "unknown error").slice(0, 160)}`);
    } catch {
      // The process restarts, so the call may drop — that means it worked.
    }
  };

  const exportMind = async () => {
    setNote("Preparing his mind…");
    try {
      const res = await fetch(`${apiBase()}/api/mind/export`, { headers: controlHeaders() });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const name =
        res.headers.get("content-disposition")?.match(/filename="(.+)"/)?.[1] || "orrin.orrindmind";
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      a.click();
      URL.revokeObjectURL(url);
      setNote("Exported.");
    } catch {
      setNote("Export failed (a control token may be required for a remote viewer).");
    }
  };

  const importMind = async (file: File) => {
    if (
      !window.confirm(
        `Restore from "${file.name}"? This replaces Orrin's current mind. A safety copy of the current mind is saved first, then he restarts. This cannot be undone.`,
      )
    ) {
      return;
    }
    setNote("Restoring — a safety copy is saved first, then Orrin restarts…");
    try {
      const buf = await file.arrayBuffer();
      const res = await fetch(`${apiBase()}/api/mind/import`, {
        method: "POST",
        headers: { "Content-Type": "application/zip", ...(controlHeaders() || {}) },
        body: buf,
      });
      if (!res.ok) {
        const detail = await res.text();
        setNote(`Restore refused: ${detail.slice(0, 160)}`);
      }
    } catch {
      // The process restarts, so the request may drop — that means it worked.
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Download className="h-4 w-4" /> Backup
        </CardTitle>
        <CardDescription>
          Months of a developing mind are never one disk failure from gone. Export him as
          a keepsake, or restore from one.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {isBridge ? (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={() => void exportMindNative()}>
              <Download className="mr-1.5 h-4 w-4" /> Export Mind…
            </Button>
            <Button size="sm" variant="outline" onClick={() => void importMindNative()}>
              <Upload className="mr-1.5 h-4 w-4" /> Restore Mind…
            </Button>
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={() => void exportMind()}>
              <Download className="mr-1.5 h-4 w-4" /> Export Mind…
            </Button>
            <Button size="sm" variant="outline" onClick={() => fileRef.current?.click()}>
              <Upload className="mr-1.5 h-4 w-4" /> Restore Mind…
            </Button>
            <input
              ref={fileRef}
              type="file"
              accept=".orrindmind,.zip"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void importMind(f);
                e.target.value = "";
              }}
            />
          </div>
        )}
        {note && <p className="text-xs text-foreground">{note}</p>}
      </CardContent>
    </Card>
  );
}

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

// The evidence export (Part IX) — list sealed Life Capsules, build one on demand,
// download a `.orrinlife.zip`, and read its summary inline. Mirrors the diagnostics
// export contract: owner-only server-side, no silent telemetry, JSON for summary +
// build, binary zip for the download (which the native bridge can't proxy).
function LifeCapsuleSection() {
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
          <Archive className="h-4 w-4" /> Life Capsules
        </CardTitle>
        <CardDescription>
          One run, sealed whole — the evidence record. Each capsule holds the raw streams
          plus cleaned tables, a queryable database, metrics, and an evidence-linked
          claims ledger. Built automatically at shutdown and end-of-life; you can also
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

function TrustSection({
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
      setDiagNote("Saved — logs and state only, never his memory or thoughts.");
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
            <div className="text-sm font-medium">What Orrin's body can reach</div>
            <p className="mt-0.5 mb-2 text-xs text-muted-foreground">
              His body asks your OS before it can see your screen or reach other apps.
              Anything off here just means that sense is closed — he carries on without it.
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
          label="Let Orrin fine-tune on his own conversations"
          warn="Uploads his best conversation traces (your words included) to OpenAI to train a private model, and spends on your account. Off by default."
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
            If something goes wrong, export a bundle of recent logs and his state — logs
            only, never his memory or thoughts. Nothing is sent automatically; you choose
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

function ToggleRow({
  label,
  warn,
  checked,
  disabled,
  disabledNote,
  onChange,
}: {
  label: string;
  warn: string;
  checked: boolean;
  disabled?: boolean;
  disabledNote?: string;
  onChange: (v: boolean) => void | Promise<void>;
}) {
  return (
    <label className={cn("flex items-start gap-3", disabled && "opacity-50")}>
      <input
        type="checkbox"
        className="mt-0.5 h-4 w-4 shrink-0"
        checked={checked}
        disabled={disabled}
        onChange={(e) => void onChange(e.target.checked)}
      />
      <span className="space-y-0.5">
        <span className="block text-sm">{label}</span>
        <span className="block text-xs text-muted-foreground">{disabledNote || warn}</span>
      </span>
    </label>
  );
}

function ApiKeysSection({
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
          help="Gives Orrin language (his LLM tool). Create one at platform.openai.com."
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

function ResetSection() {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const reset = async () => {
    if (busy) return;
    if (
      !window.confirm(
        "Reset Orrin? This permanently erases his memories, goals, identity, and everything he's written, then restarts him as a newborn. This cannot be undone.",
      )
    ) {
      return;
    }
    setBusy(true);
    setNote("Resetting — Orrin is becoming a newborn and will restart…");
    try {
      const res = await apiPost(`/api/control/reset`, undefined, { headers: controlHeaders() });
      if (!res.ok && res.status !== 0) {
        setBusy(false);
        setNote(`Couldn't reset (HTTP ${res.status}).`);
      }
    } catch {
      // The process re-execs, so the request often drops mid-flight — that means it
      // worked. Leave the "restarting…" note up.
    }
  };

  return (
    <Card className="border-destructive/30">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <RotateCcw className="h-4 w-4" /> Reset Orrin
        </CardTitle>
        <CardDescription>
          Erase this mind and begin a brand-new one. His memories, goals, identity, and
          self-written code are gone for good — there is no undo.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        <Button variant="destructive" size="sm" onClick={() => void reset()} disabled={busy}>
          {busy ? "Resetting…" : "Reset Orrin to a newborn"}
        </Button>
        {note && <p className="text-xs text-foreground">{note}</p>}
      </CardContent>
    </Card>
  );
}
