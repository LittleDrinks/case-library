# 文件、资料与案例版本存储基线

核对日期：2026-09-30。源码基线固定为 `7afc5bb9e182b1c61827d6024670002a42937fc6`，下列源码链接均指向该提交；源码通过 `git show` 阅读。本笔记不修改运行时代码、不访问用户内容、不执行备份或恢复，也没有运行测试。生产目录、实际 bucket 内容、容量、对象版本设置与备份执行结果均未验证；不能由 Compose 推断生产机器现状。

外部官方实践和首版工程建议见[文件管理实践](file-management-practices-20260930.md)。

## 核心发现

1. 文件字节在对象存储，文件说明及业务引用在 MongoDB。案例版本复制的是正文与引用记录，不会复制对象字节；附件版本保存 `blobId`，全局素材版本视图却没有 `blobId`，两者的历史稳定性不同。[附件快照字段](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/attachments/service.py#L17-L27)、[案例版本组装](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/cases/versions.py#L168-L188)、[素材视图及快照](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/case_materials/service.py#L11-L65)。
2. 当前备份只枚举四类对象引用，遗漏真实持久化的 Skill ZIP 根 `skill_versions.packageSha256`；恢复检查重复相同枚举，因此不能发现这类遗漏。`materials.blobId` 也未直接枚举，但现有正常审批流程保留候选记录，素材文件通常被候选根间接覆盖。[备份枚举](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/scripts/backup-bundle-tool.sh#L35-L60)、[恢复枚举](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/scripts/backup-bundle-tool.sh#L178-L190)、[Skill 字节写入](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/skills/service.py#L79-L85)、[素材审批](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/materials/service.py#L271-L310)。
3. Word 临时输入和图片持久化已是 [Word、图片与表格提取](https://github.com/LittleDrinks/case-library/issues/159) 的明确要求（核对时 OPEN），不是待重新选择的产品规则。当前仅有附件文字抽取；Agent 文件上传、正文图片和可编辑表格链路尚未实现。[Agent 上传限制](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/agent/routes.py#L247-L285)、[正文节点白名单](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/cases/document_schema.py#L7-L42)、[DOCX 文字抽取](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/attachments/text.py#L52-L77)。

## 一个教师流程中的三层对象

教师现在把 Word 上传为案例附件，会写入一份对象字节，建立一个 `attachments` 文件记录。资料区的来源列表和正文引用再使用业务 ID 指向它。教师保存版本或投稿，版本记录保存正文和附件快照，其中仍是同一个 `blobId`；没有第二份 Word 对象。正文中已经引用的附件不能直接删除；删除未被正文引用的当前附件后，如果历史版本或快照仍引用它，对象字节保留。这里描述的是当前附件功能，不是 既定的临时 Word 提取任务。[上传持久化](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/attachments/service.py#L119-L173)、[版本资产](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/cases/versions.py#L168-L188)、[删除](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/attachments/service.py#L244-L280)。

| 层次 | 实际保存什么 | 主要定位方式 |
| --- | --- | --- |
| 文件字节 | Word、图片等原始文件；Skill ZIP 包 | MinIO bucket 的 `blobs/<blobId>`；上传原名不是物理对象路径 |
| 文件元数据 | 名称、类型、大小、权限、抽取文字及对象定位 | 附件 `attachments.id → blobId`；候选/素材 `id → blobId/sha256`；Skill 版本 `id → packageSha256` |
| 业务引用 | 哪个案例挂载哪个来源、正文引用哪个来源、历史版本保留哪些来源 | `case_materials`、`case_sources`、正文引用标记、`case_versions` / `case_snapshots` 中的嵌入记录 |

表中定义依据：[存储对象路径](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/attachments/storage.py#L38-L72)、[附件元数据](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/attachments/service.py#L163-L173)、[候选元数据](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/materials/service.py#L44-L81)、[挂载素材](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/case_materials/service.py#L109-L147)、[案例来源记录](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/case_sources/service.py#L112-L133)、[引用校验](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/cases/citations.py#L25-L40)。

## 持久化文件的真实写入与读取

| 对象类别 | 写入及命名 | 读取及保留 |
| --- | --- | --- |
| 案例附件 | 每次上传产生随机 32 位十六进制 `blobId`；先 `store.put`，再事务插入元数据并推进草稿修订号。不按内容去重。 | 使用权限核验后的附件记录打开同一个对象；历史版本/快照也保存 `blobId`。 |
| 全局素材候选 | 文件内容 SHA-256 同时作为 `sha256` 与 `blobId`；候选按 SHA 去重。压缩包导入逐个有效文件写入，外层归档不是额外长期附件。 | 审批复制该文件定位到 `materials`，候选记录仍保留；拒绝不删除对象。 |
| 已审批全局素材 | 审批不会再上传或复制文件。素材也可只有外部 `sourceUrl`，下载走外部地址，不代表该网站内容已存入本地。 | 下载查当前 `materials`，要求 `status=active` 和当前权限，再读 `blobId`；外链不是受本地对象备份保护的字节。 |
| Skill 包 | ZIP 内容 SHA-256 为对象 ID；MongoDB `skill_versions.packageSha256` 指向完整 ZIP，成员描述另存路径、SHA、大小。 | 运行读取 ZIP 中资源；删除版本设置 `deletedAt`，明确保留已固化调用所需字节。 |

对应依据：[附件随机命名及事务](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/attachments/service.py#L119-L173)、[附件读取](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/attachments/service.py#L211-L241)、[候选去重](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/materials/service.py#L36-L81)、[审批保留候选](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/materials/service.py#L271-L310)、[当前素材读取](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/materials/service.py#L172-L225)、[Skill 上传](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/skills/service.py#L79-L85)、[Skill 删除](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/skills/service.py#L127-L147)、[Skill 元数据及 ZIP 读取](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/skills/service.py#L241-L255)、[读取 ZIP](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/skills/service.py#L320-L324)。

所有类别共用 `BlobStore`，MinIO 的操作分别是 `put_object/get_object/remove_object`，路径为 `blobs/<id>`。下载流结束会关闭 HTTP 响应并释放连接。Release Compose 把 MinIO `/data` 挂到 `minio_data` 命名卷；MongoDB 有独立命名卷。这只能定位容器内存储设计，不能确认生产宿主机绝对路径。[存储适配器](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/attachments/storage.py#L14-L87)、[Release MinIO](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/deploy/release/compose.yaml#L95-L110)、[命名卷声明](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/deploy/release/compose.yaml#L259-L264)。

附件的对象删除失败会被吞掉，调用没有重试队列；元数据可已删除而字节留下。素材在对象写入后若候选数据库写入失败，也保留无候选根的字节，现有测试明确验证该行为。这些是现状中的孤立对象来源，不等于已经有回收或对账流程。[附件尽力清理](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/attachments/service.py#L131-L148)、[素材持久化](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/materials/service.py#L71-L118)、[失败后保留对象测试](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/tests/test_material_imports.py#L465-L476)。

## 挂载、版本与删除的边界

| 操作/对象 | 当前实现 | 对历史和文件字节的影响 |
| --- | --- | --- |
| 删除当前草稿附件 | 仅作者草稿操作；先阻止正文仍引用它，再 CAS 删除当前元数据。 | 若 `case_versions` 或 `case_snapshots` 仍有相同 `blobId`，不删对象；否则尽力删除对象。 |
| 删除案例历史版本 | 删除版本记录及其版本批注；当前发布/投稿版本、含批注或审批生命周期记录的版本不可删。 | 该路径没有 BlobStore 或回收调用。最后一条历史引用消失，不会在此自动回收文件。 |
| 恢复历史案例 | 先创建“恢复前的当前稿”版本，再重建附件、素材和案例来源的当前关系。 | 只操作 MongoDB；附件恢复依赖旧 `blobId` 仍存在，不重新上传字节。 |
| 移除案例中的全局素材 | 校验正文引用及修订号，删除 `case_materials` 关系。 | 不删除全局 `materials`、候选或对象。 |
| 移除案例中的案例来源 | 校验正文引用及修订号，删除 `case_sources` 关系。 | 来源关系记录固定 `sourceCaseId + versionId`，不复制来源案例文件或正文；原案例版本仍是内容来源。 |
| 全局素材替换、停用、删除 | 当前 materials 路由没有这些 API；现有测试中的直接数据库 `disabled`/删除只是可用性探针。 | 不能将素材版本或停用/删除计划描述为已实现，也不能推断未来历史处理规则。 |

依据：[附件删除](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/attachments/service.py#L244-L280)、[历史版本删除限制](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/cases/versions.py#L239-L265)、[恢复关系与保存当前稿](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/cases/snapshots.py#L143-L182)、[素材移除](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/case_materials/service.py#L150-L171)、[来源固定版本](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/case_sources/service.py#L98-L133)、[来源移除](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/case_sources/service.py#L209-L218)、[现有 materials 路由](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/materials/routes.py#L42-L124)。

**全局素材的案例快照仅冻结列表与显示信息，不冻结文件内容定位。** `VIEW_FIELDS` 不含 `blobId` 或 `sha256`，`snapshot_materials()` 返回该视图。读取来源时按素材 ID 查 live `materials`，再执行当前可用性与权限核验。因此未来若要允许素材替换且承诺旧发布版本仍使用旧文件，需要补充明确的内容版本定位；当前没有这项实现。冻结旧文件版本也不意味着冻结旧访问权限，权限仍需即时核验。[字段和快照](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/case_materials/service.py#L11-L65)、[live 素材查询](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/case_materials/service.py#L109-L117)、[来源可用性计算](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/cases/sources.py#L91-L108)、[当前素材权限](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/materials/service.py#L172-L199)。

## 图片、Agent 上传、Word 与临时文件

| 场景 | 固定 HEAD 的事实 | 清理/持久化边界 |
| --- | --- | --- |
| 图片作为普通附件或全局素材文件 | 走通用文件对象流程；正文 schema 尚无 image/table 节点。 | 原始图片文件可持久化，但不能据此声称正文内嵌图片及发布/导出贯通。 |
| Agent 上传文件 | `VercelAIAdapter(... allow_uploaded_files=False)`；canonical message 接受普通文字及 data 部分，其余返回 422。 | 当前没有 Agent Word 文件临时输入生命周期可供验证。 |
| 当前 Word 文字抽取 | 从输入流用 `python-docx Document(source)` 抽取段落和表格单元格的纯文字；限制 ZIP 展开及抽取文字量。 | 此 helper 没有自己创建磁盘临时文件，未抽出图片，也未生成可编辑表格。Agent 来源读取另用 `BytesIO` 包装已读对象。 |
| 素材批量/归档导入 | `TemporaryDirectory(prefix="material-import-")`；复制为 `source-N`，归档成员展开到 `archive-N`。 | 上下文退出时清理该临时树；代码未指定绝对目录，不能声称生产一定在 `/tmp`。未看到进程崩溃残留目录的扫描清理合同。 |
| DOCX 导出 | 文档构建至 `BytesIO` 并返回 bytes；当前图片是应用自带校徽资源。 | 不向 BlobStore 保存新的长期导出对象。 |

依据：[正文白名单](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/cases/document_schema.py#L7-L42)、[Agent 限制](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/agent/routes.py#L247-L285)、[文字抽取安全与实现](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/attachments/text.py#L39-L77)、[来源内存读取](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/agent/source_reader.py#L81-L102)、[归档展开路径](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/materials/archive.py#L278-L309)、[导出内存构建](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/documents/render.py#L311-L324)、[静态校徽](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/documents/render.py#L36-L38)。框架内部 UploadFile 的 spooling 不等于上述业务已实现 Word 任务的临时目录与重试清理合同，本次没有读取框架运行时或生产临时目录。

[Word、图片与表格提取](https://github.com/LittleDrinks/case-library/issues/159) 已要求：Word 仅为提取任务临时输入，任务与重试结束后清理，不成为长期附件/文末来源；图片进入资料区并在正文使用同一资源；表格可编辑；确认、保存、刷新、投稿及导出保留结果。上述是待实现的既定要求，不应再次向用户询问 Word 是否长期保存。

## 备份 manifest 与 bundle 的实际覆盖

数据库 dump 保存所选业务数据库，显式排除 `sessions`、`ai_usage` 以及搜索派生/控制集合（`search_outbox`、`search_revocations`、`search_catalog_state`、`search_control`、`search_catalog_generation`、`search_worker_state`）；其余集合记录名称与条数。manifest 保存数据库 archive/hash/collections、对象 bucket/count/hash-list、枚举引用、Git SHA/dirty 与 app image ID。manifest 生成器只是组装这些输入，没有独立发现业务对象。[数据库范围及清单](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/scripts/backup-bundle-tool.sh#L26-L51)、[manifest 格式](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/scripts/backup-manifest.jq#L1-L20)。

| 文件根 | 备份是否直接枚举 | 说明 |
| --- | --- | --- |
| `attachments.blobId` | 是 | 当前附件 |
| `case_versions.attachments.blobId` | 是 | 正式/历史案例版本附件 |
| `case_snapshots.attachments.blobId` | 是 | 案例快照附件 |
| `material_candidates.blobId` | 是 | 包括当前正常审批后仍存在的候选 |
| `materials.blobId` | 否 | 正常现有流程由候选间接覆盖；只有素材记录而没有候选根的对象不会被发现 |
| `skill_versions.packageSha256` | 否 | 真实 Skill ZIP 会写入同一 bucket，但其根未加入清单 |
| 无上述数据库根的孤立对象 | 否 | 选择性复制，不是整个 bucket 镜像；此遗漏在现有测试中是刻意验证的行为 |
| 只有 `sourceUrl` 的外部资料 | 不适用 | 数据库可保存链接，本地没有对应完整文件字节 |

表依据：[对象根与选择性复制](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/scripts/backup-bundle-tool.sh#L35-L60)、[素材下载及外链](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/materials/service.py#L219-L225)、[Skill 字节和根](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/skills/service.py#L79-L85)、[Skill 版本字段](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/skills/service.py#L241-L255)、[孤立对象未打包测试](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/tests/failover/backup-restore.sh#L73-L80)。

恢复验证会检查数据库集合计数、对象哈希及枚举引用，但再度从同样四类根产生预期引用。因此“恢复 drill 通过”仅证明已枚举范围的一致性，不能单独证明全部持久化对象可恢复；此处结论来自静态控制流，本次没有执行 drill。[恢复计数与根核验](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/scripts/backup-bundle-tool.sh#L167-L190)、[对象核验](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/scripts/backup-bundle-tool.sh#L203-L224)。备份包装脚本在 app 原先运行时先停止 app、完成创建与校验后启动；本笔记未执行该有运行影响的脚本。[包装流程](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/scripts/mongo-backup.sh#L44-L65)。

## 已有测试证明什么

以下均为已阅读的现有测试，**本次未运行**；用例存在不等于生产或当前运行环境验证完成。

| 证据 | 有意义的覆盖 | 不能据此宣称的范围 |
| --- | --- | --- |
| [附件并发测试](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/tests/test_attachment_concurrency.py#L152-L193) | 上传输给投稿竞态清除本次字节；删除输给投稿竞态保留字节；不确定提交结果保留已有记录及字节 | 不是全库对象回收证明 |
| [附件删除失败测试](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/tests/test_attachments.py#L199-L226) | 当前记录可删除；对象删除失败仍返回成功并从列表移除 | 没有证明之后自动重试清理 |
| [附件真实存储 E2E](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/tests/test_attachment_e2e.py#L230-L263) | 投稿/发布附件列表冻结；删除当前草稿附件后历史原字节仍可下载，恢复同一字节 | 没有全局素材替换版本或图片正文链路 |
| [素材真实导入 E2E](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/tests/test_material_import_e2e.py#L115-L164) | 真实 RAR 69 个候选/对象、重导入去重、审批文件下载及权限 | 没有素材停用/删除/替换 API |
| [DOCX 候选与持久化失败](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/tests/test_material_imports.py#L179-L191)、[失败分支](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/tests/test_material_imports.py#L465-L476) | DOCX 作为一个文件候选；数据库失败后保留 canonical 对象 | 没有 Word 图片/表格提取验收 |
| [素材快照测试](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/tests/test_case_materials.py#L120-L150)、[来源可用性测试](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/tests/test_case_sources.py#L365-L411) | 素材列表冻结；素材缺失/disabled 后保留来源条目但不可用；隐藏来源案例时即时检查可读性 | 数据库探针不是已交付的管理员操作 |
| [备份恢复脚本测试](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/tests/failover/backup-restore.sh#L159-L207) | synthetic 附件、版本/快照、候选根；缺对象失败、manifest 篡改与范围隔离；孤立对象不打包 | 没有 `materials` 独立根或 Skill ZIP 的完整性用例 |

## 供后续产品决策使用的边界

现有事实能够支撑分别讨论：从案例中移除一个引用、让全局素材停止向新使用者提供、替换素材内容、永久删除文件字节。这些操作作用的层次不同，不能合为一个“删除”按钮的未明合同。需要明确新使用与已有草稿、已发布内容、历史版本的各自结果，再让既有素材版本/停用/删除规划承接实现；本笔记不指定保留期、权限豁免、回收阈值或删除策略。

实施事实层面的缺口是：未来素材替换需选择并记录内容版本定位；字节回收需能够遍历所有真实根并处理失败重试；备份根需要覆盖 Skill 包及独立素材根，测试要能独立发现枚举遗漏。它们是由上述代码差异推导的待补能力，不是已经做出的产品决定。Word 临时输入与图片持久化依照已有 Word 提取要求继续实施，不重新询问该规则。
