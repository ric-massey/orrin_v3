# Orrin — full-stack image: the symbolic brain + daemons + telemetry backend, which
# also serves the built "Face & Brain" SPA as static files on a single port. No Vite
# dev server and no Node at runtime (CODEBASE_CLEANUP_PLAN Phase 2): the frontend is
# compiled to static assets in a build stage and served by the FastAPI backend
# (backend/server/app.py mounts the dist at "/").
#
# The embedding layer runs offline (HF_HUB_OFFLINE=1), so the models are
# pre-downloaded at build time into the Hugging Face cache. A fresh container that
# tried to fetch them at runtime would fail.

# ── Stage 1: build the frontend into static assets ───────────────────────────
FROM node:20-slim AS ui-build
WORKDIR /ui
# Install deps against the lockfile first (cache-friendly), then build.
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
# `npm run build` = tsc --noEmit && vite build → ./dist (host-agnostic; the SPA
# talks to its own origin, so no backend host is baked in).
RUN npm run build

# ── Stage 2: python runtime that serves brain + API + static UI ───────────────
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # Pin the Hugging Face cache to an explicit path so the models pre-downloaded
    # at build time are exactly where the offline runtime (HF_HUB_OFFLINE=1) looks.
    HF_HOME=/opt/hf-cache

# Minimal system deps (no Node — the UI is prebuilt in stage 1).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git \
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
RUN python -c "from sentence_transformers import SentenceTransformer; [SentenceTransformer(m, device='cpu') for m in ('all-mpnet-base-v2', 'all-MiniLM-L6-v2')]"

# Optional: spaCy language model (regex fallback if absent). `|| true` keeps the
# build green on a transient download hiccup — Orrin still runs without it.
RUN python -m spacy download en_core_web_sm || true

# --- App source + the prebuilt UI from stage 1 ---
COPY . .
COPY --from=ui-build /ui/dist ./frontend/dist

# Telemetry API + WebSocket + static UI (8800), Prometheus metrics (9100).
EXPOSE 8800 9100

# Headless server: serve the static UI + API on one port, bind all interfaces, and
# do NOT open a browser. With ORRIN_UI_DEV unset, main.py takes the static-serve
# path (no Vite/native window): the backend serves the SPA from ./frontend/dist.
ENV ORRIN_BACKEND_HOST=0.0.0.0 \
    ORRIN_BACKEND_PORT=8800 \
    ORRIN_UI=1 \
    ORRIN_UI_OPEN=0 \
    HF_HUB_OFFLINE=1

CMD ["python", "main.py"]
