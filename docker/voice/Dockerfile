# =============================================================================
# ZuuSwarm-AI — Voice Worker container
#
# A LiveKit agent worker that joins LiveKit Cloud rooms and runs the voice
# pipeline. No exposed ports — the worker connects *outbound* to LiveKit.
#
# Two stages:
#
#   1. builder  — installs CPU-only PyTorch + requirements.txt into a venv.
#   2. runtime  — slim image with the venv copied in. Runs ``python -m voice.run``.
# =============================================================================

# ── Stage 1 ── build deps ────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build-time native deps (psycopg2 needs libpq + a C compiler). 
# Voice itself doesn't need PortAudio inside the container because 
# the worker streams audio via WebRTC, not a local mic.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build

# CPU-only torch (Silero VAD wants torch). Saves ~2 GB vs the CUDA wheel.
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
    LANGFUSE_PROMPTS=false

# Runtime libs:
#   libpq5      — psycopg2 client (orchestrator hits Supabase via achat)
#   procps      — provides ``pgrep`` for the healthcheck below
#   ca-certs    — for outbound TLS to LiveKit Cloud + Deepgram
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        procps \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

COPY src    ./src
COPY config ./config
COPY .env*  ./

# Liveness probe: is the worker process still alive? The worker has no
# HTTP port to curl — it speaks the LiveKit signaling protocol over a
# persistent websocket. ``pgrep`` confirms the process exists.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD pgrep -f "voice.run" >/dev/null || exit 1

# No EXPOSE — outbound-only worker.

CMD ["python", "-m", "voice.run", "start"]
