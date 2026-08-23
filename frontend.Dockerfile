# syntax=docker/dockerfile:1.7

FROM node:20.19-bookworm-slim AS dependencies

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

FROM dependencies AS test

COPY frontend/ ./
CMD ["npm", "test"]

FROM dependencies AS build

COPY frontend/ ./
RUN npm run build

FROM nginx:1.28-alpine AS runtime

COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
