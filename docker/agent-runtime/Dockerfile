FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Seoul

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend ./backend
COPY config ./config
COPY RELEASE.md ./RELEASE.md

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH=/app

RUN mkdir -p /app/logs/agents

EXPOSE 8090

CMD ["sh", "-c", "uvicorn backend.app.agent_runtime.main:app --host ${AGENT_RUNTIME_HOST:-0.0.0.0} --port ${AGENT_RUNTIME_PORT:-8090}"]
