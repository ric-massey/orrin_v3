import { Activity, Clock, Cpu, HardDrive, HeartPulse, MemoryStick, Sparkles } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { useLexicon, type LexId } from "@/lib/lexicon";
import { usePolledJSON } from "@/lib/usePolled";

// Life Support (§9.10) — the same numbers as a sysadmin's stats, framed as a being's
// vital signs (Resource Manager in the engineering dialect). Two honesty rules from
// the code: Life Remaining is his *felt* estimate (never the true countdown), and
// resources are about HIM (disk = his mind's room to grow).

interface LifeFeed {
  cpu?: { available_pct?: number; load_pct?: number };
  memory?: { available_bytes?: number; total_bytes?: number };
  storage?: { free_bytes?: number; used_bytes?: number; total_bytes?: number };
  mind_disk?: { used_bytes?: number; ceiling_bytes?: number; ratio?: number };
  thinking_rate_per_min?: number;
  cycle?: number;
  mortality?: {
    born_at?: string;
    age_days?: number;
    felt_days_remaining?: number;
    phase?: string;
  };
  interests?: string[];
}

const GB = 1024 ** 3;
const fmtGB = (b?: number) => (b == null ? "—" : `${(b / GB).toFixed(1)} GB`);
const PHASE_LABEL: Record<string, string> = {
  early: "the early phase of his life",
  middle: "midlife",
  late: "the late phase of his life",
  terminal: "his final days",
};

export default function Life() {
  const { t } = useLexicon();
  const life = usePolledJSON<LifeFeed>("/api/life", 5000);

  const cpuAvail = life?.cpu?.available_pct;
  const rate = life?.thinking_rate_per_min ?? 0;
  const slow = rate > 0 && rate < 1.5;
  const lowCpu = cpuAvail != null && cpuAvail < 15;

  return (
    <div className="mx-auto w-full max-w-4xl space-y-5 px-4 py-6 sm:px-6">
      <div className="space-y-1">
        <h1 className="text-xl font-semibold tracking-tight">{t("nav_life")}</h1>
        <p className="text-sm text-muted-foreground">
          His resources, his thinking rate, his age, and the life he believes he has
          left — read as a body, not a server.
        </p>
      </div>

      {(slow || lowCpu) && (
        <div className="rounded-lg border border-signal-warn/40 bg-signal-warn/10 px-4 py-2.5 text-sm">
          He's thinking slowly — the machine is busy.
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Vital lex="life_cpu" t={t} icon={Cpu} amber={lowCpu}
          value={cpuAvail != null ? `${cpuAvail.toFixed(0)}%` : "—"}
          detail={life?.cpu?.load_pct != null ? `load ${life.cpu.load_pct.toFixed(0)}%` : ""} />
        <Vital lex="life_mem" t={t} icon={MemoryStick}
          value={fmtGB(life?.memory?.available_bytes)}
          detail={life?.memory?.total_bytes ? `of ${fmtGB(life.memory.total_bytes)}` : ""} />
        <Vital lex="life_disk" t={t} icon={HardDrive}
          amber={(life?.mind_disk?.ratio ?? 0) > 0.9}
          value={
            life?.mind_disk?.ceiling_bytes != null
              ? fmtGB(Math.max(0, (life.mind_disk.ceiling_bytes ?? 0) - (life.mind_disk.used_bytes ?? 0)))
              : fmtGB(life?.storage?.free_bytes)
          }
          detail={
            life?.mind_disk?.ceiling_bytes != null
              ? `his mind is ${fmtGB(life.mind_disk.used_bytes)} of ${fmtGB(life.mind_disk.ceiling_bytes)}`
              : life?.storage?.used_bytes != null ? `${fmtGB(life.storage.used_bytes)} used` : ""
          } />
        <Vital lex="life_rate" t={t} icon={HeartPulse} amber={slow}
          value={rate > 0 ? `${rate.toFixed(1)}/min` : "0"}
          detail={rate > 0 ? `cycle ${life?.cycle ?? 0}` : "not thinking right now"} />
        <Vital lex="life_age" t={t} icon={Clock}
          value={life?.mortality?.age_days != null ? `${life.mortality.age_days.toFixed(1)} days` : "—"}
          detail={life?.mortality?.born_at ? `born ${life.mortality.born_at.slice(0, 10)}` : ""} />
        <Vital lex="life_remaining" t={t} icon={Activity}
          value={life?.mortality?.felt_days_remaining != null ? `~${Math.round(life.mortality.felt_days_remaining)} days` : "—"}
          detail={life?.mortality?.phase ? `he feels he's in ${PHASE_LABEL[life.mortality.phase] || life.mortality.phase}` : "what he believes — not the true number"} />
      </div>

      <Card>
        <CardContent className="pt-5">
          <div className="mb-2 flex items-center gap-2 text-sm font-medium text-muted-foreground">
            <Sparkles className="h-4 w-4" /> {t("life_interests")}
          </div>
          {life?.interests && life.interests.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {life.interests.map((g, i) => (
                <span key={i} className="rounded-full border bg-background px-2.5 py-1 text-sm">
                  {g}
                </span>
              ))}
            </div>
          ) : (
            <p className="text-sm italic text-muted-foreground">Nothing actively pulling at him right now.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Vital({
  lex,
  t,
  icon: Icon,
  value,
  detail,
  amber,
}: {
  lex: LexId;
  t: (id: LexId) => string;
  icon: typeof Cpu;
  value: string;
  detail?: string;
  amber?: boolean;
}) {
  return (
    <Card className={cn(amber && "border-signal-warn/50")}>
      <CardContent className="space-y-1 pt-5">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Icon className="h-4 w-4" />
          {t(lex)}
        </div>
        <div className={cn("text-2xl font-semibold tabular-nums", amber && "text-signal-warn")}>{value}</div>
        {detail && <div className="text-xs text-muted-foreground">{detail}</div>}
      </CardContent>
    </Card>
  );
}
