import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Activity, Brain as BrainIcon, Circle, Power, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { setLexMode, useLexicon } from "@/lib/lexicon";
import { TelemetryState } from "@/lib/telemetry";
import { apiBase } from "@/lib/cognitive";

interface HeaderProps {
  mode: "face" | "brain";
  telemetry: TelemetryState;
}

export default function Header({ mode, telemetry }: HeaderProps) {
  const navigate = useNavigate();

  const status =
    telemetry.source === "live" && telemetry.connected
      ? { label: "Live", color: "text-signal-ok" }
      : telemetry.source === "demo"
      ? { label: "Demo", color: "text-signal-warn" }
      : { label: "Connecting", color: "text-muted-foreground" };

  return (
    <header className="sticky top-0 z-40 glass border-b">
      <div className="mx-auto flex h-14 max-w-[1600px] items-center justify-between gap-2 px-3 sm:h-16 sm:px-5">
        {/* Brand */}
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground sm:h-9 sm:w-9">
            <Sparkles className="h-5 w-5" />
          </div>
          <div className="leading-tight">
            <div className="text-[15px] font-semibold tracking-tight">Orrin</div>
            <div className="hidden text-[11px] text-muted-foreground min-[400px]:block">
              {mode === "face" ? "Public Face" : "Core Brain"}
            </div>
          </div>
        </div>

        {/* Status + premium segmented toggle */}
        <div className="flex items-center gap-2 sm:gap-4">
          <div className="hidden items-center gap-2 text-xs text-muted-foreground sm:flex">
            <Circle className={cn("h-2.5 w-2.5 fill-current", status.color)} />
            <span className={status.color}>{status.label}</span>
            <span className="text-border">·</span>
            <span className="tabular-nums">cycle {telemetry.cycle}</span>
          </div>

          {mode === "brain" && <TerminologyToggle />}
          <ModeToggle mode={mode} onChange={(m) => navigate(`/${m}`)} />
          <StopButton />
        </div>
      </div>
    </header>
  );
}

/** Fix 12 — the biological ↔ engineering vocabulary switch. Re-labels the
 *  UI chrome only; Orrin's own output renders verbatim in both modes. Brain
 *  view only (the Face stays in plain human language by design). */
function TerminologyToggle() {
  const { mode } = useLexicon();
  return (
    <div
      role="tablist"
      aria-label="Terminology"
      className="flex items-center rounded-full border bg-secondary/60 p-0.5 text-[11px] font-medium"
      title="Terminology: the same data labeled in the biological vocabulary (default) or the engineering one. Hover any translated label to see its counterpart."
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
    if (!window.confirm("Stop Orrin? This shuts down the cognitive loop, daemons, and UI server.")) {
      return;
    }
    setStopping(true);
    try {
      // SECURITY (H3): this is a destructive, network-reachable control action
      // (`vite.config.ts` sets host:true/allowedHosts:true). When a shared secret
      // is configured via VITE_CONTROL_TOKEN, send it so the backend can authorize
      // the caller. The BACKEND must (a) require this token on /api/control/* and
      // (b) reject cross-origin requests. Until it does, do NOT expose this UI
      // beyond localhost while the shutdown route is unauthenticated.
      const token = import.meta.env.VITE_CONTROL_TOKEN as string | undefined;
      await fetch(`${apiBase()}/api/control/shutdown`, {
        method: "POST",
        headers: token ? { "X-Orrin-Control-Token": token } : undefined,
      });
    } catch {
      // The process may tear down before the response returns — that's expected.
    }
  };

  return (
    <Button
      variant="destructive"
      size="sm"
      onClick={stop}
      disabled={stopping}
      title="Stop Orrin"
    >
      <Power className="h-4 w-4" />
      <span className="hidden sm:inline">{stopping ? "Stopping…" : "Stop"}</span>
    </Button>
  );
}

function ModeToggle({
  mode,
  onChange,
}: {
  mode: "face" | "brain";
  onChange: (m: "face" | "brain") => void;
}) {
  return (
    <div
      role="tablist"
      aria-label="View mode"
      className="relative flex items-center rounded-full border bg-secondary/60 p-1 shadow-inner"
    >
      {/* sliding pill — icon-only tabs (w-10) below sm, full labels above */}
      <span
        aria-hidden
        className={cn(
          "absolute top-1 h-8 rounded-full bg-background shadow-sm ring-1 ring-border transition-all duration-300 ease-out",
          mode === "face" ? "left-1 w-10 sm:w-[118px]" : "left-[44px] w-10 sm:left-[122px] sm:w-[116px]"
        )}
      />
      <ToggleTab
        active={mode === "face"}
        onClick={() => onChange("face")}
        icon={<Activity className="h-4 w-4" />}
        label="Public Face"
      />
      <ToggleTab
        active={mode === "brain"}
        onClick={() => onChange("brain")}
        icon={<BrainIcon className="h-4 w-4" />}
        label="Core Brain"
      />
    </div>
  );
}

function ToggleTab({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      role="tab"
      aria-selected={active}
      aria-label={label}
      onClick={onClick}
      className={cn(
        "relative z-10 flex h-8 w-10 items-center justify-center gap-1.5 rounded-full text-[13px] font-medium transition-colors sm:w-[114px] sm:px-3.5",
        active ? "text-foreground" : "text-muted-foreground hover:text-foreground"
      )}
    >
      {icon}
      <span className="hidden sm:inline">{label}</span>
    </button>
  );
}
