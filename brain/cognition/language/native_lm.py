# brain/cognition/language/native_lm.py
#
# Orrin's NATIVE language faculty — grown from his own experience. Not an LLM.
#
# A small decoder-only TRANSFORMER (nanoGPT-style) over a subword vocabulary. It
# learns language by predicting the next token of everything he reads, thinks,
# and is told, and keeps learning for life — consolidating during sleep with
# replay so new learning doesn't erase old (complementary learning systems).
#
# Transformer + subword (vs the earlier byte-GRU) makes acquisition far more
# data-efficient: he learns words and structure much faster from the same
# reading. Small enough for an 8 GB M1. Starts as noise; becomes word-like as his
# experience accumulates. Honest: still data-bound — this is the developing
# organ, fed by the library (#1) and, optionally, a one-time schooling (pretrain).
from __future__ import annotations

import functools
import threading
import time
from pathlib import Path
from typing import Dict, Optional

from brain.utils.log import log_private
from brain.cognition.language import tokenizer as tok

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    _TORCH = True
except Exception:
    _TORCH = False

_DIR = Path(__file__).resolve().parents[2] / "data" / "language"
_CKPT = _DIR / "native_lm.pt"

# Architecture (small for 8 GB M1; ~8-9M params).
_N_EMBD = 256
_N_HEAD = 4
_N_LAYER = 4
_BLOCK = 128
_DROPOUT = 0.1
_BASE_LR = 3e-4   # steady lifelong-learning rate; pretraining may schedule around it

_model = None
_opt = None
_device = "cpu"
_vocab = 0
_meta: Dict = {"steps": 0, "tokens_seen": 0, "born": None}

# Checkpoint write throttle: the model+optimizer is ~50 MB, so saving every bout
# (the idle loop runs often) is needless disk churn. Save at most this often;
# call flush() to force a save at the end of a pretraining run.
_SAVE_INTERVAL_S = 90.0
_last_save = 0.0

# The model/optimizer are a single shared global, but train_on() (learning bouts,
# from acquisition) and generate()/evaluate() (inference, from voice) are reached
# from different points in the cognitive cycle and can run on different threads. A
# learning bout's loss.backward() needs the weights at the version they had during
# its forward pass; if an overlapping call runs _opt.step() (an in-place weight
# update — and head.weight is tied to tok.weight, a strided view) or flips train/
# eval mode mid-bout, the pending graph is corrupted. That surfaced once in the
# wild as: "a variable needed for gradient computation has been modified by an
# inplace operation … AsStridedBackward0, version 170". Serialize every entry point
# that touches _model/_opt so training and inference can never interleave.
_MODEL_LOCK = threading.Lock()


def _locked(fn):
    """Serialize a native-LM entry point on _MODEL_LOCK (see note above)."""
    @functools.wraps(fn)
    def _w(*a, **k):
        with _MODEL_LOCK:
            return fn(*a, **k)
    return _w


def available() -> bool:
    return _TORCH


# ── model ─────────────────────────────────────────────────────────────────────
def _build(vocab: int):
    class Block(nn.Module):
        def __init__(self):
            super().__init__()
            self.ln1 = nn.LayerNorm(_N_EMBD)
            self.attn = nn.MultiheadAttention(_N_EMBD, _N_HEAD, dropout=_DROPOUT, batch_first=True)
            self.ln2 = nn.LayerNorm(_N_EMBD)
            self.mlp = nn.Sequential(
                nn.Linear(_N_EMBD, 4 * _N_EMBD), nn.GELU(),
                nn.Linear(4 * _N_EMBD, _N_EMBD), nn.Dropout(_DROPOUT),
            )

        def forward(self, x, mask):
            T = x.size(1)
            h = self.ln1(x)
            a, _ = self.attn(h, h, h, attn_mask=mask[:T, :T], need_weights=False)
            x = x + a
            return x + self.mlp(self.ln2(x))

    class GPT(nn.Module):
        def __init__(self):
            super().__init__()
            self.tok = nn.Embedding(vocab, _N_EMBD)
            self.pos = nn.Embedding(_BLOCK, _N_EMBD)
            self.drop = nn.Dropout(_DROPOUT)
            self.blocks = nn.ModuleList([Block() for _ in range(_N_LAYER)])
            self.lnf = nn.LayerNorm(_N_EMBD)
            self.head = nn.Linear(_N_EMBD, vocab, bias=False)
            self.head.weight = self.tok.weight  # weight tying: fewer params, better small-LM data-efficiency
            mask = torch.triu(torch.full((_BLOCK, _BLOCK), float("-inf")), diagonal=1)
            self.register_buffer("mask", mask)

        def forward(self, idx):
            T = idx.size(1)
            pos = torch.arange(T, device=idx.device)
            x = self.drop(self.tok(idx) + self.pos(pos)[None, :, :])
            for b in self.blocks:
                x = b(x, self.mask)
            return self.head(self.lnf(x))
    return GPT()


