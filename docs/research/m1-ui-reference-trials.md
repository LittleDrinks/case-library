---
sources:
  ck_demo: https://ckeditor.com/ckeditor-5/demo/collaboration/
  ck_collaboration: https://support.ckeditor.com/hc/en-us/articles/360000013420-What-are-CKEditor-5-collaboration-features
  google_docs: https://workspace.google.com/products/docs/
  google_suggestions: https://support.google.com/docs/answer/6033474?hl=zh-Hans
  github_review: https://docs.github.com/en/pull-requests/how-tos/review-pull-requests/reviewing-proposed-changes-in-a-pull-request
  zotero_basics: https://www.zotero.org/support/quick_start_guide
  zotero_related: https://www.zotero.org/support/related
  zotero_tags: https://www.zotero.org/support/collections_and_tags
  kumu_examples: https://kumu.io/kumu
  kumu_focus: https://docs.kumu.io/guides/focus
  kumu_pricing: https://docs.kumu.io/frequently-asked-questions/what-pricing-plans-does-kumu-have
  chatgpt_research: https://help.openai.com/en/articles/10500283-deep-research
  skill_directory: https://www.skills.sh/
  frontend_design: https://raw.githubusercontent.com/anthropics/skills/main/skills/frontend-design/SKILL.md
  interface_review: https://raw.githubusercontent.com/vercel-labs/agent-skills/main/skills/web-design-guidelines/SKILL.md
