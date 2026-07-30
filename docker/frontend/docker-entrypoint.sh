#!/bin/sh
set -eu

parse_listen_port() {
  raw="${1:-}"
  default="${2:-}"

  if [ -z "$raw" ]; then
    printf '%s' "$default"
    return
  fi

  case "$raw" in
    tcp://*)
      host_port="${raw#tcp://}"
      case "$host_port" in
        *:*)
          port="${host_port##*:}"
          case "$port" in
            ''|*[!0-9]*) ;;
            *) printf '%s' "$port"; return ;;
          esac
          ;;
      esac
      ;;
    *)
      case "$raw" in
        ''|*[!0-9]*) ;;
        *) printf '%s' "$raw"; return ;;
      esac
      ;;
  esac

  printf '%s' "$default"
}

resolve_listen_port() {
  explicit="${1:-}"
  merged="${2:-}"
  default="${3:-}"

  if [ -n "$explicit" ]; then
    parse_listen_port "$explicit" "$default"
    return
  fi

  parse_listen_port "$merged" "$default"
}

export BACKEND_API_HOST="${BACKEND_API_HOST:-backend}"
export BACKEND_API_PORT="$(
  resolve_listen_port \
    "${BACKEND_API_LISTEN_PORT:-}" \
    "${BACKEND_API_PORT:-}" \
    "8080"
)"
export FRONTEND_PORT="$(
  resolve_listen_port \
    "${FRONTEND_LISTEN_PORT:-}" \
    "${FRONTEND_PORT:-}" \
    "9001"
)"

envsubst '${BACKEND_API_HOST} ${BACKEND_API_PORT} ${FRONTEND_PORT}' \
  < /etc/nginx/templates/default.conf.template \
  > /etc/nginx/conf.d/default.conf

exec /usr/sbin/nginx -g "daemon off;"
