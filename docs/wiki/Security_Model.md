# Security Model

Orrin is an experimental research prototype, **not security-hardened**. It can read and write local
files, run local tooling, expose a local UI/backend, and — when configured — call external services
and write its own code. Treat it accordingly. This page consolidates the security-relevant behavior
that's otherwise spread across the backend, remote-access, and packaging pages; the repo also has a
[`SECURITY.md`](https://github.com/ric-massey/orrin_v3/blob/main/SECURITY.md) policy.

## Trust boundaries

- **Local by default.** In native window mode the UI runs over an in-process bridge with **no open
  port**. Nothing is network-exposed unless you choose to expose it.
- **The loopback backend is zero-config and unauthenticated.** That's fine on localhost; it is *not*
  fine on a shared network. Auth turns on the moment a client is non-loopback.

## The three tokens

Enforced by `backend/server/auth.py`, all optional on loopback:

| Token | Protects | Frontend var |
|-------|----------|--------------|
| `ORRIN_READ_TOKEN` | Reading telemetry (REST + WebSocket) from non-loopback clients | `VITE_READ_TOKEN` |
| `ORRIN_CONTROL_TOKEN` | `/api/control/*` — the Stop button and any steering | `VITE_CONTROL_TOKEN` |
| `ORRIN_INGEST_TOKEN` | `POST /ingest` — so only the real loop can push telemetry | — |

`ORRIN_EXTRA_ORIGINS` allow-lists additional browser origins (e.g. a tunnel); the local Vite origin
and backend host are trusted automatically.

**Before exposing Orrin beyond localhost, set `ORRIN_CONTROL_TOKEN`** — otherwise anyone who can
reach the UI can stop or steer the agent. A tunnel URL is effectively the read secret; treat it as
sensitive and stop the tunnel when done ([Remote Access & Tunneling](Remote_Access_Tunneling)).

## Secrets

API keys are never stored in the app bundle or a plaintext file in the packaged app. Keys pasted in
Settings go to the **OS keychain** — Keychain (macOS) / Credential Manager (Windows) / libsecret
(Linux) — via `brain/utils/secrets.py`. In development, `.env` is convenient but gitignored; don't
commit secrets.

## LLM containment

The LLM is fail-closed and tool-only by default (`ORRIN_LLM_TOOL_ONLY=1`): only allow-listed callers
can invoke it, errors never return fabricated content, and a circuit breaker degrades to
symbolic-only on repeated failure ([LLM Integration](LLM_Integration)).

## Self-modification

Orrin can write and register its own cognitive functions. This is fenced structurally: it can only
write to two directories, cannot touch the selection/repair core, validates all generated code in a
sandbox before registering it, and keeps a manifest — with the Architect peer reviewing changes.
Still, **review generated code before relying on it**
([Self-Code and Extension](Self_Code_and_Extension)).

## Operator checklist

- Don't run Orrin on a machine you don't trust.
- Don't expose control endpoints publicly without `ORRIN_CONTROL_TOKEN` + network controls.
- Keep keys in the keychain or `.env`; never commit them.
- Treat remote access, tunnels, and Funnel/Tailscale setups as advanced configurations.
- Review self-extension output before depending on it.

## Reporting

Report security concerns via a GitHub issue with a high-level description and **no** secrets, tokens,
or exploitable detail. See the repo `SECURITY.md`.
