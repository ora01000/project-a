#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

# Postgres-only branch (dev-axplatform-multi-pod): tags use pgYYMMDD.
DEFAULT_TAG="${IMAGE_TAG:-pg$(date +%y%m%d)}"
BACKEND_IMAGE="${BACKEND_IMAGE:-ora01000/project-a-backend:${DEFAULT_TAG}}"
FRONTEND_IMAGE="${FRONTEND_IMAGE:-ora01000/project-a-frontend:${DEFAULT_TAG}}"
PLATFORMS="${PLATFORMS:-linux/amd64}"
BUILDER_NAME="${BUILDER_NAME:-project-a-multiarch}"
PUSH="${PUSH:-true}"

# Backend image bundles agent prompts/skills/templates/guides from docs/
# (see docker/backend/Dockerfile).
# workflow_template / workflow_front: copy whole directories — md files may be added or renamed freely.
BACKEND_DEPLOY_DIRS=(
  docs/system-prompt
  docs/skill
  docs/workflow_template
  docs/workflow_front
)

# Frontend Vite public assets (copied via COPY frontend/ in docker/frontend/Dockerfile).
FRONTEND_DEPLOY_DIRS=(
  frontend/public/workflow-icons
)

verify_backend_deploy_assets() {
  local missing=()
  for dir in "${BACKEND_DEPLOY_DIRS[@]}"; do
    if [[ ! -d "${ROOT_DIR}/${dir}" ]]; then
      missing+=("${dir}")
    fi
  done
  if [[ ${#missing[@]} -gt 0 ]]; then
    echo "Missing backend deploy directories (required for image COPY):" >&2
    printf '  - %s\n' "${missing[@]}" >&2
    exit 1
  fi
  # Do not pin filenames; any *.md under workflow_template is included by directory COPY.
  if ! compgen -G "${ROOT_DIR}/docs/workflow_template/*.md" > /dev/null; then
    echo "docs/workflow_template has no *.md files (directory is included as a whole at build)" >&2
    exit 1
  fi
  if [[ ! -f "${ROOT_DIR}/docs/workflow_front/workflow_front.md" ]]; then
    echo "docs/workflow_front/workflow_front.md is required for the workflow idle guide API" >&2
    exit 1
  fi
}

verify_frontend_deploy_assets() {
  local missing=()
  for dir in "${FRONTEND_DEPLOY_DIRS[@]}"; do
    if [[ ! -d "${ROOT_DIR}/${dir}" ]]; then
      missing+=("${dir}")
    fi
  done
  if [[ ${#missing[@]} -gt 0 ]]; then
    echo "Missing frontend deploy directories (required for Vite public assets):" >&2
    printf '  - %s\n' "${missing[@]}" >&2
    exit 1
  fi
  if ! compgen -G "${ROOT_DIR}/frontend/public/workflow-icons/*.svg" > /dev/null; then
    echo "frontend/public/workflow-icons has no *.svg files" >&2
    exit 1
  fi
  if ! compgen -G "${ROOT_DIR}/frontend/public/workflow-icons/light/*.svg" > /dev/null; then
    echo "frontend/public/workflow-icons/light has no *.svg files" >&2
    exit 1
  fi
}

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
verify_backend_deploy_assets
verify_frontend_deploy_assets
build_image docker/backend/Dockerfile "${BACKEND_IMAGE}"
build_image docker/frontend/Dockerfile "${FRONTEND_IMAGE}"

echo "==> Done"
echo "    ${BACKEND_IMAGE} (${PLATFORMS})"
echo "    ${FRONTEND_IMAGE} (${PLATFORMS})"
