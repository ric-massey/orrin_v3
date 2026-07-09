import { CloudMoon } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { API } from "@/lib/cognitive";
import { usePoll } from "@/lib/usePoll";
import PanelInfo from "./PanelInfo";
import { LexText, PanelSubtitle } from "./Lex";
import StaleBadge from "./StaleBadge";
import { MiniBars } from "./viz";

/** Box ⑨ — Inner weather / felt time. The strongest "it's a someone" data in
 *  brain/data (temporal_state is live, rich, and human-readable), previously
 *  fully hidden. Pure read of three small files. */

interface Temporal {
  session_cycles?: number;
  felt_cycles?: number;
  internal_clock_rate?: number;
  session_arc?: string;
  felt_duration_label?: string;
  time_texture?: string;
  cycles_since_contact?: number;
  boundary_count?: number;
  temporal_self_location?: string;
  retrospective_feel?: string;
  last_landmark?: { content?: string; cycles_ago?: number; felt_distance?: string; importance?: number } | null;
}
interface Mood { valence?: number; energy?: number; stability?: number }
// Felt-only view from life_status() — the true lifespan/noise offset is never served (§10.3).
interface Lifespan { born_at?: string | null; age_days?: number; felt_days_remaining?: number | null; final_thoughts_written?: boolean }

const words = (s?: string) => (s || "").replace(/_/g, " ");

export default function InternalStatePanel() {
  const data = usePoll<{ temporal?: Temporal; mood?: Mood; lifespan?: Lifespan }>(`${API}/innerweather`, 15_000);
  const t = data?.temporal;
  const mood = data?.mood;
  const life = data?.lifespan;

  // Mood values run -1..1 (valence) / 0..1; normalize for bars.
  const moodRows = mood
    ? [
        { label: "valence", value: Math.max(0, Math.min(1, (Number(mood.valence ?? 0) + 1) / 2)), title: "reward sign − ↔ + (50% = neutral)" },
        { label: "energy", value: Math.max(0, Math.min(1, Number(mood.energy ?? 0))) },
        { label: "stability", value: Math.max(0, Math.min(1, Number(mood.stability ?? 0))) },
      ]
    : [];

  let ageDays: number | null = life?.age_days ?? null;
  if (ageDays == null && life?.born_at) {
    const born = new Date(life.born_at).getTime();
    if (!isNaN(born)) ageDays = (Date.now() - born) / 86_400_000;
  }

  return (
    <Card id="box-innerweather" className="flex h-full flex-col overflow-hidden">
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          <CloudMoon className="h-4 w-4" /> <LexText id="innerweather_title" />
          <PanelInfo
            title="Clock & state summary"
            perspective="agent-accessible"
            what="The runtime's internal clock estimate, distinct from how much wall-clock has passed: internal vs. real cycles, the session's arc, the texture of the present ('waiting, long absence'), how far back the last notable event is estimated — plus its smoothed signal state and its lifecycle position (it has a finite projected runtime budget)."
            source="brain/data/temporal_state.json · smoothed_state.json · runtime_lifetime.json"
            good="There is no 'good' here — this box is a window, not a gauge. Watch felt time stretch when nothing happens and compress when a lot does."
            src={{ file: "brain/cognition/temporal_state.py", start: 1, end: 70, label: "temporal_state" }}
          />
          <PanelSubtitle id="innerweather_sub" />
          <StaleBadge url={`${API}/innerweather`} pollMs={15_000} />
        </CardTitle>
        <span className="text-[11px] capitalize text-muted-foreground/60">{t?.session_arc ?? "—"}</span>
      </CardHeader>
      <CardContent className="scrollbar-thin min-h-0 flex-1 space-y-3 overflow-auto pb-3">
        {!t ? (
          <div className="py-8 text-center text-xs text-muted-foreground">No temporal state yet.</div>
        ) : (
          <>
            {/* The felt-time phrase — the L0 of personhood. */}
            <div className="rounded-lg border border-border bg-card/60 px-3 py-2">
              <p className="text-[13px] font-medium capitalize leading-snug text-foreground/95">
                {words(t.session_arc)} · est. {t.felt_duration_label || "—"}
              </p>
              <p className="mt-0.5 text-[11px] text-muted-foreground">
                {words(t.time_texture)} · {t.temporal_self_location || "—"}
              </p>
            </div>

            <div className="grid grid-cols-3 gap-2 text-center">
              <div>
                <div className="text-lg font-semibold tabular-nums">{Math.round(Number(t.felt_cycles ?? 0))}</div>
                <div className="text-[9px] uppercase tracking-wide text-muted-foreground">felt cycles</div>
              </div>
              <div>
                <div className="text-lg font-semibold tabular-nums">{t.session_cycles ?? "—"}</div>
                <div className="text-[9px] uppercase tracking-wide text-muted-foreground">real cycles</div>
              </div>
              <div>
                <div className="text-lg font-semibold tabular-nums">×{Number(t.internal_clock_rate ?? 1).toFixed(2)}</div>
                <div className="text-[9px] uppercase tracking-wide text-muted-foreground">clock rate</div>
              </div>
            </div>

            {t.last_landmark?.content && (
              <div>
                <div className="mb-1 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">Last landmark</div>
                <div className="rounded-md border border-border bg-card/40 px-2 py-1.5">
                  <p className="truncate text-[10.5px] text-foreground/85" title={t.last_landmark.content}>{t.last_landmark.content}</p>
                  <p className="mt-0.5 text-[9.5px] text-muted-foreground">
                    {t.last_landmark.felt_distance || "—"} · {t.last_landmark.cycles_ago ?? "?"} cycles ago
                  </p>
                </div>
              </div>
            )}

            {moodRows.length > 0 && (
              <div>
                <div className="mb-1 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">Smoothed state</div>
                <MiniBars rows={moodRows} color="hsl(var(--signal-info))" />
              </div>
            )}

            {life && life.born_at != null && (
              <div className="border-t border-border/60 pt-2 text-[10px] leading-snug text-muted-foreground">
                {ageDays != null && <>Alive {ageDays.toFixed(1)} days</>}
                {life.felt_days_remaining != null && <> · ~{Math.round(life.felt_days_remaining)} days left by his own estimate</>}
                {" · "}final thoughts {life.final_thoughts_written ? "written" : "not yet written"}.
                <span className="block text-muted-foreground/60">
                  cycles since contact: {t.cycles_since_contact ?? "—"} · session boundaries: {t.boundary_count ?? 0}
                </span>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
