// Transport — the single seam through which ALL UI ↔ brain I/O flows.
//
// One interface, two implementations:
//   • HttpTransport   — fetch + WebSocket (this file). Used in the browser/dev
//                       and by remote viewers of the opt-in hub.
//   • BridgeTransport — the in-process pywebview js_api bridge (added in B2).
//                       Selected when `window.pywebview` exists → no network.
//
// Every REST call (reads via fetchJSON, writes via apiPost/apiGet) goes through
// `transport.fetch()`; the live stream goes through `transport.connectTelemetry()`.
// Swapping the implementation is therefore the *whole* of "make the app talk over
// the bridge instead of a socket" — no call site changes when B2 lands.

export interface TelemetryStreamHandlers {
  onSnapshot: (state: unknown) => void;
  onDelta: (frame: unknown) => void;
  /** Stream became live (socket open / bridge attached). */
  onOpen: () => void;
  /** Stream dropped. The transport does NOT auto-reconnect — the caller owns
   *  the reconnect/backoff policy by calling connectTelemetry() again. Not fired
   *  for an intentional close (the fn returned by connectTelemetry). */
  onClose: () => void;
}

export interface Transport {
  /** True for the in-process bridge (no network egress). */
  readonly isBridge: boolean;
  /** HTTP origin for REST, no trailing slash (e.g. http://127.0.0.1:8800). */
  apiBase(): string;
  /** The one request primitive every REST read+write flows through. */
  fetch(input: string, init?: RequestInit): Promise<Response>;
  /** Open the live telemetry stream; returns a close() that won't reconnect. */
  connectTelemetry(handlers: TelemetryStreamHandlers): () => void;
}

// ── HTTP implementation (fetch + WebSocket) ──────────────────────────────────
class HttpTransport implements Transport {
  readonly isBridge = false;

  apiBase(): string {
    // 1. explicit VITE_API_URL, 2. explicit VITE_TELEMETRY_HOST, 3. the page's
    // own origin (the native window loads same-origin off the loopback server;
    // a tunnel/LAN viewer gets Vite's proxied /api). Mirrors wsUrl() below.
    const explicit = import.meta.env.VITE_API_URL as string | undefined;
    if (explicit) return explicit.replace(/\/$/, "");
    const envHost = import.meta.env.VITE_TELEMETRY_HOST as string | undefined;
    if (envHost) return `http://${envHost}`;
    return window.location.origin;
  }

  fetch(input: string, init?: RequestInit): Promise<Response> {
    return window.fetch(input, init);
  }

  private wsUrl(): string {
    // The backend authenticates the WS handshake with the read token for
    // non-loopback clients; browsers can't set handshake headers, so it rides as
    // a query param when VITE_READ_TOKEN is configured.
    const token = import.meta.env.VITE_READ_TOKEN as string | undefined;
    const withToken = (u: string) => (token ? `${u}?token=${encodeURIComponent(token)}` : u);

    const explicit = import.meta.env.VITE_TELEMETRY_WS as string | undefined;
    if (explicit) return withToken(explicit);
    const envHost = import.meta.env.VITE_TELEMETRY_HOST as string | undefined;
    // When accessed remotely (tunnel/LAN), proxy /ws through Vite so the socket
    // uses the same host/port as the page instead of hardcoded localhost.
    if (!envHost) {
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      return withToken(`${proto}//${window.location.host}/ws/telemetry`);
    }
    return withToken(`ws://${envHost}/ws/telemetry`);
  }

  connectTelemetry(h: TelemetryStreamHandlers): () => void {
    let ws: WebSocket;
    try {
      ws = new WebSocket(this.wsUrl());
    } catch {
      // Construction failed (bad URL) — surface as a close so the caller's
      // reconnect/demo logic kicks in, exactly as a dropped socket would.
      h.onClose();
      return () => {};
    }
    // Per-socket intentional flag: under React StrictMode the cleanup runs, then
    // the remount re-subscribes BEFORE this (async) onclose fires. Without a flag
    // scoped to THIS socket, the dead socket would reconnect and leave two live
    // streams. The closure variable survives the remount and prevents that.
    let intentional = false;
    ws.onopen = () => h.onOpen();
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === "snapshot") h.onSnapshot(msg.state);
        else if (msg.type === "delta") h.onDelta(msg.frame);
      } catch {
        /* ignore malformed frame */
      }
    };
    ws.onclose = () => {
      if (intentional) return;
      h.onClose();
    };
    ws.onerror = () => ws.close();
    return () => {
      intentional = true;
      ws.close();
    };
  }
}

// ── In-process bridge implementation (pywebview js_api, no network) ──────────
type PyApi = {
  request: (p: { method: string; path: string; body?: string; headers?: Record<string, string> }) => Promise<{
    status: number;
    body: string;
    contentType: string;
  }>;
  telemetry_subscribe: () => Promise<unknown>;
  telemetry_unsubscribe: () => Promise<unknown>;
};

