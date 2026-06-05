# Case Library

强国有我大思政课案例库。当前基线是 FastAPI + MongoDB 后端，以及 Vue 3 + Vite 前端。

## Development

推荐使用 Dev Container。也可以直接用 Docker Compose：

```bash
docker compose up --build
```

服务端口：

- Backend API: `http://localhost:8001`
- Vue frontend: `http://localhost:18080`
- MongoDB: container network only, `mongo:27017`

## Checks

```bash
docker compose run --rm app make check
docker compose config
```

`make check` runs:

- `ruff check backend`
- `python backend/test_submit_flow.py`
- `frontend` dependency install and Vite build

## Project Layout

```text
backend/      FastAPI app, MongoDB data layer, migration and smoke scripts
frontend/     Vue 3 + Vite app
skills/       Case classification and writing templates used by backend helpers
```

Private account files such as `backend/accounts.csv`, local agent notes, runtime data, and generated caches are ignored.
