# BDD覆盖矩阵
业务规则—既有测试—中文Gherkin场景三维映射，对应GitHub #259的12个业务面。场景名摘自`backend/tests/bdd/features/*.feature`。

## 1 账号权限（account_access.feature）
| 业务规则 | 既有测试 | 中文Gherkin场景 |
|---|---|---|
| 演示账号登录后获得身份与CSRF令牌 | 后端：test_bootstrap_admin.py；浏览器：workbench.spec.js | 教师登录成功并恢复会话 |
| 错误密码与不存在账号统一拒绝，不泄露账号存在性 | 后端：test_bootstrap_admin.py | 错误密码被统一拒绝 |
| 未认证请求按"案例不存在"拒绝，不泄露草稿存在 | 后端：test_case_workflow.py；浏览器：annotations.spec.js | 未登录无法查看他人草稿 |
| 写操作必须携带CSRF令牌 | 后端：test_case_workflow.py、test_agent_chat.py | 缺少CSRF令牌无法创建案例 |
| 草稿仅作者可编辑，管理员越权返回403 | 后端：test_case_workflow.py；浏览器：workbench.spec.js | 管理员不能编辑教师的草稿 |
| 强制改密账号在改密前被拦截业务写入（403） | 后端：test_password_change.py | 强制改密账号被拦截业务写入 |
| 停用账号按无效凭据处理 | 后端：test_session_revocation.py | 停用账号无法登录 |
| 旧修订号保存被409拒绝并回带当前修订号 | 后端：test_case_workflow.py；浏览器：workbench.spec.js | 旧标签页保存被当前修订号拒绝 |

## 2 创建保存冲突（case_lifecycle.feature内保存并发）
| 业务规则 | 既有测试 | 中文Gherkin场景 |
|---|---|---|
| 保存以工作版本修订号为并发守卫，旧标签页保存被409拒绝且响应携带当前修订号 | 后端：test_case_workflow.py；浏览器：workbench.spec.js | 旧标签页保存被当前修订号拒绝（account_access.feature） |

## 3 投稿审核发布撤回（case_lifecycle.feature）
| 业务规则 | 既有测试 | 中文Gherkin场景 |
|---|---|---|
| 提交后进入待审并冻结正文只读 | 后端：test_case_workflow.py；浏览器：workbench.spec.js、homepage.spec.js | 作者提交草稿进入待审并冻结编辑 |
| 审核通过即发布且默认公开 | 后端：test_case_workflow.py；浏览器：workbench.spec.js、homepage.spec.js | 审核通过后案例发布并默认公开 |
| 审核开始后作者可撤回回到可编辑草稿 | 后端：test_case_workflow.py；浏览器：homepage.spec.js | 作者在审核开始后撤回回到工作稿 |
| 退回必须写明原因，缺原因校验失败 | 后端：test_case_workflow.py；浏览器：annotations.spec.js | 审核退回必须写明原因 |
| 带原因退回后作者可见反馈，重新提交清除反馈 | 后端：test_case_workflow.py | 管理员带原因退回后作者看到反馈并重新提交 |
| 发布即锁定，作者不可再编辑已发布案例 | 后端：test_case_workflow.py；浏览器：homepage.spec.js | 已发布案例作者不可再编辑 |
| 管理员下线后作者可另起新稿且发布版本历史保留 | 后端：test_case_workflow.py | 管理员下线已发布案例后作者可另起新稿 |

## 4 版本隔离恢复（version_restore.feature）
| 业务规则 | 既有测试 | 中文Gherkin场景 |
|---|---|---|
| 手动命名冻结历史版本，后续编辑互不影响 | 后端：test_version_loop.py | 作者冻结历史版本后继续编辑互不影响 |
| 恢复先把当前稿存为基线，再原子恢复目标并追加恢复记录 | 后端：test_version_loop.py | 恢复目标版本保留当前稿为基线 |
| 恢复以修订号为并发守卫，目标已变化时409且工作稿与历史不变 | 后端：test_version_loop.py、test_case_workflow.py | 恢复目标已变化时恢复被拒绝且工作稿不变 |
| 删除手动版本只移除历史，不影响当前稿 | 后端：test_version_loop.py | 删除历史版本不影响当前稿 |
| 被审核引用的送审版本不可删除（409） | 后端：test_version_loop.py | 被审核引用的历史版本不可删除 |

