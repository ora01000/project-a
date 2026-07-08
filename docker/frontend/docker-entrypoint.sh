#!/bin/sh
set -eu

export BACKEND_API_HOST="${BACKEND_API_HOST:-backend}"
export BACKEND_API_PORT="${BACKEND_API_PORT:-8080}"
export FRONTEND_PORT="${FRONTEND_PORT:-9001}"

envsubst '${BACKEND_API_HOST} ${BACKEND_API_PORT} ${FRONTEND_PORT}' \
  < /etc/nginx/templates/default.conf.template \
  > /etc/nginx/conf.d/default.conf

exec /usr/sbin/nginx -g "daemon off;"
