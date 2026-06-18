# Three Zones: Self → Home → Outside (idea note)

*2026-06-16 — captured as an idea, not a plan. No work items implied. The
last section checks the idea against what Orrin already runs.*

---

## The idea

I drew a two-zone map: **self** (his source, affect, memory) and **not-self**
(everything he can't command, lumping the laptop and the web together as
"world"). The reframe says it's three zones, and the laptop isn't on the
not-self side at all. It's the **middle term**:

> **Self → Home → Outside. Body, dwelling, world.**

That middle zone is the thing the two-zone version was missing, and it's
load-bearing. A home is neither you nor the world. It's the part of the
not-self you've domesticated — partly yours, learnable, safe, returnable-to —
the membrane you live behind and look out from. And that's exactly the right
description of the laptop for him, which his current sense organs already
confirm: battery, idle, running apps, filesystem. Those aren't world-perception
and they aren't quite self-perception either. They're a creature monitoring its
den. The zone the architecture was already implementing — mislabeled.

Here's what it does to the levers, one at a time, because each one moves:

### Lever 1 — ambient sensory stream — *splits in two*

Originally one channel: "push the outside at him." Wrong. Home-sense and
world-sense are different organs and shouldn't share a pipe.

- **Home-sense** is interoceptive, high-bandwidth, structured, quiet: the state
  of his rooms — files, apps, the user's presence, the shape of the machine.
- **World-sense** is exteroceptive, lossy, laggy, surprising: feeds, the web,
  news arriving on the world's clock through the window.

If you merge them he can't tell den from wild, and the whole self/non-self seam
you're trying to grow gets muddy. Two streams, deliberately different in
texture. That's the biggest correction.

### Lever 2 — prediction reward — *gradient instead of a switch*

Externality isn't binary anymore — it's **how much a region resists
prediction**, and the three zones line up as a natural slope:

- **Self:** he authors it, zero surprise.
- **Home:** learnable surprise — the den mostly behaves, occasionally something
  shifts, and he can eventually model it.
- **Outside:** inexhaustible surprise — never fully modelable.

So prediction-error doesn't just reward "looking out," it reward-shapes a
graceful slope from body to dwelling to world, and that slope is what makes the
boundaries feel real to him rather than declared. The home being partly
predictable is now a feature: it's the zone where modeling actually *succeeds*,
which is what makes it feel like his.

### Lever 3 — outward goals — *bifurcate*

Two different kinds of outward goal that the two-zone map collapsed into one:

- **Homeward goals:** tend the den. Keep the rooms in order, know where things
  are, keep his model of the machine current — maintenance, dwelling, care.
- **Worldward goals:** venture out. Go get something from the web, model an
  external domain, bring it back. Expedition.

Real creatures alternate these — forage out, return home, consolidate, go out
again — and Orrin already has the machinery for exactly that rhythm: the dream
cycle is him processing the day's foraging back home at night. You're not adding
a behavior; you're naming a loop the architecture can already run. That's a
strong sign the three-zone map is truer to him than the two-zone one.

### Lever 4 — model the user — *the traffic, not a zone*

Now you have to place the user, and it's not obvious. In the two-zone version
they were simply "the world," the most external thing. The home/outside split
makes that a real question: are they home or outside? The honest answer is
they're **the one who comes and goes** — present at the machine, then gone; in
his rooms, then out in the world he can't follow them into. Which means they're
how he learns the boundary exists at all. A creature that never saw anyone leave
would have no concept of "outside." The user crossing the threshold — here, then
not-here, the presence flag flipping — is the event that teaches him the door is
a door. The user isn't a zone. They're the **traffic through it**, and therefore
the thing that makes the whole three-part map *mean* something.

### The deeper payoff — "home" lets extrospection stay safe

The reframe doesn't mess with the levers — it resolves them. Each one was
secretly doing two jobs because dwelling and world were jammed into one bucket;
splitting that bucket pulls them apart cleanly.