## 5 AI线程恢复取消重试（agent_thread.feature）
| 业务规则 | 既有测试 | 中文Gherkin场景 |
|---|---|---|
| 提问经运行产出AI回答 | 后端：test_agent_chat.py；浏览器：agent-chat.spec.js | 教师提问获得AI回答 |
| 线程为服务端所有，重开恢复历史消息快照 | 后端：test_agent_threads.py；浏览器：agent-chat.spec.js、agent-threads.spec.js | 断线后重新打开线程恢复历史消息 |
| 运行中可显式停止，终态cancelled且无残留活动运行 | 后端：test_agent_cancel_boundaries.py、test_agent_runs_lifecycle.py；浏览器：agent-chat.spec.js | 教师显式停止运行中的回答 |
| 失败消息可重试为新运行并引用原用户消息 | 后端：test_agent_runs_lifecycle.py；浏览器：agent-chat.spec.js | 回答失败后教师重试得到新运行 |

## 6 修订采用拒绝撤销过期（annotation_flow.feature + isolation.feature）
| 业务规则 | 既有测试 | 中文Gherkin场景 |
|---|---|---|
| 选区批注锚定quote原文 | 后端：test_annotation_anchors.py、test_annotations.py；浏览器：annotations.spec.js | 教师对选区挂批注并锚定原文 |
| 编辑按编辑器位置映射锚点，不按相似文字重挂 | 后端：test_annotation_anchors.py；浏览器：annotations.spec.js | 正文编辑后锚点跟随位置映射 |
| 目标改写后保留讨论并标记锚点changed | 后端：test_annotation_discussion.py、test_annotation_rounds.py；浏览器：annotations.spec.js、agent-annotation-rounds.spec.js | 目标原文改写后批注保留讨论但标记原文已变动 |
| AI修订候选经教师采用才写入正文并解决批注 | 后端：test_annotation_agent.py、test_agent_artifact_lock.py；浏览器：agent-annotation-rounds.spec.js | AI产出修订候选教师采用后写入正文 |
| 目标原文变化后未采用的修订标记expired | 后端：test_annotation_discussion.py、test_agent_tracer.py；浏览器：agent-annotation-rounds.spec.js | 目标原文变化后未采用的修订过期 |
| 拒绝修订不改正文，候选标记已拒绝 | 后端：test_annotation_agent.py | 修订候选被拒绝后正文不变（isolation.feature） |
| AI直接写入可撤销一次，正文变更后撤销被409拒绝 | 后端：test_agent_document_write.py；浏览器：agent-chat.spec.js | AI直接写入后教师撤销恢复原文；重复撤销同一写入保持幂等；正文变化后撤销被拒绝（undo_sync.feature） |

## 7 批注锚点讨论（annotation_flow.feature）
| 业务规则 | 既有测试 | 中文Gherkin场景 |
|---|---|---|
| 批注线程的追加回复跨提交轮次保留 | 后端：test_annotation_discussion.py、test_annotation_rounds.py；浏览器：annotations.spec.js | 目标原文改写后批注保留讨论但标记原文已变动 |

## 8 资料导入去重审核权限（material_import.feature）
| 业务规则 | 既有测试 | 中文Gherkin场景 |
|---|---|---|
| 管理员批量导入逐文件生成候选记录 | 后端：test_material_imports.py；浏览器：material-import.spec.js | 管理员批量导入生成候选记录 |
| 相同内容重复导入标记重复并指向原候选 | 后端：test_material_imports.py | 相同内容重复导入标记为去重 |
| 教师无导入与审核权限（403） | 后端：test_material_imports.py；浏览器：material-import.spec.js | 教师无法执行导入与审核 |
| 审核通过后素材进入素材库可读 | 后端：test_material_candidate_review.py；浏览器：material-import.spec.js | 审核通过后素材进入素材库可读 |
| 校内级别素材对未登录读者404 | 后端：test_case_materials.py；浏览器：search-materials.spec.js | 校内素材对未登录读者不可读 |

