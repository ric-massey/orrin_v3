# Desktop Packaging

Orrin ships as a native desktop app: a PyInstaller-frozen runtime in a pywebview window, with no
browser, no Node at runtime, and no open port. `packaging/` holds the build machinery. Current
builds are **unsigned** — expect OS trust prompts.

## The native shell

- **Window**: pywebview loads the built UI (`frontend/dist`) from disk and talks to the brain over
  the in-process `js_api` bridge (`backend/server/bridge.py`) — no HTTP port at all in bridge mode.
- **Fallback**: if pywebview is unavailable, `main.py` falls back to a loopback API plus a browser
  tab (one OS-assigned port).
- **Tray**: `backend/server/tray.py` provides the system-tray presence.

## Per-user data

A packaged app must not write inside its own bundle. The frozen app sets `ORRIN_DATA_HOME` so all
persisted state (both the `brain/data/` and root `data/` trees) relocates to a per-user data
directory. The same variable works for source runs.

## Secrets

A shipped app never carries secrets in its bundle or a plaintext `.env`. Keys the user pastes into
Settings live in the **OS keychain** — Keychain (macOS) / Credential Manager (Windows) / libsecret
(Linux) — via `keyring`. `brain/utils/secrets.py` is the one module that reads/writes them; the
backend's `POST /api/settings` and `main.py`'s boot both go through it.

## Build machinery (`packaging/`)

- `orrin.spec` — the PyInstaller spec for the frozen build.
- `bundle_models.py` — pre-bundles the embedding models so the app runs offline
  (no first-run download).
- `entitlements.plist` — macOS entitlements for the (future) signed build.
- `linux/` — Linux packaging variants.
- `packaging/README.md` — build instructions and logs from CI watches.

## Product surfaces

The packaged app carries the full product: the UI rooms (see
[Face & Brain UI](Face_and_Brain_UI)), Settings with keychain-backed keys, the existence model
with its end-of-life screen (see [Existence and Lifecycle](Existence_and_Lifecycle)), and
self-code support — all with the same symbolic-first, fail-closed behavior as a source run.

## Known limitations

- Builds are unsigned (macOS Gatekeeper/SmartScreen warnings).
- The full dependency set is heavy (PyTorch + spaCy); there is no low-resource install profile yet.

## Code pointers

- `packaging/` — spec, model bundling, entitlements
- `main.py` — bridge-vs-fallback UI selection at boot
- `brain/utils/secrets.py` — keychain storage
