# 素材掌控台整合原型

打开同目录的 [HTML](material-console-prototype.html)，或在仓库根目录运行：

```sh
python3 -m http.server 18745 --bind 127.0.0.1 --directory docs/prototypes
```

浏览器地址为 `http://localhost:18745/material-console-prototype.html`。默认 D 是本轮整合方案，底部左右箭头切换 A/B/C/D，URL `?variant=` 可分享与刷新保留。

本轮问题：把已有素材掌控台搬进资料管理，保留用户喜欢的 PDF 小图标，并把详情改成约 80% 屏幕的居中浮窗，是否便于查找资料和理解使用关系？产品名称与归属模型仍未整体定稿。

实际参考来自 [MaterialExplorerView.vue](../../frontend/src/views/MaterialExplorerView.vue:252) 的工作视图、权威性/类型/公开筛选、搜索、分页与选入案例，以及 [MaterialDetailView.vue](../../frontend/src/views/MaterialDetailView.vue:118) 的主内容和素材信息两栏；网站壳与 PDF 图标沿用前轮 Claude 原型。

可操作路径：

1. 搜索文件名或来源，切换筛选和分页；翻页、筛选清除当前勾选。
2. 点击文件名打开大浮窗，左边看示例预览，右边看出处、版本、引用及时间；关闭按钮、点遮罩或 Escape 返回原列表。
3. 打开“为案例选材”，勾选教材并点击“加入当前案例”；“当前案例资料”可查看本案例专用附件和选用知识。其他案例专属附件不能勾选为共享知识。

全部为虚构示例与内存状态，刷新不保留新增选材关系。没有真实原件，下载入口禁用；预览标注为示例，不伪装为原始 PDF。私人资料只示意汇总占用。原型没有调用生产 API，也没有新增权限或生命周期规则。

已用 Chromium 独立检查桌面 1440×960、手机 390×844、独立文件打开、筛选/分页/选材/浮窗关闭与焦点。桌面浮窗宽高比均为 0.8；手机四种视图无整页横向溢出。没有页面脚本错误，未验证其他浏览器。

截图：[列表](material-console-desktop.png)、[浮窗](material-console-detail.png)、[选材](material-console-case.png)、[手机列表](material-console-mobile.png)、[手机浮窗](material-console-mobile-detail.png)。
