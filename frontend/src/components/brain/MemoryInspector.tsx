import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Code2, Database, Info, Search, X } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { API } from "@/lib/cognitive";
import { fetchJSON, TTL } from "@/lib/fetchJSON";
import { MemoryRecord, TelemetryState } from "@/lib/telemetry";
import { cn, fmtTime } from "@/lib/utils";
import { usePoll } from "@/lib/usePoll";
import PanelInfo from "./PanelInfo";
import { LexText, PanelSubtitle } from "./Lex";

type SrcRef = { file: string; start: number; end: number; label: string };
type StoreDef = { key: string; label: string; color: string; what: string; src: SrcRef };

// His memory architecture — each store, what it does, and the real code behind it.
const STORES: StoreDef[] = [
  {
    key: "working", label: "Working", color: "#3b82f6",
    what: "Short-term active buffer (~25 items). New thoughts land here; similar items chunk together to make room; low-salience items decay and the salient ones promote to long-term.",
    src: { file: "brain/cog_memory/working_memory.py", start: 145, end: 235, label: "update_working_memory" },
  },
  {
    key: "long", label: "Long-term", color: "#22c55e",
    what: "Consolidated long-term store. Salient working-memory entries promote here; routine ones are digested into summaries; old/unused ones fade (forgetting). Recall is reconstructive, not verbatim.",
    src: { file: "brain/cog_memory/long_memory.py", start: 1, end: 70, label: "long_memory" },
  },
  {
    key: "knowledge", label: "Knowledge graph", color: "#a855f7",
    what: "His semantic world model — typed entities (people / places / concepts) and the relations between them. This is what he 'knows' as structured facts, distinct from episodic memory.",
    src: { file: "brain/cognition/knowledge_graph.py", start: 299, end: 352, label: "_add_entity_inplace" },
  },
  {
    key: "concept", label: "Concepts", color: "#06b6d4",
    what: "Named abstractions distilled over clusters of rules and experiences — his higher-order ideas, the building blocks the Cognitive Sphere groups by.",
    src: { file: "brain/cognition/concept_memory.py", start: 1, end: 70, label: "concept_memory" },
  },
  {
    key: "recall", label: "Recall", color: "#eab308",
    what: "Reconstructive recall — he rebuilds a memory from its gist plus cues rather than replaying it verbatim, the way human episodic recall works (and mis-remembers).",
    src: { file: "brain/cog_memory/reconstruction.py", start: 1, end: 70, label: "reconstruction" },
  },
  {
    key: "chat", label: "Conversation", color: "#ec4899",
    what: "His running conversation history with the people he talks to.",
    src: { file: "brain/cog_memory/chat_log.py", start: 1, end: 60, label: "chat_log" },
  },
  {
    key: "semantic", label: "Semantic facts", color: "#f59e0b",
    what: "Action→outcome regularities distilled from experience during consolidation — compact 'when I do X in context Y, Z happens' facts with confidence counts.",
    src: { file: "brain/cognition/dreaming/semantic_extractor.py", start: 1, end: 70, label: "semantic_extractor" },
  },
];
const storeOf = (k?: string) => STORES.find((s) => s.key === (k || "").toLowerCase()) || STORES[1];

// Stores the backend can browse directly (GET /api/memory?store=…) — the real
// files on disk, as opposed to the live op ring streamed over the socket.
const BROWSABLE = ["long", "working", "knowledge", "semantic"] as const;
type BrowsableStore = (typeof BROWSABLE)[number];

/** One raw entry from a real store file. Shapes vary per store; we surface the
 *  common fields and keep the rest for the drawer's raw view. */
interface StoreEntry {
  id?: string;
  content?: string;
  timestamp?: string | number;
  event_type?: string;
  importance?: number | string;
  [k: string]: unknown;
}

