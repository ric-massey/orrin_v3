import { ReactNode, useEffect, useRef, useState } from "react";
import { ArrowUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useTelemetryState } from "@/App";
import { useThought } from "@/lib/thoughts";
import { apiGet, apiPost, transportFetch } from "@/lib/transport";

/**
 * The conversation surface — composer + history + reply pipeline. Extracted
 * from the Face page (plan §2 C2) so /orrin (companion home, dark field) and
 * /face (the calm light room) share one implementation and one stored history.
 * Styling stays on semantic tokens, so it follows the room's light/dark theme.
 */

interface Message {
  id: string;
  role: "user" | "orrin";
  text: string;
}

const CHAT_URL = import.meta.env.VITE_CHAT_URL as string | undefined;

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// Persisted chat history: survives leaving/returning to the page and reloads, so
// the conversation isn't erased from view and old chats remain visible.
const CHAT_STORAGE_KEY = "orrin.chat.history.v1";
const CHAT_HISTORY_CAP = 500; // keep the last N messages

function loadStoredMessages(): Message[] {
  try {
    const raw = localStorage.getItem(CHAT_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? (parsed as Message[]) : [];
  } catch {
    return [];
  }
}

export default function Chat({
  emptyState,
  composerHint = true,
}: {
  /** Rendered when there is no history yet (each room brings its own greeting). */
  emptyState?: ReactNode;
  /** Show the "Press Enter to send" line under the composer. */
  composerHint?: boolean;
}) {
  const telemetry = useTelemetryState();
  const thought = useThought(telemetry);
  const [messages, setMessages] = useState<Message[]>(loadStoredMessages);
  const [draft, setDraft] = useState("");
  const [thinking, setThinking] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, thinking]);

  // Fix 10.4: the conversation used to be browser-local only — a new browser or
  // device showed an empty chat with a runtime that remembers it. Merge the
  // canonical server history (brain/data/chat_log.json via /api/chat) on load;
  // localStorage still gives instant rendering and offline continuity.
  useEffect(() => {
    let stop = false;
    (async () => {
      try {
        const r = await apiGet(`/api/chat?n=200`);
        const d = await r.json();
        if (stop || !Array.isArray(d?.messages)) return;
        const server: Message[] = d.messages
          .filter((m: any) => m && (m.content || m.text))
          .map((m: any, i: number) => ({
            id: `srv-${i}-${String(m.timestamp || "")}`,
            role: m.role === "user" || m.speaker === "user" ? "user" : "orrin",
            text: String(m.content ?? m.text ?? ""),
          }));
        if (server.length === 0) return;
        setMessages((local) => {
          // M3: dedup by OCCURRENCE, not by content. Keying on `role|text`
          // collapsed legitimately-repeated messages ("ok", "yes") into one.
          // Instead, consume one local occurrence per matching server message,
          // so the Nth identical line survives.
          const remaining = new Map<string, number>();
          for (const m of local) {
            const k = `${m.role}|${m.text}`;
            remaining.set(k, (remaining.get(k) || 0) + 1);
          }
          const missing = server.filter((m) => {
            const k = `${m.role}|${m.text}`;
            const c = remaining.get(k) || 0;
            if (c > 0) { remaining.set(k, c - 1); return false; }
            return true;
          });
          if (missing.length === 0) return local;
          // Server history predates whatever this browser saw — prepend it.
          return [...missing, ...local].slice(-CHAT_HISTORY_CAP);
        });
      } catch {
        /* backend unreachable — keep the local view */
      }
    })();
    return () => { stop = true; };
  }, []);

  // Persist the conversation so it isn't lost when leaving the page or reloading,
  // and so old chats are visible again on the next visit. Capped to the last N.
  useEffect(() => {
    try {
      localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(messages.slice(-CHAT_HISTORY_CAP)));
    } catch {
      /* storage unavailable/full — non-fatal */
    }
  }, [messages]);

  // auto-grow textarea
  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
  }, [draft]);

  async function send() {
    const text = draft.trim();
    if (!text || thinking) return;
    const userMsg: Message = { id: crypto.randomUUID(), role: "user", text };
    setMessages((m) => [...m, userMsg]);
    setDraft("");
    setThinking(true);
    try {
      const reply = await getReply(text, telemetry.narrative);
      setMessages((m) => [...m, { id: crypto.randomUUID(), role: "orrin", text: reply }]);
    } finally {
      setThinking(false);
    }
  }

  const empty = messages.length === 0;

  return (
    <>
      {/* Conversation */}
      <div ref={scrollRef} className="scrollbar-thin flex-1 overflow-y-auto px-3 sm:px-4">
        <div className="mx-auto w-full max-w-2xl py-5 sm:py-8">
          {empty ? (
            emptyState ?? null
          ) : (
            <div className="flex flex-col gap-6">
              {messages.map((m) => (
                <Bubble key={m.id} role={m.role} text={m.text} />
              ))}
              {thinking && <ThinkingBubble narrative={thought} />}
            </div>
          )}
        </div>
      </div>

      {/* Composer */}
      <div className="border-t bg-background/80 pb-[env(safe-area-inset-bottom)] backdrop-blur">
        <div className="mx-auto w-full max-w-2xl px-3 py-3 sm:px-4 sm:py-4">
          <div className="flex items-end gap-2 rounded-2xl border bg-card p-2 shadow-sm focus-within:ring-2 focus-within:ring-ring">
            <textarea
              ref={taRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              rows={1}
              placeholder="Message Orrin…"
              className="max-h-[200px] flex-1 resize-none bg-transparent px-3 py-2 text-base leading-relaxed outline-none placeholder:text-muted-foreground sm:text-[15px]"
            />
            <Button
              size="icon"
              onClick={send}
              disabled={!draft.trim() || thinking}
              className="h-9 w-9 shrink-0 rounded-xl"
              aria-label="Send"
            >
              <ArrowUp className="h-5 w-5" />
            </Button>
          </div>
          {composerHint && (
            <p className="mt-2 hidden text-center text-[11px] text-muted-foreground sm:block">
              Orrin reflects before it answers. Press Enter to send · Shift+Enter for a new line.
            </p>
          )}
        </div>
      </div>
    </>
  );
}

