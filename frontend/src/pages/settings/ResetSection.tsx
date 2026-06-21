import { useState } from "react";
import { RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { apiPost } from "@/lib/transport";
import { controlHeaders } from "./shared";

export function ResetSection() {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const reset = async () => {
    if (busy) return;
    if (
      !window.confirm(
        "Reset Orrin? This permanently erases his memories, goals, identity, and everything he's written, then restarts him as a newborn. This cannot be undone.",
      )
    ) {
      return;
    }
    setBusy(true);
    setNote("Resetting — Orrin is becoming a newborn and will restart…");
    try {
      const res = await apiPost(`/api/control/reset`, undefined, { headers: controlHeaders() });
      if (!res.ok && res.status !== 0) {
        setBusy(false);
        setNote(`Couldn't reset (HTTP ${res.status}).`);
      }
    } catch {
      // The process re-execs, so the request often drops mid-flight — that means it
      // worked. Leave the "restarting…" note up.
    }
  };

  return (
    <Card className="border-destructive/30">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <RotateCcw className="h-4 w-4" /> Reset Orrin
        </CardTitle>
        <CardDescription>
          Erase this mind and begin a brand-new one. His memories, goals, identity, and
          self-written code are gone for good — there is no undo.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        <Button variant="destructive" size="sm" onClick={() => void reset()} disabled={busy}>
          {busy ? "Resetting…" : "Reset Orrin to a newborn"}
        </Button>
        {note && <p className="text-xs text-foreground">{note}</p>}
      </CardContent>
    </Card>
  );
}
