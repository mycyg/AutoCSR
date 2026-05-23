# syntax=docker/dockerfile:1.6
# AutoCSR backend — multi-stage build.
#
#   stage 1 (builder) — install backend wheels into a venv at /opt/venv
#   stage 2 (runtime) — slim image carrying only the venv + app source
#
# Build:   docker build -t autocsr-backend ./backend
# Run:     docker run -p 8766:8766 -e LLM_API_KEY=$LLM_API_KEY autocsr-backend
# Compose: docker compose up backend
# ---------------------------------------------------------------------------

ARG PYTHON_VERSION=3.11

# ------------------------------ builder ------------------------------------
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps required to compile a few wheels (lifelines, scipy, pymupdf).
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      gcc \
      g++ \
      libffi-dev \
      libssl-dev \
      libxml2-dev \
      libxslt1-dev \
      pkg-config \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build

COPY pyproject.toml ./
COPY app ./app

RUN pip install --upgrade pip wheel setuptools && \
    pip install -e ".[queue]"

# ------------------------------ runtime ------------------------------------
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    AUTOCSR_HOME=/app

# Runtime libraries (no compilers) — keeps image small.
RUN apt-get update && apt-get install -y --no-install-recommends \
      libxml2 \
      libxslt1.1 \
      libgomp1 \
      fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 autocsr

COPY --from=builder /opt/venv /opt/venv

WORKDIR ${AUTOCSR_HOME}
COPY --chown=autocsr:autocsr pyproject.toml ./
COPY --chown=autocsr:autocsr app ./app
COPY --chown=autocsr:autocsr tests ./tests

# Data dir must be writable + persisted via volume mount.
RUN mkdir -p /app/data && chown -R autocsr:autocsr /app

USER autocsr

EXPOSE 8766

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8766/api/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "app.server.main:app", "--host", "0.0.0.0", "--port", "8766"]
