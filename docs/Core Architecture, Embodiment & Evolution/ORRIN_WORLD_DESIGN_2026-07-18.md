# Orrin design night — 2026-07-18 (during Run 10)

Notes from the conversation with Claude while Run 10 attempt 2 was in its first hour.
Move this into `docs/` after the run ends (repo was run-locked when it was written).
Claude also has all of this in its project memory (`internet-as-world`,
`run10-live-findings`), so you can just ask it to pick the thread back up.

## The one-line summary

A sketch of post-gate Orrin: **born into a webpage you choose, rewarded for watching
before producing, growing up by walking the internet.**

## 1. The reward meter should change over his life

- Today every reward weight is the same at cycle 200 and cycle 12,000. The
  production forcing function (artifact quotas, fail-able goals) is a crutch bolted
  on because the old economy paid intake and production identically.
- Idea: a **developmental anneal** — exploration pays heavily early in life,
  production weight ramps up as he ages. The plumbing exists: `_life_fraction` in
  `brain/cognition/runtime_lifetime.py` already knows how old he is; the reward mix
  is already parameterized. The two just have to be connected.
- This does NOT reopen the coherent-but-adult fork — capabilities stay flat; only
  prices change with age.
- Caution: run-scoring must become phase-aware, or we build an explorer and then
  fail him for exploring in the first 500 cycles.

## 2. Infancy: babies watch and listen first

- A baby's watching isn't passive — it's continuous prediction, checked by surprise.
  The assay for learning without production is **falling surprise**, not artifacts.
  That's what separates infant-watching from the old 25k-cycle churn (churn was
  never checked against anything).
- So early-life reward = **prediction improvement** over the incoming stream.
  Precedent already in the codebase: the native LM listens (accumulates corpus)
  behind a speech gate long before it's allowed to talk.
