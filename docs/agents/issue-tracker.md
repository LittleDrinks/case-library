# Issue tracker: GitHub

本仓库的任务和规格维护在 GitHub Issues，通过 `gh` CLI 操作；仓库由当前 checkout 的 Git remote 确定。

## 读取与发布

- 开始任务时，读取目标 issue 正文、标签、评论及关联决定；采用后续有效决议。
- 读取单票：`gh issue view <number> --comments`；列表按实际标签、状态和父子关系筛选。
- 创建、编辑和评论分别使用 `gh issue create`、`gh issue edit`、`gh issue comment`。多行正文写入临时文件，以 `--body-file` 传入。
- 发布格式、证据和隐私边界遵循根目录 `AGENTS.md` 第 5 节；发布后读回内容及关联。
- 关闭前核对现有实现、未完成验收和依赖；规格发布、实施、合并和部署按各自授权执行。

## Pull requests as a triage surface

**PRs as a request surface: no.**

## Wayfinder

- 使用 Wayfinder 时先读取其 `SKILL.md`。路线图使用 `wayfinder:map`，调查、原型、产品决策和任务使用对应 `wayfinder:<type>` 标签。
- 父子关系使用 GitHub 原生 sub-issues，阻塞关系使用原生 issue dependencies。命令以当前 `gh` 帮助为准。
- API 关联使用 issue 的数字数据库 ID，通过 `gh api repos/{owner}/{repo}/issues/<number> --jq .id` 读取；编号和 node ID 不能代替数据库 ID。
- 就绪判断读取当前父子和阻塞关系，并核对依赖需要的实际接口或产物；标签不能代替验收证据。
- 决定记录在相关 issue，路线图保存有意义的来源链接。

## Skill 的发布与读取约定

- “publish to the issue tracker”：发布到 GitHub Issues。
- “fetch the relevant ticket”：读取目标 issue 及其评论和关联决定。
- 使用 triage 时先读取 `docs/agents/triage-labels.md`，按其中映射使用标签。
