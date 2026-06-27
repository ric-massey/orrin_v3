import { BookOpenText } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { API } from "@/lib/cognitive";
import { usePoll } from "@/lib/usePoll";
import PanelInfo from "./PanelInfo";
import StaleBadge from "./StaleBadge";
import { LexText, PanelSubtitle } from "./Lex";
import { MiniBars } from "./viz";

/** Language-organ box — the from-scratch language system (ORRIN_LANGUAGE_PLAN):
 *  phrase banks, learned phrases, what it's actually said (with quality
 *  scores), the books it's read, and the native LM artifacts on disk. */

interface SpeechRow { ts?: string; reply?: string; quality?: number | null }

function fmtBytes(n?: number | null): string {
  if (n == null) return "—";
  if (n > 1e6) return `${(n / 1e6).toFixed(1)} MB`;
  if (n > 1e3) return `${(n / 1e3).toFixed(0)} KB`;
  return `${n} B`;
}

function fmtDate(ts?: string): string {
  if (!ts) return "";
  const d = new Date(ts);
  return isNaN(d.getTime()) ? "" : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export default function LanguagePanel() {
  const data = usePoll<{
    phrase_banks?: Record<string, number>;
    learned_phrases?: number;
    speech_total?: number;
    speech_recent?: SpeechRow[];
    books_read?: Record<string, number>;
    native_lm_bytes?: number | null;
    tokenizer_bytes?: number | null;
  }>(`${API}/language?n=8`, 30_000);
  const banks = Object.entries(data?.phrase_banks || {}).sort((a, b) => b[1] - a[1]);
  const maxBank = Math.max(1, ...banks.map(([, n]) => n));
  const books = Object.keys(data?.books_read || {});
  const recent = data?.speech_recent || [];

  return (
    <Card id="box-language" className="flex h-full flex-col overflow-hidden">
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="flex min-w-0 items-center gap-2 text-sm font-medium text-muted-foreground">
          <BookOpenText className="h-4 w-4" /> <LexText id="language_title" />
          <PanelInfo
            title="Language organ"
            perspective="agent-accessible"
            what="The language it's growing from scratch, separate from any external LLM: curated phrase banks, phrases it's learned from use, everything it's actually said (with quality scores once evaluated), the books it's read into its replay corpus, and the native language model + tokenizer artifacts on disk."
            source="GET /api/language over brain/data/vocabulary.json · learned_phrases.json · speech_log.json · language/ (native_lm.pt, tokenizer.json, book_reads.json)"
            good="Phrase banks and learned phrases growing with use, speech quality scores trending up, and the native LM artifact actually present on disk."
            src={{ file: "brain/cognition/language_acquisition.py", start: 1, end: 60, label: "language_acquisition" }}
          />
          <PanelSubtitle id="language_sub" />
          <StaleBadge url={`${API}/language`} pollMs={30_000} />
        </CardTitle>
        <span className="text-[11px] text-muted-foreground/60">{data?.speech_total ?? 0} utterances</span>
      </CardHeader>
      <CardContent className="scrollbar-thin min-h-0 flex-1 space-y-3 overflow-auto pb-3">
        <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[10.5px]">
          <Stat k="learned phrases" v={String(data?.learned_phrases ?? 0)} />
          <Stat k="books read" v={String(books.length)} />
          <Stat k="native LM" v={fmtBytes(data?.native_lm_bytes)} />
          <Stat k="tokenizer" v={fmtBytes(data?.tokenizer_bytes)} />
        </div>

        {banks.length > 0 && (
          <div>
            <div className="mb-1 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">Phrase banks</div>
            <MiniBars
              rows={banks.map(([k, n]) => ({ label: k.replace(/_/g, " "), value: n / maxBank, title: `${n} phrases` }))}
              format={(v) => String(Math.round(v * maxBank))}
            />
          </div>
        )}

        {recent.length > 0 && (
          <div>
            <div className="mb-1 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">What it said recently</div>
            <div className="space-y-1">
              {[...recent].reverse().map((s, i) => (
                <div key={i} className="rounded-md border border-border bg-card/40 px-2 py-1.5">
                  <p className="text-[10.5px] leading-snug text-foreground/85" title={s.reply}>{s.reply || "—"}</p>
                  <div className="mt-0.5 flex gap-2 text-[9px] text-muted-foreground/70">
                    {s.quality != null ? <span>quality {Number(s.quality).toFixed(2)}</span> : <span>not yet evaluated</span>}
                    <span className="ml-auto tabular-nums">{fmtDate(s.ts)}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Stat({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-2">
      <span className="truncate text-muted-foreground">{k}</span>
      <span className="font-mono tabular-nums text-foreground/85">{v}</span>
    </div>
  );
}
