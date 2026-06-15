# Packaging Orrin — the freeze/ship runbook (Group I)

## Cross-platform builds from one Mac → GitHub Actions

You don't need a Windows or Linux machine. `.github/workflows/build.yml` builds
**macOS (arm64 + Intel), Windows, and Linux** on GitHub's runners — PyInstaller can't
cross-compile, so each OS builds on its own runner. Trigger it from the **Actions** tab
("Run workflow"), or push a tag:

```bash
git tag v0.1.0 && git push origin v0.1.0
```

Each run produces downloadable artifacts (`.dmg` / `.zip` / `.tar.gz`); a tag also
attaches them to a **GitHub Release**. Builds are **unsigned** for now.

**What downloaders see (unsigned):**
- **macOS** — Gatekeeper blocks a double-click; users **right-click → Open** once (or
  `xattr -dr com.apple.quarantine Orrin.app`). Removed by I4 (notarization).
- **Windows** — SmartScreen shows "Windows protected your PC"; users click **More info →
  Run anyway** once. Removed by a Windows code-signing cert. Needs the **WebView2**
  runtime (present on most Win10/11; bundle the bootstrapper in I5 to guarantee it).
- **Linux** — the `.tar.gz` unpacks to a folder; run `./Orrin/Orrin`. The native window
  needs **WebKitGTK** installed; without it Orrin falls back to a browser tab (A1).

To add signing later, see the per-OS sections below and switch the workflow's package
steps to sign before upload.

---


> **These steps run on a real build machine per target OS — not in CI here.** Freezing
> the torch/spaCy/sentence-transformers stack is the plan's #1 risk and needs iteration
> on each OS (no reliable cross-compile). Phases 1–H produced a fully working native app
> *from source*; this turns that known-good app into a download.

The in-repo code that makes freezing possible is **already done and tested**:

- **I1 — embedded interpreter** (`brain/utils/runtime_python.py`): the sandbox
  (`behavior/tools/sandbox.py`, `think/sandbox_runner.py`) invokes the bundled CPython
  when frozen, `sys.executable` in dev. Override: `ORRIN_EMBEDDED_PYTHON`.
- **I2 — offline weights** (`brain/utils/model_assets.py`): `apply_offline_env()` (called
  at the top of `main.py`) points HF/sentence-transformers at the bundle and goes
  hard-offline; spaCy loads from a bundled path. Override: `ORRIN_MODELS_DIR`.

## Build order (macOS, the strictest case)

```bash
# 0. Build the UI (from repo root)
cd frontend && npm run build && cd ..

# 1. Pre-fetch the ML weights into the bundle layout (needs network; once per release)
python packaging/bundle_models.py --out packaging/build/models

# 2. (optional) Stage an embedded CPython under packaging/build/python and either set
#    ORRIN_EMBEDDED_PYTHON at runtime or add it to the spec's datas. Without it the
#    sandbox falls back to the host (still timeout-guarded) — fine for a first build.

# 3. Freeze → dist/Orrin.app  (expect to iterate on hidden imports for torch/spaCy)
pyinstaller packaging/orrin.spec --noconfirm

# 4. Smoke test the freeze on THIS machine
dist/Orrin.app/Contents/MacOS/Orrin

# 5. Sign (hardened runtime + entitlements) and notarize
codesign --deep --force --options runtime \
  --entitlements packaging/entitlements.plist \
  --sign "Developer ID Application: <YOU> (<TEAMID>)" dist/Orrin.app
ditto -c -k --keepParent dist/Orrin.app dist/Orrin.zip
xcrun notarytool submit dist/Orrin.zip --apple-id <id> --team-id <TEAMID> --wait
xcrun stapler staple dist/Orrin.app

# 6. Wrap in a .dmg for distribution
hdiutil create -volname Orrin -srcfolder dist/Orrin.app -ov -format UDZO dist/Orrin.dmg
```

**Acceptance (Part 4):** install on a Mac that has never had Python, **Wi-Fi off** →
Orrin boots, thinks, and renders. Take a screenshot / open an allow-listed app *after*
granting permission; before granting, Trust shows the capability "off" (never a crash).

## Windows (I5)
Reuse `orrin.spec` (drop the `BUNDLE`/Info.plist macOS block). Build a single-file or
folder app, wrap with **Inno Setup / NSIS**, **bundle the WebView2 bootstrapper** (most
Win10/11 have it, but guarantee it), and **code-sign** to clear SmartScreen.

## Linux (I6)
Reuse `orrin.spec`. Package as **AppImage** (easiest; unsigned) and optionally `.deb`.
Document the **WebKitGTK** runtime requirement.

## Auto-update (I7) — wired to the schema spine
Updates must **export the mind first** (reuse `brain/utils/mind_archive.py`) and respect
the **schema migration spine** (`brain/utils/schema_migration.py`, G1): older state
migrates forward, newer refuses. Per platform: **Sparkle** (macOS signed appcast),
**Squirrel/MSIX** (Windows), **zsync/AppImageUpdate** (Linux). Updates are opt-in and
respect the existence mode (don't kill an *Always thinking* Orrin mid-thought). The
product promise: *you are never one update away from losing him without a copy.*

## Status
- **Done & tested in-repo:** I1, I2.
- **I3 — DONE & verified on macOS arm64 (2026-06-15):** `pyinstaller packaging/orrin.spec`
  produces a standalone **`dist/Orrin.app` (807 MB)** that boots from the per-user data
  dir, seeds a newborn, loads the bundled ML weights (torch + sentence-transformers),
  and runs real cognitive cycles — no Python/Node required. Two fixes were needed and are
  committed: (a) `Analysis([str(ROOT/"main.py")])` (spec ran relative to `packaging/`);
  (b) `main.py` skips its `sys.path` bootstrap when `sys.frozen` (the bundled `brain/`
  dir was shadowing the PyInstaller frozen importer → `No module named 'utils.paths'`).
  Build with this venv after `pip install pyinstaller`. The native pywebview window needs
  a GUI session; a headless launch falls back to a browser tab (by design, A1).
- **Needs a build machine + certs (not runnable here):** I4 sign/notarize (Apple Dev
  cert), I5 Windows, I6 Linux, I7 auto-update infra.
