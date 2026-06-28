import { API } from "@/lib/cognitive";
import { usePoll } from "@/lib/usePoll";
import { lastSuccessAt } from "@/lib/fetchJSON";
import { ChipStatus, StatusChip } from "./viz";
import StaleBadge from "./StaleBadge";

/**
 * The L0 vital-signs row (UI_FIXES §new-surfaces): one health chip per
 * subsystem, each a word+number+color computed SERVER-side by /api/resources so
 * this row polls one URL on one ~10s timer — the "understandable initially"
 * layer. Clicking a chip scrolls to its box.
 */
interface VitalChip {
  key: string;
  label: string;
  value: string;
  status: ChipStatus;
  detail?: string;
}

export default function ResourceSignsRow() {
  const url = `${API}/vitals`;
  const data = usePoll<{ chips?: VitalChip[] }>(url, 10_000);
  const chips = data?.chips || [];

  // M4: don't silently vanish on backend failure. If we have no chips but a
  // fetch has previously succeeded (or has been attempted), show a visibly
  // degraded strip + StaleBadge rather than removing the whole row — a missing
  // health summary is a weaker failure signal than a degraded one.
  if (chips.length === 0) {
    const ok = lastSuccessAt(url);
    if (!ok) return null; // truly nothing yet (first poll in flight) — stay quiet
    return (
      <div className="mb-4 flex items-center gap-2 text-[11px] text-muted-foreground">
        <span className="rounded bg-signal-warn/10 px-1.5 py-0.5 text-signal-warn">Health metrics unavailable</span>
        <StaleBadge url={url} pollMs={10_000} />
      </div>
    );
  }

  const jump = (key: string) => {
    document.getElementById(`box-${key}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  return (
    <div className="scrollbar-thin mb-4 flex items-center gap-2 overflow-x-auto pb-1">
      {chips.map((c) => (
        <StatusChip
          key={c.key}
          label={c.label}
          value={c.value}
          status={c.status}
          title={c.detail ? `${c.detail} — click to jump to the box` : "Click to jump to the box"}
          onClick={() => jump(c.key)}
        />
      ))}
      <StaleBadge url={url} pollMs={10_000} />
    </div>
  );
}
