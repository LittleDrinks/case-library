# 用户、角色与管理员边界：当前实现基线

本笔记服务于 Wayfinder 问题「确定上线运营所需的用户、角色与管理员边界」，只收集事实、限制和可独立讨论的问题，不替用户确定权限政策。

## 证据范围

- 查阅日期：2026-09-30。
- 固定本地 HEAD：`7afc5bb9e182b1c61827d6024670002a42937fc6`。只读 `gh api repos/LittleDrinks/case-library/commits/main` 确认上游 main 为同一 SHA；返回 commit date 为 `2026-09-28T03:10:29Z`。下文源码链接固定此提交。
- 查看源码、上游问题正文和评论，以及用户已有的 [上海大学统一身份认证接入研究](shu-identity-integration.md:11)；重新打开其中三条学校官方来源。未运行测试、未访问部署主机、未查询实际用户或数据库数据，也未读取环境文件、密钥或连接串。
- “未发现”限于该提交的 auth 模块、注册的 API 路由、前端路由和后台页面，以及针对用户写操作和 SSO 标识的源码搜索。它不是生产环境运行结果。

## 账号生命周期：已实现与尚未实现

| 能力 | 当前实现状态 | 一手证据 |
| --- | --- | --- |
| 用户角色 | 常量声明 `user`、`admin`；`UserView.role` 是字符串，并无教师、审核员、运维员等独立角色枚举。`campusVerified` 是独立布尔属性。 | [operations.py:65–71][roles]；[auth/models.py:20–26][models] |
| 账号密码登录 | 用户名加本地密码，查询要求 `status=active`；登录创建 cookie 会话。已有独立登录页面。 | [auth/service.py:23–27][authenticate]；[auth/routes.py:44–56][login]；[LoginView.vue:25–31、40–63][login-ui] |
| 创建管理员 | CLI 要求 production 环境，经 `bootstrap_admin` 插入 admin、active、无需首次改密、`campus_verified=True` 的本地账号；校内标记在创建时设定，并非学校验证结果。函数没有“已有管理员则拒绝”的人数限制，重复用户名由数据库唯一约束拒绝。 | [cli/bootstrap_admin.py:17–38][bootstrap-cli]；[auth/admin_bootstrap.py:29–59][bootstrap-admin] |
| 创建普通用户／自助注册 | 源码里有演示账号种子；未发现生产普通账号创建、自助注册、邀请入口。启动逻辑按配置决定是否种入演示账号，并在 production 拒绝已有演示账号。不得把种子当生产开户产品。 | [auth/seed.py:14–24、42–61][seed]；[core/bootstrap.py:14–23][bootstrap]；[api/router.py:24–44][api-router] |
| 本人修改密码 | 校验当前密码、强度和新旧不同；更新密码并递增 `token_version`，删除该用户全部会话；接口删除当前 cookie。 | [auth/service.py:37–59][change-password]；[auth/routes.py:64–77][password-route] |
| 管理员停用、删除用户、改角色、重置密码 | 未发现对应管理 API、UI 或服务方法。底层登录和会话解析识别 active 状态，不等于已实现管理员停用操作。 | [auth/routes.py:44–88][auth-routes]；[auth/service.py:23–67][auth-service]；[AdminDashboardView.vue:40–75][admin-ui]；[api/router.py:24–44][api-router] |
| 会话撤销 | 退出删除当前会话；本人改密撤销该用户所有会话。每次解析会话均重新读取用户 active 状态并比较 `token_version`；因此状态变化、用户记录消失或版本变化会使后续会话查找失败。未发现管理员手动撤销会话入口。 | [auth/sessions.py:38–54][sessions]；[auth/service.py:37–50][change-password]；[auth/routes.py:80–88][logout] |
| 账号操作审计 | auth 登录、改密、退出及 bootstrap 路径中未发现独立账号操作审计事件或可查询审计后台。案例生命周期有 `actorId`、`actorRole`、时间等事件，但这是案例操作历史。 | [auth/routes.py:44–88][auth-routes]；[auth/service.py:23–67][auth-service]；[auth/admin_bootstrap.py:46–60][bootstrap-admin]；[cases/lifecycle.py:84–94][case-events] |

