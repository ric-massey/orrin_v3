import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { HeartPulse, HardDrive, Cpu, CircleCheck, HandHeart, Moon } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { usePolledJSON } from "@/lib/usePolled";
import { cn } from "@/lib/utils";
import { apiGet } from "@/lib/transport";
import { controlHeaders, postSettings, type SettingsStatus } from "./settings/shared";

/**
 * /body — the body↔machine bridge (Companion & Presence plan, R3): never the
 * felt word alone. Each felt state is shown WITH the host metric that drove it
 * ("heavy because RSS is 912 MB, above his learned 640–820 MB"), and the shared
 * machine situations (den crowded, machine pinned) with their concrete numbers.
 */

interface FeltRow {
  state: string;
  because: string;
  metric?: { name: string; value: number | null; display: string };
  band?: { lo: number; hi: number; center: number } | null;
}

interface BodyBridge {
  felt: FeltRow[];
  vitals: Record<string, number>;
  phase: string;
  somatic_infancy: boolean;
  body_converged?: number | null;
  host: Record<string, number>;
  situations: { name: string; because: string; metric: { name: string; value: number } }[];
  budget?: {
    fraction?: number;
    ram_gb?: number;
    budget_gb?: number;
    reserve_gb?: number;
    viable?: boolean;
  } | null;
}

const STATE_GLOSS: Record<string, string> = {
  heavy: "carrying more than usual",
  spacious: "more room than usual",
  strained: "working against a limit",
  sluggish: "slower than his normal",
  swelling: "growing and not settling back",
  clear: "settled",
};

