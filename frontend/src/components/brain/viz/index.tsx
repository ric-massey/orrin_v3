import { cn } from "@/lib/utils";

/**
 * Shared viz primitives for the new information surfaces (UI_FIXES
 * §new-surfaces). Every box composes from these so the boxes stay consistent
 * and readable at a glance. All are tiny dependency-free SVG/DOM.
 *
 *   StatusChip   pill: dot · label · value, colored by health   (L0 row, all boxes)
 *   Gauge        donut arc with a center value                  (ratios, rates)
 *   Sparkline    tiny inline line, no axes                      (L1 trends)
 *   MiniBars     horizontal labeled bars (0..1)                 (drives, coverage)
 *   HitMissStrip row of green/red ticks (recent events)         (predictions)
 *   StackedFlow  one horizontal stacked bar (a→b→c split)       (closure funnel)
 *   Timeline     vertical dated rows (before→after)             (revisions, autobiography)
 *   MiniGraph    small node-link arc diagram                    (causal/knowledge graph)
 */

export type ChipStatus = "ok" | "warn" | "err" | "off";

const STATUS_COLOR: Record<ChipStatus, string> = {
  ok: "hsl(var(--signal-ok))",
  warn: "hsl(var(--signal-warn))",
  err: "hsl(var(--signal-error))",
  off: "hsl(var(--muted-foreground))",
};
export const statusColor = (s: ChipStatus) => STATUS_COLOR[s] ?? STATUS_COLOR.off;

export function StatusChip({
  label,
  value,
  status,
  title,
  onClick,
}: {
  label: string;
  value: string;
  status: ChipStatus;
  title?: string;
  onClick?: () => void;
}) {
  const color = statusColor(status);
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className={cn(
        "flex flex-none items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-1 text-[11px] shadow-sm transition-colors",
        onClick && "hover:bg-muted",
      )}
    >
      <span className="h-2 w-2 rounded-full" style={{ background: color }} />
      <span className="font-medium text-muted-foreground">{label}</span>
      <span className="font-semibold tabular-nums" style={{ color }}>{value}</span>
    </button>
  );
}

export function Gauge({
  value,
  label,
  color = "hsl(var(--signal-accent))",
  size = 64,
  text,
}: {
  /** 0..1 */
  value: number;
  label?: string;
  color?: string;
  size?: number;
  /** Center text override (defaults to a percentage). */
  text?: string;
}) {
  const stroke = Math.max(5, size * 0.09);
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(1, value));
  return (
    <div className="flex flex-col items-center gap-0.5">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="hsl(var(--secondary))" strokeWidth={stroke} />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={color}
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={`${c * pct} ${c}`}
            style={{ transition: "stroke-dasharray 0.5s ease" }}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center text-[12px] font-semibold tabular-nums">
          {text ?? `${Math.round(pct * 100)}%`}
        </div>
      </div>
      {label && <div className="text-[9px] uppercase tracking-wide text-muted-foreground">{label}</div>}
    </div>
  );
}

export function Sparkline({
  points,
  width = 110,
  height = 28,
  color = "hsl(var(--signal-accent))",
  min,
  max,
}: {
  points: number[];
  width?: number;
  height?: number;
  color?: string;
  min?: number;
  max?: number;
}) {
  if (!points.length) return null;
  const lo = min ?? Math.min(...points);
  const hi = max ?? Math.max(...points);
  const span = hi - lo || 1;
  const step = points.length > 1 ? width / (points.length - 1) : 0;
  const d = points
    .map((v, i) => `${i === 0 ? "M" : "L"}${(i * step).toFixed(1)},${(height - 2 - ((v - lo) / span) * (height - 4)).toFixed(1)}`)
    .join(" ");
  return (
    <svg width={width} height={height} className="overflow-visible">
      <path d={d} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" />
      <circle
        cx={(points.length - 1) * step}
        cy={height - 2 - ((points[points.length - 1] - lo) / span) * (height - 4)}
        r={2}
        fill={color}
      />
    </svg>
  );
}

