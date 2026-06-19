# Desktop app — what's left (2026-06-15)

The desktop-app plan (`docs/archive/DESKTOP_APP_PLAN_2026-06-14.md`, now archived) is
functionally complete and downloadable. The pure-code remainder was finished on branch
`finish-desktop-polish` (memory-ceiling eviction, E6/E7, F1, §10.6, I1/I5/I6 packaging,
Part 8 ℹ️ drill-down, H2 SDK verification). This file tracks only what is **not** done,
and why.

## Blocked on certs / accounts / hosting (cannot be done in-repo)

- **I4 — macOS signing + notarization.** Needs an Apple Developer account. Until then
  Gatekeeper blocks a double-click (users right-click → Open once). The hardened-runtime
  entitlements (`packaging/entitlements.plist`) and Info.plist usage strings
  (`packaging/orrin.spec`) are already written — they just need to be applied at sign time.
- **Windows code-signing.** The I5 installer (`packaging/windows/orrin.iss`) builds and
  bundles the WebView2 bootstrapper, but the resulting `Orrin-Setup-windows-x64.exe` is
  unsigned, so SmartScreen shows "Windows protected your PC" (More info → Run anyway).
  Needs a Windows code-signing certificate.
- **I7 — auto-update platform swap + hosting.** The in-repo layer is done and tested
  (version stamp, opt-in `check_for_update`, export-the-mind-first `prepare_update`,
  Settings UI, CI version stamping). Still external: the actual binary swap —
  **Sparkle** (macOS signed appcast), **Squirrel/MSIX** (Windows),
  **zsync/AppImageUpdate** (Linux) — plus a place to host the appcast/releases. The swap
  must (1) only run after `prepare_update()` has exported the mind, (2) hand off via the
  existing graceful shutdown so an *Always-thinking* Orrin isn't killed mid-thought, and
  (3) let the next launch's migration spine carry the mind forward.

## Needs a real desktop to verify (written, not GUI-tested here)

- **F1 — Always-thinking tray.** `backend/server/tray.py` (pystray) + the close→hide /
  reattach wiring in `main.py` are implemented and best-effort (a missing/failed tray
  falls back to headless-on-close, so the user is never trapped). The live behavior —
  especially macOS NSStatusBar sharing pywebview's Cocoa run loop via `run_detached()` —
  could not be exercised headlessly. **Verify on a real desktop:** Show / Hide-on-close /
  Quit, on macOS + Windows + Linux; iterate if the macOS run-loop integration misbehaves.

## Verified only on the next tagged build (CI, not runnable locally)

These run in `.github/workflows/build.yml` on a tag (`git tag vX.Y.Z && git push --tags`)
and need a clean run to confirm:

- **I1 — embedded CPython staging** (`packaging/stage_embedded_python.py`): confirm the
  standalone CPython lands where `brain/utils/runtime_python.py` probes on each OS, and
  that the frozen sandbox uses it instead of the host. Best-effort; set
  `ORRIN_REQUIRE_EMBEDDED=1` to make staging failures fatal during a release build.
- **I5 — Windows installer**: confirm `choco install innosetup` + `ISCC` produce the
  Setup.exe and the WebView2 bootstrapper installs silently on a machine without it.
- **I6 — Linux AppImage** (`packaging/linux/make_appimage.sh`): confirm `appimagetool`
  produces a runnable `Orrin-linux-x86_64.AppImage` (WebKitGTK is the native-window
  runtime dep; without it Orrin falls back to a browser tab).

## Environment note (not a code gap)

The test-isolation guard in `tests/conftest.py` reports a false "mutated live Orrin
state" error when a **live Orrin instance is running** (it writes `brain/data` during the
test run). Test assertions still pass; CI has no live Orrin, so it's clean there. Stop the
running instance to get a clean local run.
