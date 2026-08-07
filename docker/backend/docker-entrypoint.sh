#!/bin/sh
set -eu

HOST="${BACKEND_HOST:-0.0.0.0}"
PORT="$(python -c 'from backend.app.config import resolve_backend_listen_port; print(resolve_backend_listen_port())')"
ROLE="$(python -c 'from backend.app.config import load_backend_role; print(load_backend_role())')"

if [ "${ROLE}" = "worker" ]; then
  exec uvicorn backend.app.worker:app --host "$HOST" --port "$PORT"
fi

exec uvicorn backend.app.main:app --host "$HOST" --port "$PORT"
