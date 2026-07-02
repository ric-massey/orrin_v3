import { useCallback, useEffect, useState } from "react";
import { FlaskConical } from "lucide-react";
import { apiGet, apiPost } from "@/lib/transport";
import { controlHeaders } from "./shared";
import { ToggleRow } from "./ToggleRow";

/** P7/A2 — the ablation panel (sandbox mode). Per-subsystem toggles for the
 *  NEXT run: each subsystem checks its flag at its own entry point and no-ops
 *  when off, so you can watch what Memory / Goals / Affect actually contribute
 *  by taking them away. Flags are boot-time by design — the current run is
 *  never changed mid-flight, so every trace stays attributable to one stamped
 *  configuration. */

interface RunConfig {
  subsystems: string[];
  current: Record<string, boolean>;
  run_stamp: string;
  pending_ablate: string[];
  env_override: boolean;
}

const LABELS: Record<string, string> = {
  memory: "Memory",
  goals: "Goals",
  signals: "Affect / control signals",
  workspace: "Global workspace",
  metacognition: "Metacognition",
  host_coupling: "Host coupling",
  idle_consolidation: "Idle consolidation",
  llm_tools: "LLM tools",
  research_tools: "Research tools",
  persistence: "Persistence",
};

const WARNS: Record<string, string> = {
  memory: "off: no long-term recall — expect continuity collapse",
  goals: "off: nothing commits — expect drift",
  signals: "off: affect frozen — expect flattened priorities",
  workspace: "off: no conscious winner, no broadcast",
  metacognition: "off: no watcher, no breakthroughs",
  host_coupling: "off: no body sense from the host",
  idle_consolidation: "off: never dreams / consolidates",
  llm_tools: "off: every LLM call fails closed (symbolic only)",
  research_tools: "off: no web reach",
  persistence: "off: amnesic run — nothing written to disk",
};

export function RunConfigSection() {
  const [cfg, setCfg] = useState<RunConfig | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await apiGet(`/api/run-config`, { headers: controlHeaders() });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setCfg((await res.json()) as RunConfig);
      setError(null);
    } catch {
      setError("Couldn't read the run configuration.");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const setAblate = useCallback(
    async (name: string, ablated: boolean) => {
      if (!cfg) return;
      const next = new Set(cfg.pending_ablate);
      if (ablated) next.add(name);
      else next.delete(name);
      setBusy(true);
      try {
        const res = await apiPost(
          `/api/run-config`,
          { ablate: Array.from(next) },
          { headers: controlHeaders() },
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        await refresh();
      } catch {
        setError("Couldn't save the run configuration.");
      } finally {
        setBusy(false);
      }
    },
    [cfg, refresh],
  );

  if (!cfg) return null;

  return (
    <section className="space-y-3 rounded-lg border bg-card px-4 py-4">
      <div className="flex items-center gap-2">
        <FlaskConical className="h-4 w-4" />
        <h2 className="text-sm font-semibold">Sandbox — next run's subsystems</h2>
      </div>
      <p className="text-xs text-muted-foreground">
        Current run: <code className="rounded bg-muted px-1">{cfg.run_stamp}</code>. Changes
        apply at the next start and are stamped into that run's Life Capsule, so ablated
        traces stay comparable.
        {cfg.env_override && " (ORRIN_ABLATE is set in the environment — it overrides these.)"}
      </p>
      {error && <p className="text-xs text-signal-warn">{error}</p>}
      <div className="space-y-2.5">
        {cfg.subsystems.map((s) => (
          <ToggleRow
            key={s}
            label={LABELS[s] ?? s}
            warn={WARNS[s] ?? ""}
            checked={!cfg.pending_ablate.includes(s)}
            disabled={busy || cfg.env_override}
            onChange={(on) => setAblate(s, !on)}
          />
        ))}
      </div>
    </section>
  );
}
