import { apiPost } from "@/lib/transport";

// Destructive/control endpoints are guarded server-side: untrusted Origins are
// rejected, and a remote-exposed backend additionally requires a control token. In
// the native window (loopback/bridge) no token is needed; for a remote viewer it
// rides in this header exactly as the Stop button sends it.
export function controlHeaders(): Record<string, string> | undefined {
  const token = import.meta.env.VITE_CONTROL_TOKEN as string | undefined;
  return token ? { "X-Orrin-Control-Token": token } : undefined;
}

export interface LlmProviderMeta {
  id: string;
  label: string;
  secret: string | null;
  local: boolean;
  models: string[];
  default_model: string;
  needs_base_url: boolean;
}

export interface SettingsStatus {
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
export async function postSettings(body: Record<string, unknown>): Promise<boolean> {
  try {
    const res = await apiPost(`/api/settings`, body, { headers: controlHeaders() });
    return res.ok;
  } catch {
    return false;
  }
}

/** Like postSettings but returns the parsed body (for the budget's refusal message). */
export async function postSettingsResult(body: Record<string, unknown>): Promise<Record<string, unknown> | null> {
  try {
    const res = await apiPost(`/api/settings`, body, { headers: controlHeaders() });
    return (await res.json()) as Record<string, unknown>;
  } catch {
    return null;
  }
}
