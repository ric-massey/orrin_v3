import { LexId, useLexicon } from "@/lib/lexicon";

/**
 * Lexicon-aware chrome helpers.
 *
 * <LexText id/> — one engineering label.
 * <PanelSubtitle id/> — the muted plain-language one-liner every CardTitle
 * carries (the "what is this box" first-contact layer).
 */

export function LexText({ id }: { id: LexId }) {
  const { t } = useLexicon();
  return <span>{t(id)}</span>;
}

export function PanelSubtitle({ id }: { id: LexId }) {
  const { t } = useLexicon();
  return (
    <span className="hidden truncate text-[10px] font-normal text-muted-foreground/60 lg:inline">
      — {t(id)}
    </span>
  );
}