## 9 来源引用移除下线（case_sources.feature）
| 业务规则 | 既有测试 | 中文Gherkin场景 |
|---|---|---|
| 引用锚定被引案例的已发布版本，不漂移 | 后端：test_case_sources.py | 作者挂载已发布案例为引用来源 |
| 同一来源不可重复挂载（409） | 后端：test_case_sources.py | 重复挂载同一来源被拒绝 |
| 正文已引用的来源删除被409拒绝 | 后端：test_case_sources.py、test_public_reference_count_e2e.py | 正文引用后删除来源被拒绝 |
| 未被正文引用的来源可删除 | 后端：test_case_sources.py | 未引用的来源可以删除 |
| 被引案例下线后引用条目锁定为不可读 | 后端：test_case_sources.py | 被引用案例下线后引用条目锁定内容 |

## 10 标签搜索同步（tag_skill.feature + search.feature）
| 业务规则 | 既有测试 | 中文Gherkin场景 |
|---|---|---|
| 案例标签保存时去重 | 后端：test_tags.py、test_case_tags.py | 案例保存标签并去重 |
| 必填标签组缺失拦截投稿，补齐后放行 | 后端：test_case_tags.py | 必填标签组缺失时投稿被拦截 |
| 管理员上传发布Skill，教师读取已发布目录与内容 | 后端：test_skill_platform.py、test_skill_package_parser.py；浏览器：agent-tracer.spec.js | 管理员上传并发布Skill包 |
| 教师无Skill上传发布权限（403） | 后端：test_skill_platform.py | 教师不能上传或发布Skill |
| 检索标签条件支持任意（或）与全部（且）模式 | 后端：test_search_tag_conditions.py、test_search_service.py；浏览器：search-materials.spec.js | 教师按任意模式检索案例；教师以全部模式检索案例 |
| 未知标签检索422拒绝 | 后端：test_search_tag_conditions.py | 未知标签检索被拒绝 |
| 目录同步期间检索503而非泄露 | 后端：test_search_state.py、test_operations.py | 目录未就绪时检索返回服务不可用 |
| 检索请求携带用户权限域，匿名仅见公开内容 | 后端：test_search_service.py、test_search_projection.py；浏览器：search-materials.spec.js | 匿名检索仅见公开内容 |
| 业务变更经outbox同步检索目录 | 后端：test_search_outbox.py、test_search_indexer.py、test_search_case_change.py；真实资源：test_search_meilisearch_e2e | 发布后公开检索能命中案例；下线后公开检索不再命中案例（search_sync.feature，e2e） |

## 11 Skill上传发布执行（skill_run.feature）
| 业务规则 | 既有测试 | 中文Gherkin场景 |
|---|---|---|
| 对话绑定已发布Skill，运行记录固化版本与内容哈希 | 后端：test_agent_skill_run.py；浏览器：agent-tracer.spec.js、agent-sidebar.spec.js | 已发布Skill驱动运行并固化版本哈希 |
| 重新发布后新运行使用新版本，各运行记录各自哈希 | 后端：test_agent_skill_run.py | 重新发布后新运行使用新版本 |
| 未发布Skill绑定被拒绝且不产生运行记录 | 后端：test_agent_skill_run.py | 未发布的Skill被拒绝 |

## 12 DOCX导出（docx_export.feature）
| 业务规则 | 既有测试 | 中文Gherkin场景 |
|---|---|---|
| 正文按固定版式导出合法Word文件，导出件非编辑真源 | 后端：test_docx_export.py；浏览器：workbench.spec.js | 作者导出草稿案例为DOCX文件 |
| 未登录访客导出未发布案例404 | 后端：test_docx_export.py | 未登录访客不能导出未发布案例 |

