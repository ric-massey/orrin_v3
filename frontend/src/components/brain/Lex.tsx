import { LexId, useLexicon } from "@/lib/lexicon";

/**
 * Lexicon-aware chrome helpers (Fix 11 step 3 + Fix 12).
 *
 * <LexText id/> — one translated label; hovering shows the other dialect, so
 * the terminology toggle doubles as a glossary.
 * <PanelSubtitle id/> — the muted plain-language one-liner every CardTitle
 * carries (the "what is this box" first-contact layer).
 */

export function LexText({ id }: { id: LexId }) {
  const { t, tip } = useLexicon();
  return <span title={tip(id)}>{t(id)}</span>;
}

export function PanelSubtitle({ id }: { id: LexId }) {
  const { t, tip } = useLexicon();
  return (
    <span className="hidden truncate text-[10px] font-normal text-muted-foreground/60 lg:inline" title={tip(id)}>
      — {t(id)}
    </span>
  );
}
