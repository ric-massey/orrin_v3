import { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import {
  Activity,
  Brain as BrainIcon,
  Circle,
  Clock,
  Database,
  Eye,
  MessageCircle,
  Network,
  Power,
  Settings as SettingsIcon,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { setLexMode, useLexicon, type LexId } from "@/lib/lexicon";
import { TelemetryState, useStreamStale } from "@/lib/telemetry";
import { apiPost } from "@/lib/transport";

interface HeaderProps {
  telemetry: TelemetryState;
}

// The named rooms (§9.1), left→right. Face is the calm public surface; the rest are
// progressively deeper views of the same mind, ending in the full research grid.
// `research: true` rooms get the engineering-dialect toggle (their chrome translates).
const ROOMS: { path: string; lex: LexId; icon: typeof Activity; research: boolean }[] = [
  { path: "/watch", lex: "nav_watch", icon: Eye, research: false },
  { path: "/face", lex: "nav_face", icon: MessageCircle, research: false },
  { path: "/cognition", lex: "nav_cognition", icon: BrainIcon, research: true },
  { path: "/life", lex: "nav_life", icon: Activity, research: true },
  { path: "/memory", lex: "nav_memory", icon: Database, research: true },
  { path: "/timeline", lex: "nav_timeline", icon: Clock, research: true },
  { path: "/learning", lex: "nav_learning", icon: TrendingUp, research: true },
  { path: "/brain", lex: "nav_brain", icon: Network, research: true },
];

export default function Header({ telemetry }: HeaderProps) {
  const navigate = useNavigate();
  const { t } = useLexicon();

  // M1: one liveness verdict — a connected-but-frozen stream reads "Stalled".
  const stale = useStreamStale(telemetry);
  const status =
    telemetry.source === "live" && telemetry.connected
      ? stale
        ? { label: "Stalled", color: "text-signal-warn" }
        : { label: "Live", color: "text-signal-ok" }
      : telemetry.source === "stopped"
      ? { label: "Stopped", color: "text-muted-foreground" }
      : telemetry.source === "demo"
      ? { label: "Demo", color: "text-signal-warn" }
      : {
          label: telemetry.retries > 0 ? `Reconnecting (${telemetry.retries})` : "Connecting",
          color: "text-muted-foreground",
        };

  return (
    <header className="sticky top-0 z-40 glass border-b">
      <div className="mx-auto flex h-14 max-w-[1600px] items-center justify-between gap-2 px-3 sm:h-16 sm:px-5">
        {/* Brand */}
        <div className="flex shrink-0 items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground sm:h-9 sm:w-9">
            <Sparkles className="h-5 w-5" />
          </div>
          <div className="hidden leading-tight min-[480px]:block">
            <div className="text-[15px] font-semibold tracking-tight">Orrin</div>
          </div>
        </div>

        {/* Named-room nav */}
        <nav className="flex min-w-0 flex-1 items-center justify-center gap-0.5 overflow-x-auto sm:gap-1">
          {ROOMS.map((r) => (
            <NavLink
              key={r.path}
              to={r.path}
              className={({ isActive }) =>
                cn(
                  "flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1.5 text-[13px] font-medium transition-colors",
                  isActive
                    ? "bg-background text-foreground shadow-sm ring-1 ring-border"
                    : "text-muted-foreground hover:text-foreground",
                )
              }
              title={t(r.lex)}
            >
              <r.icon className="h-4 w-4 shrink-0" />
              <span className="hidden sm:inline">{t(r.lex)}</span>
            </NavLink>
          ))}
        </nav>

        {/* Status + controls */}
        <div className="flex shrink-0 items-center gap-2 sm:gap-3">
          <div className="hidden items-center gap-2 text-xs text-muted-foreground lg:flex">
            <Circle className={cn("h-2.5 w-2.5 fill-current", status.color)} />
            <span className={status.color}>{status.label}</span>
            <span className="text-border">·</span>
            <span className="tabular-nums">cycle {telemetry.cycle}</span>
          </div>

          <TerminologyToggle />
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate("/settings")}
            title={t("nav_settings")}
            aria-label={t("nav_settings")}
          >
            <SettingsIcon className="h-4 w-4" />
          </Button>
          <StopButton />
        </div>
      </div>
    </header>
  );
}

/** Fix 12 — the biological ↔ engineering vocabulary switch. Re-labels UI chrome
 *  only; Orrin's own output renders verbatim in both modes. Settings is the
 *  canonical home (§9.11); this stays as a fast in-context switch. */
function TerminologyToggle() {
  const { mode } = useLexicon();
  return (
    <div
      role="tablist"
      aria-label="Terminology"
      className="hidden items-center rounded-full border bg-secondary/60 p-0.5 text-[11px] font-medium md:flex"
      title="Terminology: the same data labeled in the biological vocabulary (default) or the engineering one."
    >
      {(["bio", "eng"] as const).map((m) => (
        <button
          key={m}
          role="tab"
          aria-selected={mode === m}
          onClick={() => setLexMode(m)}
          className={cn(
            "rounded-full px-2 py-1 transition-colors sm:px-2.5",
            mode === m ? "bg-background text-foreground shadow-sm ring-1 ring-border" : "text-muted-foreground hover:text-foreground",
          )}
        >
          <span className="sm:hidden">{m === "bio" ? "Bio" : "Eng"}</span>
          <span className="hidden sm:inline">{m === "bio" ? "Biological" : "Engineering"}</span>
        </button>
      ))}
    </div>
  );
}

function StopButton() {
  const [stopping, setStopping] = useState(false);

  const stop = async () => {
    if (stopping) return;
    if (!window.confirm("Stop Orrin? This halts his thinking (the cognitive loop and daemons). The window stays open so you can keep viewing his mind — close the window to quit.")) {
      return;
    }
    setStopping(true);
    const markStopped = () => window.dispatchEvent(new CustomEvent("orrin:stopped"));
    try {
      // SECURITY (H2/H3): destructive control action. The backend rejects untrusted
      // Origins on /api/control/*; when VITE_CONTROL_TOKEN is configured it is sent
      // so a remote-exposed backend can authorize the caller.
      const token = import.meta.env.VITE_CONTROL_TOKEN as string | undefined;
      const res = await apiPost(`/api/control/shutdown`, undefined, {
        headers: token ? { "X-Orrin-Control-Token": token } : undefined,
      });
      if (res.ok) {
        markStopped();
      } else {
        setStopping(false);
        window.alert(`Couldn't stop Orrin: the backend refused the request (HTTP ${res.status}). A control token may be required for remote control.`);
      }
    } catch {
      markStopped();
    }
  };

  return (
    <Button variant="destructive" size="sm" onClick={stop} disabled={stopping} title="Stop Orrin">
      <Power className="h-4 w-4" />
      <span className="hidden sm:inline">{stopping ? "Stopping…" : "Stop"}</span>
    </Button>
  );
}
