import { API } from "@/lib/cognitive";
import { usePoll } from "@/lib/usePoll";
import { ChipStatus, StatusChip } from "./viz";

/**
 * The L0 vital-signs row (UI_FIXES §new-surfaces): one health chip per
 * subsystem, each a word+number+color computed SERVER-side by /api/vitals so
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

export default function VitalSignsRow() {
  const data = usePoll<{ chips?: VitalChip[] }>(`${API}/vitals`, 10_000);
  const chips = data?.chips || [];
  if (chips.length === 0) return null;

  const jump = (key: string) => {
    document.getElementById(`box-${key}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  return (
    <div className="scrollbar-thin mb-4 flex gap-2 overflow-x-auto pb-1">
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
    </div>
  );
}
