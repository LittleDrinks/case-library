# ADR 0013：OnlyOffice 主编辑器（自研块编辑器退役）

状态：已定案（v2.1）

## 决策

- 案例正文真源为 docx（`files/cases/`，gitignore）；blocks JSON 保留作回写副本，供详情页轻量渲染、检索语料、AI 上下文使用。
- OnlyOffice Document Server docker 部署（`docker-compose.yml`，8081，JWT 开启）；server.py 出 config（JWT HS256 签名、document.key=caseId+docxVer、callbackUrl），回调 status 2/6 落盘并回写 blocks+bump key。
- AI 生成内容以真实 track-changes 进入文档：服务端用 python-docx oxml 把新段落包 `w:ins`（替换模式旧段包 `w:del`/`w:delText`），教师在 OO 修订面板逐条接受/拒绝。
- 批注线程保留自研侧栏（annotations 表），定位走 Automation API 文本搜索；句级引用锚点维持 quote 文本指纹，不做 docx bookmark 手术；版本快照=docx 副本。
- 自研块编辑器保留为 OO 不可达时的回退。

## 理由

自研编辑器是演示用草率产物；OnlyOffice 提供类 Word 体验且原生修订模式恰好承载"AI 生成以修订出现、教师接受/拒绝"的形态，不自造轮子。

## 已知取舍

iframe 内选区能力（选区批注/改写）不可用，以"以修订追加/新节"代替；编辑器内未保存的改动不进大纲/自检（已开 forcesave+UI 提示）。
