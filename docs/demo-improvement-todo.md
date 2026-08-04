# v2.1 迭代范围

全部功能归入 v2.1（分支 `v2.1`），按依赖排序执行，整体验收后合回 main 打 tag。

- 不做登录：保留下拉切换账号。
- 持久化用 SQLite（`./data/cases.db`），数据模型按正式形态设计。
- 引用目标：句级锚点 + 证据面板。素材按上万条 + 自动采集设计。
- 编辑器：OnlyOffice 替换自研工作台（docker 部署，修订模式承载 AI 生成）。
- 图谱：Neo4j（docker）+ 全局问答 + 反查。

## WP1 闭环地基

1. SQLite 持久层：`cases`（status 状态机）、`reviews`（留痕）、`annotations`、`versions`、`favorites`、`likes`；`citations` 预留 `evidence` 字段。REST：`/api/cases` CRUD、`submit|withdraw|review`、`annotations`、`versions`。沿用 token 身份做归属，不加登录。
2. `store.js` 改 API-backed（写操作先 API 后更新缓存，失败明确提示）；种子案例迁移为服务端 seed。
3. 检索统一走服务端 `/api/search`，删前端本地 BM25（`store.js:802`）；命中带 `sec` 切片深链（ADR 0010）。
4. 验收：两台浏览器两账号跑通"提交→退回（挂批注）→修改→复审发布"互相可见；检索页与 Copilot 同词同结果。

## WP2 素材查找与管理员治理

4. 工作台"资料"页签：按知识点/已引用/类型自动推候选；检索下沉，命中即挂引用。
5. 结果卡片：信源等级 S/A/B/C 色标、来源、日期、审核状态、被引次数、时效标；排序=权威性×相关性×新鲜度×被引；收藏/最近引用/引用历史。
6. 分面：信源等级/类型/课程/思政元素/时间，计数随查询收窄（ADR 0004）；预留三库视图字段位。
7. 管理台账：批量调密级/停用/豁免淘汰；待淘汰清理（ADR 0003）；`sourceUrl` 健康检查标"来源失效"；统计看板。
8. 入库闸：URL+top-3 相似双重查重；必填信源等级+定级依据+链接+日期；B 级人工确认进生成语料；`status` 加"候选"态，候选池/正式库分离。

## WP3 证据链：句级锚点 + 证据面板

9. `citations[]` 升级：docx 锚点（WP6）+ `evidence{materialId, sec, 片段原文, 采集时间}`；〔n〕与证据面板互跳。
10. 生成强制证据绑定：事实句必带〔n〕映射实际 chunk，对不上降级"待核实"；审校员加引用蕴含判断；prompt 契约三类文本分层。
11. 证据面板：点〔n〕→原文片段高亮、来源、发布时间、信源等级、切片深链。
12. 验收：AI 起草后每个事实句可点击看原文；素材停用后引用自动标"来源失效"。

## WP4 审核与反馈沉淀

12. 审核状态机：draft→机审中→待人工→通过/退回/补充/隐藏；退回理由结构化分类（事实错误/引用不支持/牵强映射/过度拔高/表述不规范），作反例库数据源。
13. 机审第一层：思政垂直词库 v0（教材固定表述、领导人姓名职务、二十大规范表述、易错词）；预留黑马/蜜度 API 位（`AI_REVIEW_ENABLED`）；反例库 v0：10 类风险各 2–3 条样例作 few-shot。
14. AI 生成标识：AI生成/AI辅助/人工、模型版本、审核人，写入导出 Word 页脚。
15. 反馈沉淀：版本 diff 落库；组织资产页（被退回表达清单、教研组模板），人工可读台账，不接进 prompt。
16. 记忆 bench：20–30 个"虚拟教师画像×生成任务"，三臂对照（无记忆/显式偏好/自动记忆），指标=采纳率/修改幅度/错误记忆注入率/政治风险事件/token 成本。**出结论前不实现任何自动记忆写入。**

## WP5 自动盯源与众筹雏形

17. 定时任务：白名单栏目抓取→去重（URL+内容指纹）→候选素材卡→机审初筛→只进候选池；默认只存标题+摘要+链接+元数据；同事件多报道聚类成事件卡。
18. 众筹雏形：三种贡献入口（素材链接/知识点关联/完整案例）分级审核、先审后发；作者"被引用/被改编"数据页。

## WP6 OnlyOffice 主编辑器

19. docker 部署 Document Server（JWT secret 进 `.env`）；案例正文 docx 化（`files/cases/`），工作台改 OnlyOffice JS API 嵌入（document.key + callbackUrl 回写）；blocks→docx 迁移脚本含种子案例。
20. 能力嫁接：句级引用=docx bookmark/content control（`cite-n`，Automation API/插件插入）；批注→原生 comments；AI 生成走修订模式（track changes）教师接受/拒绝；版本快照=forcesave+docx 副本。
21. 自研编辑器验收前留作回退，验收后退役。
22. 验收：起草→AI 修订→接受/拒绝→句级引用→批注→提交审核全程在 OnlyOffice 内完成，无功能回退。

## WP7 Neo4j 图谱 + 全局问答 + 反查

23. docker 部署 Neo4j（密码进 `.env`）；节点 `Material/Knowledge/Case/Policy/Person/Org/Event/SizhengElement/KnowledgePoint`，关系 `CITES/SUPPORTS/RELATES_TO/EMBODIES/TEACHES/MENTIONS`；`server.py` 接 neo4j 驱动。
24. 建库：素材+知识节+案例 LLM 批处理实体/关系抽取，增量写入，挂素材管道；教材 52 节 kn 骨架灌入作初始图谱。
25. 全局问答：检索页"图谱问答"页签，Cypher 召回子图+证据交 LLM 综合，回答带引用。
26. 反查：节点多跳反查素材与案例，接入检索页与详情页；`graph.js` 改读 Neo4j 接口。
27. 验收：全局问答回答 3 类全局问题且带证据；思政元素节点两跳反查到素材与案例。

## 收尾

28. 完整闭环联测：盯源候选→入库→检索/图谱选材→AI 起草（修订+句级引用）→机审→提交→退回→修改→复审发布→导出带标识 Word→被引统计→图谱可查。
29. 新增 ADR 0012（SQLite 持久化）、0013（OnlyOffice）、0014（Neo4j 图谱）；README 同步。
30. 合回 main，打 tag `v2.1`。

## 不做

- 登录/注册/密码；自动记忆写入（先过 bench）；自研思政大模型。
