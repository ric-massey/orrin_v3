import { useEffect, useState } from "react";
import { Clock, Star, Wind, Fingerprint, Search } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { usePolledJSON } from "@/lib/usePolled";
import InfoDot from "@/components/brain/InfoDot";
import { ROOM_INFO } from "@/lib/roomMetrics";

// Which source note backs each lens (Part 8 drill-down).
const LENS_INFO: Record<Lens, keyof typeof ROOM_INFO> = {
  recent: "memory_list",
  important: "memory_list",
  forgotten: "memory_forgotten",
  identity: "memory_identity",
};

// Memory Explorer (§9.5) — four lenses over data that already ships. The "Forgotten"
// lens is the quietly powerful one: visible decay is what makes "the memory store
// stays bounded" believable. All four are honest-empty on a fresh runtime.

type Lens = "recent" | "important" | "forgotten" | "identity";

const LENSES: { id: Lens; label: string; icon: typeof Clock }[] = [
  { id: "recent", label: "Recent", icon: Clock },
  { id: "important", label: "Important", icon: Star },
  { id: "forgotten", label: "Forgotten", icon: Wind },
  { id: "identity", label: "Identity", icon: Fingerprint },
];

interface MemFeed { entries?: Record<string, unknown>[]; matched?: number; total?: number }
interface ForgetFeed { sweeps?: Record<string, unknown>[]; total?: number }
interface SelfFeed { autobiography?: Record<string, unknown>; opinions?: Record<string, unknown>[] }

export default function Memory() {
  const [lens, setLens] = useState<Lens>("recent");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");

  // Debounce search → query so we don't refetch every keystroke.
  useEffect(() => {
    const id = window.setTimeout(() => setQuery(search.trim()), 350);
    return () => window.clearTimeout(id);
  }, [search]);

  const memPath =
    lens === "important"
      ? `/api/memory?store=long&order=importance&n=40&q=${encodeURIComponent(query)}`
      : `/api/memory?store=long&order=recency&n=40&q=${encodeURIComponent(query)}`;

  return (
    <div className="mx-auto w-full max-w-4xl space-y-5 px-4 py-6 sm:px-6">
      <div className="space-y-1">
        <h1 className="flex items-center gap-1 text-xl font-semibold tracking-tight">
          Memory
          <InfoDot info={ROOM_INFO[LENS_INFO[lens]]} />
        </h1>
        <p className="text-sm text-muted-foreground">What the runtime retains, what it keeps, and what it lets decay.</p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {LENSES.map((l) => (
          <button
            key={l.id}
            onClick={() => setLens(l.id)}
            className={cn(
              "flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm transition-colors",
              lens === l.id ? "bg-background text-foreground ring-1 ring-border" : "text-muted-foreground hover:text-foreground",
            )}
          >
            <l.icon className="h-3.5 w-3.5" />
            {l.label}
          </button>
        ))}
        {(lens === "recent" || lens === "important") && (
          <div className="ml-auto flex min-w-[180px] flex-1 items-center gap-2 rounded-md border border-border bg-background px-2.5 sm:flex-none">
            <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search memories…"
              className="min-w-0 flex-1 bg-transparent py-1.5 text-sm outline-none"
            />
          </div>
        )}
      </div>

      {lens === "recent" || lens === "important" ? (
        <MemoryList path={memPath} />
      ) : lens === "forgotten" ? (
        <ForgottenList />
      ) : (
        <IdentityList />
      )}
    </div>
  );
}

function MemoryList({ path }: { path: string }) {
  const feed = usePolledJSON<MemFeed>(path, 8000);
  const entries = feed?.entries ?? [];
  if (feed && entries.length === 0)
    return <Empty>No memories here yet{feed.total === 0 ? " — fresh runtime" : ""}.</Empty>;
  return (
    <div className="space-y-2">
      {feed?.matched != null && (
        <p className="text-xs text-muted-foreground">{feed.matched} of {feed.total} memories</p>
      )}
      {entries.map((e, i) => (
        <Card key={i}>
          <CardContent className="space-y-1 py-3">
            <p className="text-sm">{String(e.content ?? e.summary ?? e.text ?? JSON.stringify(e)).slice(0, 600)}</p>
            <Meta entry={e} />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function ForgottenList() {
  const feed = usePolledJSON<ForgetFeed>("/api/forgetting?n=40", 8000);
  const sweeps = feed?.sweeps ?? [];
  if (feed && sweeps.length === 0) return <Empty>Nothing forgotten yet — nothing has decayed or been pruned.</Empty>;
  return (
    <div className="space-y-2">
      <p className="text-xs text-muted-foreground">Decay keeps the memory store bounded.</p>
      {[...sweeps].reverse().map((s, i) => (
        <Card key={i}>
          <CardContent className="py-3 text-sm">
            {String(s.summary ?? s.reason ?? s.kind ?? JSON.stringify(s)).slice(0, 400)}
            {s.count != null && <span className="text-muted-foreground"> · {String(s.count)} items</span>}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function IdentityList() {
  const feed = usePolledJSON<SelfFeed>("/api/identity", 8000);
  const opinions = feed?.opinions ?? [];
  const auto = feed?.autobiography ?? {};
  const autoEntries = Object.entries(auto);
  if (feed && opinions.length === 0 && autoEntries.length === 0)
    return <Empty>No identity state formed yet.</Empty>;
  return (
    <div className="space-y-4">
      {autoEntries.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-sm font-medium text-muted-foreground">Run history</h2>
          {autoEntries.slice(0, 12).map(([k, v]) => (
            <Card key={k}>
              <CardContent className="py-3 text-sm">
                <span className="text-muted-foreground">{k}: </span>
                {String(typeof v === "string" ? v : JSON.stringify(v)).slice(0, 400)}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
      {opinions.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-sm font-medium text-muted-foreground">Learned beliefs</h2>
          {opinions.slice(-12).reverse().map((o, i) => (
            <Card key={i}>
              <CardContent className="py-3 text-sm">
                {String(o.topic ?? o.subject ?? "")} {o.topic || o.subject ? "— " : ""}
                {String(o.opinion ?? o.stance ?? o.text ?? JSON.stringify(o)).slice(0, 400)}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function Meta({ entry }: { entry: Record<string, unknown> }) {
  const imp = entry.importance ?? entry.salience ?? entry.weight;
  const ts = entry.ts ?? entry.timestamp ?? entry.created_at;
  if (imp == null && ts == null) return null;
  return (
    <p className="text-xs text-muted-foreground">
      {imp != null && <>importance {Number(imp).toFixed(2)}</>}
      {imp != null && ts != null && " · "}
      {ts != null && <>{typeof ts === "number" ? new Date(ts * (ts > 1e12 ? 1 : 1000)).toLocaleString() : String(ts)}</>}
    </p>
  );
}

const Empty = ({ children }: { children: React.ReactNode }) => (
  <Card>
    <CardContent className="py-8 text-center text-sm italic text-muted-foreground">{children}</CardContent>
  </Card>
);
