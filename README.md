# 强国有我大思政课案例库

上海大学"强国有我"大思政课案例库平台，基于原有的Skill系统开发，包含完整的前端界面、后端API、案例库数据库、智能搜索和审核流程管理系统。

## 功能特性

### 1. 前端界面
- 现代化的响应式设计
- 首页展示、案例库浏览、案例创建、审核管理、数据统计
- 美观的卡片布局和搜索功能
- 支持案例详情查看和互动

### 2. 数据库系统
- MongoDB 存储案例、用户、审核记录、版本历史等业务数据
- 通过 `counters` 集合为各业务集合分配整数 `id`，便于外部引用
- 关键查询字段与全文检索均建立索引（详见 `backend/database.py:init_db()`）
- 完整的版本管理和审核追踪

### 3. 智能搜索
- 全文搜索支持
- 高级筛选（类型、主题等）
- 热门案例推荐
- 最新案例更新

### 4. 审核流程
- 草稿、待审核、已通过（自动入库）、需修改 的完整流程
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

> 前置条件：本地或可访问的 MongoDB 实例。连接信息通过 `.env` 中的 `MONGODB_URI`（默认 `mongodb://localhost:27017`）和 `MONGODB_DB_NAME`（默认 `case_library`）配置，由 `backend/database.py` 读取。

#### 1. 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

#### 2. 初始化演示数据与用户（首次启动各执行一次）

```bash
python demo.py        # 写入示例案例
python init_users.py  # 创建初始账号
```

#### 3. 启动后端服务

```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8001
```

#### 4. 打开前端

在浏览器中访问：http://localhost:8001/

## 项目结构

```
强国有我大思政课案例库/
├── frontend/                       # 前端界面（纯静态资源，由 FastAPI 挂载提供）
│   ├── index.html
│   ├── css/
│   └── js/
├── backend/                        # 后端服务
│   ├── main.py                     # FastAPI 入口与全部路由
│   ├── database.py                 # MongoDB 数据访问层与索引初始化
│   ├── search_engine.py            # 搜索 / 推荐辅助封装
│   ├── case_processor.py           # 案例分类与处理
│   ├── demo.py                     # 演示数据初始化脚本
│   ├── init_users.py               # 初始用户创建脚本
│   ├── account_admin.py            # 账号管理脚本
│   ├── migrate_sqlite_to_mongo.py  # 一次性迁移脚本：旧 SQLite → MongoDB
│   ├── migrate_timestamps.py       # 一次性时间戳格式迁移脚本
│   ├── smoke_test_mongo.py         # MongoDB 烟测
│   ├── test_submit_flow.py         # 提交流程测试
│   ├── requirements.txt
│   └── accounts.csv
├── data/                           # 数据目录
│   ├── cases.db                    # 旧 SQLite 文件，仅供 migrate_sqlite_to_mongo.py 读取
│   └── uploads/                    # 上传文件存放目录
├── skills/                         # AI 案例处理 Skill 系统
│   ├── SKILL.md                    # 顶层 Skill 入口
│   ├── anlibianxie/                # 案例编写：SKILL.md 与三套写作模板
│   ├── shenhe/                     # 审核
│   └── zhutifenlei/                # 主题分类（classifier.md）
├── SKILL.md                        # 项目级 Skill 索引
├── CLAUDE.md / AGENTS.md           # 协作约定
├── requirements.txt                # 根目录依赖（与 backend/requirements.txt 略有版本差异）
├── start.bat                       # Windows 启动脚本
└── README.md
```

## 数据库设计

存储后端为 MongoDB。除 Mongo 自带的 `_id` 外，每个业务集合还使用由 `counters` 集合分配的整数 `id` 字段，便于 URL 与外部系统引用。索引在 `backend/database.py:init_db()` 中创建。

### cases — 案例集合
常用字段：`id`、`title`、`type`（TYPE_A/B/C）、`theme`、`content`、`status`（draft/pending_review/approved/needs_revision）、`author`、`owner_username`、`department`、`keywords`、`created_at`、`updated_at`、`is_approved`、`is_in_library`、`view_count`、`like_count`。

索引：`id` 唯一索引；`(status, created_at)`、`(author, status, created_at)`、`(owner_username, status, created_at)` 三个复合索引；以及覆盖 `title / content / keywords` 的全文索引 `cases_text_idx`。

### users — 用户集合
常用字段：`id`、`username`、`password_hash`、`role`（normal/admin）、`status`（active/no_active）、`created_at`。`id` 与 `username` 均为唯一索引。

### reviews — 审核记录集合
常用字段：`id`、`case_id`、`reviewer`、`comment`、`status`（pending/approved/rejected/needs_revision）、`review_at`。

### versions — 版本历史集合
常用字段：`id`、`case_id`、`version_number`、`content`（按 `database.py` 中 `VERSIONED_FIELDS` 定义的字段快照）、`changed_by`、`change_reason`、`created_at`。

### counters — 整数 id 分配器
为 `users / cases / reviews / versions / deployments` 集合分别维护一个自增计数。

### deployments — 部署记录集合
索引已建立，但当前代码中没有写入路径，属于预留集合。

## API接口

### 认证
- `POST /api/auth/login` - 登录
- `POST /api/auth/change-password` - 修改密码

### 案例管理
- `GET /api/cases` - 获取案例列表
- `GET /api/cases/{id}` - 获取案例详情
- `POST /api/cases` - 创建新案例
- `PUT /api/cases/{id}` - 更新案例
- `POST /api/cases/{id}` - 更新案例（兼容路径）
- `DELETE /api/cases/{id}` - 删除案例
- `POST /api/cases/{id}/submit` - 提交审核
- `POST /api/cases/{id}/like` - 点赞案例
- `POST /api/cases/{id}/unlike` - 取消点赞
- `POST /api/cases/{id}/visibility` - 修改可见性

### 搜索功能
- `GET /api/search` - 搜索案例
- `GET /api/search/advanced` - 高级筛选
- `GET /api/recommendations/{id}` - 获取推荐案例
- `GET /api/trending` - 获取热门案例
- `GET /api/latest` - 获取最新案例

### 审核流程
- `POST /api/reviews/{id}` - 提交审核结果
- `GET /api/reviews/{id}` - 获取审核记录
- `GET /api/versions/{id}` - 获取版本历史

### 统计与常量
- `GET /api/statistics` - 获取统计数据
- `GET /api/constants` - 获取案例类型、主题、状态等常量

## 案例类型

### TYPE_A - 思政课教学案例
适合在思政课堂上讲授，体现党的创新理论实践

### TYPE_B - 课程思政共享资源案例
体现专业课程与思政的有机结合，有课程载体

### TYPE_C - 实践育人案例
围绕社会实践活动、志愿服务、基层服务等

## 主题分类

主题列表的具体取值以 `GET /api/constants` 接口返回的 `themes` 字段为准（定义在 `backend/main.py`）。文档不再独立列举，避免与代码各写一份导致不同步。

## 开发说明

### 前端开发
- 纯HTML/CSS/JavaScript，无框架依赖
- 使用Fetch API与后端交互
- 响应式设计，支持移动端

### 后端开发
- FastAPI 框架
- MongoDB 数据库（`pymongo` 驱动）
- RESTful API 设计

### 添加新模板
在 `skills/anlibianxie/` 下新增模板文件，遵循现有 `template-*.md` 格式

## 支持

如有问题或建议，请联系上海大学相关工作专班。

---

**强国有我 · 大思政课案例库**

落实立德树人根本任务，汇聚优秀思政教育案例
