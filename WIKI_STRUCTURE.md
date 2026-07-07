# Orrin Wiki Structure Blueprint

**Status:** Complete outline with page templates. All 35 pages mapped with headers, sections, and content requirements.

---

## Overview

This document maps the complete Orrin wiki: 35 pages across 7 tiers, with detailed outline for each page. Use this as the master reference for wiki creation and maintenance.

**Total estimated words:** 50,600  
**Total pages:** 35  
**Organization:** Conceptual flow (not file structure)  
**Quality standard:** Each page includes: diagrams, code examples, file pointers, related pages, FAQs, scientific foundations.

---

## TIER 1: ENTRY POINTS (4 pages)

### Page 1.1: **Home**
**Audience:** Everyone (first landing)  
**Purpose:** Orientation + navigation  

**Sections:**
- Welcome paragraph (elevator pitch)
- "What are you looking for?" quick links
  - I want to understand Orrin
  - I want to run Orrin
  - I want to modify Orrin
  - I have a question about X
- Search tips (terminology to search for)
- Table of contents (all 7 tiers)
- "Most popular pages" (links to tier 2 + 3)

**Estimated words:** 400

---

### Page 1.2: **Glossary of Terms**
**Audience:** Everyone  
**Purpose:** Quick reference for terminology  

**Format:** Alphabetical list; each term has:
- 1-2 line definition
- Link to detail page(s)
- Example usage

**Key terms to include:**
- Affect state / Control signals
- Workspace / Ignition
- Bandit selector
- Executive / Goals daemon
- Consolidation / Forgetfulness
- Host coupling
- Peer
- Symbolic reasoning
- (30+ more)

**Estimated words:** 800

---

### Page 1.3: **FAQ**
**Audience:** Everyone (common questions)  
**Purpose:** Fast answers to 30 repeating questions  

**Format:** Question + 2-3 line answer + link to detail page

**Example questions:**
- Why isn't the LLM the center of Orrin?
- How does Orrin work without prompts?
- Can Orrin run offline?
- What happens when Orrin gets confused?
- How long does a cycle take?
- Can I modify Orrin's goals?
- (25+ more)

**Estimated words:** 1200

---

### Page 1.4: **Quick Navigation Guide**
**Audience:** Developers / technical readers  
**Purpose:** "I want to... where do I go?"  

**Format:** Flowchart as structured text + table

**Flowchart branches:**
- I want to **understand** Orrin
  - → Conceptual tier pages
- I want to **run** Orrin
  - → Operations tier pages
- I want to **modify** Orrin
  - → Subsystem deep dives + how-to guides
- I want to **debug** Orrin
  - → Subsystem deep dives
- I want to **extend** Orrin
  - → Developer guides

**Table:** "I'm looking for..." → "Read these pages in order"

**Estimated words:** 600

---

## TIER 2: CONCEPTUAL OVERVIEW (6 pages)

### Page 2.1: **What is Orrin?**
**Audience:** Anyone new to the project  
**Purpose:** Conceptual clarity + differentiators  

**Sections:**
1. **Elevator pitch** (3 sentences)
2. **Core idea** — "Make the LLM the smallest part, not the whole"
3. **Differentiators** (vs. typical agents)
   - Symbolic-first cognition
   - Continuous autonomy (bandit, not prompts)
   - Persistent memory + consolidation
   - Observable runtime (UI rooms, not chat)
   - Host-aware (machine is part of context)
4. **What Orrin is NOT**
   - Not a chatbot
   - Not a reasoning loop on top of LLM
   - Not production software (experimental)
5. **Scientific grounding** (Russell/Barrett, Baars, Dehaene, etc.)
6. **"Is it right for me?" flowchart**

**Estimated words:** 1200

---

### Page 2.2: **The Cognitive Loop**
**Audience:** Conceptual readers  
**Purpose:** Step-by-step walkthrough of the loop  

**Sections:**
1. **ASCII diagram** of loop phases
2. **Each phase explained** (perceive, recall, ignition, select, execute, reward, persist, maintain, idle)
   - What happens
   - Why it matters
   - Example (concrete scenario)
