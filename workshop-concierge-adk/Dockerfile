# Workshop Concierge — Foundry Hosted Agent container (Responses protocol).
#
# The hosting platform requires linux/amd64. Build with:
#   docker build --platform linux/amd64 -t workshop-concierge:dev .
# The Responses protocol library serves /responses and /readiness on port 8088.
FROM python:3.13-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8088

WORKDIR /app

# Install pinned dependencies first for layer caching. The lock is a COMPLETE
# freeze of a validated environment, so install it with --no-deps to reproduce
# that exact set (avoids an unsatisfiable re-resolve between google-adk's
# opentelemetry<=1.42.1 cap and the azure-monitor exporter's ~=1.43 request).
COPY requirements.lock.txt ./
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-deps -r requirements.lock.txt

# App code + version-controlled catalog.
COPY src/ ./src/
COPY catalog/ ./catalog/

ENV PYTHONPATH=/app/src \
    WORKSHOP_CATALOG_DIR=/app/catalog

EXPOSE 8088

# The Responses host binds 0.0.0.0:8088 and exposes /readiness for health checks.
CMD ["python", "-m", "adapter.app"]

# ---- test stage: builds on base and runs the same suite inside the image ----
FROM base AS test
COPY pyproject.toml ./
COPY tests/ ./tests/
RUN pip install "pytest>=8" "pytest-asyncio>=1.0" "httpx"
ENV OTEL_SDK_DISABLED=true
RUN python -m pytest
