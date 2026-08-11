FROM node:22-alpine AS build

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

FROM nginx:1.31.3-alpine

ENV TZ=Asia/Seoul

RUN apk add --no-cache gettext tzdata \
  && rm -f /etc/nginx/conf.d/default.conf

COPY docker/frontend/nginx-main.conf /etc/nginx/nginx.conf
COPY docker/frontend/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY docker/frontend/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh \
  && sed -i 's/\r$//' /docker-entrypoint.sh

COPY --from=build /app/dist /usr/share/nginx/html

# OKD restricted SCC: arbitrary UID with GID 0 must write runtime paths.
RUN mkdir -p /tmp/nginx \
    /var/cache/nginx \
    /var/log/nginx \
    /etc/nginx/conf.d \
  && chgrp -R 0 /tmp/nginx /var/cache/nginx /var/log/nginx /etc/nginx/conf.d /usr/share/nginx/html \
  && chmod -R g+rwX /tmp/nginx /var/cache/nginx /var/log/nginx /etc/nginx/conf.d /usr/share/nginx/html

EXPOSE 9001

CMD ["/bin/sh", "/docker-entrypoint.sh"]
