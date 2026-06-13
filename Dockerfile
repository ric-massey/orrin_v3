# Orrin — full-stack image: the symbolic brain + daemons + telemetry backend
# + the Vite "Face & Brain" UI, all in one container so `docker compose up` shows
# the running system end-to-end.
#
# Two non-obvious things this image handles for you:
#   1. The UI is a Vite dev server (Node), which main.py spawns as a child process,
#      so the image needs BOTH Python and Node.
#   2. The embedding layer runs offline (HF_HUB_OFFLINE=1), so the models are
#      pre-downloaded at build time into the Hugging Face cache. A fresh container
#      that tried to fetch them at runtime would fail.
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # Pin the Hugging Face cache to an explicit path so the models pre-downloaded
    # at build time are exactly where the offline runtime (HF_HUB_OFFLINE=1) looks.
    HF_HOME=/opt/hf-cache

# --- System deps: Node.js 20 (for the Vite UI) + a few essentials ---
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg git \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- Python deps ---
# Install the CPU-only Torch wheel first so sentence-transformers reuses it instead
# of pulling the ~2 GB CUDA build. Then the brain (root) + backend requirements.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt ./
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r backend/requirements.txt

# --- Pre-cache the embedding models for offline runtime ---
# Brain uses all-mpnet-base-v2; similarity + memory daemon use all-MiniLM-L6-v2.
# NB: a single-line `python -c` (not a heredoc) so this works on both the classic
# Docker builder and BuildKit — the classic builder silently ignores heredocs.
RUN python -c "from sentence_transformers import SentenceTransformer; [SentenceTransformer(m, device='cpu') for m in ('all-mpnet-base-v2', 'all-MiniLM-L6-v2')]"

# Optional: spaCy language model (regex fallback if absent). `|| true` keeps the
# build green on a transient download hiccup — Orrin still runs without it.
RUN python -m spacy download en_core_web_sm || true

# --- Frontend deps (baked in so `npm run dev` works without mounting node_modules) ---
COPY frontend/package*.json ./frontend/
RUN cd frontend && npm install

# --- App source ---
COPY . .

# UI (5173), telemetry API + WebSocket (8800), Prometheus metrics (9100)
EXPOSE 5173 8800 9100

# Bind to all interfaces so the host can reach the container; don't try to open a
# browser from inside the container (you open http://localhost:5173 yourself).
ENV ORRIN_BACKEND_HOST=0.0.0.0 \
    ORRIN_UI=1 \
    ORRIN_UI_OPEN=0

CMD ["python", "main.py"]
