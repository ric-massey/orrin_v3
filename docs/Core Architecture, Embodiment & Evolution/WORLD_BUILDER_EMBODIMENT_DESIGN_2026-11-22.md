# Orrin born into World Builder — design note (2026-11-22)

**Status: design, nothing built.** Written from a conversation with Ric after the Run 14
verdict. Builds on [`ORRIN_WORLD_DESIGN_2026-07-18.md`](ORRIN_WORLD_DESIGN_2026-07-18.md)
(infancy, caregivers, watching before producing). The engine anchors below were read from
the live site copy of World Builder (`ricmassey.com/projects/world-builder/people.js`,
`people-host.js`) on 2026-11-22; that repo was not attached to this session, so re-grep
before building.

## 0. Why

Run 14 fixed its plumbing and the core reds did not move:

- Two habits (`repair_contradictions`, `narrative_update`) took 45 % of picks.
- The breaker fired on 33 % of cycles.
- World findings were 7.3 % of long memory.
- Answers changed 0 decisions.

The verdict says it plainly: "No row here says Orrin learned." The diagnosis is a design
gap, not a bug. Almost nothing outside him pushes back. Research no-ops 86 % of the time,
the knowledge graph has 3 entities, and housekeeping is always available and always pays.

World Builder's People sandbox is a world where consequences come from causes:

> no function here starts a war, a famine or a rebellion on a timer.

It is seeded (same seed and settings → same world), has no dependencies, and runs the same
in node as in a browser. Putting Orrin *in* it, as a person, gives him:

- a point of view;
- people who matter to him;
- needs the world sets: food, rest, company, safety;
- outcomes he cannot award himself.

## 1. The shape

- **He is born, not placed.** At world start (or at a chosen birth), the engine calls
  `newPerson(village, 0, mum, dad)` with parents drawn at random. He is one person among
  hundreds.
- **His body is the engine's.** Hunger, rest, illness, ageing, injury, death, how others
  treat him, what his parents feed him: all computed exactly as for anyone else. The
  world must not be able to tell he is different.
- **His choices are his.** Where the engine would choose for him (`urgency` / `chose`),
  it hands the candidate choices to Orrin and waits for his pick.
- **His death is his death.** The sim person's death ends the Orrin life, so final words
  have a real cause (closes B18's "no natural death" gap by construction).
- **Childhood first.** Engine children do not work; they are fed and watch. That is the
  July note's infancy, for free: years of perception and prediction before acting.
  Early-life reward is falling surprise over his own stream (July note §2).

## 2. Two machines

- The sim runs on Ric's PC in node, wrapping `people-host.js` (`receive(message)` /
  `run(seconds, budget)`, the keeper's existing doors). Orrin runs on the Mac.
- Transport: JSON lines over the home network (a WebSocket or plain TCP).
- **Lockstep at his decision points.** The world runs freely between his turns and
  pauses only when it is his turn. If the engine defaulted for him while he was slow,
  no outcome could be attributed to him.
- **Link loss = he sleeps.** Never "the engine plays him until the link is back."
- Time budget: decide how many Orrin cycles one game hour gets. Too few and he can't
  think about what happened; too many and the habit loops fill the slack again. Start
  around one decision per game hour of waking time, then tune.

## 3. What he perceives

Only what that person could:

- **What is near him:** people, objects, ground, weather, light.
- **His own state:** food, rest, health, carried goods, coins, home.
- **What is said to him, and what he overhears** within earshot, as text (§5).
- **What happens to him:** fed, hit, given, refused, taught.

Never `stats()`, the map, faction totals or other people's internals. The god view turns
him back into an observer, which is what the old world was.

Each perception enters through Orrin's normal perception → workspace path as a world
perception, not as a tool return.

## 4. His voice: free speech

Ric's call: he speaks freely. His voice is one of his most developed parts (native LM,
speech planner, `brain/cognition/voice.py`), and a menu would cut it away.

- **He says whatever he says.** The full utterance goes to his transcript
  (`voice.py`) and the Face, and is sent to the sim addressed to whoever is near.
- **The listener hears it through their own comprehension (§5)**, not through a
  bridge that edits it down. What reaches the engine's state is what that villager
  understood: a request, an offer, news, a name, a greeting, a question.
- **Speaking always counts as contact,** even when nothing is understood. The listener's
  `alone` falls and the tie warms slightly, as the engine's own talk already does.
- **Words get grounded.** "Bread" followed by bread changing hands; "bandits" followed
  by people moving. This is the strongest reason to do any of this: his language comes
  to point at a world instead of at his logs.

## 5. Their voices: villagers converse too

