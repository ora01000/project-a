FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl jq tzdata vim-tiny \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Seoul \
    AGENT_RUNTIME_MODE=mock

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend ./backend
COPY config ./config
COPY RELEASE.md ./RELEASE.md

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH=/app

# OKD restricted SCC: arbitrary UID with GID 0 must write SQLite/logs under /app/data.
RUN mkdir -p /app/data /app/logs/agents /app/data/user_comm_logs \
    && chgrp -R 0 /app \
    && chmod -R g+rwX /app

EXPOSE 8080

COPY docker/backend/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
