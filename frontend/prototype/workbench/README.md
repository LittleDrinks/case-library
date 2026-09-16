# CKEditor 工作台原型

从 `frontend` 目录启动：

```bash
PROTOTYPE_EVIDENCE_DIR=/home/q2635/wsl-workspace/case-library-v2/.scratch/m1-309-ckeditor-prototype/luna npm run prototype:workbench
```

打开 <http://127.0.0.1:5179/prototype/workbench/>。代理只在服务端读取主仓 `.env` 中的 `AI_BASE_URL`、`AI_API_KEY`、`AI_MODELS`、`AI_DEFAULT_MODEL`、`AI_TIMEOUT_SECONDS`；浏览器只访问同源接口，不接触密钥、base URL 或鉴权头。聊天、选区总结和修订建议使用真实模型，事件证据写入 `ai-events.jsonl`，请求/响应文本已脱敏。

这是交互原型：文档和会话状态在内存中，资料与联网能力仍为 Later/未接入，不代表生产数据或生产部署。
