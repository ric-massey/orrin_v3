#!/usr/bin/env python3
"""
packaging/stage_embedded_python.py — drop a private CPython into the frozen bundle (I1).

A frozen Orrin shells out to a *private* interpreter for sandboxed code execution, not
to whatever `python3` the user happens to have (see brain/utils/runtime_python.py). The
in-repo half is done — `runtime_python.interpreter()` already probes the bundle for the
embedded interpreter and falls back to the host if it's missing. This script is the
build half: it fetches a relocatable standalone CPython (astral-sh/python-build-standalone)
and stages it where runtime_python.py looks:

  • macOS  → dist/Orrin.app/Contents/Resources/python/bin/python3
  • Windows → dist/Orrin/python/python.exe
  • Linux  → dist/Orrin/python/bin/python3

Run AFTER pyinstaller, on each OS runner (no cross-staging). It's best-effort: a
failure prints a warning and exits 0, because the host fallback still works (the
sandbox stays timeout-guarded either way) — a first build shouldn't be blocked on it.
Set ORRIN_REQUIRE_EMBEDDED=1 to make staging failures fatal instead.
"""
from __future__ import annotations

import io
import os
import platform
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

# Pin the standalone-CPython release + version so builds are reproducible. Bump together.
PBS_TAG = "20240814"
PY_VERSION = "3.12.5"

# (os.name/system, machine) → python-build-standalone target triple (install_only).
_TRIPLES = {
    ("Darwin", "arm64"): "aarch64-apple-darwin",
    ("Darwin", "x86_64"): "x86_64-apple-darwin",
    ("Windows", "AMD64"): "x86_64-pc-windows-msvc",
    ("Linux", "x86_64"): "x86_64-unknown-linux-gnu",
    ("Linux", "aarch64"): "aarch64-unknown-linux-gnu",
}

ROOT = Path(__file__).resolve().parent.parent


def _bundle_python_dir() -> Path:
    """Where the `python/` tree must land so runtime_python.py finds it."""
    if platform.system() == "Darwin":
        return ROOT / "dist" / "Orrin.app" / "Contents" / "Resources" / "python"
    return ROOT / "dist" / "Orrin" / "python"


def _asset_url() -> str:
    key = (platform.system(), platform.machine())
    triple = _TRIPLES.get(key)
    if not triple:
        raise RuntimeError(f"no standalone-CPython triple for {key}")
    name = f"cpython-{PY_VERSION}+{PBS_TAG}-{triple}-install_only.tar.gz"
    return f"https://github.com/astral-sh/python-build-standalone/releases/download/{PBS_TAG}/{name}"


def _stage() -> None:
    target = _bundle_python_dir()
    if not target.parent.exists():
        raise RuntimeError(f"bundle dir not found: {target.parent} — run pyinstaller first")

    url = _asset_url()
    print(f"[embed-python] fetching {url}")
    with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310 (pinned URL)
        data = resp.read()

    # install_only archives extract to a top-level `python/` dir; relocate it onto target.
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        tmp = ROOT / "packaging" / "build" / "_embed_python_tmp"
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir(parents=True, exist_ok=True)
        tf.extractall(tmp)  # noqa: S202 (trusted, pinned release)
        extracted = tmp / "python"
        if not extracted.exists():
            raise RuntimeError("archive did not contain a top-level python/ dir")
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(extracted), str(target))
        shutil.rmtree(tmp, ignore_errors=True)

    # Sanity: the interpreter runtime_python.py will probe must exist + be executable.
    interp = (target / "python.exe") if platform.system() == "Windows" else (target / "bin" / "python3")
    if not interp.exists():
        raise RuntimeError(f"staged interpreter missing at {interp}")
    if platform.system() != "Windows":
        os.chmod(interp, 0o755)
    print(f"[embed-python] staged {PY_VERSION} → {interp}")


def main() -> int:
    try:
        _stage()
        return 0
    except Exception as e:
        msg = f"[embed-python] staging failed: {e}"
        if os.environ.get("ORRIN_REQUIRE_EMBEDDED") == "1":
            print(msg, file=sys.stderr)
            return 1
        print(msg + " — continuing; the sandbox will use the host interpreter (host fallback).")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
