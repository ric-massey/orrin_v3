import { useEffect, useMemo, useRef, useState } from "react";
import { Target, Brain, Moon, Lightbulb, Globe, UploadCloud, Circle, Hammer } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { apiGet } from "@/lib/transport";
import InfoDot from "@/components/brain/InfoDot";
import { ROOM_INFO } from "@/lib/roomMetrics";

// "While you were away" (§9.8) — the feature that most makes an autonomous system
// feel alive. The "last seen" marker is a per-viewer client value (localStorage in the
// browser; config.json in the desktop app), so the summary is honest per viewer and
// needs no server session state.

const LAST_SEEN_KEY = "orrin.lastSeen.v1";
// R7: which reunion line this viewer has already seen (its ts) — shown once.
const REUNION_SEEN_KEY = "orrin.reunionSeen.v1";

interface ActEvent { type: string; ts: number; label: string }
interface ActFeed { events?: ActEvent[]; summary?: Record<string, number>; since?: number }
interface Reunion { text?: string; gap_s?: number; ts?: number }

const ICON: Record<string, typeof Target> = {
  goal: Target,
  memory: Brain,
  dream: Moon,
  belief: Lightbulb,
  web: Globe,
  finetune: UploadCloud,
  selfmod: Hammer,
};
const SUMMARY_LABEL: Record<string, (n: number) => string> = {
  goal: (n) => `Generated ${n} goal${n === 1 ? "" : "s"}`,
  memory: (n) => `Created ${n} memor${n === 1 ? "y" : "ies"}`,
  dream: (n) => `Dreamed ${n} time${n === 1 ? "" : "s"}`,
  belief: (n) => `Revised ${n} belief${n === 1 ? "" : "s"}`,
  web: (n) => `Visited ${n} site${n === 1 ? "" : "s"}`,
  finetune: (n) => `Ran ${n} fine-tune upload${n === 1 ? "" : "s"}`,
  selfmod: (n) => `Taught himself ${n} new skill${n === 1 ? "" : "s"}`,
};

function formatGap(s: number): string {
  if (s >= 86400) return `${Math.floor(s / 86400)} day${s >= 172800 ? "s" : ""} away`;
  if (s >= 3600) return `${Math.floor(s / 3600)} hour${s >= 7200 ? "s" : ""} away`;
  return `${Math.max(1, Math.floor(s / 60))} minutes away`;
}

function readLastSeen(): number {
  try {
    const v = localStorage.getItem(LAST_SEEN_KEY);
    if (v) return Number(JSON.parse(v));
  } catch {
    /* private mode */
  }
  return Date.now() / 1000 - 86400; // first visit → last 24h
}

export default function Timeline() {
  // Capture last-seen at mount; the summary is "since then". Advance it afterwards.
  const sinceRef = useRef<number>(readLastSeen());
  const [feed, setFeed] = useState<ActFeed | null>(null);
  const [reunion, setReunion] = useState<Reunion | null>(null);

  useEffect(() => {
    let alive = true;
    const since = sinceRef.current;
    (async () => {
      try {
        const res = await apiGet(`/api/activity?since=${Math.floor(since)}`);
        if (res.ok && alive) setFeed((await res.json()) as ActFeed);
      } catch {
        /* honest-empty */
      }
    })();
    // R7: his own registration of the gap — shown once per viewer, above the list.
    (async () => {
      try {
        const res = await apiGet(`/api/reunion`);
        if (!res.ok || !alive) return;
        const r = (await res.json()) as Reunion;
        if (!r?.text || !r?.ts) return;
        let seen = 0;
        try {
          seen = Number(JSON.parse(localStorage.getItem(REUNION_SEEN_KEY) || "0"));
        } catch {
          /* private mode */
        }
        if (r.ts > seen && alive) {
          setReunion(r);
          try {
            localStorage.setItem(REUNION_SEEN_KEY, JSON.stringify(r.ts));
          } catch {
            /* private mode */
          }
        }
      } catch {
        /* no reunion — the list stands alone */
      }
    })();
    // Advance "last seen" to now so the NEXT visit measures from here.
    try {
      localStorage.setItem(LAST_SEEN_KEY, JSON.stringify(Date.now() / 1000));
    } catch {
      /* private mode */
    }
    return () => {
      alive = false;
    };
  }, []);

  const sinceLabel = useMemo(() => {
    const d = new Date(sinceRef.current * 1000);
    const sameDay = new Date().toDateString() === d.toDateString();
    return sameDay ? `today, ${d.toLocaleTimeString()}` : d.toLocaleString();
  }, []);

  const summary = feed?.summary ?? {};
  const summaryRows = Object.entries(summary).filter(([, n]) => n > 0);
  const events = feed?.events ?? [];

  return (
    <div className="mx-auto w-full max-w-3xl space-y-5 px-4 py-6 sm:px-6">
      <div className="space-y-1">
        <h1 className="flex items-center gap-1 text-xl font-semibold tracking-tight">
          While you were away
          <InfoDot info={ROOM_INFO.timeline} />
        </h1>
        <p className="text-sm text-muted-foreground">since {sinceLabel}</p>
      </div>

      {/* R7 — he registers the gap as himself, before the list. His words, verbatim. */}
      {reunion?.text && (
        <div className="rounded-xl border bg-card p-4 animate-fade-in sm:p-5">
          <p className="text-[15px] leading-relaxed">“{reunion.text}”</p>
          <p className="mt-1.5 text-xs text-muted-foreground">
            — Orrin, waking after {formatGap(reunion.gap_s ?? 0)}
          </p>
        </div>
      )}

      <Card>
        <CardContent className="pt-5">
          {summaryRows.length > 0 ? (
            <ul className="space-y-1.5">
              {summaryRows.map(([type, n]) => {
                const Icon = ICON[type] ?? Circle;
                const label = (SUMMARY_LABEL[type] ?? ((x: number) => `${x} ${type}`))(n);
                return (
                  <li key={type} className="flex items-center gap-2 text-sm">
                    <Icon className="h-4 w-4 text-muted-foreground" />
                    {label}
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="text-sm italic text-muted-foreground">
              {feed ? "Nothing happened while you were away." : "Loading the recent activity log…"}
            </p>
          )}
        </CardContent>
      </Card>

      {events.length > 0 && (
        <div>
          <h2 className="mb-2 text-sm font-medium text-muted-foreground">Full timeline</h2>
          <ol className="relative space-y-2 border-l pl-4">
            {events.map((e, i) => {
              const Icon = ICON[e.type] ?? Circle;
              return (
                <li key={i} className="relative">
                  <span className="absolute -left-[21px] top-1.5 flex h-3 w-3 items-center justify-center rounded-full bg-background ring-1 ring-border">
                    <Icon className="h-2 w-2 text-muted-foreground" />
                  </span>
                  <Card>
                    <CardContent className="flex items-baseline justify-between gap-3 py-2.5">
                      <span className="min-w-0 truncate text-sm">{e.label}</span>
                      <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                        {new Date(e.ts * 1000).toLocaleTimeString()}
                      </span>
                    </CardContent>
                  </Card>
                </li>
              );
            })}
          </ol>
        </div>
      )}
    </div>
  );
}
