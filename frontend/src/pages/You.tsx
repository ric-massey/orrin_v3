import { UserRound } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { usePolledJSON } from "@/lib/usePolled";
import { agoLabel, cn } from "@/lib/utils";

/**
 * /you — his model of you (Companion & Presence plan, R1): what Orrin currently
 * believes about each person he talks to, surfaced from the theory-of-mind state
 * his mentalizing model already keeps. Provenance on every belief (which
 * exchange produced it) and staleness are the point — legibility is what turns
 * surveillance into intimacy. Read-only.
 */

interface TomPerson {
  name: string;
  current: { affective_state: string; cognitive_state: string; intention: string; as_of: string };
  belief_model: {
    feels_understood: boolean | null;
    in_alignment: boolean | null;
    satisfied_last: boolean | null;
    belief_discordance: boolean;
    consecutive_misalignments: number;
    preference_alignment: number | null;
    last_artifact_correction?: string | null;
  };
  prediction: { intention?: string; family?: string; state?: string; accuracy: number; hits: number; total: number };
  synchrony: number;
  misalignment_streak: number;
  history: { state?: string; cognitive_state?: string; intention?: string; ts?: string }[];
}

function epoch(iso: string | undefined): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : t / 1000;
}

export default function You() {
  const feed = usePolledJSON<{ people: TomPerson[] }>("/api/theory_of_mind", 6000);
  const people = feed?.people ?? [];

  return (
    <div className="mx-auto w-full max-w-3xl space-y-5 px-4 py-6 sm:px-6">
      <div className="space-y-1">
        <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight">
          <UserRound className="h-5 w-5" /> His model of you
        </h1>
        <p className="text-sm text-muted-foreground">
          Orrin keeps a running simulation of the person he's talking to — what
          you think, intend, and feel. This is that model, opened up: every read
          is stamped with the exchange that produced it, and it goes stale
          honestly when you're away.
        </p>
      </div>

      {people.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            He hasn't formed a model of anyone yet. It builds as you talk to him
            — nothing here is collected any other way.
          </CardContent>
        </Card>
      ) : (
        people.map((p) => <PersonCard key={p.name} person={p} />)
      )}
    </div>
  );
}

function PersonCard({ person: p }: { person: TomPerson }) {
  const asOf = epoch(p.current.as_of);
  const stale = asOf !== null && Date.now() / 1000 - asOf > 3600;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-baseline justify-between text-base">
          <span>{p.name}</span>
          <span className={cn("text-xs font-normal", stale ? "text-signal-warn" : "text-muted-foreground")}>
            {asOf !== null ? `last exchange ${agoLabel(asOf)}` : "no exchanges recorded"}
            {stale && " · this read is stale"}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {/* the current read */}
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          <ReadBox label="Feeling (his read)" value={p.current.affective_state || "—"} />
          <ReadBox label="Thinking (his read)" value={p.current.cognitive_state || "—"} />
          <ReadBox label="Wanting (his read)" value={p.current.intention || "—"} />
        </div>

        {/* belief model */}
        <div className="space-y-1.5">
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            What he believes about the conversation
          </div>
          <TriStateRow label="You feel understood" value={p.belief_model.feels_understood} />
          <TriStateRow label="You two are in alignment" value={p.belief_model.in_alignment} />
          <TriStateRow label="You were satisfied last time" value={p.belief_model.satisfied_last} />
          {p.belief_model.consecutive_misalignments > 0 && (
            <p className="text-xs text-signal-warn">
              He's registered {p.belief_model.consecutive_misalignments} misalignment
              {p.belief_model.consecutive_misalignments === 1 ? "" : "s"} in a row.
            </p>
          )}
          {p.belief_model.last_artifact_correction && (
            <p className="text-xs text-muted-foreground">
              Last correction he took to heart: “{p.belief_model.last_artifact_correction}”
            </p>
          )}
        </div>

        {/* prediction + synchrony */}
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <div className="rounded-lg border px-3 py-2">
            <div className="text-xs text-muted-foreground">His guess at your next move</div>
            <div className="mt-0.5">{p.prediction.intention || "—"}</div>
            <div className="mt-1 text-xs text-muted-foreground">
              {p.prediction.total > 0
                ? `right ${p.prediction.hits} of ${p.prediction.total} recent guesses (${Math.round(p.prediction.accuracy * 100)}%)`
                : "no guesses scored yet"}
            </div>
          </div>
          <div className="rounded-lg border px-3 py-2">
            <div className="text-xs text-muted-foreground">Emotional synchrony</div>
            <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary transition-all"
                style={{ width: `${Math.round(p.synchrony * 100)}%` }}
              />
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              {Math.round(p.synchrony * 100)}% — how closely your moods have been moving together
            </div>
          </div>
        </div>

        {/* provenance trail */}
        {p.history.length > 0 && (
          <div className="space-y-1">
            <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Where these reads came from
            </div>
            <ul className="space-y-0.5">
              {[...p.history].reverse().map((h, i) => {
                const t = epoch(h.ts);
                return (
                  <li key={i} className="flex items-baseline justify-between gap-3 text-xs">
                    <span className="truncate text-muted-foreground">
                      read you as <span className="text-foreground">{h.state || "?"}</span>
                      {h.intention ? <> · {h.intention}</> : null}
                    </span>
                    <span className="shrink-0 tabular-nums text-muted-foreground">
                      {t !== null ? agoLabel(t) : ""}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ReadBox({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border px-3 py-2">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-0.5 capitalize">{value.replace(/_/g, " ")}</div>
    </div>
  );
}

function TriStateRow({ label, value }: { label: string; value: boolean | null }) {
  const state =
    value === true
      ? { mark: "yes", cls: "text-signal-ok" }
      : value === false
      ? { mark: "no", cls: "text-signal-warn" }
      : { mark: "unsure", cls: "text-muted-foreground" };
  return (
    <div className="flex items-center justify-between rounded-md border px-3 py-1.5">
      <span>{label}</span>
      <span className={cn("text-xs font-medium", state.cls)}>{state.mark}</span>
    </div>
  );
}
