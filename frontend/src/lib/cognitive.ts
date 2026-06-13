// Shared bits for the Cognitive Map / Sphere views.

export const TELEMETRY_HOST =
  (import.meta.env.VITE_TELEMETRY_HOST as string | undefined) || "127.0.0.1:8800";

/**
 * Canonical HTTP base for the telemetry backend. Resolution mirrors wsUrl():
 *   1. explicit `VITE_API_URL` (trailing slash stripped),
 *   2. explicit `VITE_TELEMETRY_HOST`,
 *   3. the page's own origin — Vite proxies `/api` (and `/ws`) to the backend,
 *      so a tunnel/LAN viewer gets working REST with zero config (Fix 5).
 * Single source of truth — previously duplicated in Header.tsx and Face.tsx (L4).
 */
export function apiBase(): string {
  const explicit = import.meta.env.VITE_API_URL as string | undefined;
  if (explicit) return explicit.replace(/\/$/, "");
  const envHost = import.meta.env.VITE_TELEMETRY_HOST as string | undefined;
  if (envHost) return `http://${envHost}`;
  return window.location.origin;
}

/** REST root for the Brain panels' data endpoints. Always the `/api/` form so
 *  the single Vite proxy rule covers every endpoint (catalog, goals, history,
 *  source, code, memory, consciousness, …) — the backend serves both the bare
 *  and `/api/`-prefixed paths. */
export const API = `${apiBase()}/api`;

export const SUB_COLOR: Record<string, string> = {
  Affect: "#ef4444",
  Memory: "#3b82f6",
  Planning: "#22c55e",
  Perception: "#c084fc",
  Reflection: "#eab308",
  "Prediction/Learning": "#06b6d4",
  Action: "#f59e0b",
  Language: "#ec4899",
  Self: "#10b981",
  Generated: "#8b5cf6",
  "Self-Improvement": "#14b8a6",
  Control: "#f43f5e",
  Dialogue: "#0ea5e9",
  Values: "#a3e635",
  Body: "#fb923c",
  Curiosity: "#d946ef",
  Experimentation: "#65a30d",
  Cognition: "#94a3b8",
  Other: "#64748b",
};

export const colorFor = (s: string): string => SUB_COLOR[s] || SUB_COLOR.Other;