def _ensure() -> bool:
    """Build/load the model once a tokenizer exists. Returns False if no tokenizer
    (caller must seed one from a corpus first)."""
    global _model, _opt, _device, _vocab, _meta
    if not _TORCH:
        return False
    if _model is not None:
        return True
    v = tok.vocab_size()
    if v <= 0:
        return False  # no tokenizer yet — can't tie the model's vocabulary
    try:
        # MPS deadlocks when torch is entered from the brain's background
        # thread (synchronous Metal dispatch never returns). Run on CPU —
        # the native LM is small enough that CPU is fast and thread-safe.
        _device = "cpu"
        _DIR.mkdir(parents=True, exist_ok=True)
        _vocab = v
        _model = _build(v).to(_device)
        _opt = torch.optim.AdamW(_model.parameters(), lr=_BASE_LR)
        if _CKPT.exists():
            try:
                sd = torch.load(_CKPT, map_location=_device)
                if int(sd.get("vocab", -1)) == v:   # only load if vocab matches
                    _model.load_state_dict(sd["model"])
                    _opt.load_state_dict(sd["opt"])
                    _meta = sd.get("meta", _meta)
                else:
                    log_private("[native_lm] vocab changed — starting model fresh")
            except Exception as e:
                log_private(f"[native_lm] checkpoint load failed, fresh start: {e}")
        if not _meta.get("born"):
            _meta["born"] = time.time()
        return True
    except Exception as e:
        log_private(f"[native_lm] init failed: {e}")
        return False


def _save(force: bool = False):
    """Persist the checkpoint, throttled so frequent idle bouts don't thrash the
    disk. `force=True` always writes (use at end of a pretraining run)."""
    global _last_save
    now = time.time()
    if not force and (now - _last_save) < _SAVE_INTERVAL_S:
        return
    try:
        torch.save({"model": _model.state_dict(), "opt": _opt.state_dict(),
                    "meta": _meta, "vocab": _vocab}, _CKPT)
        _last_save = now
    except Exception as e:
        log_private(f"[native_lm] save failed: {e}")


def flush() -> None:
    """Force an immediate checkpoint save (e.g., at the end of pretraining)."""
    if _model is not None:
        _save(force=True)


def set_lr(lr: float) -> None:
    """Override the optimizer learning rate (used by pretraining to warm up then
    decay). The continual loop leaves it at _BASE_LR for steady lifelong learning."""
    if _opt is None:
        return
    for g in _opt.param_groups:
        g["lr"] = float(lr)