上游[「收敛账号、平台 AI 与供给统计后台」](https://github.com/LittleDrinks/case-library/issues/42)仍 OPEN，正文要求维护账号、角色、禁用、重置密码、会话撤销，并要求每条管理员用户路径验证权限、审计与敏感信息边界；查询时无评论。上述未实现项仍是需求，不能因票存在就写成已有能力。

上游[「增加独立登录页面」](https://github.com/LittleDrinks/case-library/issues/254)仍 OPEN，正文称 Later、具体视觉与登录方案后续确认，查询时无评论；但本 HEAD 已存在 `LoginView` 和 `/login` 路由。这表明票的状态与部分源码实现不能直接互相代替。[frontend/router.js:19–22][frontend-router]

## 管理人和读取私人内容的实际边界

“管理员”在当前代码中同时覆盖多种内容管理职能，但没有已实现的账号管理界面。后台工具链接包含素材入库、Skill、标签目录、平台 AI，以及案例审核和发布管理；前端 requiresAdmin 检查 `role=admin`，后端各相应模块也独立检查管理员身份。[AdminDashboardView.vue:40–75][admin-ui]；[frontend/router.js:65–98、109–118][frontend-router]；[materials/routes.py:29–39][material-admin]；[ai/routes.py:52–73][ai-admin]

| 对象 | 管理员通过当前业务 API 的权限 | 一手证据 |
| --- | --- | --- |
| 任意案例及未投稿私人草稿 | `admin` 被视为内部读者；管理列表读取全部案例，按 ID 读取也放行管理员，返回内部工作内容。后台视图仅展示待审／发布队列，不构成 API 权限收窄。 | [cases/service.py:110–119、147–168、234–238][cases-service]；[AdminDashboardView.vue:7–18、29–34][admin-ui] |
| 案例正文编辑 | 正文写权限要求作者 ID；管理员身份本身不能编辑他人正文。生命周期审核、发布等管理员操作另有授权。 | [cases/service.py:118–119、277–285][cases-service]；[cases/lifecycle.py:37–65][case-authorize] |
| 私人 AI 对话 | 对话列表、默认对话与具名对话都把当前 `user.id` 用作 thread ownerId；数据库查找同时匹配 caseId 和 ownerId。没有“admin 可查别人的 ownerId”分支。作者工作稿对话还要求是案例作者；管理员可对待审案例创建／读取属于自己的审核对话。 | [agent/routes.py:96–100、149–178、191–205、548–596][agent-routes]；[agent/repository.py:86–118][agent-repository] |
| 私人素材 | 全局素材 `private`／非 public、campus 分支允许管理员或素材 createdBy；管理员能读其他人的私人素材。素材详情与下载共用此门禁。 | [materials/service.py:172–199、215–225][materials-service] |
| 案例资料区和私人附件 | 非公开案例的资料区、附件允许管理员和作者访问；附件内容也有 admin／owner 直接放行。不能将“对话仅本人可读”扩展为“私人资料仅本人可读”。 | [case_materials/service.py:34–39、69–89][case-materials]；[attachments/service.py:54–59、176–199、235–241][attachments] |

以上描述的是已追踪的公共业务调用链。掌握数据库或存储基础设施权限的人能做什么，不由这些应用角色检查决定；本次没有检查或赋予任何基础设施权限。

## 本地账号与学校身份接入缺口

1. 当前认证请求只含本地用户名、密码；用户返回字段只有本地 ID、用户名、姓名、角色、首次改密要求和校内验证标记。注册路由中未发现学校登录发起、回调、外部身份绑定入口。没有证据把当前实现称为学校 SSO。[auth/models.py:6–26][models]；[auth/routes.py:22–88][auth-routes]；[api/router.py:24–44][api-router]
2. `campus_verified` 已参与权限判断，却没有本次发现的用户管理界面来确认、更新或撤销学校身份；管理员 bootstrap 会直接设为 true。它是本地业务标记，不证明学校签发了身份断言。[auth/admin_bootstrap.py:29–43][bootstrap-admin]；[materials/service.py:172–184][materials-service]
3. 校内资料存在两套实现口径：全局素材要求 `campus_verified` 或 admin；案例附件的 campus 分支仅检查已登录 user。即使决定沿用本地登录，校内内容的身份标准也需要明确。[materials/service.py:172–184][materials-service]；[attachments/service.py:235–241][attachments]
4. **已知公开事实**：本次重新打开[学生统一身份认证官方说明](https://newits.shu.edu.cn/sytplb/xsfw/tysfrz.htm)，正文明确介绍 E-Passport.SHU 和面向校内第三方应用的统一认证／单一登录服务；[系统统一身份认证申请官方页面](https://its.shu.edu.cn/sytplb/bmfw/xttysfrzsq.htm)说明学校提供统一认证及授权访问数据接口。既有研究笔记第 13–20 行指向的[学校授权跳转实例](https://newsso.shu.edu.cn/oauth/authorize?client_id=WUHWfrntnWYHZfzQ5QvXUCVy&redirect_uri=https%3A%2F%2Fselfreport.shu.edu.cn%2FLoginSSO.aspx%3FReturnUrl%3D%252f&response_type=code&scope=1)本次仍跳到学校登录 URL，原授权请求包含 `client_id`、`redirect_uri`、`response_type=code`、`scope`。这说明有 OAuth 风格的授权跳转实例；不能据此认定 Case Library 已获接入资格或学校提供 OIDC。
5. **尚需接入方提供的事实**：Case Library 实际批准使用的协议和完整端点、申请／注册材料、稳定外部用户标识、是否释放教师／学生／在职／在籍属性、属性字段含义与授权范围、测试环境、上线要求和撤销语义，仍无正式接入合同支撑。尤其没有证据保证登录后可自动识别教师／学生身份。既有笔记第 57–68 行列的是索取清单，不是已取得的学校能力。本次只读公开页面，未完成登录或调用身份交换／用户信息端点；不猜 OIDC、CAS、SAML 或自定义协议。

## 可供用户逐个回答的最小独立问题

以下是待定问题，不是推荐方案或已确认决定；这里只为当前 HITL 票提供讨论材料。

1. 首次上线的写作用户如何获得账号：由管理员逐一创建、邀请／申请后开通、还是自行注册？学校 SSO 是上线前提，还是后续接入？依据：目前只有生产管理员创建和本地登录入口，普通用户生产开户缺失。[bootstrap-cli] [auth-routes]
2. 第一阶段需要哪些权限差异：作者、内容审核、账号管理、平台配置是否由同一类管理员承担？依据：当前仅 user/admin，admin 同时覆盖多类后台能力。[roles] [admin-ui]
3. 管理员是否可以读取未投稿私人草稿、私人资料；私人对话是否始终只归对话创建者？如需例外协助，用户是否必须主动授权？依据：当前“草稿／资料管理员可读、对话按 ownerId 隔离”。[cases-service] [materials-service] [agent-repository]
4. 停用、重置密码、改角色、会话撤销分别由谁发起，是否需要强制首次改密、保留操作人与理由、以及保护最后一个管理员？账号删除后内容归属是否保留？依据：这些管理入口未实现，现有数据存在 ownerId/createdBy 关系。[auth-routes] [change-password] [bootstrap-admin] [cases-service]
5. “校内用户”以人工确认还是学校返回身份为准？过期／离校如何撤销；校内素材和附件是否必须使用同一规则？依据：当前两个 campus 门禁不同，学校身份接入合同未知。[materials-service] [attachments]

[roles]: https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/api/operations.py#L65-L71
[models]: https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/auth/models.py#L6-L26
[authenticate]: https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/auth/service.py#L23-L27
[login]: https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/auth/routes.py#L44-L56
[login-ui]: https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/frontend/src/views/LoginView.vue#L25-L63
[bootstrap-cli]: https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/cli/bootstrap_admin.py#L17-L38
[bootstrap-admin]: https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/auth/admin_bootstrap.py#L29-L60
[seed]: https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/auth/seed.py#L14-L61
[bootstrap]: https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/core/bootstrap.py#L14-L23
[api-router]: https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/api/router.py#L24-L44
[auth-routes]: https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/auth/routes.py#L22-L88
[auth-service]: https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/auth/service.py#L23-L67
[change-password]: https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/auth/service.py#L37-L59
[password-route]: https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/auth/routes.py#L64-L77
[sessions]: https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/auth/sessions.py#L38-L54
[logout]: https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/auth/routes.py#L80-L88
[case-events]: https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/cases/lifecycle.py#L84-L94
[admin-ui]: https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/frontend/src/views/AdminDashboardView.vue#L7-L75
[frontend-router]: https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/frontend/src/router.js#L19-L125
[material-admin]: https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/materials/routes.py#L29-L39
[ai-admin]: https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/ai/routes.py#L52-L73
[cases-service]: https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/cases/service.py#L110-L285
[case-authorize]: https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/cases/lifecycle.py#L37-L65
[agent-routes]: https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/agent/routes.py#L96-L596
[agent-repository]: https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/agent/repository.py#L86-L118
[materials-service]: https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/materials/service.py#L172-L225
[case-materials]: https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/case_materials/service.py#L34-L89
[attachments]: https://github.com/LittleDrinks/case-library/blob/7afc5bb9e182b1c61827d6024670002a42937fc6/backend/app/modules/attachments/service.py#L54-L241
