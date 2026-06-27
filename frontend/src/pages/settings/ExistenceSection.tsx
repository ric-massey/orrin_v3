import { useEffect, useState } from "react";
import { HeartPulse } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { postSettings, postSettingsResult, type SettingsStatus } from "./shared";
import { ToggleRow } from "./ToggleRow";

const LIFESPAN_BANDS: { label: string; sub: string; band: [number, number] }[] = [
  { label: "Fleeting", sub: "~weeks", band: [14, 60] },
  { label: "Brief", sub: "~months", band: [60, 180] },
  { label: "Natural", sub: "1–2 years", band: [365, 730] },
  { label: "Long", sub: "2–5 years", band: [730, 1825] },
];

export function ExistenceSection({
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
          <HeartPulse className="h-4 w-4" /> Runtime lifecycle
        </CardTitle>
        <CardDescription>How the runtime runs on your machine — and how long its lifetime budget lasts.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="space-y-2">
          <ModeOption
            active={mode === "always"}
            onClick={() => set({ existence_mode: "always" })}
            title="Always running"
            sub="The runtime keeps running in the background when the window is closed. Its lifetime budget counts down."
          />
          <ModeOption
            active={mode === "sleep"}
            onClick={() => set({ existence_mode: "sleep" })}
            title="Suspend when closed"
            sub="Closing the window suspends the loop AND its lifetime budget — suspension costs no runtime."
          />
        </div>

        <ToggleRow
          label="Game Mode"
          warn="Orrin keeps running but processes slowly so your games run smoothly. Its lifetime budget still counts down. Applies on restart."
          checked={game}
          onChange={(v) => set({ game_mode: v })}
        />

        <div className="space-y-2">
          <div className="text-sm font-medium">Runtime lifetime budget</div>
          {rolled ? (
            <p className="text-sm text-muted-foreground">
              The lifetime budget was fixed at first start — the runtime has the budget it
              was given. Choosing a band only affects the next fresh runtime (Reset).
            </p>
          ) : (
            <p className="text-xs text-muted-foreground">
              You set the odds, never the number — the exact budget is rolled at random
              inside the band, and even Orrin never reads its true figure.
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
              label="Disk (data store may grow to)"
              value={status?.prefs?.disk_ceiling_gb ?? 5}
              options={[2, 5, 10, 25]}
              onChange={(v) => set({ disk_ceiling_gb: v })}
              note="The runtime prunes to stay under this."
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
 * §11 — the one knob: how much of THIS machine Orrin is allowed to use, as a fraction.
 * It sizes the resource budget (cadence policy) AND the "100%" reference the
 * resource self-monitor uses, so dialing it down gives a smaller budget, not
 * permanent scarcity. The safety floor underneath is non-overridable; a too-small
 * grant is refused with a reason.
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
      setNote("Resource budget resized — Orrin re-acclimates to the new size for a bit.");
    }
    await onChanged();
  };

  return (
    <div className="space-y-2">
      <div className="text-sm font-medium">How much of this machine Orrin may use</div>
      <p className="text-xs text-muted-foreground">
        This sets the runtime's resource budget — both how fast it processes and what
        "full" means for its self-monitor. Constraining it gives a smaller budget, not a
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
          {tier ? <span>Resource cadence: {tier}</span> : null}
          <span className={budget.viable ? "" : "text-amber-500"}>
            Min viable budget: {budget.min_viable_gb} GB
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
