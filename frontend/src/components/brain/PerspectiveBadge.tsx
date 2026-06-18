import { cn } from "@/lib/utils";

export type PerspectiveLayer = "dev-only" | "agent-accessible" | "in-attention";

const LAYERS: Record<PerspectiveLayer, { label: string; title: string; className: string }> = {
  "dev-only": {
    label: "dev-only",
    title: "Developer instrumentation: useful for observers, not something Orrin is directly attending to.",
    className: "border-muted-foreground/30 text-muted-foreground",
  },
  "agent-accessible": {
    label: "agent-accessible",
    title: "Agent-accessible state: Orrin can read or use this internal state, but it is not necessarily in attention right now.",
    className: "border-primary/40 text-primary",
  },
  "in-attention": {
    label: "in-attention",
    title: "In-attention state: this is part of the current workspace, felt state, or active cognitive contents.",
    className: "border-signal-ok/45 text-signal-ok",
  },
};

export function PerspectiveBadge({
  layer,
  className,
}: {
  layer?: PerspectiveLayer;
  className?: string;
}) {
  if (!layer) return null;
  const meta = LAYERS[layer];
  return (
    <span
      title={meta.title}
      className={cn(
        "inline-flex shrink-0 items-center rounded border px-1.5 py-0.5 text-[9px] font-medium uppercase leading-none",
        meta.className,
        className,
      )}
    >
      {meta.label}
    </span>
  );
}