3. **Timing** (cycle sleep, ignition threshold, etc.)
4. **Daemons alongside** (Executive, Memory, Supervisor, Backend)
5. **One complete cycle walkthrough** (narrative)
6. **Code pointers** (brain/ORRIN_loop.py, brain/loop/*)
7. **FAQ box**
   - Why cycles at all? (vs. event-driven)
   - Can I change cycle timing?
   - What if something breaks mid-cycle?

**Estimated words:** 1500

---

### Page 2.3: **Symbolic-First Design**
**Audience:** Conceptual + intermediate readers  
**Purpose:** Why the LLM is a tool, not the core  

**Sections:**
1. **The problem statement** — typical agents glue LLM to everything
2. **Orrin's approach** — symbolic-first, LLM as optional tool
3. **What runs without an LLM**
   - Cognitive loop
   - Memory consolidation
   - Goal management
   - Control signals
   - Symbolic reasoning
   - Host monitoring
4. **"Fail closed" contract** — graceful degradation if LLM is unavailable
5. **When the LLM is used** (tool calls, generation)
6. **Trade-offs**
   - Symbolic is predictable but limited
   - LLM is powerful but emergent
7. **Comparison table** (Orrin vs. typical agent)
8. **Code pointers** (brain/utils/llm_providers/, brain/cognition/tools/ask_llm.py)

**Estimated words:** 1400

---

### Page 2.4: **The Workspace & Ignition**
**Audience:** Intermediate readers  
**Purpose:** Understand salience competition and deliberation  

**Sections:**
1. **Global workspace concept** (Baars 1988, Dehaene 2014)
   - Parallel subsystems propose
   - Competition on salience
   - Bottleneck (one winner)
   - Broadcast
2. **How it works in Orrin**
   - Which subsystems propose
   - What they compete on
   - Hysteresis (continuity)
3. **ASCII diagrams**
   - Subsystem competition (before → after)
   - Broadcast flow
4. **Ignition gate** (deliberation_gate.py)
   - What triggers deliberation?
   - Low-power cycles (non-ignited)
   - MAX_SILENT_CYCLES floor
5. **Workspace prior** (additive bias on action selection)
6. **Conflict recruitment** (System-2 on uncertainty)
7. **Code pointers** (brain/cognition/global_workspace.py, brain/think/deliberation_gate.py)
8. **FAQ box**
   - Can I disable ignition?
   - What if multiple things are equally salient?
   - How is hysteresis calculated?

**Estimated words:** 1300

---

### Page 2.5: **Control Signals (Overview)**
**Audience:** Intermediate readers  
**Purpose:** Understand internal state regulation  

**Sections:**
1. **What are control signals?** (Russell/Barrett core affect)
   - Reward signal
   - Activation level
   - Named pressures (demand, throttle, etc.)
2. **Why do they matter?**
   - Bias what runs next
   - Stability regulation
   - Visible in UI
3. **Two readers**
   - Background machinery: raw floats
   - Reasoning layer: qualitative descriptions
4. **Setpoint regulation** (velocity budgets, not flat midpoint)
5. **Simple example** (scenario: Orrin gets confused)
   - Reward signal drops
   - Activation rises
   - How each subsystem reacts
6. **Code pointers** (brain/control_signals/, brain/control_signals/signal_summary.py)
7. **Link to deep dive page**
8. **FAQ box**
   - Can I tune setpoints manually?
   - What if signals go unstable?

**Estimated words:** 1000

---

### Page 2.6: **Host Coupling**
**Audience:** Intermediate readers  
**Purpose:** Why the machine's health matters to Orrin  

**Sections:**
1. **The concept** — machine as runtime context AND substrate
2. **Three separate mappings**
   - Absolute floors (reflex, host_resources.py)
   - Deviation bands (control signals, learning)
   - Resource cadence (cycle speed)
3. **What metrics?**
   - Disk free
   - Swap usage
   - Memory free
   - Battery
4. **How it works**
   - Learns "normal" for that machine (infancy.py)
   - Detects deviations
   - Adjusts behavior accordingly
5. **Example** (small laptop vs. beefy workstation)
   - Same Orrin code
   - Different learned behavior
6. **Code pointers** (supervisor/host_resources.py, brain/cognition/host_resource_monitor.py)
7. **FAQ box**
   - Does Orrin slow down on weak machines?
   - Can I override resource limits?

**Estimated words:** 900

---

## TIER 3: SYSTEM ARCHITECTURE (8 pages)

### Page 3.1: **Loop Phases: Detailed Walkthrough**
**Audience:** Intermediate + advanced  
**Purpose:** Each phase in depth  

**Sections:** (One section per phase)
1. **Perceive** — sense the environment, read input queue, update sensors
2. **Recall** — retrieve relevant memories based on current context
3. **Prepare Workspace** — assemble candidates for workspace competition
4. **Ignition** — decide whether to deliberate or stay in low-power
5. **Select Function/Action** — bandit picks the next cognitive function
6. **Execute** — run the function, update state
7. **Reward Accounting** — assign credit, update learning
8. **Persist** — write state to disk
9. **Maintain** — cleanup, health checks
10. **Idle/Consolidate** — memory consolidation, decay, learning

**Per-phase structure:**
- ASCII diagram of inputs/outputs
- Pseudocode (simplified algorithm)
- Real code pointer
- Decisions made (control flow)
- State changes
- Time cost
- Failure modes
- Example scenario

**Estimated words:** 2000

---

### Page 3.2: **Control Signals: Deep Dive**
**Audience:** Advanced readers / developers  
**Purpose:** Implement and tune control signals  

**Sections:**
1. **Data model** (what's stored in affect_state)
   - Reward signal (float)
   - Activation level (float)
   - Demands (dict)
   - Throttle (float)
   - Reward accounting (cumulative)
2. **Two readers** (reprise from conceptual, deeper)
   - Raw floats path: bandit, EVC, attention
   - Qualitative path: signal_summary.py → reasoning layer
3. **Rendering logic** (how raw signals become text)
   - Adaptation adjustment (habituation)
   - Qualitative vocabulary
   - Why this matters for reasoning
4. **Setpoint regulation** (technical)
   - Per-signal baselines
   - Velocity budgets
   - Math (pseudocode)
5. **Convergence** (arbiters, proposal inboxes)
   - Race conditions avoided
   - Daemon proposals integrate cleanly
6. **Tuning guide**
   - Setpoints (ORRIN_REWARD_SETPOINT, etc.)
   - Velocity budgets
   - Adaptation rates
   - When to tune and why
7. **Code walkthrough** (key functions)
   - commit_signals()
   - render_signal_summary()
   - apply_setpoint_regulation()
8. **FAQ box**
   - My rewards are stuck high/low
   - Signals thrashing wildly
   - Why qualitative rendering at all?

**Estimated words:** 1800

---

### Page 3.3: **Memory System**
**Audience:** Advanced readers / memory developers  
**Purpose:** Understand WAL, consolidation, retrieval  

**Sections:**
1. **Architecture overview**
   - Working memory (ephemeral)
   - Long-term memory (persistent)
   - Embedding store
   - WAL + snapshots
2. **Memory daemon** (memory/)
   - Runs alongside loop
   - Ingests new memories
   - Consolidates during idle
   - Handles forgetting/decay
3. **Write-ahead log (WAL)**
   - Why: durability, recovery
   - Format (jsonl)
   - Capping (bounded size)
   - Checkpoints
4. **Consolidation cycle**
   - What triggers it
   - Embedding step
   - Replay & connection
   - Decay & forgetfulness
   - Timeline (15 min, 1 hr, 1 day windows)
5. **Retrieval**
   - Semantic search (embedding similarity)
   - Fallback (token overlap)
   - Limits (top-K, recency bias)
6. **Data structures**
   - Memories (content, timestamp, tags, embedding)
   - Episodic log
   - Semantic index
7. **Code pointers** (memory/, brain/cog_memory/)
   - memory_daemon.py
   - retrieval.py
   - wal.py
8. **Debugging memory issues**
   - Memory not being retrieved
   - Consolidation takes forever
   - Embedding errors
9. **FAQ box**
   - Why embedding + semantic?
   - Does Orrin forget important stuff?
   - Can I tune memory decay?

**Estimated words:** 1700

---

### Page 3.4: **Goals: Executive vs. Goals Daemon**
**Audience:** Advanced readers / goal developers  
**Purpose:** Understand two-level goal architecture  

**Sections:**
1. **Why two subsystems?**
   - Decoupling: durable state ≠ in-process speed
   - Trade-off: latency vs. persistence
2. **Goals daemon** (goals/)
   - Separate durable store
   - WAL + snapshots
   - Goal lifecycle (creation → completion/failure)
   - Long-term ownership
3. **Executive** (brain/cognition/planning/executive.py)
   - In-process scheduler
   - Advances goal steps every ~7s
   - Responsive to control signals
   - Bridges loop and daemon
4. **Goal hierarchy**
   - Lifetime goals
   - Quarterly goals
   - Weekly subgoals
   - Daily tasks
   - Slots (capacity)
5. **Goal states**
   - Active / paused / completed / failed / abandoned
   - Transitions & logic
6. **Planning & adaptation**
   - How goals break into steps
   - Replanning on failure
   - Capability-aware selection
7. **Effect ledger** (goals produce artifacts)
   - Symbolic productions
   - File writes
   - Delivered notes
   - Reward keying
8. **Code pointers** (goals/, brain/cognition/planning/)
   - goals_daemon.py
   - executive.py
   - effect_ledger.py
9. **How to add custom goals** (developer guide link)
10. **FAQ box**
    - Can goals override each other?
    - What if Executive crashes?
    - How long can goals run?

**Estimated words:** 1600

---

### Page 3.5: **Symbolic Reasoning**
**Audience:** Advanced readers / symbolic system developers  
**Purpose:** World models, causality, concepts  

**Sections:**
1. **Overview** (what is symbolic reasoning in Orrin?)
   - Build models of the world
   - Query and reason about them
   - Revise on evidence
   - All without an LLM
2. **World model** (graph structure)
   - Entities (objects, concepts, relationships)
   - Predicates (properties, actions)
   - Temporal dimensions
3. **Description logic** (DL)
   - Inheritance
   - Constraints
   - Class hierarchies
   - Role definitions
4. **Causal reasoning** (Pearl-style)
   - Causal graphs
   - Interventions vs. observations
   - Counterfactual reasoning
   - Examples
5. **Concept formation**
   - Clustering examples
   - Abstracting commonalities
   - Naming new concepts
6. **Analogies**
   - Structural mapping
   - Transfer learning
   - Cross-domain application
7. **Experimentation**
   - Autonomous experiments
   - Hypothesis testing
   - Learning from outcomes
8. **Code pointers** (brain/symbolic/)
   - world_model.py
   - causal_model.py
   - concept_formation.py
9. **Adding new operations** (guide link)
10. **FAQ box**
    - Why not just use an LLM for reasoning?
    - Are these correct?
    - Can I inspect the models?

**Estimated words:** 1500

---

### Page 3.6: **Peers (Outside Observers)**
**Audience:** Advanced readers / peer developers  
**Purpose:** Architecture and role of peer entities  

**Sections:**
1. **What are peers?** (outside observers that nudge attention)
2. **Key principle** — peers propose, never command
3. **Each peer's role**
   - **Architect** — reviews self-modifications before they happen
   - **Signal Historian** — tracks chronic control-signal patterns
   - **Goal Auditor** — flags low-quality goals
   - **Observer** — catches unproductive loops
   - **Reward Auditor** — notices when bandit reward has collapsed
4. **Architecture**
   - Read-only access to Orrin's state
   - Wake conditions (when to activate)
   - Signal injection (how they push proposals)
   - Signal router (common pathway)
5. **Signal injection** (how it works)
   - Peers create signal proposals
   - Added to proposal queue
   - Router integrates into control signals
   - Next cycle sees the nudge
6. **Example** — Signal Historian detects chronic distress
   - Reads affect history
   - Notices pattern
   - Creates signal proposal
   - Injects into router
   - Control signals shift
7. **Code pointers** (brain/peers/)
   - Each peer's implementation
   - signal_router.py
   - Base peer class
8. **Writing a custom peer** (developer guide link)
9. **FAQ box**
   - Can peers override each other?
   - What if a peer's logic is wrong?
   - How do I debug a peer?

**Estimated words:** 1400

---

### Page 3.7: **Action Selection & Bandit Learning**
**Audience:** Advanced readers / action selection developers  
**Purpose:** How Orrin chooses what to do  

**Sections:**
1. **The problem** — many possible actions, one to pick
2. **Bandit selector** (multi-armed bandit)
   - Each "arm" = a cognitive function
   - Reward signal = feedback
   - UCB1 algorithm (exploration-exploitation)
3. **Prior from workspace** (additive bias)
   - Workspace winner gets a boost
   - Biases toward coherent action
4. **Cost prediction** (EVC layer)
   - Expected value of control
   - Effort vs. reward trade-off
   - Which functions are worth the cost?
5. **Action arbiter** (prevent race conditions)
   - Converges reactive + deliberative proposals
   - Single writer pattern
   - Integrates control signals
6. **Learning** (how does the bandit improve?)
   - Immediate reward
   - Delayed reward (evaluator daemon)
   - Credit assignment
   - Performance metrics
7. **Depth bandit** (meta-learning)
   - Learns optimal draft-critique-revise cycles
   - UCB1 over cycle depths
   - Per-function adaptation
8. **Code pointers** (brain/think/)
   - select_function.py
   - action_arbiter.py
   - depth_bandit.py
9. **Tuning** (exploration vs. exploitation)
   - ORRIN_BANDIT_EPSILON
   - Per-function priors
10. **FAQ box**
    - Why bandit and not MCTS/planning?
    - How long does learning take?
    - Can I force a specific action?

**Estimated words:** 1400

---

### Page 3.8: **Learning & Adaptation**
**Audience:** Advanced readers / ML-focused  
**Purpose:** How Orrin improves over time  

**Sections:**
1. **Learning surfaces** (multiple mechanisms)
   - Function selector (bandit)
   - Depth bandit
   - Thinking depth
   - Delayed-learning daemons
2. **Function selector** (primary bandit)
   - UCB1 algorithm
   - Reward signal feedback
   - Exploration-exploitation trade-off
3. **Delayed-learning daemons** (brain/eval/)
   - **Evaluator** — credit past decisions when outcomes are known
     - Memory retrieved → reward
     - Goal closes → reward
     - ~50 cycle lookback
   - **Demand-expectations** — learn which actions satisfy demands
     - Action → demand satisfaction
     - Prediction error → control signal update
4. **Self-shaping fine-tuning** (OpenAI only)
   - Filters conversation traces (outcome ≥ 0.65)
   - Submits fine-tune job
   - Repoints model on completion
   - Drift toward what worked for *this* Orrin
5. **Learning UI** (before → after → because)
   - Behavior changes visualized
   - Belief revisions shown
6. **Metrics**
   - Success rate per function
   - Reward trajectory
   - Goal closure rate
   - Memory retrieval quality
7. **Code pointers** (brain/eval/, brain/cognition/finetuning/)
8. **Limitations**
   - Emergent behavior under-tested
   - Long runs may drift
   - No developmental arc (by design)
9. **FAQ box**
   - Is learning reliable?
   - Can I turn off fine-tuning?
   - How do I verify Orrin learned correctly?

**Estimated words:** 1300

---

## TIER 4: SUBSYSTEM DEEP DIVES (10 pages)

### Page 4.1: **Control Signals Module** (`brain/control_signals/`)
**Similar structure to 3.2 but with:**
- Module layout (files, responsibilities)
- Class hierarchy
- Key functions with pseudocode
- State serialization
- Common bugs & fixes

**Estimated words:** 2000

---

### Page 4.2: **Cognition Module** (`brain/cognition/`)
**Structure:**
- Overview of 20+ cognitive functions
- Organization (subdirs)
- Each major subsystem:
  - Planning & Executive
  - Attention & salience
  - Inner loop & System-2
  - Language (nascent)
  - Tools (LLM, web search, etc.)
- How they coordinate
- Common entry points
- Code pointers

**Estimated words:** 2200

---

### Page 4.3: **Thinking/Action Selection** (`brain/think/`)
**Structure:**
- Module organization
- Bandit implementation
- Deliberation gate
- Action arbiter
- Cost prediction layer
- Function selector (detailed)
- Debugging (common issues)

**Estimated words:** 1800

---

### Page 4.4: **Symbolic Reasoning** (`brain/symbolic/`)
**Structure:**
- Implementation of DL, causality, concepts
- World model data structures
- Query engine
- Learning mechanisms
- Extensions (how to add operations)
- Examples (concrete scenarios)

**Estimated words:** 1900

---

### Page 4.5: **Memory System** (`memory/`)
**Structure:**
- Daemon architecture
- WAL format & capping
- Embedding pipeline
- Consolidation algorithm
- Retrieval ranking
- Performance tuning
- Debugging issues

**Estimated words:** 1800

---

### Page 4.6: **Goals Daemon** (`goals/`)
**Structure:**
- Daemon architecture
- WAL + snapshots
- State store
- Runner (executor)
- Goal lifecycle
- Planning algorithm
- Custom goal creation (guide)

**Estimated words:** 1700

---

### Page 4.7: **Host Coupling & Supervisor** (`supervisor/`, `brain/cognition/host_resource_monitor.py`)
**Structure:**
- Absolute floors (reflex)
- Deviation bands
- Cadence control
- Infancy (learning normal)
- Resource budgets
- Alerts & emergencies
- Configuration

**Estimated words:** 1600

---

### Page 4.8: **Peers** (`brain/peers/`)
**Structure:**
- Each peer (Architect, Signal Historian, etc.)
- Architecture diagram
- Signal proposal format
- Integration with router
- Writing custom peer (tutorial)
- Common patterns

**Estimated words:** 1500

---

### Page 4.9: **Backend & Telemetry** (`backend/`)
**Structure:**
- WebSocket protocol
- State serialization
- UI room mapping
- Hub architecture
- Client registry
- Telemetry buffering

**Estimated words:** 1400

---

### Page 4.10: **LLM Integration** (`brain/utils/llm_providers/`, `brain/cognition/tools/ask_llm.py`)
**Structure:**
- Provider interface
- Adapter implementations (OpenAI, Anthropic, Gemini)
- Fail-closed contract
- Tool-only mode
- Fine-tuning pipeline
- Token budgeting
- Debugging LLM issues

**Estimated words:** 1600

---

## TIER 5: HOW-TO GUIDES (5 pages)

### Page 5.1: **Adding a Custom Peer**
**Structure:**
- Architecture review (quick recap)
- Step-by-step
  - Create class (inherit PeerBase)
  - Implement wake conditions
  - Implement signal proposal logic
  - Test
  - Register
- Full worked example
- Common patterns
- Debugging

**Estimated words:** 1000

---

### Page 5.2: **Tuning Control Signal Setpoints**
**Structure:**
- When to tune and why
- Current setpoints (reference)
- Impact analysis (each setpoint's effect)
- Tuning process
- Monitoring impact
- Rollback strategy
- Example scenario

**Estimated words:** 900

---

### Page 5.3: **Extending Symbolic Operations**
**Structure:**
- Overview (what can you add?)
- World model extensions
- Causal reasoning extensions
- Concept formation extensions
- Step-by-step for each
- Testing
- Example

**Estimated words:** 1000

---

### Page 5.4: **Debugging Memory Issues**
**Structure:**
- Common symptoms
  - Memory not retrieved
  - Consolidation stalls
  - Embeddings error
  - State corruption
- Diagnosis steps
- Fixes
- Logs to read
- When to reset

**Estimated words:** 900

---

### Page 5.5: **Writing a Custom Cognitive Function**
**Structure:**
- What is a cognitive function?
- Requirements
- Architecture (input, state, output)
- Entry point in the loop
- Testing
- Integration with bandit
- Example (annotated code)
- Common mistakes

**Estimated words:** 1100

---

## TIER 6: OPERATIONS & DEPLOYMENT (3 pages)

### Page 6.1: **Configuration Reference**
**Structure:**
- All ORRIN_* variables
- Table: variable, default, effect, when to use
- Groups (UI, cognition, memory, goals, host, backend, metrics)
- Advanced tuning
- Example configs (minimal, dev, production)

**Estimated words:** 1200

---

### Page 6.2: **Running with Docker**
**Structure:**
- Pull vs. build
- Environment setup
- Volumes & state persistence
- API ports
- Logs
- Debugging in container
- Docker Compose reference

**Estimated words:** 800

---

### Page 6.3: **Remote Access & Tunneling**
**Structure:**
- Security implications
- Tunnel setup (expose_orrin.command)
- URL format
- Control tokens
- Viewing from remote device
- Stopping tunnels
- Best practices

**Estimated words:** 600

---

## TIER 7: RESEARCH & EVIDENCE (2 pages)

### Page 7.1: **Scientific Foundations**
**Structure:**
- Philosophy of the wiki (inspired, not validated)
- Each subsystem's inspiration
  - Russell & Barrett (affect)
  - Baars & Dehaene (workspace)
  - Pearl & Granger (causality)
  - Friston / Rescorla-Wagner (prediction)
  - Carver & Scheier (control)
  - Schultz (reward prediction error)
  - Flavell / Nelson & Narens (metacognition)
  - Redgrave / Prescott / Gurney (action selection)
  - Botvinick et al. (conflict monitoring)
- Citations & links
- Caveats (working interpretations, not reproductions)

**Estimated words:** 1000

---

### Page 7.2: **Benchmarks & Verification**
**Structure:**
- Overview of benchmark suite
- What Orrin claims vs. evidence
- Capability benchmarks
- Reliability metrics
- Links to demo runs
- How to run benchmarks
- Interpreting results

**Estimated words:** 800

---

## Summary

**Total words:** ~50,600  
**Total pages:** 35  
**Reading time (full wiki):** ~10 hours  
**Reading time (conceptual tiers only):** ~2 hours  

### Maintenance Notes
- Update subsystem pages when code changes
- Keep "Glossary" & "FAQ" current (add Q&A as they come up)
- Link between related pages consistently
- Use consistent terminology (reference glossary)
- Archive outdated design decisions in docs/

