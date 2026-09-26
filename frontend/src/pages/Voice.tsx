import { useMemo } from "react";
import { AudioLines } from "lucide-react";
import { useTelemetryState } from "@/App";
import { useStreamStale, type Utterance } from "@/lib/telemetry";
import { useLocalStorage } from "@/lib/useLocalStorage";
import { cn, fmtTime } from "@/lib/utils";

/**
 * /voice — the transcript. One room made only of what Orrin actually SAID.
 *
 * Every other room describes him; this one quotes him. The lines arrive in the
 * `voice` telemetry field from brain/cognition/voice.py, which is fed only by
 * call sites that already hold first-person content: the felt winner of the
 * global workspace, an introspection miss, a goal he committed to, a question
 * he closed, anything composed through the expression door, and his last words.
 *
 * Two rules this page exists to hold:
 *   1. VERBATIM. The UI authors the chrome — the kind labels, the timestamps,
 *      this paragraph — and never a word of the transcript itself. (The Watch
 *      page's headline is a UI-authored gloss keyed off active_fn; that is the
 *      mistake this room is the answer to.)
 *   2. The narrative composer is NOT a source. Its prose is working-memory
 *      strings read back as content — the self-echo bug — so wiring it to a
 *      voice would broadcast damage and read as damage. It stays out until the
 *      de-prosing work lands.
 */

// The kinds, in the order the filter row shows them. `label` is UI chrome; the
// utterance text beside it is his.
const KINDS: { id: string; label: string; hint: string; dot: string; text: string }[] = [
  { id: "felt", label: "felt", hint: "a control signal crossed its line and won the workspace",
    dot: "bg-signal-warn", text: "text-signal-warn" },
  { id: "prediction", label: "prediction", hint: "he predicted, it felt true, behavior disagreed",
    dot: "bg-signal-accent", text: "text-signal-accent" },
  { id: "intent", label: "intent", hint: "the goal he just committed to",
    dot: "bg-signal-info", text: "text-signal-info" },
  { id: "closeout", label: "close-out", hint: "a question closed — answered, or honestly not",
    dot: "bg-signal-ok", text: "text-signal-ok" },
  { id: "speech", label: "speech", hint: "composed for a person through the expression door",
    dot: "bg-foreground", text: "text-foreground" },
  { id: "final", label: "last words", hint: "written once, at the end of a life",
    dot: "bg-signal-error", text: "text-signal-error" },
];

const KIND_BY_ID = Object.fromEntries(KINDS.map((k) => [k.id, k]));
const ALL = KINDS.map((k) => k.id);
const FILTER_KEY = "orrin.voice.kinds.v1";