---
# M1 界面参考与试用
保留校徽、品牌配色和已确认功能；探索工作台、审核与资源浏览的布局、交互和组件细节。先挑选具体行为，再把选中的行为放进同一套可点击原型。颜色、圆角或某张截图不单独决定方案。
## 五个互补入口
| 产品与入口 | 本轮核实 | 账号与费用条件 | 主要挑选点 |
| --- | --- | --- | --- |
| [CKEditor 协作演示](https://ckeditor.com/ckeditor-5/demo/collaboration/) | 匿名 Chromium 已加载可编辑正文、右侧批注和红绿修订；未执行接受或拒绝。官方提供 Comments、Track Changes、Revision History（`ck_demo`） | 本轮无登录、无付费即进入演示；生产集成的商业许可另议，不因演示开放而认定可免费集成 | 正文与侧栏联动、修改前后如何同时看清、长文工具栏 |
| [Google Docs 新建文档](https://docs.google.com/document/create) | 核对官方操作说明，未登录亲测。建议模式保留原文，删除加删除线；可预览接受或拒绝全部建议后的文档（`google_suggestions`） | 新建需要 Google 账号；官方说明任何 Google 账号可创建文档，部分高级功能另需 Workspace；本轮不要求购买高级功能（`google_docs`） | “评论”与“建议修改”的区别、接受前预览 |
| [Zotero 桌面版](https://www.zotero.org/download/) | 核对官方文档，未启动用户文献库。列表选中项在右栏显示资料；Related 可直接跳到相关条目，标签可以逐步筛选（`zotero_basics`、`zotero_related`、`zotero_tags`） | 桌面程序免费；安装耗时不计入试用时间。本轮不涉及付费附件同步；未亲测当前安装向导或账号提示（`zotero_basics`） | 不画图也能看懂关系、详情抽屉、筛选后保留上下文 |
| [Kumu 官方 Community Network](https://kumu.io/kumu/community-network) | 匿名 Chromium 已渲染网络和类型筛选；未完成逐项操作测试。官方 Focus 支持邻居范围扩展、收缩及搜索后构建局部图（`kumu_examples`、`kumu_focus`） | 查看此公开示例本轮无需账号或付款；创建项目需要账号，公开项目免费，私有项目收费（`kumu_pricing`） | “人—项目”“项目—组织”等关系视角切换、只看相关邻居 |
| [ChatGPT](https://chatgpt.com/) 的 Deep research | 核对官方流程，未代用户发起任务。运行前可调整计划，运行中可看进度并中断，报告带活动历史和来源（`chatgpt_research`） | 实际入口、地区支持和次数取决于账号与套餐；不能承诺当前账号免费可用。已有入口再试，否则看官方帮助页中的界面示例，不必购买（`chatgpt_research`） | 当前在做什么、哪些已完成、如何停止或改方向 |
## 每项两三分钟怎么试
### CKEditor：点击批注后，能否直接理解要改哪里
向下滚到演示正文，停留在 Collaboration 标签。先点击右侧一条已有批注，再点正文对应高亮；比较视线移动和定位是否自然。找到已有替换建议，分别观察删除的旧字、插入的新字以及接受/拒绝入口。最后滚到较后面的段落，尝试选中文字并找加粗入口。只使用演示中的样本文字。
挑选：喜欢侧栏卡片随位置排列，还是固定显示当前批注；喜欢正文红绿对照，还是先后文并排。不要照搬网页的营销横幅和浮动销售聊天框。
### Google Docs：先看改后效果，再决定接受
在自己的空白文档输入“学生讨论案例。教师总结要点。”；切到建议模式，将“讨论”改成“分组讨论”。点建议补充一句“便于各组表达不同观点”，再用“工具 → 查看建议的修改”切换接受/拒绝后的预览。最后接受一次，观察正文和建议卡片怎样收起。未登录或网络不可用时，可直接对照官方中文说明里的界面。
挑选：改前/改后切换是否比两段纯文本容易理解；批注意见与修改建议是否应在同一卡片内分层呈现。本项目已确认总评与关联批注至少一项，不能因参考产品有某个必填框而改变这条规则。
### Zotero：不用图谱，从一个资料走到相关资料
在独立的临时分类中手工建三个不含真实资料的条目，命名“案例 A”“课程 B”“素材 C”。给 A、C 加同一标签，在 A 的 Related 中关联 C；先点标签筛选，再从 A 右侧 Related 点击 C。观察进入 C 后是否还能知道自己来自 A、是否容易回到原筛选结果。Related 默认表达双向关联，不能直接替代案例库中“引用自”“适用于课程”等有方向和类型的关系（`zotero_related`）。
挑选：老师是不是只需要“相关课程 / 可用素材 / 引用案例”三组可点击列表；哪些任务确实还需要一张局部图。不要为试用改动已有文献库。
### Kumu：先选关系问题，再缩小网络
打开示例后，先在顶部“Click to see filtered views”选择“People & Projects”，再换“Projects & Organizations”；对比同一资源集合按不同关系组织的可读性。选一个可见节点，按官方 Focus 操作聚焦其邻居，再扩大一层、缩回一层，最后退出聚焦。Focus 的入口与快捷键以当前界面为准；本轮只核实了页面和控件加载，没有逐个点验（`kumu_focus`）。
挑选：是否需要先问“我想看哪种关系”；关系类型和连接理由应放在哪儿。该示例初始全图仍很密，不作为目标首屏，也没有证明本系统万级数据的性能。案例库原型应同时比较关联列表、按主题聚合、局部关系图，选老师最快找到答案的一种或组合。
### ChatGPT：只观察前两分钟的进度表达
仅在已有 Deep research 权限时，用不含项目数据的问题，例如“比较图书馆与博物馆开展大学生公共教育的常见方式”。先看计划是否允许调整；开始后观察两分钟：当前步骤、活动记录、来源和停止入口是否清楚。可中断任务，不必等待完整报告；发起任务可能消耗账号额度。没有入口则看官方帮助页，不为界面参考开通套餐。
挑选：默认显示一句当前进度，还是展开步骤列表；完成步骤是否折叠；遇到失败后是否仍知道哪些结果可用。阶段标题来自真实执行状态或明确标注的摘要，不能用动画假装模型已完成某项推理。
## 可进入原型的候选组合
| 教师任务 | 候选设计 | 要在试用中判断的事 |
| --- | --- | --- |
| 写长文、选段加批注 | 持续可达的格式工具栏 + 正文高亮 + 右侧当前批注 | 不回到页首能否完成编辑；点击正文后能否继续输入 |
| 看修改、决定是否采纳 | 正文差异高亮 + 改前/改后预览 + 同位置接受/拒绝 | 能否指出具体变动，并预测接受后的结果 |
| 退回给老师修改 | 总评输入 + 可选关联批注清单 + 提交前预览 | 不写总评时能否仅凭选中批注提交；长总评能否展开阅读 |
| 找到可用案例和依据 | 搜索结果 + 按关系分组的详情 + 按需局部图 | 能否回答“为何相关”和“下一步如何使用”，而非只看到连线 |
| 等待 AI 工作 | 当前阶段摘要 + 可展开活动记录 + 独立任务/工具状态 | 一次工具失败会不会被误读为整轮成功；耗时是否真实更新 |
GitHub 的审核把定位评论先汇集为待提交 review，再和总评、审核动作一起提交，证明“局部意见汇总到一次审核”已有成熟路径（`github_review`）。这里只借鉴组织关系，不引入代码审查术语、分支规则或其必填条件。
万级资源是后台数据规模；本轮未测量渲染上限或检索延迟。原型比较先用同一组教师任务和同一份样本：找到适合某门课的案例、看出案例采用哪些素材、从某份素材找到相关案例、解释两条资源为何相关。记录是否完成、首次正确点击、绕路次数及耗时；不以节点数量或主观漂亮程度代替可用性。
## 设计 Skill 候选
| Skill | 已检查内容 | 用法与边界 |
| --- | --- | --- |
| `anthropics/skills` 的 `frontend-design` | 已读上游完整技能；要求从用户、主题、品牌出发，先做字体/色彩/布局计划，再构建与截图自评。目录显示约 884.1K installs；仓库 API 返回 176207 stars，均为本轮快照（`skill_directory`、`frontend_design`） | 适合原型 agent 探索两种布局。校徽、品牌色、已确认交互和教师任务优先；不能让追求视觉独特性盖过可用性。尚未安装或运行 |
| `vercel-labs/agent-skills` 的 `web-design-guidelines` | 已读上游技能，流程是读取最新规范后检查 UI 代码并输出定位；目录约 631.4K installs，仓库 API 返回 31177 stars（`skill_directory`、`interface_review`） | 适合独立检查键盘、焦点、表单、状态反馈等细节；本轮只评估技能用途，未执行该审查。尚未安装 |
建议先让用户从上述试用中挑三至五个具体行为，再把同一任务交给原型 agent 做两种可点击布局。独立 reviewer 在同一原型工作树审查，用户实际操作后再确定产品方案；不靠安装量或 agent 自评认定设计通过。
## 访问证据
匿名浏览器只执行导航、等待与滚动，没有注册、付费、提交评论、上传用户资料或更改正式系统。CKEditor 与 Kumu 的实际页面已截图；其余产品是第一方文档核实，试用步骤待用户执行。
原始搜索结果、网页读取输出、探针脚本、两轮浏览器 JSON、DOM 文本及截图保存于主仓 `.scratch/m1-285-uat/wayfinder/research-logs/`。核心证据为 `public-demos-probe-followup.json`、`ckeditor-followup.png`、`kumu-followup.png`；它们只证明匿名页面加载及可见界面，不证明全部功能或校园网络可达性。
