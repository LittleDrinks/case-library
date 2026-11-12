# Penpot 工具

设计使用[服务器上的 Penpot](../../deploy/penpot/README.md)，代理通过该实例的官方 MCP 连接；客户端也兼容官方托管实例。浏览器中登录后，在目标设计文件选择 File → MCP Server → Connect，并保持标签页活跃。自部署的 MCP 2.19.1 同样需要浏览器插件在线。

```sh
npm ci --prefix tools/penpot
node tools/penpot/mcp.cjs check
python3 design/mcp_client.py list
```

MCP 地址通过 `PENPOT_MCP_URL` 环境变量提供，也可以通过 `PENPOT_MCP_CONFIG` 指定含 `mcp_servers.penpot.url` 的本地 TOML 配置。默认读取仓库忽略的 `.codex/config.toml`。地址含个人凭据，只在本地配置，不写入 Git、Issue 或命令示例。

`check` 只读取当前文件和页面；`execute` 与 `tool` 可修改设计，运行前检查代码和目标文件。历史浏览器预览导出脚本依赖客户端浏览器，需要单独配置；它们不属于服务器启动依赖。

设计阶段完成后，从 Penpot 导出包含所需共享库的 `.penpot` 文件到 `design/case-library.penpot`，与文字化设计数据一起提交并 push。该文件由 Git LFS 保存，恢复时安装 Git LFS 后执行 `git lfs pull`。未导出的在线编辑不属于 Git 快照。

参考：[官方 MCP](https://help.penpot.app/mcp/)、[文件导入导出](https://help.penpot.app/user-guide/export-import/export-import-files/)、[Git LFS](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-git-large-file-storage)。
