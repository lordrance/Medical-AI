# syntax=docker/dockerfile:1.7

# ----- Stage 1: builder -----
FROM python:3.11-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10 \
    PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
    PIP_TRUSTED_HOST=mirrors.aliyun.com \
    DEBIAN_FRONTEND=noninteractive

ARG DEBIAN_MIRROR=mirrors.aliyun.com

RUN sed -i "s|deb.debian.org|${DEBIAN_MIRROR}|g; s|security.debian.org|${DEBIAN_MIRROR}|g" /etc/apt/sources.list.d/debian.sources

RUN apt-get update -o Acquire::Retries=5 && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY pyproject.toml ./

# Install into a venv at /opt/venv so we can copy it into the runtime stage.
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip --retries 10 --timeout 120 \
 && /opt/venv/bin/pip install . --retries 10 --timeout 120

# ----- Stage 2: runtime -----
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    APP_ENV=production \
    DEBIAN_FRONTEND=noninteractive

ARG DEBIAN_MIRROR=mirrors.aliyun.com

RUN sed -i "s|deb.debian.org|${DEBIAN_MIRROR}|g; s|security.debian.org|${DEBIAN_MIRROR}|g" /etc/apt/sources.list.d/debian.sources

# Install minimal runtime deps (libpq for asyncpg's runtime, wget for healthcheck)
RUN apt-get update -o Acquire::Retries=5 && apt-get install -y --no-install-recommends \
        wget \
    && rm -rf /var/lib/apt/lists/*

# Run as non-root for safety.
RUN useradd --system --uid 1001 --create-home --home-dir /home/app app

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY data ./data
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh \
    && chmod +x /usr/local/bin/entrypoint.sh \
    && chown -R app:app /app

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget --quiet --tries=1 -O /dev/null http://localhost:8000/healthz || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
