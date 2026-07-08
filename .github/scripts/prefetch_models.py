#!/usr/bin/env python3
"""Prefetch the MiniLM sentence-embedding model for CI.

The test suite's selector-characterization goldens are captured with the
embedder available (the real-runtime path). MiniLM is downloaded from the
HuggingFace Hub on first use; unauthenticated CI IPs are aggressively
rate-limited, and `brain/utils/embed_similarity` latches its failure flag on the
first exception for the rest of the process — which silently degrades capability
matching to keyword-only and flips pinned decisions.

Fetching the model here (cached across runs via actions/cache), with retries and
backoff, makes the embedder reliably present before pytest starts. It is a
best-effort warmup: if every attempt is rate-limited we exit 0 rather than fail
the build, and the suite runs in fallback mode as it would locally.
"""
from __future__ import annotations

import sys
import time

_MODEL = "all-MiniLM-L6-v2"
_ATTEMPTS = 5


def main() -> int:
    try:
        from sentence_transformers import SentenceTransformer
    except Exception as exc:  # pragma: no cover - CI install issue
        print(f"prefetch: sentence-transformers unavailable ({exc}); skipping")
        return 0

    for attempt in range(1, _ATTEMPTS + 1):
        try:
            SentenceTransformer(_MODEL, device="cpu")
            print(f"prefetch: {_MODEL} ready (attempt {attempt})")
            return 0
        except Exception as exc:
            wait = 2 ** attempt
            print(f"prefetch: attempt {attempt}/{_ATTEMPTS} failed ({exc}); retrying in {wait}s")
            time.sleep(wait)

    print("prefetch: could not fetch model after retries; suite will run in fallback mode")
    return 0


if __name__ == "__main__":
    sys.exit(main())
