#!/usr/bin/env python3
"""
packaging/bundle_models.py — pre-fetch Orrin's ML weights into the bundle layout (I2).

A frozen Orrin must boot with ZERO network (Part 4). Run this ON the build machine
(which DOES have a network) to download the sentence-transformers embedding model and the
spaCy English model into `Resources/models/`, laid out exactly how
`brain/utils/model_assets.py` expects:

    <out>/sentence_transformers/    SENTENCE_TRANSFORMERS_HOME cache (all-mpnet-base-v2)
    <out>/hf/                       HF_HOME cache (anything HF pulls in)
    <out>/spacy/en_core_web_sm/     the loaded spaCy model dir (loaded by PATH)

Then point the freeze at it: `--add-data "<out>:models"` (see orrin.spec), and at runtime
`model_assets.apply_offline_env()` + `spacy_model()` find it and go offline.

Usage:
    python packaging/bundle_models.py [--out packaging/build/models]

Acceptance: after bundling + freezing, the app boots on a machine that never had Python,
Wi-Fi OFF (Part 4).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Keep these in sync with the load sites (embedder.py / embed_similarity.py / knowledge_graph.py).
EMBED_MODEL = "all-mpnet-base-v2"
SPACY_MODEL = "en_core_web_sm"


def bundle(out: Path) -> None:
    st_home = out / "sentence_transformers"
    hf_home = out / "hf"
    spacy_dir = out / "spacy"
    for d in (st_home, hf_home, spacy_dir):
        d.mkdir(parents=True, exist_ok=True)

    # Download the embedding model INTO the bundle cache by pointing the env at it first.
    os.environ["SENTENCE_TRANSFORMERS_HOME"] = str(st_home)
    os.environ["HF_HOME"] = str(hf_home)
    print(f"[bundle] downloading sentence-transformers/{EMBED_MODEL} → {st_home}")
    from sentence_transformers import SentenceTransformer  # type: ignore

    SentenceTransformer(EMBED_MODEL, device="cpu")  # populates the cache

    # spaCy: download the package, then copy its installed model dir into the bundle so
    # it can be loaded by PATH (spacy.load(<path>)) with nothing pip-installed at runtime.
    print(f"[bundle] downloading spaCy/{SPACY_MODEL} → {spacy_dir / SPACY_MODEL}")
    import subprocess

    subprocess.run([sys.executable, "-m", "spacy", "download", SPACY_MODEL], check=True)
    import importlib

    mod = importlib.import_module(SPACY_MODEL)
    src = Path(mod.__file__).resolve().parent
    # The real model data lives in a versioned subdir (e.g. en_core_web_sm-3.7.1).
    model_data = next((p for p in src.iterdir() if p.is_dir() and p.name.startswith(SPACY_MODEL)), src)
    import shutil

    dest = spacy_dir / SPACY_MODEL
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(model_data, dest)
    print(f"[bundle] done — {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Pre-fetch Orrin's ML weights for an offline bundle.")
    ap.add_argument("--out", default="packaging/build/models", help="output models dir")
    args = ap.parse_args()
    bundle(Path(args.out).resolve())


if __name__ == "__main__":
    main()
