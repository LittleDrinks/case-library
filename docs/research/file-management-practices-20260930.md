# 文件管理实践：元数据、文件内容与历史引用

日期：2026-09-30。任务来源：[查清上传文件、资料资源与案例版本的真实存储模型](https://github.com/LittleDrinks/case-library/issues/345)。调查基线：仓库 `7afc5bb9e182b1c61827d6024670002a42937fc6`；官方网页于本日实时核验。本报告研究外部实践和项目建议，源码完整盘点另见[存储基线](file-storage-baseline-20260930.md)；未验证生产 bucket 的配置、容量或运行状态。

## 结论

继续使用现有 MongoDB 保存记录、MinIO 保存文件内容的方向。首版需要补齐的是每份文件的来源、权限、引用、保留和恢复规则。数据库存文件也可行，但迁往 GridFS 并不会自动解决历史引用、权限和删除问题。

这里的“推荐”是根据小型校内平台、投稿冻结版本和私有内容边界作出的工程判断，不是所有 CMS 都遵守的唯一行业标准。尤其是“替换后旧案例仍读旧文件”，需要本平台主动实现。

## 1. 文件可以存数据库，也可以与数据库分开

| 方案 | 一手证据 | 对本项目的判断 |
| --- | --- | --- |
| 文件内容在存储服务，文件记录在数据库 | Directus 将文件上传到 storage adapter，在 `directus_files` 保存元数据；文件记录包含存储位置、存储文件名、下载文件名和上传者。[Files API](https://directus.com/docs/api/files) | 与现有 Mongo + MinIO 接近，可继续使用。 |
| 内容、记录、业务引用分层 | Rails Active Storage 的 Blob 记录保存文件元数据和服务 key；Attachment 将业务记录与 Blob 关联，同一 Blob 可以被多个记录引用。[Blob](https://api.rubyonrails.org/classes/ActiveStorage/Blob.html)、[Attachment](https://api.rubyonrails.org/classes/ActiveStorage/Attachment.html) | 同一物理文件可被多个案例使用，业务引用仍需独立记录。 |
| 直接存 MongoDB | MongoDB 官方允许小于 16 MiB 的文件使用文档 BinData，大文件可用 GridFS 分块。GridFS 不支持多文档事务；整文件原子替换推荐上传新版本再更新元数据指针。[GridFS](https://www.mongodb.com/docs/manual/core/gridfs/) | 技术上可行，当前没有迁移必要；“数据库支持事务”不等于外部文件操作或 GridFS 自动参与同一事务。 |

例如上传 `教学资料.pdf`：MinIO 保存 PDF 的字节；Mongo 保存“谁上传、原名、大小、哪一个对象、权限”；案例版本保存“使用了哪份文件内容”。下载时平台先检查这个业务入口的读取权限，再读取 MinIO 对象。Directus 官方建议通过 API 访问文件，以使文件权限生效，而不是直接暴露存储目录。[Access Files](https://directus.com/docs/guides/files/access)

## 2. 分清“同一份资料”与“同一批字节”

建议区分三类信息，可由现有集合演进，不要求为每类立即新建独立服务：

- **内容对象**：存储 key、大小、SHA-256、上传完成状态；一旦被使用，不原地改写。
- **资料记录**：名称、上传者、来源、公开/校内/私人范围、当前内容版本、是否允许新引用；这些可以修改并留记录。
- **案例引用**：引用的资料记录及具体内容对象，必要的来源说明，以及所属草稿/投稿版本/发布版本。

Rails 官方将 Blob 的文件引用视为不可变，变更内容或创建派生内容时创建新 Blob；这支持上面的对象分层。[Blob](https://api.rubyonrails.org/classes/ActiveStorage/Blob.html) 但 **冻结案例引用旧字节** 是本项目可追溯要求下的工程选择：Strapi 官方的“替换”反而保留 asset 身份、让已有内容继续指向替换后的文件，旧文件不可恢复；删除正在使用的文件也会破坏原内容。[Replacing / deleting assets](https://docs.strapi.io/cms/features/media-library#replacing-an-asset-file)

内容 SHA-256 去重只证明字节相同，不能证明上传者、来源、权限、保留期限相同。**工程推论**：可以共用内容对象，但不要因此合并业务资料记录，更不能通过某条公开记录绕过另一条私人记录的读取权限。

## 3. 历史版本、对象版本与权限各自解决不同问题

**已验证的存储能力：** S3 Versioning 让同一 key 的覆盖生成新 version ID，普通删除产生 delete marker；指定 version ID 的删除可以永久删除该版本。每个版本保存完整对象，会增加空间占用。[Versioning](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Versioning.html)、[Deleting versions](https://docs.aws.amazon.com/AmazonS3/latest/userguide/DeletingObjectVersions.html) MinIO 官方项目文档同样说明通过 version ID 读取旧版本、指定版本永久删除；实际能力还应按部署版本和拓扑核验。[MinIO versioning](https://github.com/minio/minio/blob/master/docs/bucket/versioning/README.md)

**工程建议：** 首版优先让每次不同内容得到不同 key，案例冻结版本指向具体 key；若启用存储 versioning，则引用需同时保存并在读取时使用 version ID。只保存一个可覆盖的 key，即使 bucket 保留旧版本，也不能让业务自动读到正确历史文件。S3 的条件写入 `If-None-Match: *` 可防止覆盖已有当前对象；是否能在现有 MinIO/SDK 路径直接使用，需要另行验证。[Conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html)

“保留旧字节”不意味着“永久公开旧字节”。**待用户决定的产品规则**：资料因错误、隐私或授权撤销而下线时，是只禁止新引用，还是同时停止旧案例下载；后者建议保留引用标识与下线说明，而不是悄悄换成另一份文件。普通内容更新与紧急停止访问应为两个独立动作。

对需要撤权立即作用于后续访问的私人/校内文件，建议继续经平台鉴权下载。S3 presigned URL 是持有者即可使用的凭据，过期前仍可被使用；开始下载后的流也不会因链接过期自动停止。这意味着发出短时签名 URL 会形成一个允许访问的时间窗口，不能承诺平台撤权会立刻吊销已发链接。[Presigned URLs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html)

## 4. 删除先处理业务影响，再回收字节

Rails 的 Attachment 外键阻止仍被其他记录引用的 Blob 被清除，`purge_later` 在后台执行删除。这是一种成熟引用保护实践；Mongo 版需要应用实现相应保护，不能照搬 SQL 外键。[Attachment](https://api.rubyonrails.org/classes/ActiveStorage/Attachment.html)

**建议的最小语义：**

| 用户动作 | 建议结果 |
| --- | --- |
| 从一篇草稿移除附件 | 去掉这篇草稿的引用；不影响其他草稿或已投稿版本。 |
| 删除资料记录 | 进入回收站并禁止新增引用；在用内容不自动被物理删除。展示引用数量/影响范围。 |
| 替换文件 | 为新内容创建对象，更新当前版本；已冻结引用保留旧对象。 |
| 停止文件访问 | 下载入口按当前停用状态拒绝，历史引用保留说明；涉及的公开展示方式由用户决定。 |
| 物理清理 | 仅清理无任何需要保留的草稿、投稿/发布历史版本、快照引用，无处理中任务持有，且超过保留期的对象；删除结果留记录，可重试。 |

回收站保留期限不是技术文档能替用户决定的行业常数。7 天、30 天都只能作为容量和误删恢复需要下的可配置候选，尚未确认。

S3 Lifecycle 按前缀、标签、对象大小等匹配对象；它没有读取 Mongo 案例引用的机制。[Lifecycle filters](https://docs.aws.amazon.com/AmazonS3/latest/userguide/intro-lifecycle-filters.html) **工程推论**：不要把“所有上传对象超过 N 天删除”当作在用资料管理。永久资料的回收应由应用根据引用判定；Lifecycle 可辅助处理已明确隔离的临时前缀。保留旧版本时，还需避免 noncurrent 版本过期误删业务仍引用的历史字节。

## 5. 失败上传与临时文件需要可解释状态

Rails 官方承认文件已上传、但没有完成业务绑定的情况，并给出定期清理 unattached uploads 的示例；示例使用年龄门槛而不是即时清理。[Purging unattached uploads](https://guides.rubyonrails.org/active_storage_overview.html#purging-unattached-uploads)

**建议流程：** 建立待上传记录和唯一 key → 上传并校验大小/hash → 标记完成 → 绑定业务引用。步骤失败留下“待上传/失败/未绑定”的状态，可重试或延后回收。Mongo 事务只保证其中的数据库变化；不能把 MinIO 写入当作同一数据库事务。清理任务应再次检查引用，并通过删除状态与引用建立流程的协调，防止扫描之后有人新引用、随即被清理的竞态。首版定时人工执行带预览报告的清理也可以，不必先建复杂队列。

要区分两种垃圾：未完成 multipart 的碎片，以及上传已完成、却未绑定任何业务的完整对象。S3 `AbortIncompleteMultipartUpload` 只清理前者，不删除完整对象，因此不能代替应用孤儿对象扫描。[Abort incomplete uploads](https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpu-abort-incomplete-mpu-lifecycle-config.html)

临时解析输入与正式素材使用独立用途/生命周期；Word 临时输入沿既有 [Word 内容抽取规则](https://github.com/LittleDrinks/case-library/issues/159)，本报告不重新定义。派生缩略图、预览和抽取文本应记录原始对象与处理版本；可重建的结果可以回收重算，用户修改过或已成为案例事实来源的结果不能仅按“缓存”删除。Rails 的变换/预览能力证明派生内容可单独管理，但上述保留界线是本项目工程建议。[Active Storage overview](https://guides.rubyonrails.org/active_storage_overview.html)

## 6. 首版最低可维护方案

1. 保留 Mongo + MinIO，统一登记三类已有文件入口：附件、资料、Skill 包；统一提供来源、大小、状态、权限和引用查询。查询仍按原业务权限过滤，管理员管理平台公共/校内素材和已投稿可审阅资源；他人未投稿草稿、私人资料和 AI 对话不因文件后台而开放。私人对象的容量/健康汇总不带可识别内容、来源或预览。
2. 不覆盖已使用字节，投稿/发布固定具体内容引用；禁止绕过业务授权直接按存储 key 下载。
3. 删除采用回收站、引用保护、延后物理清理；孤儿扫描先输出报告，再按可配置规则执行。
4. 临时输入与正式内容可区分；失败可重试、后台清理可重复执行，每次操作留状态和结果。
5. 备份数据库、全部需要恢复的内容对象和引用清单，在隔离环境验证实际下载和 Skill 资源读取。

以上是适配当前平台的工程建议。S3 versioning 可作为误覆盖/误删除的附加保护，在测量容量和核验 MinIO 部署能力后决定。Object Lock 防止对象版本在保留期内被删除，依赖 versioning；本轮没有不可篡改保留要求，不将它作为首版前提。[Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html) 多机高可用和异机备份目标属于后续运营/容灾决策，不能由文件管理组件替代。

### 备份一致性的最低边界

Mongo 官方明确：没有 `--oplog` 且导出期间有写入，dump 不代表单一时点；`--oplog` 必须完整导出 replica set 成员，不能与 `--db` 等限定导出选项并用。它只处理 Mongo 写入，并不协调外部对象存储。[mongodump](https://www.mongodb.com/docs/database-tools/mongodump/#std-option-mongodump.--oplog)

源码 `scripts/mongo-backup.sh:52–58` 在调用 bundle 工具前暂停 Compose `app`；这是代码事实，不是生产已按该脚本备份的证明。**首版工程建议**：采用明确的短维护窗，协调所有会写入持久数据库/对象的入口和对象清理任务，随后生成元数据及全部业务引用对应的对象清单。隔离恢复既校验清单/hash，也通过实际案例附件、资料下载和 Skill 读取证明内容可用。不能仅加一个 `--oplog` 参数就宣称两套存储的备份一致。备份频率、异机位置、可接受数据损失与恢复时间保留给 [容灾、备份与恢复最低承诺](https://github.com/LittleDrinks/case-library/issues/346) 决定。

## 当前缺口与优先级

这是固定源码基线上的检查结果，不能代替生产测量：

1. **先补完整备份引用清单。** Skill 上传用包 SHA-256 保存对象、`skill_versions.packageSha256` 保存引用，但备份及恢复校验只枚举附件/附件历史/资料候选，没有 Skill 包或 `materials.blobId` 直接引用。不能断言所有素材必然漏备，因为候选可能仍保留同一对象；清单无法独立覆盖这些入口是确定缺口。[Skill 上传](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/skills/service.py#L79)、[Skill 版本记录](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/skills/service.py#L242)、[备份清单](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/scripts/backup-bundle-tool.sh#L45)
2. **补资料引用的固定内容身份。** `case_materials` 的 view/snapshot 保存展示字段和 `hasFile`，没有 `blobId`、SHA-256；读取授权时可合并 live material。若以后支持素材替换，现有快照本身不足以指定历史字节。[案例资料展示/快照](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/case_materials/service.py#L11)、[live 记录合并](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/case_materials/service.py#L113)
3. **补统一回收与失败留痕。** 附件删除已有历史版本/快照引用检查，因此不是完全没有保护；但移除存储失败会被吞掉，且附件机制不等于跨素材、Skill、任务的统一回收管理。[附件回收](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/attachments/service.py#L144)、[历史引用保护](https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/attachments/service.py#L263)
4. **生产现场待测。** bucket versioning、实际对象数/容量、失败残留、备份执行方式与恢复耗时未核验；不据本报告开启清理或版本化。

现场核查已尝试 `ssh -J smYuHangLab2 shu-caselib`，跳板连接在握手阶段超时；没有执行 Docker、数据库或对象存储的远程命令。

## 用户需要决定的边界

- 普通删除和真正停用有什么区别；已发布案例如何显示被停用的引用。
- 回收站保留期限、谁可以恢复/永久清理。
- 被旧案例引用的旧文件是否长期保留；有限保留时，如何向用户说明历史阅读能力。

资料区列表可公开、内容/下载仍按 public/campus/restricted 的独立权限规则判断，沿用既有产品决定；管理员身份不额外获得私人内容读取权。这里不新开草稿协作分享需求。这些剩余选择应在看懂具体流程后决定；不需要先让用户选择数据库、对象存储或复杂版本化术语。
