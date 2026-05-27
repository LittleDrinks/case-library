# syntax=docker/dockerfile:1.7

FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    make \
    procps \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /app/data

COPY requirements.txt requirements-dev.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt -r requirements-dev.txt

COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY pyproject.toml ./

EXPOSE 8001

CMD ["sh", "-c", "if [ -f backend/core/main.py ]; then uvicorn backend.core.main:app --host 0.0.0.0 --port 8001; else uvicorn backend.main:app --host 0.0.0.0 --port 8001; fi"]
