# ADR 0014：Neo4j 图谱与全局问答

状态：已定案（v2.1）

## 决策

- 图谱用 Neo4j（`neo4j:5-community`，docker-compose；凭据在 `.env`），pip 官方驱动（`.venv`）；Neo4j 不可达时服务正常启动、图谱接口降级，不影响其他功能。
- Schema：节点 Chapter/Knowledge/Case/Material/Tag；边 CITES / MENTIONS（LLM 抽取）/ BELONGS / HAS_TAG。初始灌库自 SQLite，LLM 逐素材抽取主题词与教材节增强；写路径挂钩增量同步，reseed 后重建。
- 接口：overview / ego（两跳子图）/ reverse（节点反查素材与案例）/ qa（全局问答：BM25 种子→一跳子图召回→LLM 综合，回答带节点引用；AI 不可用返回子图统计）。
- 前端 graph.js 改读真实图谱接口；检索页加"图谱问答"页签。

## 理由

图谱是核心资产，多跳查询与反查是 Cypher 原生表达；Neo4j Browser 可直接向教师演示图谱。全量微软 GraphRAG（社区聚类+分层摘要）demo 期过重，不做。
