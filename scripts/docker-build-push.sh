#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

BACKEND_IMAGE="${BACKEND_IMAGE:-ora01000/project-a-backend:260710}"
FRONTEND_IMAGE="${FRONTEND_IMAGE:-ora01000/project-a-frontend:260710}"
PLATFORMS="${PLATFORMS:-linux/amd64,linux/arm64}"
BUILDER_NAME="${BUILDER_NAME:-project-a-multiarch}"
PUSH="${PUSH:-true}"

ensure_builder() {
  if ! docker buildx inspect "${BUILDER_NAME}" >/dev/null 2>&1; then
    echo "==> Creating buildx builder: ${BUILDER_NAME}"
    docker buildx create --name "${BUILDER_NAME}" --driver docker-container --use
  else
    docker buildx use "${BUILDER_NAME}"
  fi

  docker buildx inspect --bootstrap >/dev/null
}

build_image() {
  local dockerfile="$1"
  local image="$2"
  local output_flag=()

  if [[ "${PUSH}" == "true" ]]; then
    output_flag=(--push)
    echo "==> Building and pushing (${PLATFORMS}): ${image}"
  else
    if [[ "${PLATFORMS}" == *,* ]]; then
      echo "Local load supports only one platform. Set PLATFORMS=linux/amd64 or linux/arm64." >&2
      exit 1
    fi
    output_flag=(--load)
    echo "==> Building local image (${PLATFORMS}): ${image}"
  fi

  docker buildx build \
    --platform "${PLATFORMS}" \
    -f "${dockerfile}" \
    -t "${image}" \
    "${output_flag[@]}" \
    .
}

ensure_builder
build_image docker/backend/Dockerfile "${BACKEND_IMAGE}"
build_image docker/frontend/Dockerfile "${FRONTEND_IMAGE}"

echo "==> Done"
echo "    ${BACKEND_IMAGE} (${PLATFORMS})"
echo "    ${FRONTEND_IMAGE} (${PLATFORMS})"