# ── learning ──────────────────────────────────────────────────────────────────
def train_tokenizer_on_library(vocab_size: int = 8192, min_chars: int = 200000,
                               extra_texts: Optional[list] = None) -> bool:
    """Train the subword vocabulary on the ENTIRE library at once — the right way
    to seed it. A rich, stable corpus yields good merges and far better
    data-efficiency for life, instead of a stunted vocabulary frozen from whatever
    small block happened to be read first. `extra_texts` folds in Orrin's OWN
    experience (his conversations/memories) so his vocabulary is represented too.
    No-op if there isn't enough text."""
    try:
        from brain.cognition.language import library
    except Exception:
        return False
    texts = []
    try:
        for f in sorted(library._LIB.glob("*.txt")):
            try:
                texts.append(f.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                continue
    except Exception:
        return False
    if extra_texts:
        texts += [t for t in extra_texts if isinstance(t, str) and t.strip()]
    if sum(len(t) for t in texts) < min_chars or not texts:
        return False
    ok = tok.train(texts, vocab_size=vocab_size)
    if ok:
        log_private(f"[native_lm] tokenizer trained: vocab={tok.vocab_size()}")
    return ok


def ensure_tokenizer(seed_text: str = "") -> bool:
    """Ensure a tokenizer exists before building the model. Prefer a vocabulary
    learned from the whole library; fall back to the seed text only if the library
    isn't big enough yet."""
    if tok.exists():
        return True
    if train_tokenizer_on_library():
        return True
    if not seed_text or len(seed_text) < 2000:
        return False
    return tok.train([seed_text])


@_locked
def train_on(text: str, steps: int = 60, batch: int = 16) -> Optional[float]:
    """One bout of learning on a block of his experience. Returns avg loss."""
    if not _TORCH or not text:
        return None
    if not ensure_tokenizer(text):
        return None
    if not _ensure():
        return None
    ids = tok.encode(text)
    if len(ids) < _BLOCK + 2:
        return None
    t = torch.tensor(ids, dtype=torch.long)
    _model.train()
    total, n = 0.0, 0
    for _ in range(steps):
        ix = torch.randint(0, len(t) - _BLOCK - 1, (batch,))
        x = torch.stack([t[i:i + _BLOCK] for i in ix]).to(_device)
        y = torch.stack([t[i + 1:i + _BLOCK + 1] for i in ix]).to(_device)
        logits = _model(x)
        loss = F.cross_entropy(logits.reshape(-1, _vocab), y.reshape(-1))
        _opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(_model.parameters(), 1.0)
        _opt.step()
        total += float(loss.item())
        n += 1
    _meta["steps"] = int(_meta.get("steps", 0)) + steps
    _meta["tokens_seen"] = int(_meta.get("tokens_seen", 0)) + len(ids)
    _save()
    return total / max(1, n)


@_locked
def generate(prompt: str = "", length: int = 80, temperature: float = 0.8) -> str:
    """Sample text in his own voice — however crude — from what he's learned."""
    if not _ensure():
        return ""
    _model.eval()
    ids = tok.encode(prompt) if prompt else [0]
    ids = ids[-_BLOCK:]
    with torch.no_grad():
        for _ in range(length):
            x = torch.tensor([ids[-_BLOCK:]], dtype=torch.long, device=_device)
            logits = _model(x)[0, -1] / max(1e-3, temperature)
            p = F.softmax(logits, dim=-1)
            nxt = int(torch.multinomial(p, 1).item())
            ids.append(nxt)
    return tok.decode(ids)


@_locked
def evaluate(text: str, blocks: int = 24, batch: int = 16) -> Optional[float]:
    """Held-out PERPLEXITY: average next-token surprise on text he is NOT training
    on, with no gradient. This is how you tell real language learning from mere
    memorisation — lower is better; ~vocab at random, dropping as he learns."""
    if not _TORCH or not text or not _ensure():
        return None
    ids = tok.encode(text)
    if len(ids) < _BLOCK + 2:
        return None
    import math
    t = torch.tensor(ids, dtype=torch.long)
    _model.eval()
    total, n = 0.0, 0
    with torch.no_grad():
        for _ in range(blocks):
            ix = torch.randint(0, len(t) - _BLOCK - 1, (batch,))
            x = torch.stack([t[i:i + _BLOCK] for i in ix]).to(_device)
            y = torch.stack([t[i + 1:i + _BLOCK + 1] for i in ix]).to(_device)
            logits = _model(x)
            loss = F.cross_entropy(logits.reshape(-1, _vocab), y.reshape(-1))
            total += float(loss.item())
            n += 1
    avg = total / max(1, n)
    return math.exp(min(20.0, avg))


def status() -> Dict:
    if not _TORCH:
        return {"available": False, "reason": "torch missing"}
    if not tok.exists():
        return {"available": True, "tokenizer": False, "note": "no tokenizer yet (no learning has occurred)"}
    if not _ensure():
        return {"available": True, "ready": False}
    age_h = (time.time() - (_meta.get("born") or time.time())) / 3600.0
    return {
        "available": True,
        "device": _device,
        "vocab": _vocab,
        "params": sum(p.numel() for p in _model.parameters()),
        "train_steps": _meta.get("steps", 0),
        "tokens_seen": _meta.get("tokens_seen", 0),
        "age_hours": round(age_h, 2),
    }
