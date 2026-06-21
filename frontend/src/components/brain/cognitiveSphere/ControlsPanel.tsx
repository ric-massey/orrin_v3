import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, SlidersHorizontal } from "lucide-react";
import { colorFor } from "@/lib/cognitive";
import { type Settings } from "./layout";

export function ControlsPanel({ settings, setSettings, subs }: { settings: Settings; setSettings: (s: Settings) => void; subs: { name: string; count: number }[] }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);
  const set = (p: Partial<Settings>) => setSettings({ ...settings, ...p });
  const toggleSub = (name: string) => set({ hiddenSubs: { ...settings.hiddenSubs, [name]: !settings.hiddenSubs[name] } });

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 rounded-md border border-border bg-card/90 px-2 py-1 text-[11px] font-medium text-muted-foreground shadow-sm backdrop-blur hover:text-foreground"
      >
        <SlidersHorizontal className="h-3.5 w-3.5" /> Customize <ChevronDown className={`h-3 w-3 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="absolute right-0 z-40 mt-1.5 w-60 rounded-lg border border-border bg-popover p-2.5 shadow-xl">
          <Group label="Display">
            <Toggle on={settings.showList} set={(v) => set({ showList: v })} label="Function list (left)" />
            <Toggle on={settings.lines} set={(v) => set({ lines: v })} label="Roads (connections)" />
            <Toggle on={settings.onlyUsed} set={(v) => set({ onlyUsed: v })} label="Only functions he's used" />
            <Toggle on={settings.effects} set={(v) => set({ effects: v })} label="Glow effects" title="Soft bloom around the active node — costs a little GPU. The view is always 3D." />
            <Toggle on={settings.autoRotate} set={(v) => set({ autoRotate: v })} label="Auto-rotate" />
          </Group>
          <Group label="Size nodes by">
            <Seg value={settings.sizeBy} opts={[["usage", "Usage"], ["reward", "Reward"], ["uniform", "Uniform"]]} set={(v) => set({ sizeBy: v as Settings["sizeBy"] })} />
          </Group>
          <Group label="Labels">
            <Seg value={settings.labels} opts={[["none", "None"], ["hover", "Hover"], ["used", "Used"], ["active", "Active"]]} set={(v) => set({ labels: v as Settings["labels"] })} />
          </Group>
          <Group label="Subsystems">
            <div className="max-h-40 overflow-y-auto pr-1">
              {subs.map((s) => {
                const on = !settings.hiddenSubs[s.name];
                return (
                  <button key={s.name} onClick={() => toggleSub(s.name)} className="flex w-full items-center gap-2 rounded px-1 py-1 text-left hover:bg-muted">
                    <span className={`flex h-3.5 w-3.5 flex-none items-center justify-center rounded border ${on ? "border-transparent" : "border-border"}`} style={on ? { background: colorFor(s.name) } : undefined}>
                      {on && <Check className="h-2.5 w-2.5 text-white" />}
                    </span>
                    <span className="flex-1 text-[11px] text-foreground">{s.name}</span>
                    <span className="text-[10px] text-muted-foreground">{s.count}</span>
                  </button>
                );
              })}
            </div>
          </Group>
        </div>
      )}
    </div>
  );
}

const Group = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <div className="mb-2 last:mb-0">
    <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</div>
    {children}
  </div>
);
const Toggle = ({ on, set, label, title }: { on: boolean; set: (v: boolean) => void; label: string; title?: string }) => (
  <button onClick={() => set(!on)} title={title} className="flex w-full items-center justify-between rounded px-1 py-1 text-left text-[11px] hover:bg-muted">
    <span className="text-foreground">{label}</span>
    <span className={`relative h-4 w-7 flex-none rounded-full transition-colors ${on ? "bg-signal-ok" : "bg-muted-foreground/30"}`}>
      <span className={`absolute top-0.5 h-3 w-3 rounded-full bg-white transition-all ${on ? "left-3.5" : "left-0.5"}`} />
    </span>
  </button>
);
export const Seg = ({ value, opts, set }: { value: string; opts: [string, string][]; set: (v: string) => void }) => (
  <div className="flex overflow-hidden rounded-md border border-border">
    {opts.map(([v, l]) => (
      <button key={v} onClick={() => set(v)} className={`flex-1 px-1.5 py-1 text-[10px] transition-colors ${value === v ? "bg-foreground/10 font-medium text-foreground" : "text-muted-foreground hover:text-foreground"}`}>
        {l}
      </button>
    ))}
  </div>
);
