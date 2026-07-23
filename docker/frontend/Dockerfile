FROM node:22-alpine AS build

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine

ENV TZ=Asia/Seoul

RUN apk add --no-cache gettext tzdata

COPY docker/frontend/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY docker/frontend/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh \
  && sed -i 's/\r$//' /docker-entrypoint.sh

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 9001

CMD ["/bin/sh", "/docker-entrypoint.sh"]
