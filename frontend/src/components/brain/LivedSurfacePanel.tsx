import { Eye } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TelemetryState } from "@/lib/types";
import PanelInfo from "./PanelInfo";

/** P7/A1 — the lived surface: what it is like to be him right now.
 *  Five curated fields assembled brain-side (brain/loop/lived_surface.py) from
 *  the same projections consciousness itself uses — the workspace winner, the
 *  PERCEIVED affect (never raw keys), the effect ledger, degraded goals, and
 *  the long-term driver's frontier. Not a state dump: felt language only. */

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-0.5">
      <div className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="text-sm leading-snug">{children}</div>
    </div>
  );
}

const dash = <span className="text-muted-foreground">—</span>;

export default function LivedSurfacePanel({ telemetry }: { telemetry: TelemetryState }) {
  const lived = telemetry.lived;
  return (
    <Card className="flex h-full flex-col overflow-hidden">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Eye className="h-4 w-4" /> Lived surface
          <PanelInfo
            title="Lived surface"
            what="What it is like to be him right now — attending-to, pressured-by, what changed, what he's steering around, and the gap he's trying to close. Assembled from the felt/perceived projections only; the raw interior is deliberately not readable here."
          />
        </CardTitle>
        <div className="text-xs text-muted-foreground">the first-person view, in felt language</div>
      </CardHeader>
      <CardContent className="flex-1 space-y-3 overflow-y-auto">
        {!lived ? (
          <div className="text-sm text-muted-foreground">Waiting for the first conscious moment…</div>
        ) : (
          <>
            <Row label="Attending to">{lived.attending_to?.trim() || dash}</Row>
            <Row label="Pressured by">
              {lived.pressured_by?.length ? (
                <div className="flex flex-wrap gap-1.5">
                  {lived.pressured_by.map((p) => (
                    <span key={p} className="rounded-full border border-border/60 bg-muted/40 px-2 py-0.5 text-xs">
                      {p}
                    </span>
                  ))}
                </div>
              ) : (
                <span className="text-muted-foreground">nothing loud</span>
              )}
            </Row>
            <Row label="What changed">{lived.what_changed?.trim() || dash}</Row>
            <Row label="Steering around">{lived.avoiding?.trim() || dash}</Row>
            <Row label="Trying to resolve">{lived.trying_to_resolve?.trim() || dash}</Row>
          </>
        )}
      </CardContent>
    </Card>
  );
}
