# =============================================================================
# ZuuSwarm-AI — API container
#
# Three stages:
#
#   1. webbuilder — builds the Vite React SPA so the image is self-contained.
#   2. builder — installs CPU-only PyTorch (saves ~2 GB vs the default CUDA
#      build) plus the rest of requirements.txt into a venv.
#   3. runtime — slim image with the venv copied in, no build tools, no apt
#      cache. Runs ``uvicorn api.main:app`` on port 8000.
# =============================================================================

# ── Stage 0 ── build the React/Vite SPA ──────────────────────────────────────
FROM node:20-slim AS webbuilder
WORKDIR /web
COPY ui/package.json ui/package-lock.json* ./
RUN npm ci || npm install
COPY ui/ ./
RUN npm run build          # → /web/dist


# ── Stage 1 ── build deps ────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build-time native deps (psycopg2 needs libpq + a C compiler at install time).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Use a venv so we can copy a single directory into the runtime stage.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build

# Pre-install CPU-only torch first. sentence-transformers depends on torch;
# resolving it later would otherwise pull the full CUDA wheel (~2 GB).
RUN pip install --upgrade pip wheel \
 && pip install --index-url https://download.pytorch.org/whl/cpu \
        torch torchvision torchaudio

COPY requirements.txt ./
RUN pip install -r requirements.txt


# ── Stage 2 ── runtime ──────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    PATH="/opt/venv/bin:$PATH" \
    HF_HOME=/root/.cache/huggingface \
    TRANSFORMERS_CACHE=/root/.cache/huggingface/transformers \
    SENTENCE_TRANSFORMERS_HOME=/root/.cache/huggingface/sentence_transformers \
    LANGFUSE_PROMPTS=false

# Runtime needs only libpq (psycopg2 client) and curl (healthcheck).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy the prebuilt venv from the builder.
COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

# Application code only — no tests/notebooks/data baked into the image.
COPY src    ./src
COPY config ./config
COPY .env*  ./

# The compiled SPA from Stage 0. FastAPI serves it at / (see api/main.py:
# StaticFiles mount). Lives at /app/ui_dist so main.py can resolve it as 
# parents[2]/ui_dist relative to src/api/main.py.
COPY --from=webbuilder /web/dist ./ui_dist

# Quick liveness check; lifespan warmup can take 30-60 s on a cold start
# while the local sentence-transformers model loads, so give it a buffer.
HEALTHCHECK --interval=30s --timeout=5s --start-period=600s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/v1/health || exit 1

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
