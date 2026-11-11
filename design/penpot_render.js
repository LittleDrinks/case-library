const UI = {
  brand: '#BA1C22', brandSoft: '#F8EEED', ink: '#202B3C', muted: '#626D7A',
  subtle: '#818A95', line: '#DCE1E7', surface: '#F4F6F8', white: '#FFFFFF',
  green: '#20744A', greenSoft: '#E8F3EC', amber: '#9C6508', amberSoft: '#FAF0DC',
  error: '#B3261E', warm: '#F6F4EF', warmLine: '#E9E3DA',
};
const FLOW_DATA = {
  foundation: { title: '上海大学 · “强国有我”思政案例库', rows: ['钱伟长图书馆——科学家精神的大思政课堂', '《智能控制》：高挑战项目牵引新工科育人', '微电子赋能生物医药——中瑞先进技术研究院的科教融合实践'], cards: ['公开教学案例|4', '可见教学素材|77', '教材知识资源|2'] },
  motion: { title: '滚动与页面动效', rows: ['进入视口|淡入 200ms，上移 16px', '背景视差|背景位移为前景的一半', '页面切换|淡入淡出 160ms', '减少动态效果|关闭非必要位移与过渡'], cards: ['只播放一次|避免反复跳动', '不阻塞检索|首屏立即可用', 'prefers-reduced-motion|完整支持'] },
  collections: { title: '专题集', rows: ['科学家精神专题|6 个案例', '红色校史思政|4 个案例', '产教融合课程思政|5 个案例'], cards: ['钱伟长图书馆|科学家精神', '任新振的“医工交叉”科技报国路|科学家精神', '红色校史中的上大故事|红色校史'] },
  preferences: { title: '教师偏好', rows: ['课程|智能控制', '学段|本科高年级及研究生', '学科|控制科学与工程', '思政元素|创新、奋斗'], cards: ['为你推荐|基于已保存偏好', '推荐理由|课程与思政元素匹配', '未设置偏好|展示全站优质案例'] },
  'search-metadata': { title: '多条件检索', rows: ['学科|工学、医学', '案例类型|科技创新与科技报国类', '课程|智能控制', '思政元素|创新、奋斗'], cards: ['《智能控制》|课程与标签均匹配', '微电子赋能生物医药|工学与医学交叉', '任新振的科技报国路|人物传记类'] },
  favorites: { title: '我的收藏', rows: ['钱伟长图书馆|已收藏', '《智能控制》|已收藏', '微电子赋能生物医药|已收藏'], cards: ['我的投稿|4', '我的收藏|3', '退回修改|1'] },
  'create-submission': { title: '投稿案例', rows: ['课程|智能控制', '案例类型|科技创新与科技报国类', '学科|控制科学与工程', '思政元素|创新、奋斗'], cards: ['空白案例|从空白草稿开始', '项目牵引教学案例|含完整教学结构', '课程思政案例|含理论映射与讨论题'] },
  'admin-stats': { title: '案例供给统计', rows: ['公开已发布|4 个案例', '全部案例|6 个案例', '统计口径|每个案例只计一次'], cards: ['人物传记类|35%', '科技创新类|28%', '校本实践类|18%'] },
  accounts: { title: '账号与资格', rows: ['王老师|教师 · 正常', '李老师|教师 · 校内资格待审批', '陈老师|管理员 · 正常', '赵老师|已停用 · 可恢复'], cards: ['正常账号|128', '待审批申请|6', '已停用|2'] },
  materials: { title: '素材包管理', rows: ['指导纲要.pdf|主文件 · 处理成功', '章节解读.md|处理成功', '课堂照片.png|待确认', '旧版本 v1|已有引用继续保留'], cards: ['待处理|2', '待确认|1', '已确认版本|3'] },
  'restricted-sharing': { title: '指定教师授权', rows: ['王老师|可阅读 · 2026-12-31 前', '李老师|已撤回', '陈老师|待确认授权范围'], cards: ['当前可访问|2 人', '已撤回|1 人', '不改变所有者|私密'] },
  'self-check': { title: '投稿前可选自检', rows: ['标题与正文|已完成', '必填标签|已完成', '事实与来源|2 项待核实', '结构建议|可增加讨论题'], cards: ['修改后重查|不自动改正文', '继续投稿|不阻塞必填规则', '转为批注|由教师选择'] },
  announcements: { title: '平台公告', rows: ['课程思政案例征集|已发布', '素材库更新说明|草稿', '寒假审核安排|已撤下'], cards: ['全校教师|可见范围', '置顶展示|1 条', '定时发布|待产品确认'] },
  'source-review': { title: '来源失效复核', rows: ['政策文件链接失效|影响 3 个案例', '素材访问级别变化|影响 1 个案例', '新版内容差异|待作者复核'], cards: ['待处理|4', '已处理|2', '保留固定版本引用|是'] },
  'conversation-export': { title: '导出当前对话', rows: ['Markdown 阅读文本|已选择', 'JSON 分析数据|已选择', '来源与 Skill 绑定|按权限导出', '历史缺失字段|明确标注'], cards: ['仅导出当前快照|不上传', '运行尚未结束|注明状态', '敏感信息|自动排除'] },
  'web-sources': { title: '公开网页核验', rows: ['教育部官网|正文读取成功', '新华网|正文读取成功', '上海大学新闻网|需人工确认完整性'], cards: ['已读取段落|12', '引用对应原文|可定位', '确认后加入资料区|不自动挂载'] },
  'teaching-pack': { title: '教学交付包', rows: ['案例正文|已确认', '教学设计|已确认', '讨论题|待确认', 'PPT 提纲|生成中', '素材汇编|已确认'], cards: ['本科版|完整', '研究生版|待生成', 'DOCX 来源清单|自动包含'] },
  'document-extract': { title: 'Word 内容提取', rows: ['正文段落|42 项成功', '内嵌图片|2 项成功', '可编辑表格|1 项待确认', '复杂文本框|1 项部分失败'], cards: ['保留成功部分|是', '列出已知遗漏|明确', '接受写入|由教师确认'] },
  'ai-expanded': { title: 'AI 对话宽屏', rows: ['当前会话与输入位置|保留', '滚动位置|还原后恢复', '修改预览|继续可操作'], cards: ['展开为宽屏|当前状态', '还原侧栏|Esc', '减少动态效果|支持'] },
  'selection-comments': { title: '划词与批注', rows: ['选中文字|“项目牵引的教学模式”', '可选评论|补充课堂实施条件', '锚点变化|原文已变动', '撤销恢复|恢复位置与讨论状态'], cards: ['保留选区高亮|是', '失效后仍可查看引用|是', '确认后才建立批注|是'] },
  relationships: { title: '关系浏览', rows: ['共同主题|科学家精神', '真实引用|政策文件与案例', '检索命中|仅表示本次查询'], cards: ['当前命中|167 条', '当前展示|20 条', '继续展开|保留分页与覆盖范围'] },
  'word-templates': { title: 'Word 导出版式', rows: ['学校通用模板|默认', '课程论文模板|已保存', '简洁阅读模板|已保存'], cards: ['标题字体|Noto Serif SC', '正文字体|Noto Sans SC 12pt', '来源清单与编号|完整保留'] },
  'version-snapshot': { title: '创建快照', rows: ['创建中|按钮保持同一挂载状态', '409 冲突|保留当前稿并提示刷新', '恢复|撤销后可重新创建'], cards: ['不显示虚假成功|是', '当前正文不丢失|是', '权限规则不变|是'] },
};

