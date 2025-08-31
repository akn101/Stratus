# Multi-stage build for Stratus ERP Integration Service
# Optimized for production deployment with non-root user and health checks

# Builder stage
FROM python:3.11-slim as builder

WORKDIR /app

# Install system dependencies for building Python packages
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install poetry==1.7.1

# Configure Poetry: don't create virtual env, install to system Python
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VENV_IN_PROJECT=1 \
    POETRY_CACHE_DIR=/opt/poetry_cache

# Copy dependency definitions
COPY pyproject.toml poetry.lock ./

# Install dependencies (without dev dependencies)
RUN poetry install --only=main --no-root && rm -rf $POETRY_CACHE_DIR

# Production stage
FROM python:3.11-slim as production

# Install runtime system dependencies
RUN apt-get update && apt-get install -y \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user
RUN groupadd --gid 1001 stratus \
    && useradd --uid 1001 --gid stratus --shell /bin/bash --create-home stratus

# Set working directory
WORKDIR /app

# Copy virtual environment from builder stage
COPY --from=builder --chown=stratus:stratus /app/.venv /app/.venv

# Ensure virtual environment is in PATH
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Copy application code
COPY --chown=stratus:stratus . .

# Create required directories
RUN mkdir -p /app/logs /app/config && \
    chown -R stratus:stratus /app

# Switch to non-root user
USER stratus

# Set Python path
ENV PYTHONPATH=/app

# Expose metrics port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/healthz || exit 1

# Default command (can be overridden)
CMD ["python", "main.py"]

# Labels for metadata
LABEL \
    org.opencontainers.image.title="Stratus ERP Integration Service" \
    org.opencontainers.image.description="Production-ready ETL service for ERP integrations" \
    org.opencontainers.image.vendor="Stratus" \
    org.opencontainers.image.version="1.0.0" \
    org.opencontainers.image.source="https://github.com/your-org/stratus-erp"