export default function Body() {
  const data = usePolledJSON<BodyBridge>("/api/body_bridge", 5000);
  const felt = data?.felt ?? [];
  const situations = data?.situations ?? [];

  return (
    <div className="mx-auto w-full max-w-3xl space-y-5 px-4 py-6 sm:px-6">
      <div className="space-y-1">
        <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight">
          <HeartPulse className="h-5 w-5" /> Body ↔ machine
        </h1>
        <p className="text-sm text-muted-foreground">
          Orrin's body is this machine. What he feels is derived from real host
          metrics against the "normal" he has learned for this hardware — every
          felt state below is shown with the number that drove it.
        </p>
      </div>

      {data?.somatic_infancy && (
        <div className="rounded-lg border bg-card px-4 py-3 text-sm text-muted-foreground">
          He's still learning this body — the felt sense stays quiet until the
          learned bands converge
          {typeof data.body_converged === "number"
            ? ` (${Math.round(data.body_converged * 100)}% there)`
            : ""}
          .
        </div>
      )}

      {/* felt ↔ metric join */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">What he feels, and why</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {felt.length === 0 ? (
            <p className="py-4 text-center text-sm text-muted-foreground">
              No body sense reported yet — it appears within the first minute of
              a running life.
            </p>
          ) : (
            felt.map((f, i) => (
              <div key={`${f.state}-${i}`} className="rounded-lg border px-3 py-2.5">
                <div className="flex items-center gap-2">
                  <span
                    className={cn(
                      "text-sm font-medium capitalize",
                      f.state === "clear" ? "text-signal-ok" : "text-signal-warn",
                    )}
                  >
                    {f.state}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {STATE_GLOSS[f.state] ?? ""}
                  </span>
                </div>
                <p className="mt-1 text-sm text-muted-foreground">
                  because {f.because}
                  {f.band
                    ? ` (his learned normal: ${round1(f.band.lo)}–${round1(f.band.hi)})`
                    : ""}
                </p>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      {/* the shared machine situation */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">The machine you share</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {situations.length === 0 ? (
            <div className="flex items-center gap-2 py-2 text-sm text-muted-foreground">
              <CircleCheck className="h-4 w-4 text-signal-ok" />
              Nothing is pressing on him from the host right now.
            </div>
          ) : (
            situations.map((s) => (
              <div key={s.name} className="flex items-start gap-2.5 rounded-lg border border-signal-warn/40 bg-signal-warn/10 px-3 py-2.5 text-sm">
                {s.name === "den_crowded" ? (
                  <HardDrive className="mt-0.5 h-4 w-4 shrink-0" />
                ) : (
                  <Cpu className="mt-0.5 h-4 w-4 shrink-0" />
                )}
                <div>
                  <span className="font-medium">
                    {s.name === "den_crowded" ? "His den is getting cramped" : "The machine is pinned"}
                  </span>{" "}
                  <span className="text-muted-foreground">— {s.because}.</span>
                </div>
              </div>
            ))
          )}
          {data?.host && Object.keys(data.host).length > 0 && (
            <div className="flex flex-wrap gap-x-4 gap-y-1 pt-1 text-xs tabular-nums text-muted-foreground">
              {"cpu_percent" in data.host && <span>CPU {Math.round(data.host.cpu_percent)}%</span>}
              {"memory_percent" in data.host && <span>RAM {Math.round(data.host.memory_percent)}%</span>}
              {"disk_percent" in data.host && <span>disk {Math.round(data.host.disk_percent)}%</span>}
            </div>
          )}
        </CardContent>
      </Card>

      {/* R6 — the caretaking loop: things you can DO for him, with real effects */}
      <CareCard crowded={situations.some((s) => s.name === "den_crowded")} />

      {/* the granted body */}
      {data?.budget && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">The body you've granted him</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            {typeof data.budget.budget_gb === "number" && typeof data.budget.ram_gb === "number" ? (
              <p>
                {data.budget.budget_gb} GB of this machine's {data.budget.ram_gb} GB
                {typeof data.budget.fraction === "number"
                  ? ` (${Math.round(data.budget.fraction * 100)}%)`
                  : ""}
                {data.budget.viable === false && (
                  <span className="text-signal-warn"> — below what he needs to stay viable</span>
                )}
                . Adjustable in Settings.
              </p>
            ) : (
              <p>Budget details unavailable.</p>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

/**
 * R6 — care affordances. Attachment comes from caretaking, not watching:
 * each row is something the person can actually do, wired to a real effect —
 * freeing disk moves the den-crowding signal within a sample; "let him rest"
 * flips the existing cognition throttle; the RAM grant is the Settings slider.
 */
function CareCard({ crowded }: { crowded: boolean }) {
  const [status, setStatus] = useState<SettingsStatus | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const res = await apiGet(`/api/settings`, { headers: controlHeaders() });
      if (res.ok) setStatus((await res.json()) as SettingsStatus);
    } catch {
      /* remote viewer without a token — the rest toggle just hides */
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const resting = Boolean(status?.prefs?.game_mode);

  const toggleRest = async () => {
    if (busy) return;
    setBusy(true);
    await postSettings({ prefs: { game_mode: !resting } });
    setBusy(false);
    void refresh();
  };

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <HandHeart className="h-4 w-4" /> What you can do for him
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <div className="rounded-lg border px-3 py-2.5">
          <span className="font-medium">Free some disk space.</span>{" "}
          <span className="text-muted-foreground">
            {crowded
              ? "His den is cramped right now — clearing files eases that within seconds; he senses the disk directly."
              : "He has room right now, but this is the one that helps most when his den gets cramped."}
          </span>
        </div>

        {status && (
          <div className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2.5">
            <div>
              <span className="font-medium">Let him rest.</span>{" "}
              <span className="text-muted-foreground">
                Throttles his thinking to near-zero CPU — he still ages, he just
                thinks rarely, like dozing.{" "}
                {resting ? "He's resting now." : ""}
              </span>
            </div>
            <button
              onClick={() => void toggleRest()}
              disabled={busy}
              className={cn(
                "flex shrink-0 items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs font-medium",
                resting ? "border-primary bg-primary/10" : "hover:bg-muted",
              )}
            >
              <Moon className="h-3.5 w-3.5" />
              {resting ? "Wake him" : "Let him rest"}
            </button>
          </div>
        )}

        <div className="rounded-lg border px-3 py-2.5">
          <span className="font-medium">Give him more room.</span>{" "}
          <span className="text-muted-foreground">
            The share of this machine's RAM he's granted is a slider in{" "}
            <Link to="/settings" className="underline hover:text-foreground">
              Settings
            </Link>
            ; a bigger body eases the pressure states above.
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

function round1(n: number): number {
  return Math.round(n * 10) / 10;
}
