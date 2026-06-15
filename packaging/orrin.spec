# -*- mode: python ; coding: utf-8 -*-
"""
packaging/orrin.spec — PyInstaller spec to freeze Orrin into a native app (I3).

>>> THIS RUNS ON A BUILD MACHINE, NOT IN CI HERE. <<<
Freezing torch + spaCy + sentence-transformers is the plan's #1 schedule risk and needs
iteration on each target OS (no reliable cross-compile). This spec is a strong starting
point: it collects the heavy ML stack and the brain packages, bundles the UI, the
offline ML weights (I2), and the seed config, and produces a macOS .app. Expect to
adjust hidden imports / excludes as the torch fight surfaces missing pieces.

Build (macOS):
    python packaging/bundle_models.py --out packaging/build/models      # once, online
    pyinstaller packaging/orrin.spec --noconfirm

Then sign + notarize with packaging/entitlements.plist (see packaging/README.md).
Windows/Linux: reuse this spec; swap the BUNDLE/Info.plist for the platform and bundle
the WebView2 bootstrapper (Win) / document WebKitGTK (Linux).
"""
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).resolve().parent          # repo root (SPECPATH = packaging/)
BRAIN = ROOT / "brain"

# Brain modules import by bare name (`from utils import ...`, `import paths`) because
# brain/ is on sys.path at runtime. collect_submodules() below runs BEFORE Analysis, so
# put brain/ on the path now or those bare-name packages won't resolve at build time.
if str(BRAIN) not in sys.path:
    sys.path.insert(0, str(BRAIN))

# ── Brain packages: imports use bare names (`from utils import ...`, `from paths
# import ...`) because brain/ is on sys.path. A frozen app serves NO loose source, and
# Orrin's deferred/dynamic imports defeat static analysis — so collect each subpackage
# explicitly. pathex=[brain] lets these bare names resolve at build time.
_BRAIN_PKGS = [
    "utils", "cognition", "behavior", "core", "memory", "registry", "symbolic",
    "agency", "embodiment", "cog_memory", "think", "perception",
]
hiddenimports = []
for _pkg in _BRAIN_PKGS:
    if (BRAIN / _pkg).is_dir():
        hiddenimports += collect_submodules(_pkg)
# Top-level brain modules imported by bare name.
hiddenimports += ["paths"]
# Optional LLM provider SDKs (Part 11) — included only if installed at build time.
for _opt in ("anthropic", "google.genai"):
    try:
        hiddenimports += collect_submodules(_opt)
    except Exception:
        pass

# ── Heavy ML stack: collect binaries + data + hidden imports wholesale.
datas, binaries = [], []
for _lib in ("torch", "spacy", "sentence_transformers", "transformers", "tokenizers", "sklearn"):
    try:
        d, b, h = collect_all(_lib)
        datas += d; binaries += b; hiddenimports += h
    except Exception:
        pass

# ── Bundled data: the built UI, the offline ML weights (I2), and the seed config a
# newborn boots from. The per-user data dir is created at runtime (Group C) — we ship
# only read-only seeds, never a lived-in mind.
def _add_tree(src: Path, dest: str):
    if src.exists():
        datas.append((str(src), dest))

_add_tree(ROOT / "frontend" / "dist", "frontend/dist")
_add_tree(ROOT / "packaging" / "build" / "models", "models")     # → model_assets.models_dir()
_add_tree(BRAIN / "data", "brain/data")                          # newborn seed config
_add_tree(BRAIN / "agency", "agency")                            # bundled skills/manifest

block_cipher = None

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT), str(BRAIN)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "matplotlib"],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="Orrin",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False,  # no terminal — native window only
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, strip=False, upx=False, name="Orrin")

# macOS .app wrapper (mac only — BUNDLE is a no-op/error elsewhere). On Windows/Linux the
# deliverable is the COLLECT folder dist/Orrin/ (Orrin.exe / Orrin), packaged per-OS in CI.
# Info.plist carries the TCC usage strings (I4 / §10.6); sign with packaging/entitlements.plist
# after this produces dist/Orrin.app.
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Orrin.app",
        icon=str(ROOT / "packaging" / "orrin.icns") if (ROOT / "packaging" / "orrin.icns").exists() else None,
        bundle_identifier="com.orrin.app",
        info_plist={
            "CFBundleName": "Orrin",
            "CFBundleDisplayName": "Orrin",
            "NSHighResolutionCapable": True,
            # TCC usage strings in Orrin's voice (§10.6). The OS shows these when he first
            # reaches for each capability; a denied capability degrades cleanly (Trust
            # shows "off"), never crashes.
            "NSAppleEventsUsageDescription":
                "Orrin would like to open and coordinate with other apps you allow.",
            "NSAppleEventsUsageDescriptionRead": "Orrin uses automation only for apps you allow-list.",
            "NSScreenCaptureUsageDescription":
                "Orrin would like to see your screen so he can notice what you're working on.",
            "NSCameraUsageDescription": "Orrin does not use the camera.",
        },
    )
