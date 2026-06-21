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