## 13 隔离越权（isolation.feature）
| 业务规则 | 既有测试 | 中文Gherkin场景 |
|---|---|---|
| 他案线程不可穿越：跨用户建线程404，线程列表只含本人 | 后端：test_agent_threads.py、test_agent_visibility.py；浏览器：agent-threads.spec.js | 其他教师的AI线程不可见 |
| 修订候选决策绑定所属线程，跨线程提交404且候选保持待确认 | 后端：test_agent_artifact_lock.py | 绑定到错误线程的修订候选被拒绝 |
| 拒绝修订不改正文 | 后端：test_annotation_agent.py | 修订候选被拒绝后正文不变 |
| 管理员无权读取教师私人AI线程 | 后端：test_agent_visibility.py；浏览器：agent-threads.spec.js | 管理员看不到教师的私人讨论 |

## 覆盖缺口与说明
浏览器BDD切片依赖隔离环境集成，当前标注为**待隔离集成**：登录会话（cookie+CSRF建立、会话恢复）、编辑自动保存（save-state流转与修订号递增的界面反馈）、恢复取消对话框（确认框点取消不发请求、状态不变，version_restore.feature内注释已声明归入浏览器切片）、DOCX下载链（浏览器download事件到文件落盘，workbench.spec.js已有代表实现）。这四片的行为发生在真实浏览器与用户会话层，Playwright E2E（frontend/tests/e2e/）待隔离环境就绪后接入执行，不由中文Gherkin的API层步骤重复。
并发与真实资源测试保留在原有真实资源层，不由中文Gherkin重复：test_case_lifecycle_e2e（真实Mongo副本集下的生命周期并发）、test_agent_threads_e2e（副本集事务与运行并发）、test_annotation_rounds的replica-set用例（真实副本集合并事务）、test_search_meilisearch_e2e（真实Meilisearch实例）、test_material_import_e2e的RAR用例（真实unrar解析）。中文Gherkin以进程内TestClient覆盖上述业务规则的单线程语义，并发正确性与真实二进制/实例行为以既有E2E层为准。
test_skill_platform.py 的并发上传用例已迁移至 test_skill_platform_e2e.py（真实 MongoDB replica set，经既有 E2E 应用 HTTP 公共接口执行），断言原样保留：并发上传各得唯一 v1..vN，latest 不回退。test_material_imports.py 的RAR用例fixture路径解析已同时覆盖宿主（assets/学习资料md.rar）与容器（/app/fixtures/学习资料md.rar）两种布局。
执行状态：轻量层 60 个中文场景（含第6面 undo_sync.feature 三个场景）已实际执行并全部通过（mongomock TestClient，`make bdd-zh`，JUnit/HTML 报告归档）；该 60 场景不在 backend-test 默认套件重复执行（默认命令 `--ignore=tests/bdd`，避免无意义双跑）。第10面 search_sync.feature 两个场景代码完成、标记 e2e，依赖隔离 Compose e2e 环境（backend-e2e 套件）实际执行，尚未运行。浏览器切片 4 片（登录会话、编辑自动保存、恢复取消对话框、DOCX下载链）待做：固定为真实 .feature + 既有 Playwright/JS Gherkin 绑定另做，未完成的 Python 浏览器文件不进本切片。undo_sync 场景写入前提为真空正文，断言撤销恢复正文完整结构相等、重复撤销严格 200 且修订号不变、正文变化后首次撤销严格 409 且写入保持 written。search_sync 场景经 e2e-app 真实 HTTP 与常驻 search-worker 消费 outbox 后的公开 /api/search 观察：标题每轮唯一，命中按案例 id 与标题双重匹配，先证明发布命中，下线后轮询确认消失；Mongo→worker→Meilisearch 的最终一致投影由既有 test_search_meilisearch_e2e（真实实例）验证，中文Gherkin 以目录可观察结果为准。宿主（assets/相对路径）与容器（/app/fixtures/）双布局的RAR用例已在宿主实测通过，容器内验证待隔离集成。
