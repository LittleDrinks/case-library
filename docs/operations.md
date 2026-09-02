# 部署、容量与容灾
## 单机部署
`make up` 构建并启动 Nginx、四个 Uvicorn worker、三成员 MongoDB 副本集、Meilisearch 检索目录和单实例 MinIO，等待全部健康检查通过。默认只绑定宿主回环地址。每次执行都会替换应用、检索 worker 与前端容器，MongoDB、检索目录和对象存储命名卷保持不变。`make logs` 查看应用日志，`make down` 停止服务并保留命名卷；`docker compose down --volumes` 会删除本地数据库、检索目录与对象数据。
单机 Compose 验证 majority write、MongoDB 选举和客户端重连，不能抵御宿主机、磁盘或机房故障，也不构成跨故障域生产容灾。
## AI 配置
| 变量 | 用途 |
| --- | --- |
| `APP_SECRET` | 个人 API Key 加密；Compose 注入 `app_secret` Docker secret |
| `AI_BASE_URL` | 平台 OpenAI 兼容接口的 HTTPS Base URL |
| `AI_API_KEY` | 平台凭据；Compose 注入 `ai_api_key` Docker secret |
| `AI_MODELS` | 管理员可选的平台模型列表，逗号分隔 |
| `AI_DEFAULT_MODEL` | 未指定管理员兜底模型时的平台默认模型 |
| `AI_TIMEOUT_SECONDS` | 模型发现与流式生成超时 |
个人模式保存 Base URL、model 与加密后的 API Key；API 不回传密钥。用户可调用提供方模型列表或直接填写 model。自动模式按管理员兜底模型、环境默认模型的顺序解析；个人配置无效时拒绝请求，不静默使用平台凭据。自定义 Base URL 只接受解析到公网地址的 HTTPS 服务。
管理员只在数据库中保存兜底模型选择，平台 Base URL、模型白名单和凭据仍由 `.env` 与 Docker secrets 管理。
## 正式部署门槛
生产拓扑未提供；默认 Compose 设置 `APP_ENV=production` 会拒绝启动。独立生产部署满足以下全部条件：
- 设置 `APP_ENV=production`、`ENABLE_DEMO_SEED=false`、`SESSION_COOKIE_SECURE=true`；`APP_SECRET` 至少 32 字节，MinIO 密码至少 16 字节，均使用高多样性随机值；age recipient 必须由配置的 identity 派生；生产密钥不使用演示值、不进入镜像和版本库。
- 入口终止 TLS；API 至少三个副本、前端至少两个副本并跨故障域，对登录、AI 流式请求和 DOCX 导出分别限流。
- MongoDB 启用认证、成员 keyfile 和 TLS，三个有数据投票成员分布到三个故障域和独立磁盘；驱动保持 majority write 与副本集重试。
- Meilisearch 目录持久化并使用独立访问密钥，至少一个检索 worker 常驻；当前物理 `indexUid`、`generation` 与 `indexEpoch`、worker 心跳和 outbox 时延共同决定就绪，异常实例返回 503 并摘流，不回查 MongoDB。
- Compose 内单实例 MinIO 只适用于本机演示。生产文件进入启用版本、服务端加密、跨故障域冗余和异地复制的 S3 兼容对象存储，数据库与对象生命周期同步备份。
- 备份公钥只进入备份任务，恢复私钥只进入隔离恢复任务；加密归档复制到异机或不可变对象存储。
- 生产主机不运行 E2E、故障演练或负载测试。测试数据库虽隔离数据，仍与业务库争用 CPU、内存和磁盘。
## 容量合同
业务峰值为 200 名活跃用户，容灾容量按 5 倍即 1000 名活跃用户验收。非 AI 混合读写在目标数据量下要求成功率不低于 99.9%、p95 低于 500ms、p99 低于 1s；1000 VU 稳态至少 15 分钟，并另做突增和 MongoDB 主节点切换恢复。AI 请求受上游模型容量影响，独立限流且不计入该吞吐结论。
负载门禁使用 12,480 条素材、独立用户会话与独立案例；结果写入 `test-results/`，验收结论以当前工作树执行产生的 artifact 为准。
默认顺序为 smoke（2 VU、15 秒）、peak（30 秒升至 200 VU、满载 2 分钟、30 秒降载）、resilience（2 分钟升至 1000 VU、满载 3 分钟、2 分钟降载）、rate（每秒 450 次迭代、2 分钟、200 个预分配 VU、最多 1000 VU）、steady（2 分钟升至 1000 VU、满载 15 分钟、2 分钟降载）。每档先重建检索目录并等待完成，再核验 Mongo 素材数、当前物理代际的 12,480 条逻辑素材和真实增量发布链路；满载 hold 单独验收，每项 operation 必须有样本。artifact 为 `load-<profile>-dataset.txt`、`-catalog.txt`、`.txt`、`-summary.json`、`-resources.tsv`、`-nginx.txt` 和 `-nginx-errors.txt`；退出后读回确认负载容器、Meilisearch 卷和 `case_library_load` 数据库均已删除。
## 验证与演练
```bash
make config
make test
make e2e
make ai-smoke
make load-smoke
make load-peak
make load-resilience
make load-rate
make load-steady
make load-all
make failover
```
`make test` 运行后端与前端测试，`make e2e` 运行真实 HTTP、MongoDB、对象存储和浏览器流程；`make ai-smoke` 仅对已启动服务验证平台 AI 配置，提交一次真实 Chat 并以 Thread 快照中的持久化 Run 成功终态确认完成，不解释流协议，生产凭据从环境或隐藏输入提供，日志不记录配置、请求和响应内容；负载测试使用隔离业务库，`make load-all` 按 smoke、peak、resilience、rate、steady 串行执行并分别产出 artifact；`make failover` 在独立 Compose 项目和命名卷中执行 MongoDB 选主与 bundle 备份恢复，销毁演练资源并校验默认栈就绪状态和业务数据哈希不变。
## 备份与恢复
`make backup` 短暂停止 app，只导出业务真源并排除会话、AI 瞬时配额和可重建检索状态；Mongo archive、被附件/工作快照/发布版本/素材候选引用的对象、集合与对象计数及逐项 SHA-256 加密为 `backups/` 下的 bundle，退出时恢复原 app 容器状态。
`make restore-drill BACKUP=backups/<bundle>.age` 校验并恢复到一次性 MongoDB 容器和随机隔离 bucket，核对数据库作用域、集合计数、对象数量、对象哈希与附件引用，结束后删除隔离资源，不连接业务 MongoDB。
正式环境以托管快照或连续 PITR 为主恢复路径、加密逻辑归档为第二路径；恢复业务真源后全量重建检索目录，再开放就绪流量。目标 RPO 15 分钟、RTO 60 分钟，每次发布前执行隔离恢复与核心 E2E。