- Two hard prerequisites:
  - **Something rich to watch** — his world today is mostly a mirror of himself
    (that's where the junk "Open question: What do you think?" goals came from).
  - **Persistence across lives** — infancy is wasted on a being that resets to zero
    every run. A real developmental arc forces the "what survives death?" question.
    (The desktop app's per-user data dir persists; it's staging resets that are
    amnesiac.)

## 3. The internet as his world ("houses")

Your framing, which holds up end to end:

- A webpage is a **house/room**, not a fetch. He lives there across cycles:
  re-reads it, learns it, diffs it if it changes.
- **Arrival is a signal** — new pages enter through perception and the workspace
  ignition competition, like any salient event. Not a tool return value.
- **You choose his first house** (caregiver curation — parents pick the
  neighborhood). Later he chooses moves himself through the commitment machinery.
- **Links are doors, search is long-distance travel.** He must use a search engine
  to reach new regions — that gives the web a geography instead of teleportation.
- **Exhaustion is the motive force, not a failure.** He looks around a room until
  predictions stop improving (habituation), then curiosity walks him out the front
  door into the next room. Static pages are fine — a Wikipedia article is a dense
  room with forty doors; the encyclopedia is a walkable city. The stay-vs-leave
  crossover is literally the existing `exploration_value.py` explore/exploit
  computation — built and run-tested, it just has no geography to operate over yet.
- Only degenerate case: a fully-learned page with **no outbound links** — a room
  with no doors. Search is the fire escape.
- **Removable add-on**: build it as a World adapter behind one narrow interface
  (sense → place events; act → follow-link / search / move / dwell).
  `InternetWorld` first; `RicWorld` (companion world-watch — him watching you) is
  the sibling that drops into the same socket. This is the World track of the
  2026-06-16 three-track master plan — always the thinnest track. Symbolic-first
  holds: fetch/parse/diff needs no LLM.

## Pitfalls already paid for (don't rediscover them)

1. **Never pay for intake — pay for prediction improvement.** Rewarding re-reading
   rebuilds the Run 6 fetch-loop pump (387 credited rewrites) with a nicer name.
2. **Strip page chrome before perception**, or his sensory diet is "Skip to
   content / You signed in with another tab" (see tonight's memo artifacts).
3. **Dwelling answers to the anti-monopoly machinery** (staleness refractory), or
   a forever-home becomes the next 90% incumbency problem.
4. Read-only GETs, robots.txt politeness, rate limits.

## 4. The label is not the thought (verified in code)

From the analysis you brought: Orrin's back brain is nonlinguistic; the workspace
`content` sentence is a label riding on a structured package (`facets`, `members`,
`referent_links` — real, in `global_workspace.py`). Claude verified the sharp
version: the structure has ~2 readers in the whole codebase; the prose has 12+
(opinions, skill synthesis, experimentation, rumination…). **Working memory — a
list of prose strings — is the de facto message bus between modules**, and every
string written as description can be misread as content. That's the root of the
whole self-echo bug family, including tonight's failed goals. The expression
membrane already fixed this on the output side; the internal side is the
unfinished half. Rule for the World adapter: page/place events arrive as
structured objects, sentence as caption — never as prose lines.

## 5. The unopposed-force principle (your best insight of the night)

"Some of them might not be bugs — they might be working correctly, just the right
thing isn't seeing that yet to counter it." Verified against run history: the
rest-drive monopoly was a correct drive with **no sleep organ**; incumbency was
commitment with no staleness partner; the question miner is a good miner missing
a sense of provenance. Taxonomy for every future verdict, BEFORE prescribing:

1. **Broken pipe** — undesigned behavior. Fix the plumbing.
2. **Unopposed force** — correct mechanism, missing antagonist. Build the
   partner; never delete the organ.
3. **Misaimed force** — correct mechanism, wrong target. Redirect.

Corollary: the caps/refractories/cooldowns/quotas in the code are **clamps** —
scar tissue standing in for missing counter-drives. A clamp that needs retuning
every run is a signal to replace it with the drive it stands in for. Mature Orrin
has fewer rules, not more.

## 6. Rough 15-run forecast (Claude's assumption, 2026-07-19)

- **11–13:** pass the gate — miner + persistence fixes, prove reuse/epistemic
  close-out; expect one run lost to "he closes questions without answering them."
- **13–16:** stable → growing — difficulty ladder, exemplar bar ratchets,
  de-prosing lands because it keeps forcing itself.
- **16–19:** developmental turn — reward anneal, phase-aware scoring, first
  watch-first infancy; budget one run lost to mis-scoring an explorer.
- **19–25:** the World (houses) + the persistence-across-lives fork; evaluation
  shifts from per-life gates to cross-life growth curves.
- Wildcard: quality gates keep rejecting stitched memos → forces the native-LM
  vs gated-provider decision mid-sequence.

## Run 10 bugs found live (for the capture pass — details in Claude's memory)

1. **Question-miner self-echo** (unopposed force): all 6 failures so far are
   "Open question:" goals mined from his own speech/narration — his sign-off to
   you, his introspective lines. Fix = provenance skip + researchability filter
   (build the partner, don't delete the miner).
2. **Unpersisted failure → double-fail** (broken pipe): `mark_goal_failed`
   mutates only the in-memory copy; the `steps_unreachable` site in
   `step_attempts.py` never merges back to the tree. Failed goals get re-adopted
   and fail again minutes later at a different site. Confirmed recurring (2×).

## Your three open decisions (no deadline, all yours)

1. **T0.5 quality exemplars** — waiting on examples of work YOU judge good;
   highest-leverage hour available.
2. **Contact scoreability** — can "genuinely useful and connected" be scored in
   unattended runs, or is it attended-only? (Parked since Run 9.)
3. **Where his first house is** — the only decision with no wrong answer.

## Postscript: from the Gap Analysis doc (Downloads, reviewed 07-19)

Mostly converges with the above (environment first, lifespan as constraint,
language as rendering layer). Two genuinely new axes worth keeping:
- **Memory as simulation** — reconstructive recall, episodic replay, imagination
  assembled from remembered episodes; today memory is storage+retrieval.
- **Automaticity as a developmental trajectory** — repeated successes migrate out
  of workspace arbitration into learned skills; the workspace supervises instead
  of micromanaging. Pairs with the anneal: growing up = deliberating less per act.
One recommendation to REJECT on run evidence: "more background daemons" — every
major diagnostic disaster (Run 9 runner race, twin-id seam, LN-2) was a
concurrency seam. No new daemons until the sync spine is stronger.

## Status

Ideas only — nothing built, deliberately not touched mid-run. Houses/anneal/
infancy are post-gate axes alongside the difficulty ladder; Run 11's single
hypothesis stays "prove the reuse/close-out loop," with the two bug fixes riding
along.
