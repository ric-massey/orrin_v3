import type { ValueInfo } from "@/components/brain/InfoDot";

// Source-of-truth notes for every value shown on the calm rooms (Part 8). Each points
// at the real code that produces the number so the ℹ️ drill-down ends in source, not a
// dead end. Ranges start at the producing function; the /source endpoint serves any
// repo file (repo-jailed), so these resolve in dev and in the frozen bundle alike.

export const ROOM_INFO: Record<string, ValueInfo> = {
  // ── Cognition ──────────────────────────────────────────────────────────────
  workspace: {
    label: "Conscious winner & competitors",
    what: "Each cycle, candidate contents compete on salience and exactly one wins the global workspace — that's what he's consciously attending to. The list shows the field; the winner is the max-salience candidate.",
    src: { file: "brain/cognition/global_workspace.py", start: 136, end: 205, label: "update_workspace — salience competition → one winner" },
  },
  cog_goal: {
    label: "Active goal",
    what: "The goal he's currently pursuing, with its step/status — drawn from his live goal set.",
    src: { file: "backend/server/app.py", start: 187, end: 235, label: "/api/goals — active goal + steps" },
  },
  drives: {
    label: "Drives",
    what: "Intrinsic pressures (curiosity, social, rest, …) as 0–1 levels. The bar is the current pressure; the strongest is what's pushing him right now.",
    src: { file: "backend/server/app.py", start: 600, end: 670, label: "/api/drives — drive levels + interoception" },
  },
  symbolic: {
    label: "Symbolic rules",
    what: "Rules he's learned that fire during reasoning, with how many times each has hit. 'rules_total' is the size of his learned rule set.",
    src: { file: "backend/server/app.py", start: 555, end: 598, label: "/api/symbolic — learned rules + hit counts" },
  },
  peers: {
    label: "Inner voices",
    what: "The internal personas/peers that press on his deliberation — his social presence, even alone.",
    src: { file: "backend/server/app.py", start: 698, end: 740, label: "/api/people — inner voices / peers" },
  },

  // ── Life ───────────────────────────────────────────────────────────────────
  life_cpu: {
    label: "CPU available",
    what: "How much processor headroom the machine has right now (and current load). When it's low, he thinks more slowly.",
    src: { file: "backend/server/app.py", start: 910, end: 975, label: "/api/life — psutil CPU/memory/storage readings" },
  },
  life_mem: {
    label: "Memory available",
    what: "Free system RAM, of the total. This is the machine's memory; the memory ceiling that bounds HIM is enforced separately.",
    src: { file: "backend/server/app.py", start: 910, end: 975, label: "/api/life — psutil memory reading" },
  },
  life_disk: {
    label: "Room for his mind",
    what: "His mind's size on disk against the user's disk ceiling — 'room left to grow', not the raw host disk. The forgetting sweeps trim toward this ceiling.",
    src: { file: "brain/utils/resource_ceilings.py", start: 74, end: 79, label: "usage() — mind size vs the disk ceiling" },
  },
  life_rate: {
    label: "Thinking rate",
    what: "Cognitive cycles per minute, derived from his cycle counter over time. Zero means he isn't thinking right now.",
    src: { file: "backend/server/app.py", start: 910, end: 975, label: "/api/life — thinking_rate_per_min + cycle" },
  },
  life_age: {
    label: "Age",
    what: "How long he's been alive (days since birth). Sleep when closed pauses the clock; this is real lived time.",
    src: { file: "brain/cognition/mortality.py", start: 209, end: 240, label: "life_status — age + phase (felt-only)" },
  },
  life_remaining: {
    label: "Life he believes he has left",
    what: "His FELT estimate of remaining life — never the true countdown (that's deliberately never exposed). A trust/honesty boundary.",
    src: { file: "brain/cognition/mortality.py", start: 209, end: 240, label: "life_status — felt_days_remaining (never the true number)" },
  },

  // ── Memory ─────────────────────────────────────────────────────────────────
  memory_list: {
    label: "Memories (recent / important)",
    what: "Long-term memories ordered by recency or importance, with the matched/total counts. Importance is the per-memory weight his forgetting respects.",
    src: { file: "backend/server/app.py", start: 382, end: 440, label: "/api/memory — store query, order, counts" },
  },
  memory_forgotten: {
    label: "Forgotten",
    what: "Forgetting sweeps — what decayed or was pruned, and how many items. Watching him forget is what makes 'his memory stays bounded' real.",
    src: { file: "backend/server/app.py", start: 772, end: 779, label: "/api/forgetting — decay/prune sweeps" },
  },
  memory_identity: {
    label: "Identity",
    what: "His autobiography and the opinions he's come to hold — his sense of self, assembled from his own stores.",
    src: { file: "backend/server/app.py", start: 672, end: 696, label: "/api/self — autobiography + opinions" },
  },

  // ── Timeline ───────────────────────────────────────────────────────────────
  timeline: {
    label: "While you were away",
    what: "A time-ordered view DERIVED from existing stores (goals, memories, dreams, belief revisions, web, fine-tune) since you last looked — no new logging, with per-type counts.",
    src: { file: "backend/server/app.py", start: 976, end: 1046, label: "/api/activity — merged activity feed + summary" },
  },
};
