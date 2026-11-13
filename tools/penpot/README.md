# Penpot 工具

设计使用[服务器上的 Penpot](../../infra/penpot/README.md)，代理通过该实例的官方 MCP 连接；客户端也兼容官方托管实例。浏览器中登录后，在目标设计文件选择 File → MCP Server → Connect，并保持标签页活跃。自部署的 MCP 2.19.1 同样需要浏览器插件在线。

```sh
npm ci --prefix tools/penpot
node tools/penpot/mcp.cjs check
node tools/penpot/mcp.cjs list
```

MCP 地址通过 `PENPOT_MCP_URL` 环境变量提供，也可以通过 `PENPOT_MCP_CONFIG` 指定含 `mcp_servers.penpot.url` 的本地 TOML 配置。默认读取仓库忽略的 `.codex/config.toml`。地址含个人凭据，只在本地配置，不写入 Git、Issue 或命令示例。

`check` 只读取当前文件和页面；`execute` 与 `tool` 可修改设计，运行前检查代码和目标文件。

## 连续预览原型

打开设计中的「原型 · 完整流程」，选择「01 · 首页 · 校园搜索」画板后启动预览。该页面保留原生画板跳转，点击搜索入口、钱伟长图书馆案例或素材会在当前标签页进入对应画板。

Penpot 2.19.1 的原生跳转要求目标画板在同一个 Page；「打开网址」固定新开标签页，没有当前标签页选项。按模块拆分的页面中，跨 Page 交互使用了网址，因此不能用这些入口验收连续流程。迁移域名和文件 ID 只修正链接目标，不改变打开方式。

首页细调从「浏览 · 首页与搜索」的「01 · 首页 · 校园搜索」开始；校园照片、渐变遮罩、文字、推荐内容已分组，可以分别编辑。完整原型与模块页面中的画板是分别保存的，编辑后需核对两处是否一致。组织需要连续演示的画板时，应保留在同一个 Page，通过画板命名和 Flow 入口区分流程。交互验收同时检查目标内容和浏览器标签页数量。

依据：[交互目标验证](https://github.com/penpot/penpot/blob/2.19.1/frontend/src/app/plugins/shape.cljs#L83)、[预览器打开网址的实现](https://github.com/penpot/penpot/blob/2.19.1/frontend/src/app/main/ui/viewer/shapes.cljs#L135)。

## 更换原型链接的站点

修改本机 `deploy/penpot/.env` 中的 `PENPOT_PUBLIC_URI`，或者通过同名环境变量覆盖。部署配置只控制服务地址；设计里已经保存的原型链接需单独迁移：

```sh
node tools/penpot/links.cjs
node tools/penpot/links.cjs --apply
```

默认检查 MCP 当前打开的设计，`--apply` 才写入。迁移前会检查目标页面和画板，并保存一个命名版本。改变域名时保留当前文件 ID；从另一实例导入后，可用 `--from-file-id <原文件ID>` 同时替换旧文件 ID。用 `--file-id <目标文件ID>` 可以限定操作对象，`--env-file <路径>` 可以选择其他部署配置。

命令处理旧版 `#/view` 和新版 `?screen=viewer` 原型地址，保留目标页面、画板及预览参数，普通外部网页和未指定的其他设计文件保持原地址。公共地址必须为 HTTP(S)，不得包含凭据或查询参数。需要 Node.js 22 或更高版本。

```sh
node --test tools/penpot/links.test.cjs
```

设计阶段完成后，从 Penpot 导出包含所需共享库的 `.penpot` 文件到 `design/case-library.penpot`，提交并 push。该文件由 Git LFS 保存，恢复时安装 Git LFS 后执行 `git lfs pull`。未导出的在线编辑不属于 Git 快照。`design/` 保存设计文件和原始素材，操作工具维护在本目录。

参考：[官方 MCP](https://help.penpot.app/mcp/)、[文件导入导出](https://help.penpot.app/user-guide/export-import/export-import-files/)、[Git LFS](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-git-large-file-storage)。
