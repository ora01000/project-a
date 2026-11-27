#!/usr/bin/env bash
# Local API boot. Users-field crypto keys live in SECRET.md (gitignored), not in the DB.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SECRET_FILE="${SECRET_FILE:-$ROOT/SECRET.md}"
CRYPTO_SECTION_HEADER="## users field crypto (local)"

_gen_key() {
  # 32-byte key as standard base64 (AES-256).
  openssl rand -base64 32 | tr -d '\n'
}

_secret_get() {
  local key="$1"
  if [[ ! -f "$SECRET_FILE" ]]; then
    return 1
  fi
  # Prefer the crypto section; fall back to any KEY=value line in the file.
  awk -v key="$key" -v hdr="$CRYPTO_SECTION_HEADER" '
    $0 == hdr { in_sec=1; next }
    in_sec && /^## / { in_sec=0 }
    in_sec && $0 ~ ("^" key "=") {
      sub("^" key "=", "")
      print
      found=1
      exit
    }
    END { if (!found) exit 1 }
  ' "$SECRET_FILE" 2>/dev/null || \
  awk -v key="$key" '
    $0 ~ ("^" key "=") {
      sub("^" key "=", "")
      print
      found=1
      exit
    }
    END { if (!found) exit 1 }
  ' "$SECRET_FILE" 2>/dev/null
}

_ensure_crypto_keys() {
  local backend kek blind version
  backend="${USERS_FIELD_CRYPTO_BACKEND:-env}"
  version="${USERS_FIELD_KEY_VERSION:-1}"

  kek="${USERS_FIELD_KEK:-}"
  if [[ -z "$kek" ]]; then
    kek="$(_secret_get USERS_FIELD_KEK || true)"
  fi
  blind="${USERS_FIELD_BLIND_KEY:-}"
  if [[ -z "$blind" ]]; then
    blind="$(_secret_get USERS_FIELD_BLIND_KEY || true)"
  fi

  local created=0
  if [[ -z "$kek" ]]; then
    kek="$(_gen_key)"
    created=1
  fi
  if [[ -z "$blind" ]]; then
    blind="$(_gen_key)"
    created=1
  fi

  if [[ "$created" -eq 1 ]]; then
    mkdir -p "$(dirname "$SECRET_FILE")"
    touch "$SECRET_FILE"
    if grep -qxF "$CRYPTO_SECTION_HEADER" "$SECRET_FILE" 2>/dev/null; then
      # Replace existing crypto section body (until next ## or EOF).
      local tmp
      tmp="$(mktemp)"
      awk -v hdr="$CRYPTO_SECTION_HEADER" \
          -v backend="$backend" -v kek="$kek" -v blind="$blind" -v version="$version" '
        $0 == hdr {
          print hdr
          print ""
          print "로컬 `./scripts/start_backend.sh` 가 없으면 생성·주입한다. DB에 넣지 말 것."
          print ""
          print "USERS_FIELD_CRYPTO_BACKEND=" backend
          print "USERS_FIELD_KEK=" kek
          print "USERS_FIELD_BLIND_KEY=" blind
          print "USERS_FIELD_KEY_VERSION=" version
          skip=1
          next
        }
        skip && /^## / { skip=0 }
        !skip { print }
      ' "$SECRET_FILE" >"$tmp"
      mv "$tmp" "$SECRET_FILE"
    else
      {
        echo ""
        echo "$CRYPTO_SECTION_HEADER"
        echo ""
        echo "로컬 \`./scripts/start_backend.sh\` 가 없으면 생성·주입한다. DB에 넣지 말 것."
        echo ""
        echo "USERS_FIELD_CRYPTO_BACKEND=$backend"
        echo "USERS_FIELD_KEK=$kek"
        echo "USERS_FIELD_BLIND_KEY=$blind"
        echo "USERS_FIELD_KEY_VERSION=$version"
      } >>"$SECRET_FILE"
    fi
    echo "[start_backend] users field crypto keys written to $SECRET_FILE" >&2
  fi

  export USERS_FIELD_CRYPTO_BACKEND="$backend"
  export USERS_FIELD_KEK="$kek"
  export USERS_FIELD_BLIND_KEY="$blind"
  export USERS_FIELD_KEY_VERSION="$version"
}

_ensure_crypto_keys

export REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"
export UPLOAD_HOME="${UPLOAD_HOME:-$PWD/upload}"

exec uv run project-a-api
