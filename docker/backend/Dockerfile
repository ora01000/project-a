FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl jq tzdata vim-tiny librsvg2-bin fontconfig fonts-noto-cjk \
    && curl -fsSL -o /tmp/d2.tar.gz "https://github.com/d2lang/d2/releases/download/v0.7.1/d2-v0.7.1-linux-amd64.tar.gz" \
    && tar -xzf /tmp/d2.tar.gz -C /tmp \
    && mv /tmp/d2-v0.7.1/bin/d2 /usr/local/bin/d2 \
    && chmod +x /usr/local/bin/d2 \
    && rm -rf /tmp/d2-v0.7.1 /tmp/d2.tar.gz \
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
COPY docs/system-prompt ./docs/system-prompt
COPY docs/skill ./docs/skill
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