export function MiniBars({
  rows,
  color = "hsl(var(--signal-accent))",
  format = (v: number) => `${Math.round(v * 100)}%`,
}: {
  /** value is 0..1 */
  rows: { label: string; value: number; title?: string }[];
  color?: string;
  format?: (v: number) => string;
}) {
  return (
    <div className="space-y-1">
      {rows.map((r) => (
        <div key={r.label} title={r.title}>
          <div className="mb-0.5 flex justify-between text-[10px]">
            <span className="truncate capitalize text-muted-foreground">{r.label}</span>
            <span className="tabular-nums text-foreground/80">{format(r.value)}</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-secondary">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{ width: `${Math.round(Math.max(0, Math.min(1, r.value)) * 100)}%`, background: color }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

export function HitMissStrip({ results, title }: { results: (boolean | null)[]; title?: string }) {
  return (
    <div className="flex flex-wrap items-center gap-[3px]" title={title}>
      {results.map((r, i) => (
        <span
          key={i}
          className="h-3 w-1.5 rounded-sm"
          style={{
            background:
              r === true ? "hsl(var(--signal-ok))" : r === false ? "hsl(var(--signal-error))" : "hsl(var(--muted-foreground) / 0.3)",
          }}
        />
      ))}
    </div>
  );
}

export function Timeline({
  rows,
  emptyText = "Nothing yet.",
}: {
  rows: {
    ts?: string | number;
    title: string;
    detail?: string;
    color?: string;
    onClick?: () => void;
  }[];
  emptyText?: string;
}) {
  if (!rows.length) {
    return <div className="py-4 text-center text-[11px] text-muted-foreground">{emptyText}</div>;
  }
  const fmt = (ts?: string | number) => {
    if (ts == null) return "";
    const d = typeof ts === "number" ? new Date(ts < 1e12 ? ts * 1000 : ts) : new Date(ts);
    return isNaN(d.getTime())
      ? ""
      : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  };
  return (
    <div className="relative space-y-1.5 pl-3">
      <span className="absolute inset-y-1 left-[3px] w-px bg-border" aria-hidden />
      {rows.map((r, i) => {
        const color = r.color || "hsl(var(--signal-accent))";
        const body = (
          <>
            <span
              className="absolute -left-3 top-1.5 h-[7px] w-[7px] rounded-full ring-2 ring-background"
              style={{ background: color }}
              aria-hidden
            />
            <div className="flex items-baseline gap-2">
              <span className="min-w-0 flex-1 truncate text-[11px] text-foreground/90" title={r.title}>{r.title}</span>
              {r.ts != null && <span className="flex-none text-[9px] tabular-nums text-muted-foreground/70">{fmt(r.ts)}</span>}
            </div>
            {r.detail && <p className="mt-0.5 text-[10px] leading-snug text-muted-foreground" title={r.detail}>{r.detail}</p>}
          </>
        );
        return r.onClick ? (
          <button key={i} onClick={r.onClick} className="relative block w-full rounded px-1 py-0.5 text-left hover:bg-secondary/40">
            {body}
          </button>
        ) : (
          <div key={i} className="relative px-1 py-0.5">{body}</div>
        );
      })}
    </div>
  );
}

export function MiniGraph({
  edges,
  width = 280,
  height = 90,
  maxNodes = 12,
  onNode,
}: {
  /** Directed weighted edges; node set is derived. */
  edges: { from: string; to: string; weight?: number }[];
  width?: number;
  height?: number;
  maxNodes?: number;
  onNode?: (name: string) => void;
}) {
  // Arc diagram: nodes ordered by degree along the baseline, edges as arcs
  // above it — readable at card size without a force simulation.
  const degree = new Map<string, number>();
  for (const e of edges) {
    degree.set(e.from, (degree.get(e.from) || 0) + 1);
    degree.set(e.to, (degree.get(e.to) || 0) + 1);
  }
  const nodes = [...degree.entries()].sort((a, b) => b[1] - a[1]).slice(0, maxNodes).map(([n]) => n);
  if (nodes.length < 2) {
    return <div className="py-3 text-center text-[10px] text-muted-foreground">Not enough edges to draw yet.</div>;
  }
  const keep = new Set(nodes);
  const shown = edges.filter((e) => keep.has(e.from) && keep.has(e.to) && e.from !== e.to);
  const pad = 8;
  const baseline = height - 14;
  const x = (n: string) => pad + (nodes.indexOf(n) / (nodes.length - 1)) * (width - pad * 2);
  const wMax = Math.max(0.001, ...shown.map((e) => e.weight ?? 1));
  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height}`} className="overflow-visible">
      {shown.map((e, i) => {
        const x1 = x(e.from);
        const x2 = x(e.to);
        const mid = (x1 + x2) / 2;
        const lift = Math.min(baseline - 4, Math.abs(x2 - x1) * 0.45 + 8);
        return (
          <path
            key={i}
            d={`M${x1},${baseline} Q${mid},${baseline - lift} ${x2},${baseline}`}
            fill="none"
            stroke="hsl(var(--signal-accent))"
            strokeOpacity={0.25 + 0.55 * ((e.weight ?? 1) / wMax)}
            strokeWidth={0.75 + 1.5 * ((e.weight ?? 1) / wMax)}
          >
            <title>{`${e.from} → ${e.to}${e.weight != null ? ` (${e.weight})` : ""}`}</title>
          </path>
        );
      })}
      {nodes.map((n) => (
        <g key={n} transform={`translate(${x(n)},${baseline})`} className={onNode ? "cursor-pointer" : undefined} onClick={onNode ? () => onNode(n) : undefined}>
          <circle r={3} fill="hsl(var(--foreground) / 0.8)" />
          <title>{n}</title>
          <text
            y={9}
            textAnchor="end"
            transform="rotate(-28)"
            className="fill-current text-muted-foreground"
            style={{ fontSize: 6.5 }}
          >
            {n.length > 14 ? n.slice(0, 13) + "…" : n}
          </text>
        </g>
      ))}
    </svg>
  );
}

export function StackedFlow({
  parts,
}: {
  parts: { label: string; value: number; color: string }[];
}) {
  const total = parts.reduce((n, p) => n + p.value, 0) || 1;
  return (
    <div>
      <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-secondary">
        {parts.filter((p) => p.value > 0).map((p) => (
          <div
            key={p.label}
            className="h-full"
            style={{ width: `${(p.value / total) * 100}%`, background: p.color }}
            title={`${p.label}: ${p.value}`}
          />
        ))}
      </div>
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
        {parts.map((p) => (
          <span key={p.label} className="flex items-center gap-1 text-[9.5px] text-muted-foreground">
            <span className="h-1.5 w-1.5 rounded-full" style={{ background: p.color }} />
            {p.label} <span className="tabular-nums text-foreground/70">{p.value}</span>
          </span>
        ))}
      </div>
    </div>
  );
}
