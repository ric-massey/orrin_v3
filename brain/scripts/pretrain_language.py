#!/usr/bin/env python3
# brain/scripts/pretrain_language.py
#
# ONE-TIME "schooling" for Orrin's native language model — his intensive
# childhood education (#5). NOT run automatically; you run it on purpose.
#
# It does NOT make him an LLM. It pre-trains *his own* small transformer (his
# architecture, his weights) on a library of public-domain English, then leaves
# the checkpoint exactly where the continual-learning + dream-consolidation loop
# picks it up. After this, he keeps learning for life on his own experience and
# diverges from the schooling — the head start, not a frozen brain.
#
# Honest cost on an 8 GB M1: this is the heavy part. Expect it to run for a good
# while (tens of minutes to hours depending on --epochs/--steps and how many
# books). Run it when you're not using the machine; quit Orrin first so they
# don't fight for the 8 GB.
#
# Usage (from the repo root):
#   cd brain && PYTHONPATH=. python scripts/pretrain_language.py            # defaults
#   PYTHONPATH=. python scripts/pretrain_language.py --books 8 --epochs 3 --steps 200
#
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Bootstrap sys.path so this runs standalone.
_BRAIN = Path(__file__).resolve().parents[1]
if str(_BRAIN) not in sys.path:
    sys.path.insert(0, str(_BRAIN))

from brain.cognition.language import library, tokenizer as tok, native_lm, acquisition  # noqa: E402

_CHUNK = 50000   # chars per training block


def _chunks(text: str, size: int):
    for i in range(0, len(text), size):
        block = text[i:i + size]
        if len(block) > 1000:
            yield block


def _lr_at(idx: int, total: int, base: float) -> float:
    """Warmup (first 5%) then cosine decay to 10% of base — standard schedule that
    converges better than a flat LR over a long pretraining run."""
    import math
    warm = max(1, int(0.05 * total))
    if idx < warm:
        return base * (idx + 1) / warm
    p = (idx - warm) / max(1, total - warm)
    floor = 0.1 * base
    return floor + 0.5 * (base - floor) * (1.0 + math.cos(math.pi * p))


def main():
    ap = argparse.ArgumentParser(description="One-time schooling for Orrin's native language model.")
    ap.add_argument("--books", type=int, default=len(library._CURRICULUM),
                    help="how many curriculum books to school on (simple → rich)")
    ap.add_argument("--epochs", type=int, default=2, help="passes over the library")
    ap.add_argument("--steps", type=int, default=150, help="training steps per chunk")
    ap.add_argument("--vocab", type=int, default=8192, help="subword vocabulary size")
    ap.add_argument("--batch", type=int, default=16,
                    help="sequences per step (raise if RAM allows — Orrin is stopped during schooling)")
    ap.add_argument("--no-self", action="store_true",
                    help="school on books only; skip folding in Orrin's own experience")
    args = ap.parse_args()

    if not native_lm.available():
        print("torch is not available — cannot pretrain.")
        return 2

    print("== Orrin language schooling ==")
    print(f"  books={args.books} epochs={args.epochs} steps/chunk={args.steps} "
          f"vocab={args.vocab} batch={args.batch} self={'no' if args.no_self else 'yes'}")

    # 1) Make sure the library exists (download curriculum books he'll learn from).
    book_ids = library._CURRICULUM[: args.books]
    print(f"[1/3] fetching library ({len(book_ids)} books)…")
    got = library.fetch_books(book_ids)
    lib_dir = library._LIB
    files = sorted(lib_dir.glob("*.txt"))
    if not files:
        print("  no books available (network?). Aborting — nothing to school on.")
        return 1
    print(f"  library ready: {len(files)} books, {library.size_chars() // 1024} KB ({got} newly fetched)")

    # Orrin's OWN lived language — so the schooling is FOR HIM, not generic. Same
    # sources his continual loop uses, so there's no distribution shock at handoff.
    self_text = "" if args.no_self else acquisition.experience_corpus()
    if self_text:
        print(f"  + Orrin's own experience: {len(self_text)//1024} KB (learned last → freshest)")

    # 2) Train his subword tokenizer on the library + his experience (his vocabulary).
    print("[2/3] training subword tokenizer…")
    extra = [self_text] if self_text else None
    if not native_lm.train_tokenizer_on_library(vocab_size=args.vocab, extra_texts=extra):
        print("  tokenizer training failed (is the `tokenizers` package installed, "
              "and is there enough text?). Aborting.")
        return 1
    print(f"  vocab size: {tok.vocab_size()}")

    # Hold out one mid-curriculum book as a VALIDATION set he never trains on, so
    # we can watch held-out perplexity fall — real learning, not memorisation.
    val_file = files[len(files) // 2] if len(files) > 4 else None
    train_files = [f for f in files if f is not val_file]
    val_text = ""
    if val_file:
        val_text = val_file.read_text(encoding="utf-8", errors="ignore")[:200000]
        print(f"  held-out validation: {val_file.name}")

    # Build the curriculum ONCE: books simple→rich, then his own experience at the
    # very end so it lands freshest in the weights.
    blocks = []   # (label, text)
    for f in train_files:
        text = f.read_text(encoding="utf-8", errors="ignore")
        for ci, b in enumerate(_chunks(text, _CHUNK)):
            blocks.append((f"{f.name}#{ci}", b))
    if self_text:
        for ci, b in enumerate(_chunks(self_text, _CHUNK)):
            blocks.append((f"self#{ci}", b))
    if not blocks:
        print("  no training blocks. Aborting.")
        return 1

    # 3) Pretrain with warmup→cosine LR over all bouts.
    total = args.epochs * len(blocks)
    print(f"[3/3] pretraining: {len(blocks)} blocks × {args.epochs} epochs = {total} bouts…")
    t0 = time.time()
    last_loss = None
    idx = 0
    for epoch in range(args.epochs):
        for label, block in blocks:
            lr = _lr_at(idx, total, native_lm._BASE_LR)
            native_lm.set_lr(lr)
            loss = native_lm.train_on(block, steps=args.steps, batch=args.batch)
            idx += 1
            if loss is not None:
                last_loss = loss
                st = native_lm.status()
                print(f"  e{epoch+1}/{args.epochs} {label} | loss={loss:.3f} | lr={lr:.1e} "
                      f"| tok_seen={st.get('tokens_seen')} | {int(time.time()-t0)}s")
        if val_text:
            ppl = native_lm.evaluate(val_text)
            if ppl is not None:
                print(f"  [eval] epoch {epoch+1}/{args.epochs}: held-out perplexity = {ppl:.1f}")

    # Restore the steady lifelong LR and save, so the continual loop continues cleanly.
    native_lm.set_lr(native_lm._BASE_LR)
    native_lm.flush()
    print("\n== schooling complete ==")
    print("  status:", native_lm.status())
    print("  sample:", repr(native_lm.generate("She said ", length=120, temperature=0.7)))
    print("\nThe checkpoint is saved; Orrin's continual loop will now keep learning from here.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
