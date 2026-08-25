<div align="center">

<img src="frontend/public/shanghai-university-horizontal-logo.png" alt="上海大学" width="360" />

# 思政教学案例平台

<a href="https://vuejs.org/"><img src="https://img.shields.io/badge/Vue-3.5-4FC08D.svg" alt="Vue 3.5" /></a>
<a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-0.138-009688.svg" alt="FastAPI 0.138" /></a>
<a href="https://www.mongodb.com/"><img src="https://img.shields.io/badge/MongoDB-7-47A248.svg" alt="MongoDB 7" /></a>
<a href="https://www.meilisearch.com/"><img src="https://img.shields.io/badge/Meilisearch-1.45-FF5CAA.svg" alt="Meilisearch 1.45" /></a>
<a href="https://www.docker.com/"><img src="https://img.shields.io/badge/Docker_Compose-Ready-2496ED.svg" alt="Docker Compose" /></a>

**面向高校教师的思政教学案例创作、审核、发布与检索平台**

</div>

Vue 3、Tiptap/ProseMirror、FastAPI、MongoDB 副本集、Meilisearch 与 S3 兼容对象存储组成的案例创作平台。

## 功能

- **公共资源**：首页展示公开案例与推荐素材；统一检索支持 AI 摘要、案例、知识、素材列表与关系图谱，并遵循资源访问权限。
- **案例创作**：从案例工作台进入素材掌控台，按工作视图、来源权威性、素材类型和对外使用条件筛选；选中素材可挂载到当前案例，并随提交、发布、版本快照与回滚流转。
- **编辑与审核**：三栏画布工作台以 Tiptap/ProseMirror 编辑，文档 JSON 是正文真源，revision 阻止旧页面覆盖；支持自动保存、版本快照、回滚、批注、AI 助手和固定版式 DOCX 导出。
- **素材与 AI**：管理员可批量导入文件、ZIP、RAR5 并以 SHA-256 去重；AI 默认使用平台配置，教师可使用个人 OpenAI 兼容配置，管理员指定平台兜底模型。

## 单机演示

宿主机只需 Docker Engine、Docker Compose、Make 和 POSIX shell，应用与测试依赖均在镜像中。

首次启动：

```bash
test -f .env || cp .env.example .env
make up
```

访问 `http://127.0.0.1:8080`；API 就绪检查为 `http://127.0.0.1:8001/health/ready`。

- 再次执行 `make up` 会构建并替换前后端容器，MongoDB 与对象存储命名卷保持不变；`make down` 停止服务并保留命名卷。
- `make` 先加载 `.env.example` 的非敏感演示默认值，再用 `.env` 覆盖同名项。
- 平台 AI 由 `.env` 中的 `AI_BASE_URL`、`AI_API_KEY`、`AI_MODELS`、`AI_DEFAULT_MODEL` 和 `AI_TIMEOUT_SECONDS` 配置；`APP_SECRET` 用于个人 API Key 加密。
- Compose 将 `APP_SECRET`、`AI_API_KEY` 注入 Docker secrets，值不得写入源码或提交到版本库。

> 默认 Compose 仅用于单机演示。设置 `APP_ENV=production` 会拒绝启动；生产拓扑未提供，部署门槛见 `docs/operations.md`。

## 演示账号

仅当 `APP_ENV=demo` 且 `ENABLE_DEMO_SEED=true` 时创建；生产环境启用演示数据会拒绝启动。

| 用户名 | 密码 | 角色 | 状态 |
| --- | --- | --- | --- |
| `admin` | `admin123` | 管理员 | 可用 |
| `user` | `user123` | 教师 | 可用 |
| `10000001` | `Demo-10000001-2026!` | 教师（小杨） | 可用，首次登录后改密 |
| `10000002` | `Demo-10000002-2026!` | 管理员（小李） | 可用，首次登录后改密 |
| `10000003` | `Demo-10000003-2026!` | 管理员（小赵） | 禁用 |

## 验证

```bash
make config
make test
make e2e
make ai-smoke
make load-smoke
make load-rate
make load-all
make failover
```

- `make ai-smoke`：对已启动服务执行平台 AI 真实连通性检查。演示环境使用 `admin/admin123`；生产环境设置 `AI_SMOKE_USERNAME`，密码从隐藏输入、标准输入或 `AI_SMOKE_PASSWORD` 读取，输出不含模型配置和生成内容。
- `make load-peak`：验收 200 名活跃用户峰值；`make load-resilience`：检查 5 倍容量的 1000 名活跃用户短时负载。
- `make load-rate`：验收每秒 450 次迭代的到达率且不允许丢迭代；`make load-steady`：执行 1000 VU 的 15 分钟满载稳态验收。
- `make load-all`：按 smoke、peak、resilience、rate、steady 串行执行完整容量门禁；结果仅适用于执行机器与当次配置。
