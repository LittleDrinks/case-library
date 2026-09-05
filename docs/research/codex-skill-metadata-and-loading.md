---
sources:
  authoring: https://learn.chatgpt.com/docs/build-skills
  app_server: https://learn.chatgpt.com/docs/app-server#skills
  parser: https://github.com/openai/codex/blob/459a79eb85400af759e9220c7bafb4429ae07516/codex-rs/skills/src/parser.rs
  host_loader: https://github.com/openai/codex/blob/459a79eb85400af759e9220c7bafb4429ae07516/codex-rs/ext/skills/src/loader/host.rs
  optional_metadata: https://github.com/openai/codex/blob/459a79eb85400af759e9220c7bafb4429ae07516/codex-rs/ext/skills/src/loader/metadata.rs
  watcher: https://github.com/openai/codex/blob/459a79eb85400af759e9220c7bafb4429ae07516/codex-rs/app-server/src/skills_watcher.rs
  turn_context: https://github.com/openai/codex/blob/459a79eb85400af759e9220c7bafb4429ae07516/codex-rs/core/src/session/turn_context.rs
  file_reads: https://github.com/openai/codex/blob/459a79eb85400af759e9220c7bafb4429ae07516/codex-rs/ext/skills/src/host_outcome.rs
  model: https://github.com/openai/codex/blob/459a79eb85400af759e9220c7bafb4429ae07516/codex-rs/skills/src/model.rs
---
# Codex Skill 元数据与加载
## 格式
Skill 以包含 `SKILL.md` 的目录组织，可附带 `references/`、`assets/`、`scripts/`。官方编写规范要求 YAML frontmatter 包含 `name` 和 `description`；初始目录只提供元数据，选用后读取正文，再按需读取配套资源。
```yaml
---
name: sizheng-case-generator
description: 按课程要求生成或润色思政案例与教学设计。
---
```
运行时解析器与编写辅助脚本不同。固定源码中的解析器允许名称缺失时使用目录名，要求描述非空；名称最长 64 字符，可选 `metadata.short-description`。`quick_validate.py` 是编写辅助检查，不能代替运行时目录、解析和加载实现。
`agents/openai.yaml` 提供可选的 `interface`、`dependencies` 和 `policy`：展示名、短描述、图标、默认提示词、工具声明及隐式调用策略。可选文件解析失败会被忽略并记录告警，不阻止有效的 `SKILL.md` 加载。主文件无法解析的条目不进入成功加载目录；解析依赖声明不等于实际运行工具或审核生成质量。
App Server 文档中从 `SKILL.json` 读取界面与依赖的表述，与编写文档和固定源码的 `agents/openai.yaml` 不一致；采用后两者共同支持的格式。
## 更新
普通本地 Skill 发生变化后，App Server watcher 清理发现缓存并发出 `skills/changed`；新一轮请求重新取得 Skill 目录。API 也支持 `skills/list` 的 `forceReload`。
`HostSkillsSnapshot` 固定目录和元数据，正文读取仍访问文件系统，并非完整内容包的字节快照。已经进入对话历史的旧指令不会因文件更新自动消失。
所核对的原生 Skill 元数据没有语义版本或会话锁版字段。插件、远程和编排器来源各有缓存边界；上述更新机制针对普通本地 Skill。结论来自固定官方源码，未实测本地二进制。
## 平台接入
接入读取标准名称、描述和可选展示信息，保留正文、模板与示例的相对目录关系。管理员上传后直接发布，试用通过普通案例工作台完成。
教师选择 Skill；版本和内容哈希由平台记录。后续执行解析当前发布内容，单次执行固定所用内容，不增加教师侧的会话锁版或版本切换操作。单次执行固定内容是平台自身的一致性约定。
真实验收分别覆盖已有稿润色、从选题生成完整案例与教学设计，展示产物、修订确认和保存恢复；二者属于验收任务，不形成两个专用管理流程。
