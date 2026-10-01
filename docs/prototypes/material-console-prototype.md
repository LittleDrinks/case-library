# 素材掌控台整合原型

打开同目录的 [HTML](material-console-prototype.html)，或在仓库根目录运行：

```sh
python3 -m http.server 18745 --bind 127.0.0.1 --directory docs/prototypes
```

浏览器地址为 `http://localhost:18745/material-console-prototype.html`。默认 D 是本轮整合方案，底部左右箭头切换 A/B/C/D，URL `?variant=` 可分享与刷新保留。

本轮问题：把已有素材掌控台搬进资料管理，保留用户喜欢的 PDF 小图标，并把详情改成约 80% 屏幕的居中浮窗，是否便于查找资料和理解使用关系？用户已认可目前的视觉方向，并确认统一检索、保留案例与共享资料的不同归属；完整名称、文件正文角色与处理规则仍在讨论。

此前版本原样保留在 [上一版快照](archive/material-console-v1/material-console-prototype.html)，浏览器地址为 `http://localhost:18745/archive/material-console-v1/material-console-prototype.html`。快照包含原 HTML、说明和七张截图；对应固定提交 `aceb18360f06565fa30a9dd1176754bff6baed6d`。

根据最新反馈，D 去掉左上方大标题，扩大工作区域、列表文字与行距；1920×945 下列表宽 1840 像素。左侧改成资料范围、权威性下拉框、类型按钮和公开过滤，常见桌面尺寸无需在筛选栏内部滚动。手机默认折叠筛选，按需展开。

实际参考来自 [MaterialExplorerView.vue](../../frontend/src/views/MaterialExplorerView.vue:252) 的工作视图、权威性/类型/公开筛选、搜索、分页与选入案例，以及 [MaterialDetailView.vue](../../frontend/src/views/MaterialDetailView.vue:118) 的主内容和素材信息两栏；网站壳与 PDF 图标沿用前轮 Claude 原型。

可操作路径：

1. 搜索文件名、来源或相关案例，输入后自动更新结果，亦可按 Enter 或点击搜索；支持中文输入期间保留输入框。结果上方显示当前条件，可逐项取消或清除全部。筛选和搜索条件可分享、刷新恢复；同一目标案例内，勾选跨搜索、筛选和翻页保留。已选项即使被当前条件隐藏，也能在选材栏查看并取消。
2. 点击文件名打开大浮窗，左边看示例预览，右边看出处、版本、引用及时间；右上方超链接图标在新标签页打开同一份素材的独立详情页，地址例如 `?detail=reading`，该页可返回资料管理。浮窗的关闭按钮、点遮罩或 Escape 返回原列表。
3. 打开“为案例选材”，勾选教材并点击“加入当前案例”，直接进入示例案例的资料区，新加入资料显示在前面并聚焦资料区；不显示成功浮窗或留页提示。“选用已有资料”和浏览器返回可回到列表；“当前案例资料”可查看本案例专用附件和选用的共享资料。其他案例专属附件不能勾选为共享资料。

全部为虚构示例与内存状态，刷新不保留新增选材关系。没有真实原件，下载入口禁用；预览标注为示例，不伪装为原始 PDF。新版所有视图已删除私人资料占用提示。加入流程只模拟全部成功；已确认的部分失败留页、仅重试未成功项，尚未做故障模拟或真实 API 验证。资料包与 PDF 正文处理仅记录产品决定和研究，尚未加入本原型。

已用 Chromium 独立检查桌面 1920×945、1440×960、1366×768、手机 390×844、独立文件打开、搜索与组合筛选、URL 恢复、分页、选材、浮窗关闭与焦点，以及真实新标签页跳转和返回。中文组合输入通过合成事件验证，未连接操作系统输入法。桌面浮窗宽高比均为 0.8；三种桌面尺寸筛选栏无需滚动，手机四种视图与独立详情无整页横向溢出。没有页面脚本错误，未验证其他浏览器。

本轮 66 项浏览器检查通过，包括跨搜索／筛选／翻页保留勾选、直接返回案例、资料区显示五项且新条目在前、无成功浮窗、浏览器返回和旧版快照可打开。详见 [检查记录](material-console-browser-check.json)。

截图：[列表](material-console-desktop.png)、[浮窗](material-console-detail.png)、[独立详情](material-console-standalone.png)、[跨搜索保留勾选](material-console-selection.png)、[加入后返回案例](material-console-case.png)、[手机列表](material-console-mobile.png)、[手机浮窗](material-console-mobile-detail.png)、[手机独立详情](material-console-mobile-standalone.png)。
