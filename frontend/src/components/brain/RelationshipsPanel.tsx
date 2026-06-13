import { Users } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { API } from "@/lib/cognitive";
import { usePoll } from "@/lib/usePoll";
import PanelInfo from "./PanelInfo";
import StaleBadge from "./StaleBadge";
import { LexText, PanelSubtitle } from "./Lex";

/** Box ⑧ — Relationships / people. Person models from relationships.json plus
 *  the known-persons registry. His internal peer observers live in the same
 *  file — rendered as a DISTINCT "internal peers" group, never as people. */

interface Person {
  name: string;
  type?: string;
  impression?: string;
  trust?: number;
  influence_score?: number;
  depth?: number;
  interactions?: number;
  last_interaction_time?: string;
}
interface Known {
  id: string;
  display_name?: string;
  person_type?: string;
  session_count?: number;
  first_seen?: string;
  last_seen?: string;
  notes?: string;
}

function fmtDate(ts?: string): string {
  if (!ts) return "";
  const d = new Date(ts);
  return isNaN(d.getTime()) ? "" : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export default function RelationshipsPanel() {
  const data = usePoll<{ people?: Person[]; peers?: Person[]; known?: Known[] }>(`${API}/people`, 30_000);
  const people = data?.people || [];
  const peers = data?.peers || [];
  const known = data?.known || [];

  return (
    <Card id="box-people" className="flex h-full flex-col overflow-hidden">
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="flex min-w-0 items-center gap-2 text-sm font-medium text-muted-foreground">
          <Users className="h-4 w-4" /> <LexText id="people_title" />
          <PanelInfo
            title="Relationships / people"
            what="Who he knows: his model of each person (impression, trust, depth, interaction count) and the known-persons registry (how often someone has shown up). His internal peer observers — synthetic voices that audit his rewards, goals and emotions from inside — live in the same store and are shown as a separate group, because they are parts of him, not people."
            source="GET /api/people over brain/data/relationships.json · known_persons.json"
            good="Person models that deepen with real interaction (trust/depth moving, impressions getting specific) — and the peers clearly separated from humans."
            src={{ file: "brain/peers/observer.py", start: 1, end: 60, label: "peer observer" }}
          />
          <PanelSubtitle id="people_sub" />
          <StaleBadge url={`${API}/people`} pollMs={30_000} />
        </CardTitle>
        <span className="text-[11px] text-muted-foreground/60">{people.length + known.length} known · {peers.length} peers</span>
      </CardHeader>
      <CardContent className="scrollbar-thin min-h-0 flex-1 space-y-3 overflow-auto pb-3">
        <div>
          <div className="mb-1 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">People</div>
          {people.length === 0 && known.length === 0 ? (
            <div className="rounded-md border border-border bg-muted/30 px-2 py-3 text-center text-[11px] text-muted-foreground">
              No people modeled yet — only anonymous contact so far.
            </div>
          ) : (
            <div className="space-y-1">
              {people.map((p) => (
                <PersonRow key={p.name} p={p} />
              ))}
              {known.map((k) => (
                <div key={k.id} className="rounded-md border border-border bg-card/40 px-2 py-1.5">
                  <div className="flex items-baseline gap-2">
                    <span className="text-[11px] font-medium capitalize text-foreground/90">{k.display_name || k.id}</span>
                    <span className="text-[9px] text-muted-foreground">{k.person_type || "unknown"}</span>
                    <span className="ml-auto text-[9px] tabular-nums text-muted-foreground">{k.session_count ?? 0} session{(k.session_count ?? 0) === 1 ? "" : "s"}</span>
                  </div>
                  <div className="mt-0.5 flex gap-2 text-[9px] text-muted-foreground/70">
                    {k.first_seen && <span>first {fmtDate(k.first_seen)}</span>}
                    {k.last_seen && <span>last {fmtDate(k.last_seen)}</span>}
                  </div>
                  {k.notes && <p className="mt-0.5 text-[10px] text-muted-foreground">{k.notes}</p>}
                </div>
              ))}
            </div>
          )}
        </div>

        {peers.length > 0 && (
          <div>
            <div className="mb-1 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground" title="Synthetic internal observers — parts of his architecture, not people.">
              Internal peers (not people)
            </div>
            <div className="space-y-1">
              {peers.map((p) => (
                <PersonRow key={p.name} p={p} peer />
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function PersonRow({ p, peer }: { p: Person; peer?: boolean }) {
  return (
    <div className={peer ? "rounded-md border border-dashed border-border bg-card/30 px-2 py-1.5" : "rounded-md border border-border bg-card/40 px-2 py-1.5"}>
      <div className="flex items-baseline gap-2">
        <span className="text-[11px] font-medium text-foreground/90">{p.name.replace(/_/g, " ")}</span>
        <span className="ml-auto flex gap-2 text-[9px] tabular-nums text-muted-foreground">
          {p.trust != null && <span title="trust">trust {Number(p.trust).toFixed(2)}</span>}
          {p.influence_score != null && <span title="influence">infl {Number(p.influence_score).toFixed(2)}</span>}
          {p.depth != null && <span title="relationship depth">depth {Number(p.depth).toFixed(2)}</span>}
        </span>
      </div>
      {p.impression && <p className="mt-0.5 text-[10px] italic leading-snug text-muted-foreground" title={p.impression}>“{p.impression}”</p>}
      <div className="mt-0.5 flex gap-2 text-[9px] text-muted-foreground/70">
        <span>{p.interactions ?? 0} interactions</span>
        {p.last_interaction_time && <span className="ml-auto">last {fmtDate(p.last_interaction_time)}</span>}
      </div>
    </div>
  );
}