function CodeBlock({ src }: { src: SrcRef }) {
  const [code, setCode] = useState<{ s: string; loading: boolean; err?: string }>({ s: "", loading: true });
  useEffect(() => {
    setCode({ s: "", loading: true });
    fetchJSON<{ source?: string; error?: string }>(`${API}/source?file=${encodeURIComponent(src.file)}&start=${src.start}&end=${src.end}`, { ttlMs: TTL.immutable })
      .then((d) => setCode({ s: d.source || "", loading: false, err: d.error }))
      .catch((e) => setCode({ s: "", loading: false, err: String(e) }));
  }, [src.file, src.start, src.end]);
  return (
    <div className="mt-2">
      <div className="mb-1 flex items-center gap-1 text-[10px] text-muted-foreground">
        <Code2 className="h-3 w-3" />
        <span className="truncate">{src.label}</span>
        <span className="ml-auto font-mono text-muted-foreground/70">{src.file.split("/").pop()}:{src.start}</span>
      </div>
      {code.loading && <div className="text-[10px] text-muted-foreground">Loading source…</div>}
      {code.err && <div className="text-[10px] text-signal-error">Couldn't load: {code.err}</div>}
      {code.s && (
        <pre className="max-h-72 overflow-auto rounded bg-muted/40 p-2 text-[10px] leading-snug">
          <code className="font-mono">{code.s}</code>
        </pre>
      )}
    </div>
  );
}

// Right-side drawer: a store's explanation+code, a single live-op record, or a
// full store entry (Browse tab — L3/L4: full content, provenance, raw record).
function MemoryDrawer({ store, record, entry, onClose }: { store: StoreDef; record?: MemoryRecord; entry?: StoreEntry; onClose: () => void }) {
  const [showCode, setShowCode] = useState(false);
  const [showRaw, setShowRaw] = useState(false);
  useEffect(() => { setShowCode(false); setShowRaw(false); }, [store.key, record?.key, entry?.id]);
  return (
    <div role="dialog" aria-modal="true" aria-label="Memory details" className="absolute inset-y-0 right-0 z-30 flex w-[min(400px,85%)] flex-col border-l border-border bg-card/95 shadow-2xl backdrop-blur">
      <div className="flex items-center gap-2 border-b border-border px-3 py-2.5">
        <button onClick={onClose} className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground" aria-label="Back">
          <ArrowLeft className="h-4 w-4" />
        </button>
        <span className="h-2.5 w-2.5 rounded-full" style={{ background: store.color }} />
        <span className="min-w-0 flex-1 truncate text-[13px] font-semibold">{record ? record.key : entry ? (entry.event_type || entry.id || store.label) : store.label}</span>
        <span className="rounded-full px-2 py-0.5 text-[10px]" style={{ background: `${store.color}22`, color: store.color }}>{store.label}</span>
        <button onClick={onClose} className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground" aria-label="Close">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-auto p-3 text-[12px]">
        {record && (
          <div className="mb-3 space-y-1.5">
            <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
              <span className={cn("rounded px-1.5 py-0.5 font-semibold", record.op === "write" ? "bg-signal-warn/15 text-signal-warn" : "bg-signal-info/15 text-signal-info")}>{record.op}</span>
              {record.salience != null && <span>salience {(Number(record.salience) * 100).toFixed(0)}/100</span>}
              <span className="ml-auto">{fmtTime(record.ts)}</span>
            </div>
            <div className="rounded-md bg-muted/40 p-2 text-[11px] leading-relaxed text-foreground/90">
              {record.summary || <span className="text-muted-foreground">(no content)</span>}
            </div>
            <div className="text-[10px] leading-snug text-muted-foreground/70">
              This is a live op record (a sampled read/write event), not the stored entry — use Browse store for the store itself.
            </div>
          </div>
        )}

        {entry && (
          <div className="mb-3 space-y-1.5">
            <div className="flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
              {entry.event_type && <span className="rounded bg-secondary px-1.5 py-0.5 font-semibold">{entry.event_type}</span>}
              {entry.importance != null && <span>importance {String(entry.importance)}</span>}
              {entry.timestamp != null && <span className="ml-auto">{String(entry.timestamp).slice(0, 19).replace("T", " ")}</span>}
            </div>
            <div className="whitespace-pre-wrap rounded-md bg-muted/40 p-2 text-[11px] leading-relaxed text-foreground/90">
              {entry.content || <span className="text-muted-foreground">(no content field — see raw record)</span>}
            </div>
            <button
              onClick={() => setShowRaw((v) => !v)}
              className="flex items-center gap-1.5 rounded-md border border-border px-2 py-1 text-[10px] font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              {showRaw ? "Hide raw record" : "Show raw record (JSON)"}
            </button>
            {showRaw && (
              <pre className="max-h-72 overflow-auto rounded bg-muted/40 p-2 text-[10px] leading-snug">
                <code className="font-mono">{JSON.stringify(entry, null, 2)}</code>
              </pre>
            )}
          </div>
        )}

        <div className="text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">About this store</div>
        <p className="mt-1 text-[11px] leading-relaxed text-foreground/85">{store.what}</p>

        <button
          onClick={() => setShowCode((v) => !v)}
          className="mt-3 flex items-center gap-1.5 rounded-md border border-border px-2 py-1 text-[10px] font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <Code2 className="h-3 w-3" /> {showCode ? "Hide code" : "Show the code that runs this store"}
        </button>
        {showCode && <CodeBlock src={store.src} />}
      </div>
    </div>
  );
}

export default function MemoryInspector({ telemetry }: { telemetry: TelemetryState }) {
  const [tab, setTab] = useState<"live" | "store">("live");
  const [q, setQ] = useState("");
  const [op, setOp] = useState<"all" | "read" | "write">("all");
  const [storeFilter, setStoreFilter] = useState<string | null>(null);
  const [drawer, setDrawer] = useState<{ store: StoreDef; record?: MemoryRecord; entry?: StoreEntry } | null>(null);

  // ── Browse-store state (Fix 8: the store, not the stream) ────────────────
  const [browseStore, setBrowseStore] = useState<BrowsableStore>("long");
  const [entries, setEntries] = useState<StoreEntry[]>([]);
  const [storeTotal, setStoreTotal] = useState(0);
  const [storeMatched, setStoreMatched] = useState(0);
  const [sizes, setSizes] = useState<Record<string, number>>({});

  // True store sizes for the chips — live-op counts are NOT sizes.
  useEffect(() => {
    let stop = false;
    const load = () =>
      fetchJSON<{ counts?: Record<string, number> }>(`${API}/memory_counts`, { ttlMs: TTL.short })
        .then((d) => { if (!stop && d.counts) setSizes(d.counts); })
        .catch(() => {});
    load();
    const id = setInterval(load, 30_000);
    return () => { stop = true; clearInterval(id); };
  }, []);

  // Browse the real store file (paged tail, searchable) while the tab is open.
  useEffect(() => {
    if (tab !== "store") return;
    let stop = false;
    const load = () =>
      fetchJSON<{ entries?: StoreEntry[]; total?: number; matched?: number }>(
        `${API}/memory?store=${browseStore}&q=${encodeURIComponent(q.trim())}&n=100`, { ttlMs: TTL.short })
        .then((d) => {
          if (stop) return;
          setEntries(Array.isArray(d.entries) ? d.entries : []);
          setStoreTotal(d.total ?? 0);
          setStoreMatched(d.matched ?? 0);
        })
        .catch(() => {});
    load();
    const id = setInterval(load, 10_000);
    return () => { stop = true; clearInterval(id); };
  }, [tab, browseStore, q]);

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const r of telemetry.memory) c[(r.store || "").toLowerCase()] = (c[(r.store || "").toLowerCase()] || 0) + 1;
    return c;
  }, [telemetry.memory]);

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return [...telemetry.memory]
      .reverse()
      .filter((r) => (op === "all" ? true : r.op === op))
      .filter((r) => (storeFilter ? (r.store || "").toLowerCase() === storeFilter : true))
      .filter((r) => (!needle ? true : `${r.key} ${r.summary} ${r.store}`.toLowerCase().includes(needle)))
      .slice(0, 250);
  }, [telemetry.memory, q, op, storeFilter]);

  // Forgetting strip (ui_fixes.md): decayed/pruned/retired per sweep — memory
  // staying bounded is only believable when you can watch him forget. Polled
  // only while the Browse tab is open.
  const forgetting = usePoll<{ sweeps?: { decayed?: number; pruned?: number; retired?: number; timestamp?: string }[] }>(
    tab === "store" ? `${API}/forgetting?n=30` : "",
    30_000,
  );
  const sweeps = forgetting?.sweeps || [];
  const lastSweep = sweeps[sweeps.length - 1];
  const forgotten = sweeps.reduce((n, s) => n + (s.decayed || 0) + (s.pruned || 0) + (s.retired || 0), 0);

  return (
    <Card id="box-memory" className="relative flex h-full flex-col overflow-hidden">
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2 space-y-0 pb-2">
        <CardTitle className="flex min-w-0 flex-1 flex-wrap items-center gap-2 text-sm font-medium text-muted-foreground">
          <Database className="h-4 w-4" /> <LexText id="memory_title" />
          <PanelSubtitle id="memory_sub" />
          <PanelInfo
            title="Memory Inspector"
            perspective="agent-accessible"
            what="Two honest views of his memory: Live ops is a sampled ticker of this session's reads/writes (≤4 per operation — it under-reports bulk sweeps by design); Browse store is the real contents on disk, searchable and paged. Chips show true store sizes; each store's ℹ️ explains it and shows its code."
            source="Live ops: telemetry socket · Browse: GET /api/memory over long_memory.json, working_memory.json, knowledge_graph.json, semantic_facts.json"
            good="Long-term growing slowly then PLATEAUING (the reaper working — ties to B1), working memory hovering around its ~25-item cap, and recalls that reference what's actually stored."
          />
          {tab === "live" ? (
            <span className="text-xs text-muted-foreground/60" title="Sampled live read/write events this session (≤4 per op) — NOT the store contents. Browse store for those.">
              {telemetry.memory.length} ops (sampled)
            </span>
          ) : (
            <span className="text-xs text-muted-foreground/60">{storeTotal} stored{q.trim() ? ` · ${storeMatched} match` : ""}</span>
          )}
        </CardTitle>
        <div className="flex w-full flex-wrap items-center gap-2 xl:w-auto">
          {/* Live ops ↔ Browse store: the stream/state split, made honest. */}
          <div className="flex rounded-md border border-border p-0.5">
            {(["live", "store"] as const).map((k) => (
              <button
                key={k}
                onClick={() => setTab(k)}
                className={cn("rounded px-2 py-0.5 text-[11px] font-medium transition-colors", tab === k ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground")}
              >
                {k === "live" ? "Live ops" : "Browse store"}
              </button>
            ))}
          </div>
          {tab === "live" && (
            <div className="flex rounded-md border border-border p-0.5">
              {(["all", "read", "write"] as const).map((k) => (
                <button
                  key={k}
                  onClick={() => setOp(k)}
                  className={cn("rounded px-2 py-0.5 text-[11px] font-medium capitalize transition-colors", op === k ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground")}
                >
                  {k}
                </button>
              ))}
            </div>
          )}
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={tab === "live" ? "Search live ops…" : "Search the store…"}
              className="h-7 w-36 rounded-md border border-border bg-background pl-8 pr-2 text-[11px] outline-none placeholder:text-muted-foreground sm:w-40"
            />
          </div>
        </div>
      </CardHeader>

      <CardContent className="relative min-h-0 flex-1 p-0">
        {/* Stores reference — chips show TRUE store sizes; live-op counts are the
            small secondary badge. Click to filter (live) / select (browse);
            ℹ️ to read what the store is + see its code. */}
        <div className="flex flex-wrap items-center gap-1.5 border-b border-border px-3 py-2">
          {tab === "live" && (
            <button
              onClick={() => setStoreFilter(null)}
              className={cn("rounded px-1.5 py-0.5 text-[10px]", !storeFilter ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground")}
            >
              all
            </button>
          )}
          {STORES.filter((s) => tab === "live" || (BROWSABLE as readonly string[]).includes(s.key)).map((s) => {
            const liveN = counts[s.key] || 0;
            const sizeN = sizes[s.key];
            const isSel = tab === "live" ? storeFilter === s.key : browseStore === s.key;
            return (
              <span key={s.key} className="flex items-center">
                <button
                  onClick={() =>
                    tab === "live"
                      ? setStoreFilter(storeFilter === s.key ? null : s.key)
                      : setBrowseStore(s.key as BrowsableStore)
                  }
                  className={cn("flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] transition-colors", isSel ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground")}
                  title={sizeN != null ? `${sizeN} entries in the store${liveN ? ` · ${liveN} live ops this session` : ""}` : liveN ? `${liveN} live ops this session` : "no live records yet"}
                >
                  <span className="h-1.5 w-1.5 rounded-full" style={{ background: s.color }} />
                  {s.label}
                  {sizeN != null && <span className="font-semibold text-foreground/70 tabular-nums">{sizeN}</span>}
                  {liveN > 0 && <span className="text-muted-foreground/50 tabular-nums">·{liveN}</span>}
                </button>
                <button onClick={() => setDrawer({ store: s })} className="rounded p-0.5 text-muted-foreground/50 hover:text-foreground" aria-label={`About ${s.label}`}>
                  <Info className="h-3 w-3" />
                </button>
              </span>
            );
          })}
        </div>

        {/* Live ops feed (sampled ticker of this session's reads/writes) */}
        {tab === "live" && (
          <div className="scrollbar-thin h-[calc(100%-2.6rem)] overflow-auto">
            <table className="w-full text-left text-xs">
              <thead className="sticky top-0 z-10 bg-card">
                <tr className="border-b border-border text-[10px] uppercase tracking-wider text-muted-foreground">
                  <Th className="w-14">Time</Th>
                  <Th className="w-12">Op</Th>
                  <Th>Key</Th>
                  <Th>Summary</Th>
                  <Th className="w-12 text-right">Sal.</Th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="py-10 text-center text-muted-foreground">No memory records {q || storeFilter ? "match" : "yet"}.</td>
                  </tr>
                ) : (
                  rows.map((r, i) => {
                    const s = storeOf(r.store);
                    return (
                      <tr
                        key={(r.id ?? "") + i}
                        onClick={() => setDrawer({ store: s, record: r })}
                        className="cursor-pointer border-b border-border/40 transition-colors hover:bg-secondary/40"
                      >
                        <Td className="tabular-nums text-muted-foreground">{fmtTime(r.ts)}</Td>
                        <Td>
                          <span className={cn("rounded px-1 py-0.5 text-[9px] font-semibold", r.op === "write" ? "bg-signal-warn/15 text-signal-warn" : "bg-signal-info/15 text-signal-info")}>{r.op}</span>
                        </Td>
                        <Td className="font-mono text-[11px]">
                          <span className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full align-middle" style={{ background: s.color }} />
                          <span className="align-middle">{r.key}</span>
                        </Td>
                        <Td className="max-w-0 truncate text-muted-foreground" title={r.summary}>{r.summary}</Td>
                        <Td className="text-right tabular-nums text-muted-foreground">{r.salience != null ? Number(r.salience).toFixed(2) : "—"}</Td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* Browse store: the real contents on disk, newest-first */}
        {tab === "store" && (
          <div className="scrollbar-thin h-[calc(100%-2.6rem)] overflow-auto">
            {/* Forgetting strip — watch him forget (pairs with B1: bounded memory). */}
            {sweeps.length > 0 && (
              <div
                className="flex flex-wrap items-center gap-x-3 gap-y-0.5 border-b border-border/60 bg-muted/20 px-3 py-1 text-[9.5px] text-muted-foreground"
                title="The forgetting ledger (forgetting_log.json): what each sweep decayed, pruned, or retired. Memory staying bounded is only believable when you can watch him forget."
              >
                <span className="font-semibold uppercase tracking-wide">Forgetting</span>
                <span>{forgotten} forgotten over {sweeps.length} sweep{sweeps.length === 1 ? "" : "s"}</span>
                {lastSweep && (
                  <span className="ml-auto tabular-nums">
                    last sweep: {lastSweep.decayed ?? 0} decayed · {lastSweep.pruned ?? 0} pruned · {lastSweep.retired ?? 0} retired
                    {lastSweep.timestamp ? ` · ${String(lastSweep.timestamp).slice(5, 16).replace("T", " ")}` : ""}
                  </span>
                )}
              </div>
            )}
            {entries.length === 0 ? (
              <div className="py-10 text-center text-xs text-muted-foreground">
                {q.trim() ? "No store entries match." : "Store is empty (or still loading)."}
              </div>
            ) : (
              entries.map((e, i) => {
                const s = storeOf(browseStore);
                return (
                  <button
                    key={(e.id ?? "") + i}
                    onClick={() => setDrawer({ store: s, entry: e })}
                    className="flex w-full items-start gap-2 border-b border-border/40 px-3 py-1.5 text-left transition-colors hover:bg-secondary/40"
                  >
                    <span className="mt-1.5 h-1.5 w-1.5 flex-none rounded-full" style={{ background: s.color }} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[11px] text-foreground/90">
                        {e.content || e.event_type || e.id || "(structured entry)"}
                      </span>
                      <span className="flex gap-2 text-[9px] text-muted-foreground">
                        {e.event_type && <span>{e.event_type}</span>}
                        {e.importance != null && <span>imp {String(e.importance)}</span>}
                        {e.timestamp != null && <span className="ml-auto">{String(e.timestamp).slice(0, 19).replace("T", " ")}</span>}
                      </span>
                    </span>
                  </button>
                );
              })
            )}
          </div>
        )}

        {drawer && <MemoryDrawer store={drawer.store} record={drawer.record} entry={drawer.entry} onClose={() => setDrawer(null)} />}
      </CardContent>
    </Card>
  );
}

function Th({ children, className }: { children: React.ReactNode; className?: string }) {
  return <th className={cn("px-3 py-1.5 font-medium", className)}>{children}</th>;
}
function Td({ children, className, title }: { children: React.ReactNode; className?: string; title?: string }) {
  return (
    <td className={cn("px-3 py-1.5", className)} title={title}>
      {children}
    </td>
  );
}
