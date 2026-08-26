---
sources:
  - https://github.github.com/gfm/
  - https://docs.github.com/en/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/basic-writing-and-formatting-syntax
  - https://docs.github.com/en/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/quickstart-for-writing-on-github
  - https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes
---
# GitHub README 居中标题块
- GitHub 没有独立的 README 标题模板规范；`<div align="center">` 包裹 logo、一级标题、徽章与一句定位，是基于 GFM 和 GitHub HTML 支持的成熟惯例。
- `<div>` 是 GFM HTML block。块内的 Markdown 与 `<div>` 开闭标签之间各保留空行，才能继续解析标题、加粗文本和 Markdown 图片链接；没有空行的内容会作为原始 HTML block 传递。
- `align="center"`、`<img src="..." alt="..." width="...">` 和图片外包裹的链接均可用；保留 `alt`，仓库内 logo 用相对路径。
- 标题块只承载项目识别与入口信息；功能、启动、账号和验证命令保持普通 Markdown。GitHub 根据标题生成目录，普通结构更利于阅读与维护。
