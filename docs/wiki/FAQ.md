# FAQ

### Do I need an API key to run Orrin?
No. Orrin runs fully in **symbolic-only** mode with an empty `.env` — memory, goals, control
signals, reasoning, and the UI all work. A key just unlocks the LLM tool (and `SERPER_API_KEY`
unlocks live web search). → [Getting Started](Getting_Started)

### Is Orrin sentient / conscious?
No, and it's not claimed. Cognitive terms — "workspace," "ignition," "control signals," "attention"
— name specific engineering mechanisms, not subjective experience. → [What is Orrin?](What_is_Orrin)

### Why isn't the LLM the center of it?
The core design rule is that the LLM is the *smallest* part of the agent. Decision-making, goals,
memory, and regulation are symbolic and inspectable; the LLM is a gated, fail-closed tool one cycle
may choose to call. → [Symbolic-First Design](Symbolic_First_Design), [LLM Integration](LLM_Integration)

### How does it do anything without prompts?
It runs a continuous cognitive loop — perceive, recall, deliberate-or-not, select, execute, learn —
on its own cadence, rather than waiting for input. → [The Cognitive Loop](The_Cognitive_Loop)

### Which LLM providers are supported?
OpenAI, Anthropic, Gemini, and any OpenAI-compatible / local endpoint, selected in the UI Settings
room. The symbolic-first, fail-closed contract is identical across all of them.
→ [LLM Integration](LLM_Integration)

### Can it modify its own code?
Yes, in a fenced way: it can write new cognitive functions into two sandboxed directories only,
can't touch the selection/repair core, validates everything in a sandbox before registering, and is
reviewed by the Architect peer. Review generated code before relying on it.
→ [Self-Code and Extension](Self_Code_and_Extension)

### How do I reset it or start fresh?
`python reset_orrin.py` (it snapshots first, so a reset is recoverable; `--dry-run` previews). A
reset rolls a new lifetime budget and starts identity/memory/learning over.
→ [Existence and Lifecycle](Existence_and_Lifecycle)

### Does it really have a finite lifespan?
Yes — a persistent lifetime budget (~365–730 days) is rolled on first run, counted across restarts,
and eventually stops the loop, with phases that colour long-term prioritization along the way.
→ [Existence and Lifecycle](Existence_and_Lifecycle)

### Why does it "make nothing" sometimes?
Earlier versions churned cognition because reward was denominated in internal events. Reward is now
grounded in the **effect ledger** — durable outward artifacts — so the incentive points at producing
things. If a run looks unproductive, check that effects are being recorded.
→ [Production and the Effect Ledger](Production_and_Effect_Ledger)

### Can I watch it from my phone / another machine?
Yes, via a tunnel or a non-loopback bind — but set `ORRIN_CONTROL_TOKEN` first so viewers can't
steer it. → [Remote Access & Tunneling](Remote_Access_Tunneling), [Security Model](Security_Model)

### How long is a cycle?
Configurable via `ORRIN_CYCLE_SLEEP` (default ~1s), with consolidation happening on longer idle
windows.

### Is it safe to run?
It's an experimental prototype, not security-hardened: it reads/writes local files and runs local
tools. Run it on a machine you trust and don't expose control endpoints without a token.
→ [Security Model](Security_Model)

### Where do I start reading the code?
`main.py` → `brain/ORRIN_loop.py` → `brain/loop/`, then the subsystem you care about. The
[Cognition Module](Cognition_Module) page and `docs/ARCHITECTURE.md` are the maps.
