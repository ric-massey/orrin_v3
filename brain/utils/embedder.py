import os
# Use locally-cached models only — never block on a network HEAD check to
# huggingface (which fails offline and spams the log). The models we use
# (all-mpnet-base-v2 here, all-MiniLM-L6-v2 in memory/) are already cached.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from typing import Union, List
from sentence_transformers import SentenceTransformer

_model = None

def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        # CPU-pinned: MPS auto-select deadlocks when called from the brain thread.
        _model = SentenceTransformer('all-mpnet-base-v2', device="cpu")
    return _model

def get_embedding(texts: Union[str, List[str]], normalize: bool = True):
    """
    Takes a string or list of strings and returns their embeddings.
    If normalize=True, embeddings are L2-normalized (better for cosine similarity).
    Returns a single vector if input is a string.
    """
    model = get_model()
    is_single = isinstance(texts, str)
    if is_single:
        texts = [texts]

    embeddings = model.encode(
        texts,
        normalize_embeddings=normalize,
        show_progress_bar=False
    )
    return embeddings[0] if is_single else embeddings