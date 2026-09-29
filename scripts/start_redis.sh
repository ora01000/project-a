#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${REDIS_CONTAINER_NAME:-project-a-redis}"
IMAGE="${REDIS_IMAGE:-redis:7-alpine}"
HOST_PORT="${REDIS_HOST_PORT:-6379}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker 가 필요합니다." >&2
  exit 1
fi

if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  echo "기존 Redis 컨테이너 재시작: $CONTAINER_NAME"
  docker rm -f "$CONTAINER_NAME" >/dev/null
fi

docker run -d \
  --name "$CONTAINER_NAME" \
  -p "${HOST_PORT}:6379" \
  "$IMAGE"

echo "Redis 기동 완료: localhost:${HOST_PORT} (container=$CONTAINER_NAME)"
