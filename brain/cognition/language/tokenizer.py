# brain/cognition/language/tokenizer.py
#
# Orrin's subword tokenizer — the unit of his language.
#
# Byte-level was honest but slow: he had to learn spelling before words. A
# byte-level BPE tokenizer lets him learn in word-ish pieces, so meaning forms
# far faster from the same amount of reading — while still handling ANY text
# (unseen words fall back to sub-pieces), so it never breaks on something new.
#
# Trained ONCE from whatever corpus is available (his experience, or the library
# during pretraining), then frozen — the model's vocabulary is tied to it.
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

_PATH = Path(__file__).resolve().parents[2] / "data" / "language" / "tokenizer.json"
_VOCAB_SIZE = 8192

_tok = None


def _try_import():
    try:
        from tokenizers import Tokenizer, models, trainers, pre_tokenizers, decoders
        return Tokenizer, models, trainers, pre_tokenizers, decoders
    except Exception:
        return None


def exists() -> bool:
    return _PATH.exists()


def get():
    """Return the loaded tokenizer, or None if not trained yet."""
    global _tok
    if _tok is not None:
        return _tok
    if not _PATH.exists():
        return None
    imp = _try_import()
    if not imp:
        return None
    Tokenizer = imp[0]
    try:
        _tok = Tokenizer.from_file(str(_PATH))
        return _tok
    except Exception:
        return None


def train(text_iter: Iterable[str], vocab_size: int = _VOCAB_SIZE) -> bool:
    """Train a byte-level BPE tokenizer on a corpus and persist it. One-time."""
    imp = _try_import()
    if not imp:
        return False
    Tokenizer, models, trainers, pre_tokenizers, decoders = imp
    try:
        tok = Tokenizer(models.BPE(unk_token="<unk>"))
        tok.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=True)
        tok.decoder = decoders.ByteLevel()
        trainer = trainers.BpeTrainer(
            vocab_size=vocab_size,
            special_tokens=["<pad>", "<unk>", "<eos>"],
            min_frequency=2,
        )
        tok.train_from_iterator(text_iter, trainer)
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        tok.save(str(_PATH))
        global _tok
        _tok = tok
        return True
    except Exception:
        return False


def vocab_size() -> int:
    t = get()
    return t.get_vocab_size() if t is not None else 0


def encode(text: str):
    t = get()
    return t.encode(text).ids if t is not None else []


def decode(ids) -> str:
    t = get()
    return t.decode(list(ids)) if t is not None else ""
