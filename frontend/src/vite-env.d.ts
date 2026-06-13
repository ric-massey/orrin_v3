/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_TELEMETRY_WS?: string;
  readonly VITE_TELEMETRY_HOST?: string;
  readonly VITE_TELEMETRY_DEMO?: string;
  readonly VITE_TELEMETRY_DEMO_FALLBACK?: string;
  readonly VITE_CHAT_URL?: string;
  readonly VITE_API_URL?: string;
  readonly VITE_CONTROL_TOKEN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
