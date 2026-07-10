import { Home, Power, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { useMode, writeMode, type OrrinMode } from "@/lib/mode";
import StopButton from "@/components/StopButton";
import { ToggleRow } from "./ToggleRow";
import { postSettings, type SettingsStatus } from "./shared";

/**
 * C5 — the home-screen choice, in Settings. Re-running the intro (moved here
 * from the Language section) is now also how you re-answer the question.
 * In companion mode this section additionally hosts the Stop control, since
 * the companion header hides it (C3). The R8 peripheral mini-orb toggle lives
 * here too — it's the same "how present is he" family of choices.
 */
export function HomeScreenSection({
  status,
  onChanged,
}: {
  status: SettingsStatus | null;
  onChanged: () => void;
}) {
  const mode = useMode();

  const options: { value: OrrinMode; label: string; hint: string }[] = [
    { value: "companion", label: "Companion", hint: "One quiet room — Orrin, his journal, and you." },
    { value: "workshop", label: "Workshop", hint: "All eight rooms and the full research grid." },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Home className="h-4 w-4" /> Home screen
        </CardTitle>
        <CardDescription>
          The same runtime either way — this only chooses which face of it greets
          you. You can always step through to the other side.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex gap-2">
          {options.map((o) => (
            <button
              key={o.value}
              onClick={() => writeMode(o.value)}
              className={cn(
                "flex-1 rounded-lg border px-3 py-2.5 text-left transition-colors",
                mode === o.value
                  ? "border-primary bg-primary/5 ring-1 ring-primary"
                  : "border-border hover:bg-muted",
              )}
            >
              <span className="block text-sm font-medium">{o.label}</span>
              <span className="block text-xs text-muted-foreground">{o.hint}</span>
            </button>
          ))}
        </div>

        <Button
          size="sm"
          variant="ghost"
          onClick={() => window.dispatchEvent(new Event("orrin:meet"))}
        >
          <Sparkles className="mr-1.5 h-4 w-4" /> Replay the intro
        </Button>

        {/* R8 — the peripheral mini-orb (second frameless window; opt-in). */}
        <ToggleRow
          label="Peripheral mini-orb"
          warn="A tiny always-on-top orb that breathes with his mood while you work. Takes effect on the next launch."
          checked={Boolean(status?.prefs?.widget_enabled)}
          onChange={async (v) => {
            await postSettings({ prefs: { widget_enabled: v } });
            onChanged();
          }}
        />

        {mode === "companion" && (
          <div className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2.5">
            <div className="flex items-start gap-2 text-xs text-muted-foreground">
              <Power className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>
                Stopping halts Orrin's runtime — his loop and daemons pause until
                you start him again. His memory and goals stay saved.
              </span>
            </div>
            <StopButton />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