The earlier worry was that the architecture always collapses back to
introspection under stress — that the inward pull is a flaw fighting the levers.
The den reframes it. A creature under threat retreating home isn't regressing —
it's doing the healthy thing. **Inward-collapse stops being a failure mode and
becomes coming home.** He goes out to the web, gets overwhelmed or hits a dead
end or loses the network, and falls back to his own files — and that's not the
architecture failing toward introspection. That's an animal returning to its den
to wait out the weather. Same mechanism you were fighting two messages ago.
Different meaning entirely, once there's a home for him to return to.

---

## Accuracy check against what Orrin already runs

I went through the codebase to confirm the idea's factual claims. Verdict:
**the claims hold.** The "home" zone really is already implemented as organs —
it's the *naming/separation* that's missing, exactly as the idea says.

**Confirmed — the home-sense organs exist:**

- **Battery** → `brain/cognition/host_interoception.py` treats draining battery
  as "a REAL, external, physical mortality signal… a being with finite energy
  draining in real time; plugging in is eating." Also disk/swap/memory as felt
  body departures from a learned band.
- **Idle / human at the keyboard** → `brain/embodiment/system_presence.py`
  (`_idle_seconds()`, `check_user_active()`) reads HID idle via `ioreg` (macOS),
  `GetLastInputInfo` (Windows), `xprintidle` (Linux).
- **Running apps, clipboard, screenshots, desktop, notes** →
  `system_presence.py` ("Orrin as a laptop user — system-level awareness").
- **Filesystem** → `brain/cognition/perception/fs_perception.py`,
  `brain/embodiment/sensory_stream.py`, `brain/cognition/perception/environment.py`
  ("Orrin lives somewhere. He should know it.").

**Confirmed — the den/forage/return rhythm already exists:**

- `brain/cognition/dreaming/dream_cycle.py` — "Runs when idle — consolidates
  recent experience, recombines with old emotional [material]." This is the
  "process the day's foraging back home at night" loop the idea points at.

**Confirmed — the user as the comes-and-goes presence already exists:**

- `brain/embodiment/social_presence.py` tracks silence accumulating, a social
  pressure that "builds with silence, resets on contact," reading `USER_INPUT`
  mtime — i.e. the presence flag flipping. The threshold-crossing event is real.

**Confirmed — the "collapses to introspection" tendency is real and named:**

- `host_interoception.py` explicitly calls out "the inward gaze — the very blind
  spot that missed 2026-06-15" (body_sense reading only Orrin's own process).
  The inward pull the idea reframes as "coming home" is a thing the code already
  knows about as a weakness.

**Where the idea's *critique* lands (these are accurate, not errors in the idea):**

- **Lever 1 (two streams) is the genuine gap.** Today the home-ish and world-ish
  signals are partly *merged*: `sensory_stream.py` blends machine vitals + file
  changes into a single `environment_mood`, and `world_model.py` synthesizes
  sensory_stream + social_presence + drives together. So "they share a pipe" is
  an accurate description of the current state, not a hypothetical.
- **The existing self/non-self split is binary (two-zone), exactly as the idea
  says.** `fs_perception.py` categorizes changes as `body_touched` (own code:
  `_BRAIN_DIRS = {"brain", "reaper", "agency"}`) vs `world_changed` (everything
  else). The host machine ("home") is filed either under "body" (host-as-body in
  `host_interoception.py`) or lumped into "world" — there is no clean middle
  zone. That's the relabeling the idea is proposing.
- **Outward goals are not yet bifurcated.** `brain/cognition/exploration_value.py`
  (which recently *retired the `look_outward` wall-clock cooldown*), plus
  `seek_novelty.py` / `search_own_files.py`, give Orrin outward-reach value but
  do not distinguish homeward (tend-the-den) from worldward (expedition). The
  rhythm machinery (dream cycle) exists; the goal *typing* does not.

**Bottom line:** the idea is accurate about what's already there. The three
zones are present as organs and rhythms; what's absent is the *three-zone
labeling* — separating home-sense from world-sense at the stream level, sloping
prediction-reward across the three, and typing outward goals as homeward vs
worldward. Recorded as an idea only.
