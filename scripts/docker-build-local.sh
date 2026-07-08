#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

arch="$(uname -m)"
case "${arch}" in
  x86_64) platform="linux/amd64" ;;
  aarch64 | arm64) platform="linux/arm64" ;;
  *)
    echo "Unsupported local architecture: ${arch}" >&2
    exit 1
    ;;
esac

export PLATFORMS="${PLATFORMS:-${platform}}"
export PUSH=false

exec "${ROOT_DIR}/scripts/docker-build-push.sh" "$@"
