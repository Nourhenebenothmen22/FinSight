# FinSight Backend - Multi-stage Dockerfile
# Target: development (default), production

# -----------------------------------------------------------------------------
# Base stage - common dependencies
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user (UID/GID 1000 for smooth local bind mounts)
RUN groupadd -g 1000 -r finsight && useradd -u 1000 -r -g finsight -d /app -s /bin/bash finsight

WORKDIR /app

# -----------------------------------------------------------------------------
# Development stage - with hot reload and dev tools
# -----------------------------------------------------------------------------
FROM base AS development

# Install Python dependencies
COPY pyproject.toml ./
COPY app ./app
RUN pip install -e ".[dev]"

# Copy remaining source code
COPY --chown=finsight:finsight . .

# Switch to non-root user
USER finsight

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health/live || exit 1

# Default command with hot reload
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# -----------------------------------------------------------------------------
# Production stage - optimized, no dev dependencies
# -----------------------------------------------------------------------------
FROM base AS production

# Install production dependencies and package
COPY pyproject.toml ./
COPY app ./app
RUN pip install .

# Copy migrations and config
COPY --chown=finsight:finsight alembic.ini ./
COPY --chown=finsight:finsight alembic ./alembic

# Switch to non-root user
USER finsight

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health/live || exit 1

# Production command (no reload, multiple workers)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
