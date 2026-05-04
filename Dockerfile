FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS base

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev --no-editable \
    && chmod +x /app/docker-entrypoint.sh

RUN groupadd --system app && useradd --system --gid app app \
    && chown -R app:app /app
USER app

ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["/app/docker-entrypoint.sh"]

# ---------------------------------------------------------------------------
# S3 target -- production image with boto3 for S3 offload.
# Build with:  docker build --target s3 -t stateful-indecision:s3 .
# ---------------------------------------------------------------------------
FROM base AS s3
USER root
RUN uv sync --frozen --no-dev --extra s3 --no-editable
RUN chown -R app:app /app
USER app

# ---------------------------------------------------------------------------
# Dev target -- includes pytest and other dev dependencies.
# Build with:  docker build --target dev -t stateful-indecision:dev .
# ---------------------------------------------------------------------------
FROM base AS dev
USER root
RUN uv sync --frozen
RUN chown -R app:app /app
USER app