function Bubble({ role, text }: { role: "user" | "orrin"; text: string }) {
  const isUser = role === "user";
  return (
    <div className={cn("flex animate-fade-in", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-[15px] leading-relaxed",
          isUser
            ? "bg-primary text-primary-foreground rounded-br-md"
            : "bg-secondary text-secondary-foreground rounded-bl-md"
        )}
      >
        {text}
      </div>
    </div>
  );
}

function ThinkingBubble({ narrative }: { narrative: string }) {
  return (
    <div className="flex justify-start animate-fade-in">
      <div className="flex items-center gap-2 rounded-2xl rounded-bl-md bg-secondary px-4 py-3 text-secondary-foreground">
        <span className="flex gap-1">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground"
              style={{ animationDelay: `${i * 0.15}s` }}
            />
          ))}
        </span>
        <span className="text-xs text-muted-foreground">{narrative || "Reflecting…"}</span>
      </div>
    </div>
  );
}

/**
 * Resolve a reply for a user message. Priority:
 *   1. VITE_CHAT_URL — a direct synchronous chat endpoint, if you have one.
 *   2. The input pipeline — POST /api/agent/input, then poll
 *      GET /api/agent/response/{id} until the core loop answers (or times out).
 *   3. Local reflection — if the backend is unreachable (e.g. demo mode).
 */
async function getReply(text: string, narrative: string): Promise<string> {
  if (CHAT_URL) {
    try {
      // A user-configured external endpoint (absolute URL) — still flows through
      // the transport so the bridge can pass it through in the packaged app.
      const res = await transportFetch(CHAT_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });
      const data = await res.json();
      if (data?.reply) return String(data.reply);
    } catch {
      /* fall through */
    }
  }

  // Submit to the core loop via the input pipeline and wait for its reply.
  try {
    const res = await apiPost(`/api/agent/input`, { message: text });
    const data = await res.json();
    const id: string | undefined = data?.id;
    if (!id) throw new Error("no id");

    const deadline = Date.now() + 30000; // wait up to 30s for the loop to respond
    while (Date.now() < deadline) {
      await sleep(800);
      const r = await apiGet(`/api/agent/response/${id}`);
      const d = await r.json();
      if (d?.reply) return String(d.reply);
    }
    return "Got it — your message reached my core loop and is still being processed (it wasn't lost). I just didn't finish a reply within the wait window; it'll fold into an upcoming cycle.";
  } catch {
    /* backend unreachable → local reflection */
  }

  await sleep(700 + Math.random() * 600);
  const openers = [
    "Sitting with that for a second —",
    "Here's where my thinking lands:",
    `While ${narrative.toLowerCase().replace(/[.…]+$/, "") || "reflecting"}, I notice this:`,
    "Honestly?",
  ];
  const opener = openers[Math.floor(Math.random() * openers.length)];
  return `${opener} my telemetry backend isn't reachable right now, so I'm answering from my local reflection layer. Start the backend (\`python backend/main.py\`) and I'll route your words into the live core loop.`;
}
