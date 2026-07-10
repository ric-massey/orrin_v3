import { NavLink, useLocation, useNavigate } from "react-router-dom";
import {
  Activity,
  Brain as BrainIcon,
  Circle,
  Clock,
  Database,
  Eye,
  HeartPulse,
  MessageCircle,
  Network,
  ListChecks,
  Settings as SettingsIcon,
  Sparkles,
  TrendingUp,
  UserRound,
  Wrench,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useLexicon, type LexId } from "@/lib/lexicon";
import { TelemetryState, useStreamStale } from "@/lib/telemetry";
import { isCompanionRoom, useMode } from "@/lib/mode";
import StopButton from "@/components/StopButton";

interface HeaderProps {
  telemetry: TelemetryState;
}

// The named rooms (§9.1), left→right. Face is the calm public surface; the rest
// are progressively deeper views of the same runtime, ending in the full
// research grid.
const ROOMS: { path: string; lex: LexId; icon: typeof Activity }[] = [
  { path: "/watch", lex: "nav_watch", icon: Eye },
  { path: "/face", lex: "nav_face", icon: MessageCircle },
  { path: "/cognition", lex: "nav_cognition", icon: BrainIcon },
  { path: "/life", lex: "nav_life", icon: Activity },
  { path: "/memory", lex: "nav_memory", icon: Database },
  { path: "/timeline", lex: "nav_timeline", icon: Clock },
  { path: "/learning", lex: "nav_learning", icon: TrendingUp },
  { path: "/you", lex: "nav_you", icon: UserRound },
  { path: "/actions", lex: "nav_actions", icon: ListChecks },
  { path: "/body", lex: "nav_body", icon: HeartPulse },
  { path: "/brain", lex: "nav_brain", icon: Network },
];

// C3: the companion lens — same rooms, three doors. Settings rides on the
// right-side gear as always, which is why it isn't listed here.
const COMPANION_NAV: { path: string; lex: LexId; icon: typeof Activity }[] = [
  { path: "/orrin", lex: "nav_orrin", icon: Sparkles },
  { path: "/timeline", lex: "nav_journal", icon: Clock },
];

export default function Header({ telemetry }: HeaderProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useLexicon();
  const mode = useMode();

  // C0's nav-depth rule: companion chrome only when standing in a companion
  // room with mode=companion. Anywhere else shows the full workshop nav —
  // but a companion user in the workshop keeps a way back (the door swings
  // both ways).
  const companionChrome = mode === "companion" && isCompanionRoom(location.pathname);
  const rooms = companionChrome ? COMPANION_NAV : ROOMS;

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
          {/* companion user standing in a workshop room — never strand them */}
          {mode === "companion" && !companionChrome && (
            <NavLink
              to="/orrin"
              className="ml-1 hidden shrink-0 rounded-full px-2 py-1 text-[13px] font-medium text-muted-foreground hover:text-foreground sm:block"
            >
              {t("nav_back_to_orrin")}
            </NavLink>
          )}
        </div>

        {/* Named-room nav */}
        <nav className="flex min-w-0 flex-1 items-center justify-center gap-0.5 overflow-x-auto sm:gap-1">
          {rooms.map((r) => (
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
            {/* the cycle counter is engineering chrome — companion mode hides it */}
            {!companionChrome && (
              <>
                <span className="text-border">·</span>
                <span className="tabular-nums">cycle {telemetry.cycle}</span>
              </>
            )}
          </div>

          {companionChrome && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate("/cognition")}
              title={t("nav_under_hood")}
            >
              <Wrench className="h-4 w-4" />
              <span className="hidden sm:inline">{t("nav_under_hood")}</span>
            </Button>
          )}

          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate("/settings")}
            title={t("nav_settings")}
            aria-label={t("nav_settings")}
          >
            <SettingsIcon className="h-4 w-4" />
          </Button>
          {/* C3: in companion chrome, Stop moves behind Settings */}
          {!companionChrome && <StopButton />}
        </div>
      </div>
    </header>
  );
}