function uiRect(board, name, x, y, width, height, fill, radius = 0, stroke = null) {
  const shape = penpot.createRectangle();
  shape.name = name; shape.x = board.x + x; shape.y = board.y + y;
  shape.resize(width, height); shape.fills = [{ fillColor: fill, fillOpacity: 1 }];
  if (radius) shape.borderRadius = radius;
  if (stroke) shape.strokes = [{ strokeColor: stroke, strokeWidth: 1, strokeStyle: 'solid', strokeAlignment: 'center' }];
  board.appendChild(shape); return shape;
}
function uiText(board, name, characters, x, y, size = 14, color = UI.ink, weight = 400, width = 0) {
  const shape = penpot.createText(String(characters));
  shape.name = name; shape.fontFamily = 'Noto Sans SC'; shape.fontSize = String(size);
  shape.fontWeight = String(weight); shape.fills = [{ fillColor: color, fillOpacity: 1 }];
  shape.x = board.x + x; shape.y = board.y + y;
  if (width) { shape.resize(width, Math.max(22, size * 1.6)); shape.growType = 'auto-height'; }
  else shape.growType = 'auto-width';
  board.appendChild(shape); return shape;
}
function uiBoard(spec) {
  const [width, height] = spec.viewport.split('x').map(Number);
  const board = penpot.createBoard(); board.name = spec.fullName;
  board.x = spec.x; board.y = spec.y; board.resize(width, height);
  board.fills = [{ fillColor: spec.layout === 'workbench' ? UI.warm : UI.surface, fillOpacity: 1 }];
  return board;
}
function uiComponent(board, name, x, y) {
  const component = penpot.library.local.components.find(item => item.name === name);
  if (!component) throw new Error(`缺少组件 ${name}`);
  const instance = component.instance(); instance.x = board.x + x; instance.y = board.y + y;
  board.appendChild(instance); return instance;
}
function uiHeader(board, mobile = false, showUser = true) {
  if (!mobile) {
    const header = uiComponent(board, 'Site Header', 0, 0);
    if (!showUser) {
      const user = header.children.find(shape => shape.name === '当前用户');
      if (user) user.hidden = true;
    }
    return;
  }
  uiRect(board, '移动头部背景', 0, 0, board.width, 72, UI.white);
  uiText(board, '移动品牌', '上海大学 · “强国有我”思政案例库', 20, 22, 14, UI.brand, 600, 300);
  uiText(board, '移动导航', '首页    我的案例    资源检索    管理', 20, 50, 11, UI.muted, 400, 340);
}
const ADMIN_LABELS = ['案例管理', '专题与公告', '素材入库', '数据统计', '账号与权限', 'Skill 管理', '标签目录', '平台 AI'];
function adminNavIndex(flow) {
  if (flow === 'collections' || flow === 'announcements') return 1;
  if (flow === 'materials' || flow === 'source-review') return 2;
  if (flow === 'admin-stats') return 3;
  if (flow === 'accounts' || flow === 'restricted-sharing') return 4;
  return 0;
}
function uiAdminNavigation(board, active = 0, mobile = false) {
  if (!mobile) {
    uiComponent(board, 'Admin Navigation', 32, 108);
    uiRect(board, '当前导航高亮', 44, 180 + active * 44, 206, 36, UI.brandSoft, 6);
    uiText(board, '当前导航文字', ADMIN_LABELS[active], 64, 188 + active * 44, 14, UI.brand, 600);
    return;
  }
  uiRect(board, '移动管理导航背景', 12, 82, board.width - 24, 42, UI.white, 6, UI.line);
  uiText(board, '移动管理导航', '案例  专题  素材  统计  账号  Skill  标签  AI', 26, 95, 12, UI.brand, 600, 320);
}
function uiTitle(board, title, subtitle, x, y, width) {
  uiText(board, '页面标题', title, x, y, 26, UI.ink, 600, width);
  if (subtitle) uiText(board, '页面说明', subtitle, x, y + 40, 12, UI.muted, 400, width);
}
function uiPanel(board, name, x, y, width, height) {
  return uiRect(board, name, x, y, width, height, UI.white, 9, UI.line);
}
function uiButton(board, label, x, y, primary = true, width = 112) {
  uiRect(board, `按钮-${label}`, x, y, width, 38, primary ? UI.brand : UI.white, 6, primary ? null : UI.line);
  uiText(board, `按钮文字-${label}`, label, x + 16, y + 10, 12, primary ? UI.white : UI.muted, 600, width - 32);
}
function uiRows(board, rows, x, y, width, limit = 5) {
  rows.slice(0, limit).forEach((row, index) => {
    const [title, meta = ''] = row.split('|');
    const top = y + index * 62;
    const metaWidth = width < 520 ? 110 : 174;
    if (index) uiRect(board, '行分隔线', x, top - 10, width, 1, UI.line);
    uiText(board, `行标题-${title}`, title, x + 16, top, 13, UI.ink, 500, width - (meta ? metaWidth + 64 : 32));
    if (meta) {
      const text = uiText(board, `行说明-${meta}`, meta, x + width - metaWidth - 16, top + 2, 11, meta.includes('失败') || meta.includes('失效') ? UI.error : UI.muted, 400, metaWidth);
      text.align = 'right';
    }
  });
}
function uiCards(board, cards, x, y, width, mobile = false) {
  const gap = 16;
  const count = mobile ? 1 : Math.min(cards.length, 3);
  const cardWidth = mobile ? width : (width - gap * (count - 1)) / count;
  cards.slice(0, mobile ? 2 : 3).forEach((card, index) => {
    const [title, meta = ''] = card.split('|');
    const left = mobile ? x : x + index * (cardWidth + gap);
    const top = mobile ? y + index * 118 : y;
    uiPanel(board, `卡片-${title}`, left, top, cardWidth, mobile ? 102 : 148);
    uiText(board, `卡片标题-${title}`, title, left + 16, top + 18, mobile ? 13 : 15, UI.ink, 600, cardWidth - 32);
    uiText(board, `卡片说明-${meta}`, meta, left + 16, top + (mobile ? 48 : 58), 12, UI.muted, 400, cardWidth - 32);
  });
}
function uiBars(board, x, y, width, kind = 'type') {
  const datasets = {
    type: [['人物传记', 35], ['科技创新', 28], ['校本实践', 18], ['其他类型', 19], ['暂未分类', 0]],
    subject: [['工学', 42], ['医学', 21], ['人文社科', 18], ['理学', 12], ['其他学科', 7]],
  };
  const bars = datasets[kind];
  const maximum = Math.max(40, ...bars.map(([, value]) => value));
  bars.forEach(([label, value], index) => {
    const top = y + index * 52;
    uiText(board, `分布-${label}`, label, x, top, 12, UI.ink, 500, 130);
    uiRect(board, '分布轨道', x + 140, top + 2, width - 220, 14, UI.surface, 7);
    if (value) uiRect(board, '分布数值', x + 140, top + 2, (width - 220) * value / maximum, 14, index % 2 ? UI.muted : UI.brand, 7);
    uiText(board, '分布百分比', `${value}%`, x + width - 66, top, 12, UI.ink, 600, 60);
  });
}
function uiGeneric(board, spec, x, y, width, mobile = false) {
  const data = FLOW_DATA[spec.flow];
  uiCards(board, data.cards, x, y, width, mobile);
  uiRows(board, data.rows, x, y + (mobile ? 254 : 184), width, mobile ? 3 : 5);
  if (!mobile) {
    uiButton(board, spec.status === 'exploratory' ? '查看方案' : '继续', x + width - 230, y + 500, true, 104);
    uiButton(board, '返回', x + width - 116, y + 500, false, 104);
  }
}
function uiHome(board, spec, mobile) {
  const width = board.width;
  const variant = mobile ? 'mobile' : 'desktop';
  if (!storage.campusImages?.[variant]) throw new Error('生成首页前需要校园图片');
  const heroWidth = width - (mobile ? 28 : 72);
  const heroHeight = mobile ? 300 : 430;
  const image = storage.campusImages[variant].clone();
  image.name = '上海大学校园湖畔';
  image.x = board.x + (mobile ? 14 : 36);
  image.y = board.y + (mobile ? 92 : 104);
  image.resize(heroWidth, heroHeight);
  image.borderRadius = 12;
  board.appendChild(image);
  const shade = uiRect(board, '图片遮罩', mobile ? 14 : 36, mobile ? 92 : 104, heroWidth, heroHeight, '#1A2A3A', 12);
  shade.opacity = 0.36;
  if (!mobile) uiText(board, '摄影信息', '上海大学官网 · 摄影：韦明其', 36 + heroWidth - 218, 104 + heroHeight - 26, 10, UI.white, 400, 200);
  if (!mobile) uiComponent(board, 'Search Field', 76, 358);
  else {
    uiRect(board, '移动检索框', 32, 282, width - 64, 54, UI.white, 9);
    uiText(board, '移动检索提示', '检索案例、知识或教学素材', 48, 300, 11, UI.subtle, 400, 190);
    uiButton(board, '检索', width - 114, 288, true, 70);
  }
  uiText(board, '首屏主标题', '上海大学 · “强国有我”思政案例库', mobile ? 32 : 76, mobile ? 126 : 148, mobile ? 16 : 20, UI.white, 600, width - (mobile ? 64 : 620));
  uiText(board, '资源统计', '4 公开案例    77 教学素材    2 教材知识', mobile ? 34 : 910, mobile ? 354 : 184, mobile ? 11 : 16, UI.white, 500, mobile ? 320 : 440);
  uiText(board, '近七天', '近 7 天    新增案例 4    新增素材 6    新发布 4', mobile ? 20 : 36, mobile ? 414 : 564, 12, UI.muted, 400, width - 72);
  uiText(board, '推荐标题', '推荐案例', mobile ? 20 : 36, mobile ? 452 : 610, 20, UI.ink, 600);
  uiRows(board, FLOW_DATA.foundation.rows, mobile ? 20 : 36, mobile ? 494 : 660, width - (mobile ? 40 : 72), mobile ? 2 : 3);
}
function uiComponents(board) {
  uiTitle(board, '统一设计系统', '品牌红、冷灰表面、细边框与 6/9px 圆角', 40, 42, 900);
  const colors = [['品牌', UI.brand], ['表面', UI.surface], ['文字', UI.ink], ['弱化', UI.muted], ['边线', UI.line], ['成功', UI.green]];
  colors.forEach(([label, color], index) => {
    const x = 40 + index * 150;
    uiRect(board, `色板-${label}`, x, 120, 128, 64, color, 6, color === UI.surface || color === UI.line ? UI.line : null);
    uiText(board, `色板名-${label}`, label, x, 196, 12, UI.muted, 500);
  });
  uiComponent(board, 'Search Field', 40, 252);
  uiComponent(board, 'Admin Navigation', 40, 352);
  uiText(board, '组件说明', '共享组件：Site Header / Admin Navigation / Search Field', 340, 380, 16, UI.ink, 600, 660);
  uiText(board, '设计变量', 'color.surface · color.surfaceInk · color.surfaceMuted · color.surfaceLine · radius.panel · space.44 · space.56', 340, 420, 12, UI.muted, 400, 680);
  uiRows(board, ['页面标题|26px / 600', '正文与表单|14px / 400–500', '辅助信息|11–12px', '面板|9px 细边框'], 340, 480, 720, 4);
}
function uiRelationships(board, spec) {
  const mobile = false;
  if (spec.name.includes('候选 A')) {
    uiRows(board, ['钱伟长图书馆|共同主题：科学家精神', '任新振科技报国路|真实引用：政策文件', '智能控制|检索命中：项目牵引', '微电子赋能生物医药|继续展开'], 50, 220, board.width - 100, 4);
    return;
  }
  if (spec.name.includes('候选 B')) {
    uiCards(board, ['科学家精神|42 个案例 · 查看关系', '科技报国|31 个案例 · 查看关系', '项目牵引|18 个案例 · 查看关系'], 50, 220, board.width - 100, mobile);
    uiText(board, '覆盖说明', '当前显示按主题聚合，数字对应真实检索结果；可继续翻页。', 50, 410, 13, UI.muted, 400, 800);
    return;
  }
  const nodes = [['检索结果', 610, 310], ['科学家精神', 330, 210], ['案例 A', 890, 190], ['案例 B', 900, 430], ['政策文件', 320, 450]];
  nodes.forEach(([label, x, y], index) => {
    if (index) {
      uiRect(board, '关系连线', 630, 330, x > 610 ? x - 630 : 630 - x, 1, UI.subtle);
    }
    uiPanel(board, `节点-${label}`, x, y, index ? 170 : 190, 64);
    uiText(board, `节点文字-${label}`, label, x + 16, y + 22, 13, index ? UI.ink : UI.brand, 600);
  });
  uiText(board, '局部覆盖', '仅展开当前命中的一部分；继续探索从当前节点分页加载。', 50, 650, 13, UI.muted, 400, 800);
}
function uiSearchMetadata(board, x, y, width) {
  uiComponent(board, 'Search Field', x, y - 26);
  uiPanel(board, '筛选面板', x, y + 58, width, 178);
  uiText(board, '筛选标题', '筛选条件', x + 24, y + 78, 14, UI.ink, 600);
  const columnWidth = (width - 72) / 2;
  FLOW_DATA['search-metadata'].rows.forEach((row, index) => {
    const [label, value] = row.split('|');
    const left = x + 24 + (index % 2) * (columnWidth + 24);
    const top = y + 120 + Math.floor(index / 2) * 54;
    uiRect(board, `筛选-${label}`, left, top, columnWidth, 38, UI.surface, 6, UI.line);
    uiText(board, '筛选名称', label, left + 14, top + 10, 12, UI.muted, 500, 88);
    uiText(board, '筛选值', value, left + 104, top + 10, 12, UI.ink, 400, columnWidth - 140);
    uiText(board, '展开筛选', '⌄', left + columnWidth - 26, top + 9, 12, UI.muted, 500);
  });
  uiText(board, '结果标题', '检索结果 · 演示案例', x, y + 264, 16, UI.ink, 600, 500);
  uiCards(board, FLOW_DATA['search-metadata'].cards, x, y + 302, width);
  uiText(board, '结果说明', '学科、课程、案例类型与思政元素可以组合筛选。', x, y + 474, 12, UI.muted, 400, 700);
}
function uiMotionScroll(board, x, y, width) {
  if (!storage.campusImages?.desktop) throw new Error('动效画板需要校园图片');
  const panelWidth = (width - 24) / 2;
  ['进入视口前', '进入视口后'].forEach((label, index) => {
    const left = x + index * (panelWidth + 24);
    const before = index === 0;
    uiPanel(board, `动效-${label}`, left, y, panelWidth, 480);
    uiText(board, '动效步骤', `0${index + 1} · ${label}`, left + 24, y + 24, 15, UI.ink, 600);
    const image = storage.campusImages.desktop.clone();
    image.name = '视差背景';
    image.resize(panelWidth - 48, Math.round((panelWidth - 48) * 430 / 1368));
    image.x = board.x + left + 24;
    image.y = board.y + y + 70 + (before ? 8 : 0);
    image.borderRadius = 8;
    board.appendChild(image);
    const offset = before ? 16 : 0;
    const card = uiPanel(board, '滚动案例卡片', left + 48, y + 286 + offset, panelWidth - 96, 108);
    card.opacity = before ? 0.15 : 1;
    const title = uiText(board, '滚动卡片标题', '科学家精神专题案例', left + 64, y + 306 + offset, 15, UI.ink, 600, panelWidth - 128);
    title.opacity = before ? 0.15 : 1;
    const text = uiText(board, '滚动卡片说明', '真实案例与教学素材入口', left + 64, y + 342 + offset, 12, UI.muted, 400, panelWidth - 128);
    text.opacity = before ? 0.15 : 1;
    uiText(board, '动效说明', before ? '卡片尚未显示，背景保持原位。' : '卡片上移 16px，背景位移 8px。', left + 24, y + 424, 12, UI.muted, 400, panelWidth - 48);
  });
  uiText(board, '动效原则', '进入视口后只播放一次，不阻塞检索；减少动态模式下取消位移与过渡。', x, y + 506, 12, UI.muted, 400, width);
}
function uiLoginPanel(board, title, x, fields, action, note) {
  uiPanel(board, title, x, 210, 420, 430);
  uiText(board, '表单标题', title, x + 28, 238, 20, UI.ink, 600, 340);
  fields.forEach(([label, placeholder], index) => {
    const top = 292 + index * 86;
    uiText(board, '字段标签', label, x + 28, top, 12, UI.ink, 500, 340);
    uiRect(board, `输入-${label}`, x + 28, top + 26, 364, 42, UI.white, 6, UI.line);
    uiText(board, '字段提示', placeholder, x + 44, top + 38, 12, UI.subtle, 400, 332);
  });
  uiButton(board, action, x + 28, 294 + fields.length * 86, true, 364);
  uiText(board, '表单说明', note, x + 28, 340 + fields.length * 86, 12, UI.muted, 400, 364);
}
function uiLogin(board, spec) {
  uiHeader(board, false, false);
  uiTitle(board, spec.name, '自助注册、账号登录与首次改密', 280, 116, 880);
  uiLoginPanel(board, '账号登录', 280, [['用户名', '请输入用户名'], ['密码', '请输入密码']], '登录', '登录后可创作与投稿；校内素材按资格授权。');
  uiLoginPanel(board, '首次登录改密', 740, [['临时密码', '请输入管理员提供的临时密码'], ['新密码', '输入新密码'], ['确认新密码', '再次输入新密码']], '保存新密码', '改密成功后使用新密码登录。');
  uiText(board, '注册入口', '没有账号？使用用户名和密码自助注册。', 280, 674, 13, UI.brand, 500, 600);
}
function uiContent(board, spec, mobile, x = mobile ? 20 : 50, y = 210, width = null) {
  const contentWidth = width || (mobile ? board.width - 40 : board.width - 100);
  if (spec.flow === 'admin-stats') {
    const chartWidth = (contentWidth - 72) / 2;
    uiPanel(board, '统计面板', x, y, contentWidth, 540);
    uiText(board, '统计范围', spec.name.includes('全部') ? '全部案例 · 6 个，含未分类' : '公开已发布 · 4 个案例', x + 24, y + 22, 14, UI.ink, 600, 360);
    uiText(board, '类型标题', '案例类型分布', x + 24, y + 70, 15, UI.ink, 600, chartWidth);
    uiText(board, '学科标题', '学科分布', x + 48 + chartWidth, y + 70, 15, UI.ink, 600, chartWidth);
    uiBars(board, x + 24, y + 108, chartWidth, 'type');
    uiBars(board, x + 48 + chartWidth, y + 108, chartWidth, 'subject');
    uiRows(board, FLOW_DATA['admin-stats'].rows, x + 24, y + 374, contentWidth - 48, 3);
    return;
  }
  if (spec.flow === 'search-metadata') { uiSearchMetadata(board, x, y, contentWidth); return; }
  if (spec.flow === 'motion' && spec.name.includes('滚动显现')) { uiMotionScroll(board, x, y, contentWidth); return; }
  if (spec.flow === 'relationships') { uiRelationships(board, spec); return; }
  uiGeneric(board, spec, x, y, contentWidth, mobile);
}
function uiBoardContent(board, spec) {
  const mobile = spec.viewport === '390x844';
  if (spec.status === 'exploratory') {
    uiRect(board, '待确认标识', board.width - 190, 78, 150, 26, UI.amberSoft, 6);
    uiText(board, '待确认文字', '待产品确认 · 探索稿', board.width - 180, 85, 10, UI.amber, 600, 132);
  }
  if (spec.layout === 'component') { uiComponents(board); return; }
  uiText(board, '设计稿标识', 'UI 设计稿 · 演示数据', board.width - 190, board.height - 32, 10, UI.subtle, 400, 150);
  if (spec.flow === 'accounts' && spec.name.includes('登录注册')) { uiLogin(board, spec); return; }
  if (spec.flow === 'foundation' && spec.name.includes('首页')) { uiHeader(board, mobile); uiHome(board, spec, mobile); return; }
  if (spec.layout === 'admin') {
    uiHeader(board, mobile); uiAdminNavigation(board, adminNavIndex(spec.flow), mobile);
    uiTitle(board, spec.name, FLOW_DATA[spec.flow].title, mobile ? 20 : 310, mobile ? 142 : 116, mobile ? 340 : 800);
    if (mobile) { uiGeneric(board, spec, 20, 218, board.width - 40, true); return; }
    uiContent(board, spec, false, 310, 210, board.width - 360); return;
  }
  if (spec.layout === 'settings') {
    uiHeader(board, mobile);
    uiPanel(board, '设置面板', mobile ? 20 : 280, mobile ? 108 : 130, mobile ? 350 : 880, mobile ? 650 : 690);
    uiTitle(board, spec.name, FLOW_DATA[spec.flow].title, mobile ? 40 : 320, mobile ? 142 : 170, mobile ? 310 : 800);
    uiRows(board, FLOW_DATA[spec.flow].rows, mobile ? 40 : 320, mobile ? 240 : 264, mobile ? 310 : 800, mobile ? 4 : 5);
    uiCards(board, FLOW_DATA[spec.flow].cards, mobile ? 40 : 320, mobile ? 510 : 540, mobile ? 310 : 800, mobile);
    return;
  }
  if (spec.layout === 'workbench') {
    uiHeader(board, false);
    uiRect(board, '目录背景', 0, 64, 200, board.height - 64, UI.warm);
    uiText(board, '目录标题', '案例目录', 24, 104, 15, UI.ink, 600);
    uiRows(board, ['案例背景', '教学目标', '教学实施', '讨论与反思'], 12, 160, 170, 4);
    uiPanel(board, '正文纸面', 224, 100, 704, board.height - 150);
    uiText(board, '正文标题', FLOW_DATA[spec.flow].title, 258, 140, 24, UI.ink, 600, 620);
    uiText(board, '正文内容', '以真实案例和已确认来源组织教学内容。教师可以审阅、修改并决定是否采用 AI 建议。', 258, 196, 14, UI.muted, 400, 620);
    uiPanel(board, 'AI 侧栏', 956, 100, 440, board.height - 150);
    uiText(board, '侧栏标题', spec.name, 980, 128, 18, UI.ink, 600, 380);
    uiRows(board, FLOW_DATA[spec.flow].rows, 972, 190, 396, 5);
    uiCards(board, FLOW_DATA[spec.flow].cards, 972, 540, 396, true);
    return;
  }
  uiHeader(board, mobile);
  uiTitle(board, spec.name, FLOW_DATA[spec.flow].title, mobile ? 20 : 50, mobile ? 112 : 116, mobile ? 340 : 1000);
  uiContent(board, spec, mobile);
}
async function ensurePage(name) {
  let page = penpotUtils.getPageByName(name);
  if (!page) page = penpot.createPage();
  page.name = name;
  penpot.openPage(page);
  for (let attempt = 0; attempt < 60; attempt += 1) {
    if (penpot.currentPage?.id === page.id) return penpot.currentPage;
    await new Promise(resolve => setTimeout(resolve, 250));
  }
  throw new Error(`页面尚未激活: 目标 ${name}，实际 ${penpot.currentPage?.name || '无活动页面'}`);
}
async function renderFlow(pageName, specs) {
  const page = await ensurePage(pageName);
  const created = [], skipped = [];
  for (const spec of specs) {
    if (penpot.currentPage.root.children.some(shape => shape.name === spec.fullName)) { skipped.push(spec.fullName); continue; }
    const board = uiBoard(spec);
    uiBoardContent(board, spec);
    created.push({ id: board.id, name: spec.fullName });
  }
  return { page: page.name, created, skipped };
}