/** Resolve `window.pywebview.api`, waiting for the `pywebviewready` event if the
 *  page's JS ran before pywebview finished injecting the bridge. */
function bridgeReady(): Promise<PyApi> {
  return new Promise((resolve) => {
    const w = window as unknown as { pywebview?: { api?: PyApi } };
    if (w.pywebview?.api) return resolve(w.pywebview.api);
    const done = () => {
      const api = (window as unknown as { pywebview?: { api?: PyApi } }).pywebview?.api;
      if (api) {
        window.removeEventListener("pywebviewready", done);
        clearInterval(poll);
        resolve(api);
      }
    };
    window.addEventListener("pywebviewready", done);
    const poll = window.setInterval(done, 50); // safety net if the event was missed
  });
}

class BridgeTransport implements Transport {
  readonly isBridge = true;

  // The bridge resolves API paths in-process; there is no HTTP origin. Call sites
  // build `${apiBase()}${path}` → just the path, which fetch() routes to js_api.
  apiBase(): string {
    return "";
  }

  async fetch(input: string, init?: RequestInit): Promise<Response> {
    // Absolute URLs (e.g. a user-configured VITE_CHAT_URL) are real network egress
    // the page can still perform; only our own API paths go over the bridge.
    if (/^https?:\/\//i.test(input)) return window.fetch(input, init);
    const api = await bridgeReady();
    const method = (init?.method || "GET").toUpperCase();
    const body = typeof init?.body === "string" ? init.body : undefined;
    const headers = (init?.headers as Record<string, string>) || undefined;
    const r = await api.request({ method, path: input, body, headers });
    return new Response(r.body, { status: r.status, headers: { "content-type": r.contentType } });
  }

  connectTelemetry(h: TelemetryStreamHandlers): () => void {
    let closed = false;
    // Python pushes snapshots/deltas as JSON strings via evaluate_js → this global.
    (window as unknown as { __orrinPush?: (s: string) => void }).__orrinPush = (s: string) => {
      if (closed) return;
      let msg: { type?: string; state?: unknown; frame?: unknown };
      try {
        msg = JSON.parse(s);
      } catch {
        return;
      }
      if (msg.type === "snapshot") h.onSnapshot(msg.state);
      else if (msg.type === "delta") h.onDelta(msg.frame);
    };
    bridgeReady()
      .then((api) => api.telemetry_subscribe())
      .then(() => !closed && h.onOpen())
      .catch(() => h.onClose());
    return () => {
      closed = true;
      bridgeReady()
        .then((api) => api.telemetry_unsubscribe())
        .catch(() => {});
    };
  }
}

// ── Selection ────────────────────────────────────────────────────────────────
let _transport: Transport | null = null;

/** True when running inside the native pywebview shell (loaded from disk, or the
 *  js_api bridge present) → use the in-process transport, no network. */
function isBridgeEnv(): boolean {
  return (
    window.location.protocol === "file:" ||
    typeof (window as unknown as { pywebview?: unknown }).pywebview !== "undefined"
  );
}

/** The active transport (singleton): the in-process bridge in the native window,
 *  HTTP (fetch + WebSocket) in a browser / dev / remote viewer. */
export function getTransport(): Transport {
  if (_transport) return _transport;
  _transport = isBridgeEnv() ? new BridgeTransport() : new HttpTransport();
  return _transport;
}

// ── Convenience helpers (used by call sites) ─────────────────────────────────
/** Canonical HTTP base for the telemetry backend, via the active transport. */
export function apiBase(): string {
  return getTransport().apiBase();
}

/** Low-level request to an absolute URL through the active transport. */
export function transportFetch(input: string, init?: RequestInit): Promise<Response> {
  return getTransport().fetch(input, init);
}

/** GET an API path (e.g. "/api/chat?n=200") through the active transport. */
export function apiGet(path: string, init?: RequestInit): Promise<Response> {
  const t = getTransport();
  return t.fetch(`${t.apiBase()}${path}`, init);
}

/** POST JSON to an API path through the active transport. A Content-Type header
 *  is added only when there's a body, so empty control POSTs match prior behavior. */
export function apiPost(path: string, body?: unknown, init: RequestInit = {}): Promise<Response> {
  const t = getTransport();
  const headers: Record<string, string> = { ...((init.headers as Record<string, string>) || {}) };
  let payload: BodyInit | undefined;
  if (body !== undefined) {
    headers["Content-Type"] = headers["Content-Type"] || "application/json";
    payload = JSON.stringify(body);
  }
  return t.fetch(`${t.apiBase()}${path}`, { method: "POST", ...init, headers, body: payload });
}