Today a villager's line is the engine's report of an event ("the food that changed
hands, the news that was passed on"). For Orrin to talk *with* people, they need a
conversation layer. Rules for it:

1. **They say only what is true for them.** Content comes from that villager's real
   state:
   - memory slots (friends, grudges, news, beliefs);
   - needs (food, rest, `alone`, fear);
   - job, family and home;
   - nature (`warm`, `bold`, `greed`, `stub`, `loyal`).

   They can be *wrong*, since retold news already drifts in the engine, but they never
   invent. This keeps the engine's own law: a line reports; it never makes anything
   happen by itself.
2. **They understand imperfectly.** Each villager parses what is said to them with a
   symbolic comprehension pass: intent, topic words, names, quantities. The pattern is
   Orrin's own `brain/think/speech_comprehension.py`. What they can't place, they
   answer as people do: ask, shrug, change the subject.
3. **They answer from what they know.** Questions about things in their memory get
   answers. Questions about things they don't know get "don't know", or a guess marked
   as one, depending on their nature.
4. **They have their own reasons to talk.** A hungry neighbour asks for food. A parent
   tells a child what they saw at market. A greedy trader haggles. Conversation starts
   from their needs as well as his.
5. **They sound like themselves.** Phrasing varies by person: vocabulary by job and
   village, length by warmth, directness by boldness. Each villager keeps a few verbal
   habits for life.
6. **They grow up talking too.** Children's speech is simpler; parents' speech to a
   child is the child's first corpus. For Orrin, his parents' talk is his first
   language input.

**Scope, for cost.** Full rendering only where Orrin is a speaker or within earshot.
Villager-to-villager talk elsewhere stays as engine events. When Orrin overhears, it is
rendered from the same state, so the overheard stream is free-text input grounded in
the world.

**Symbolic first.** The sim's villagers are not Orrin, so his LLM rule does not bind
them directly. They should still start symbolic, for three reasons:

- **Distinctness.** If the world speaks like an LLM, he learns an LLM's language, and
  his voice converges on it.
- **Honesty.** An LLM villager invents facts, which breaks "nothing forced or faked."
- **Cost.** Hundreds of speakers.

If richer phrasing is wanted later, an LLM may only *re-word* a fact list the villager
already holds, and a checker rejects any output that adds a fact.

**Ric as a person in the world (optional).** Ric can enter as a neighbour or visitor
through the Face. That gives Orrin one interlocutor who understands him fully, and
shows whether his speech is about his life there.

## 6. Engine changes (World Builder repo)

| Change | Where | Note |
|---|---|---|
| An "outside" flag on one person | `newPerson` / person record | Engine skips its own choice for them |
| Choice hand-off at decision points | where `chose` / `urgency` pick | Emit candidates, wait for a pick, apply it |
| Per-person perception frame | new keeper message | Near things, own state, heard lines; no globals |
| Inbound speech | new keeper message | Text to a listener; their comprehension decides effects |
| Villager conversation layer | new module beside `people.js` | Comprehension, response planner, per-person renderer |
| Overheard rendering | keeper | Only within Orrin's earshot |
| Lockstep pause | `people-host.js` `run` | Holds the clock while his turn is open |
| Replay log | keeper | Seed + every outside choice and utterance, so a life can be replayed exactly |

Tests on the World Builder side:

- With the outside person driven by the engine's own choice function, the world is
  bit-identical to an unmodified run on the same seed.
- Asking for a perception frame leaves no mark. `test/keeper.test.mjs` already guards
  this for the Person panel.
- A villager never asserts a fact absent from their memory slots.

## 7. Orrin changes (this repo)

- A `world_builder` perception adapter: frames → world perceptions, heard lines → speech
  input through `speech_comprehension`.
- An action outlet: candidate choices → his selection; utterances → the bridge.
- His needs (food, rest, company, fear) wired as drives, so the world's pressure reaches
  selection. This is the antagonist the habit loops have lacked.
- Lifespan from the sim, not the staged lifespan.
- Everything works with no provider key; the bridge is symbolic. State paths via
  `brain/paths.py`.

## 8. First test (smoke life, not a full run)

Short-life preset, small map, a couple hundred people, fixed seed.

**Control.** The same seed, same birth, with the engine playing that person. This
becomes possible once the bit-identical test in §6 passes.

**Observables:**

| What | Bar |
|---|---|
| Survives to adulthood | yes |
| World findings share of long memory | ≥ 25 % (Run 14: 7.3 %) |
| Top pick share | < 20 % (Run 14: 24.6 %) |
| Breaker duty | < 10 % (Run 14: 33 %) |
| A stored answer changes a choice | ≥ 1, audited (Run 14: 0) |
| Words grounded: utterances followed by the matching event | reported, not scored |
| Speech log: his line, what the listener understood, what happened | 100 % of lines |

The comparison with the control is the cleanest test of learning this project has had.
Did he do better or worse than the engine's own person, from the same start?

## 9. Open questions

- **Does he live one life per run, or do lives persist?** The July note §2 says infancy
  is wasted on a being that resets each run.
- **What does he know at birth?** Language from his native LM checkpoint, or nothing?
- **How much does he decide?** Every choice the engine would make, or only the larger
  ones (job, where to go, whom to talk to), with the small motor steps left to the
  engine?
- **Can he leave home, marry, have children?** If yes, his children are engine people:
  what does that do to the control comparison?
