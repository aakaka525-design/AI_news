# Stage 1: Build
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt psycopg2-binary

# Stage 2: Runtime
FROM python:3.12-slim

WORKDIR /app

# Only runtime deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 && \
    rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Project code
COPY src/ src/
COPY api/ api/
COPY fetchers/ fetchers/
COPY config/ config/
COPY alembic.ini ./
COPY alembic/ alembic/
COPY docker/entrypoint.sh ./
COPY rss_fetcher.py run.py ./

RUN chmod +x entrypoint.sh

# Non-root user
RUN useradd -m -r appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["./entrypoint.sh"]
