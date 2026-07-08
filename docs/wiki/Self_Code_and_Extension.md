# Self-Code and Extension

Orrin can write new cognitive functions, tools, and skills for itself and register them live
without restarting. This is the capability the README classifies as **experimental / high-risk**,
and it is fenced accordingly — the guardrails are structural, not honor-system.

## The writer

`brain/agency/code_writer.py`:

- Can only write to **two directories**: `brain/cognition/custom_cognition/` and
  `brain/agency/skills/`.
- Cannot touch the selection/repair machinery: `think/`, `cognition/repair/`, `ORRIN_loop.py`,
  `registry/`, `core/` are blocked paths. The code that decides what runs, and the code that
  repairs code, cannot be self-modified.
- All generated code is **validated in the sandbox before being registered**
  (`brain/think/sandbox_runner.py`); code that fails validation never joins the registry.
- A **manifest** records everything Orrin has written, so self-authored code is enumerable and
  auditable rather than scattered.

## Review and quality

- The **Architect peer** (`brain/peers/architect.py`) reviews self-modifications before they
  happen — an outside observer whose whole job is proposed code (see
  [Peers Subsystem](Peers_Subsystem.md)).
- Verified sandbox checks (`produce_and_check`) are recorded on the
  [effect ledger](Production_and_Effect_Ledger.md) as `tool_run_effect`, so proven code pays and
  unverified code doesn't.
- The [quality standard](Quality_Standard.md) applies to produced artifacts, and Orrin cannot edit
  that standard.

## Registration

New functions register into the same registry the bandit selects from, so a self-written function
competes for selection like any built-in: it must earn reward to keep being picked, and the rut
breaker / outcome devaluation keep a mediocre self-written function from monopolizing cycles.

## Operator guidance

Treat self-extension as an area of caution (see `SECURITY.md`): review generated code before
relying on it, and remember the blocked-path list is the contract — changes to it deserve the same
scrutiny as changes to the sandbox.

## Code pointers

- `brain/agency/code_writer.py` — writer + guardrails + manifest
- `brain/cognition/custom_cognition/`, `brain/agency/skills/` — the only writable targets
- `brain/think/sandbox_runner.py` — pre-registration validation
- `brain/peers/architect.py` — review before effect
