# syntax=docker/dockerfile:1.7

FROM node:20-bookworm-slim AS node

FROM python:3.12-slim

ARG APT_MIRROR=http://deb.debian.org/debian
ARG APT_SECURITY_MIRROR=http://deb.debian.org/debian-security
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG NPM_CONFIG_REGISTRY=https://registry.npmjs.org

ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn \
    NPM_CONFIG_REGISTRY=${NPM_CONFIG_REGISTRY}

WORKDIR /app

COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules

RUN if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i \
          -e "s|http://deb.debian.org/debian|${APT_MIRROR}|g" \
          -e "s|http://deb.debian.org/debian-security|${APT_SECURITY_MIRROR}|g" \
          /etc/apt/sources.list.d/debian.sources; \
    elif [ -f /etc/apt/sources.list ]; then \
        sed -i \
          -e "s|http://deb.debian.org/debian|${APT_MIRROR}|g" \
          -e "s|http://deb.debian.org/debian-security|${APT_SECURITY_MIRROR}|g" \
          /etc/apt/sources.list; \
    fi \
    && apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
    make \
    openssh-client \
    procps \
    zsh \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /app/data \
    && ln -sf ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -sf ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && ln -sf ../lib/node_modules/corepack/dist/corepack.js /usr/local/bin/corepack \
    && git config --system --add safe.directory /app \
    && npm config set registry "$NPM_CONFIG_REGISTRY"

COPY requirements.txt requirements-dev.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt -r requirements-dev.txt

COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY pyproject.toml ./

EXPOSE 8001

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8001"]
