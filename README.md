# 强国有我大思政课案例库

上海大学"强国有我"大思政课案例库平台，基于原有的Skill系统开发，包含完整的前端界面、后端API、案例库数据库、智能搜索和审核流程管理系统。

## 功能特性

### 1. 前端界面
- 现代化的响应式设计
- 首页展示、案例库浏览、案例创建、审核管理、数据统计
- 美观的卡片布局和搜索功能
- 支持案例详情查看和互动

### 2. 数据库系统
- SQLite数据库存储案例、审核记录和版本历史
- 支持多维度索引，提升搜索效率
- 完整的版本管理和审核追踪

### 3. 智能搜索
- 全文搜索支持
- 高级筛选（类型、主题等）
- 热门案例推荐
- 最新案例更新

### 4. 审核流程
- 草稿、待审核、已发布、需修改的完整流程
- 版本历史记录
- 审核人意见追踪
- 完整的案例管理功能

### 5. 原Skill系统集成
- 保持原有的案例分类功能
- 自动多版本生成
- 关键词提取和主题归类

## 快速开始

### 方式一：使用启动脚本（推荐）

1. 双击运行 `start.bat`
2. 等待服务启动完成
3. 打开浏览器访问：http://localhost:8001/

### 方式二：手动启动

#### 1. 安装依赖

```bash
pip install -r requirements.txt
```

#### 2. 初始化数据库并添加演示数据

```bash
cd backend
python demo.py
```

#### 3. 启动后端服务

```bash
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8001
```

#### 4. 打开前端

在浏览器中访问：http://localhost:8001/

## 项目结构

```
强国有我大思政课案例库/
├── frontend/              # 前端界面
│   ├── index.html        # 主页面
│   ├── css/style.css     # 样式表
│   └── js/app.js         # 前端逻辑
├── backend/              # 后端服务
│   ├── main.py           # FastAPI主应用
│   ├── database.py       # 数据库操作
│   ├── search_engine.py  # 搜索引擎
│   ├── case_processor.py # 案例处理
│   └── demo.py           # 演示数据脚本
├── data/                 # 数据目录
│   └── cases.db          # SQLite数据库
├── skills/               # Skill系统文件
│   ├── classifier.md
│   ├── template-sizhengke.md
│   ├── template-kechengsizheng.md
│   └── template-shijian.md
├── requirements.txt       # 依赖文件
├── start.bat             # Windows启动脚本
└── README.md             # 说明文档
```

## 数据库设计

### cases表 - 案例主表
- id: 主键
- title: 案例标题
- type: 案例类型（TYPE_A/B/C）
- theme: 主题分类
- content: 案例内容
- status: 状态（draft/pending_review/approved/needs_revision/deleted）
- author: 作者
- department: 部门
- keywords: 关键词（JSON）
- created_at: 创建时间
- updated_at: 更新时间
- is_approved: 是否发布
- view_count: 浏览量
- like_count: 点赞量

### reviews表 - 审核记录表
- id: 主键
- case_id: 案例ID
- reviewer: 审核人
- comment: 审核意见
- status: 审核状态
- review_at: 审核时间

### versions表 - 版本历史表
- id: 主键
- case_id: 案例ID
- version_number: 版本号
- content: 内容快照
- changed_by: 修改人
- change_reason: 修改原因
- created_at: 创建时间

## API接口

### 案例管理
- `GET /api/cases` - 获取案例列表
- `GET /api/cases/{id}` - 获取案例详情
- `POST /api/cases` - 创建新案例
- `PUT /api/cases/{id}` - 更新案例
- `DELETE /api/cases/{id}` - 删除案例
- `POST /api/cases/{id}/submit` - 提交审核
- `POST /api/cases/{id}/like` - 点赞案例

### 搜索功能
- `GET /api/search` - 搜索案例
- `GET /api/search/advanced` - 高级筛选
- `GET /api/recommendations/{id}` - 获取推荐案例
- `GET /api/trending` - 获取热门案例
- `GET /api/latest` - 获取最新案例

### 审核流程
- `POST /api/reviews/{id}` - 提交审核
- `GET /api/reviews/{id}` - 获取审核记录
- `GET /api/versions/{id}` - 获取版本历史

### 统计数据
- `GET /api/statistics` - 获取统计数据

### 常量数据
- `GET /api/constants` - 获取类型、主题等常量

## 案例类型

### TYPE_A - 思政课教学案例
适合在思政课堂上讲授，体现党的创新理论实践

### TYPE_B - 课程思政共享资源案例
体现专业课程与思政的有机结合，有课程载体

### TYPE_C - 实践育人案例
围绕社会实践活动、志愿服务、基层服务等

## 主题分类

1. 强国建设
2. 上海实践
3. 创新发展
4. 校园文明

## 开发说明

### 前端开发
- 纯HTML/CSS/JavaScript，无框架依赖
- 使用Fetch API与后端交互
- 响应式设计，支持移动端

### 后端开发
- FastAPI框架
- SQLite数据库
- RESTful API设计

### 添加新模板
在根目录下添加新的模板文件，遵循现有格式

## 支持

如有问题或建议，请联系上海大学相关工作专班。

---

**强国有我 · 大思政课案例库**

落实立德树人根本任务，汇聚优秀思政教育案例