export default function Voice() {
  const telemetry = useTelemetryState();
  const stale = useStreamStale(telemetry);
  const live = telemetry.connected && telemetry.source === "live" && !stale;

  const [shown, setShown] = useLocalStorage<string[]>(FILTER_KEY, ALL, {
    // Drop kinds that no longer exist; an empty/corrupt value falls back to all.
    sanitize: (raw) => {
      const kept = Array.isArray(raw) ? raw.filter((k) => ALL.includes(String(k))).map(String) : [];
      return kept.length ? kept : ALL;
    },
  });

  // Newest first: the line he just said sits under the eye, and the page never
  // scroll-jumps while you're reading further back.
  const lines = useMemo(() => {
    const out: Utterance[] = [];
    for (let i = telemetry.voice.length - 1; i >= 0; i--) {
      const u = telemetry.voice[i];
      if (u?.text && shown.includes(u.kind)) out.push(u);
    }
    return out;
  }, [telemetry.voice, shown]);

  const toggle = (id: string) =>
    setShown((prev) => {
      const next = prev.includes(id) ? prev.filter((k) => k !== id) : [...prev, id];
      return next.length ? next : ALL; // never leave the room empty by accident
    });

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-5 px-4 py-6 sm:px-6">
      <div className="space-y-1">
        <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight">
          <AudioLines className="h-5 w-5" /> Voice
          <span className="ml-1 flex items-center gap-1.5 text-xs font-normal text-muted-foreground">
            <span className="relative flex h-1.5 w-1.5">
              {live && (
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-signal-ok opacity-75" />
              )}
              <span className={cn("relative inline-flex h-1.5 w-1.5 rounded-full", live ? "bg-signal-ok" : "bg-muted-foreground/40")} />
            </span>
            {live ? "listening" : "not listening"}
          </span>
        </h1>
        <p className="text-sm text-muted-foreground">
          Only what Orrin said, verbatim, newest first. Each line exists because a
          real internal state crossed a real line — a signal at threshold, a
          prediction that missed, a question closed. Nothing here is written by
          this interface, and nothing here is written by a language model.
        </p>
      </div>

      {/* Kind filter — chrome, not content. */}
      <div className="flex flex-wrap items-center gap-1.5">
        {KINDS.map((k) => {
          const on = shown.includes(k.id);
          return (
            <button
              key={k.id}
              onClick={() => toggle(k.id)}
              title={k.hint}
              aria-pressed={on}
              className={cn(
                "flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors",
                on
                  ? "border-border bg-card text-foreground"
                  : "border-transparent bg-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              <span className={cn("h-1.5 w-1.5 rounded-full", on ? k.dot : "bg-muted-foreground/40")} />
              {k.label}
            </button>
          );
        })}
      </div>

      {lines.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border px-6 py-14 text-center">
          <div className="text-sm text-muted-foreground">
            {telemetry.voice.length === 0
              ? "He hasn't said anything yet."
              : "Nothing to show for the selected kinds."}
          </div>
          <div className="mx-auto mt-2 max-w-md text-xs leading-relaxed text-muted-foreground/70">
            Lines appear when a signal reaches threshold and wins the workspace,
            when a prediction he believed is contradicted by his own behavior,
            when he commits to a goal or closes a question, and when he composes
            something for a person.
          </div>
        </div>
      ) : (
        <div className="flex flex-col">
          {lines.map((u, i) => {
            const meta = KIND_BY_ID[u.kind];
            return (
              <div
                key={`${u.ts ?? 0}-${u.kind}-${i}`}
                className={cn(
                  "flex gap-3 border-b border-border/50 py-3 sm:gap-4",
                  i === 0 && "animate-fade-in",
                )}
              >
                <span
                  className="w-[4.5rem] shrink-0 pt-1 text-right text-xs tabular-nums text-muted-foreground/70"
                  title={u.cycle != null ? `cycle ${u.cycle}` : undefined}
                >
                  {u.ts ? fmtTime(u.ts) : ""}
                </span>
                <span
                  className={cn("mt-2 h-1.5 w-1.5 shrink-0 rounded-full", meta?.dot ?? "bg-muted-foreground/40")}
                  title={meta?.hint ?? u.kind}
                />
                <div className="min-w-0 flex-1">
                  {/* HIS WORDS — rendered exactly as they arrived. */}
                  <p
                    className={cn(
                      "whitespace-pre-wrap text-[15px] leading-relaxed",
                      i === 0 ? "text-foreground" : "text-foreground/85",
                      u.kind === "final" && "font-medium",
                    )}
                  >
                    {u.text}
                  </p>
                  <span className={cn("text-[11px] tracking-wide", meta?.text ?? "text-muted-foreground", "opacity-70")}>
                    {meta?.label ?? u.kind}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <p className="pb-2 text-xs leading-relaxed text-muted-foreground/60">
        Not shown: the runtime's own narration ("Orrin pruned 2 long memories"),
        which is written about him rather than by him, and the stitched narrative
        composer, whose prose is working-memory bookkeeping read back as content.
        The transcript keeps its own file, so it survives a restart.
      </p>
    </div>
  );
}
