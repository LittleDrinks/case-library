# AI 接入、模型管理与用量监控：研究记录

核对日期：2026-11-14。资料来自项目实现、供应商官方 API 文档及产品官方源码。本文记录接口事实、现状差距和由这些事实得到的产品判断；未使用真实密钥调用外部模型。

## 当前项目实际支持

| 范围 | 核对结果 | 源码 |
| --- | --- | --- |
| 平台接入 | 一组环境配置中的 `baseUrl`、密钥和模型白名单；管理员只修改 `fallbackModel` | [service.py](../../backend/app/modules/ai/service.py)、[models.py](../../backend/app/modules/ai/models.py) |
| 默认模型 | `fallbackModel` 实际表示自动模式账户使用的平台默认模型；当前没有调用失败后自动切换供应商的行为 | [service.py](../../backend/app/modules/ai/service.py) |
| 获取模型 | 已有个人设置接口 `POST /api/ai/models/discover`，要求请求携带 URL 和密钥；返回模型 ID，不返回能力或探测结果 | [routes.py](../../backend/app/modules/ai/routes.py)、[provider.py](../../backend/app/modules/ai/provider.py) |
| 可用状态 | `configured` 仅判断配置是否齐全；获取模型失败统一返回“无法获取模型列表”。没有真实推理探测接口 | [service.py](../../backend/app/modules/ai/service.py)、[routes.py](../../backend/app/modules/ai/routes.py) |
| 密钥 | 个人密钥已加密保存；读取只返回 `hasApiKey`。同一 URL 下编辑时空密钥保留旧值，更换 URL 要求提供新密钥 | [service.py](../../backend/app/modules/ai/service.py) |
| 协议与内网 | 运行时使用 `OpenAIChatModel`；没有 Anthropic、Ollama 原生适配。非测试环境要求 HTTPS、公网地址，现有实现不能直接接入本机 Ollama | [provider.py](../../backend/app/modules/ai/provider.py)、[transport.py](../../backend/app/modules/ai/transport.py) |
| 用量记录 | `ai_usage` 保存短期请求限额和并发租约；后端未发现输入、输出、缓存 Token 的持久化采集与聚合，不能直接提供历史用量大屏 | [quota.py](../../backend/app/modules/ai/quota.py)、[database.py](../../backend/app/core/database.py) |

## 模型发现与真实调用是不同检查

OpenAI 的 `GET /models` 返回 ID、所属方等基本信息，未提供统一的视觉、工具调用、流式输出能力字段。模型出现在列表中，仅能证明该次模型目录请求成功。[OpenAI Models API](https://developers.openai.com/api/reference/resources/models/methods/list)

Anthropic 当前 Models API 提供能力、上下文等元数据，并使用分页；Ollama 的 `/api/tags` 列出模型，`POST /api/show` 提供能力等详细信息。元数据描述供应商声明的能力，仍不能证明当前密钥、网关和模型组合可以成功完成应用请求。[Anthropic Models API](https://platform.claude.com/docs/en/api/models/list)、[Ollama 模型列表](https://docs.ollama.com/api/tags)、[Ollama 模型详情源码文档](https://github.com/ollama/ollama/blob/main/docs/api.md#show-model-information)

Open WebUI 将连接配置与模型选择分开；其 Verify Connection 实际访问 `/models`，文档明确说明部分兼容供应商不提供该接口，并提供手动填写 Model IDs 的方式。保存配置、获取目录和发出测试消息因此有不同含义。[连接配置](https://docs.openwebui.com/getting-started/quick-start/connect-a-provider/)、[兼容接口与手动模型 ID](https://docs.openwebui.com/getting-started/quick-start/connect-a-provider/starting-with-openai-compatible/)

LiteLLM 区分网关存活检查和模型健康检查；后者会向指定模型发送实际请求，并记录检查时间和错误。最小文本调用也只验证该路径，工具调用、流式输出和视觉输入需要相应请求才能验证。测试会产生少量 Token 使用量。[LiteLLM 健康检查](https://docs.litellm.ai/docs/proxy/health)

401、403、404、429、服务端错误和网络超时有不同原因；429 还可能分别表示速率或额度限制。探测结果保留脱敏后的错误类别，能帮助管理员判断应该更换密钥、模型、地址还是稍后重试。[OpenAI 错误说明](https://developers.openai.com/api/docs/guides/error-codes)

## 适用于本项目的六项产品判断

以下为研究判断，不代表功能已实现。

1. **接入记录独立管理。** 每个接入有名称、协议、地址、密钥保存状态和启停状态；使用稳定的 `providerId`。同名模型可以存在于不同接入中。Dify 和 Open WebUI 都将供应商凭据与模型选择分开管理。[Dify 模型供应商](https://docs.dify.ai/en/cloud/use-dify/workspace/model-providers)、[Open WebUI 连接配置](https://docs.openwebui.com/getting-started/quick-start/connect-a-provider/)
2. **获取模型保留手动路径。** 目录可搜索、筛选接入和启用状态；不支持 `/models` 时明确显示原因，并允许填写准确模型 ID。刷新失败不能清空已保存目录或默认选择；能力未知时显示“未验证”。[Open WebUI 兼容接口说明](https://docs.openwebui.com/getting-started/quick-start/connect-a-provider/starting-with-openai-compatible/)
3. **探测指定的接入和模型。** 结果显示测试内容、成功或错误、耗时和检查时间；未经检测显示“未检测”，保存成功不产生“在线”结论。地址、密钥或模型变化后，旧探测结果不能代表新配置。[LiteLLM 健康检查](https://docs.litellm.ai/docs/proxy/health)
4. **主模型绑定 `(providerId, modelId)`。** 备用模型也需要完整组合。自动切换会改变请求目的地和实际使用模型，需要明确配置开关、适用失败类型和备用顺序；现有 `fallbackModel` 字段不能充当这项能力已存在的证据。LiteLLM 的失败切换也是显式映射配置。[LiteLLM 失败切换](https://docs.litellm.ai/docs/proxy/reliability)、[本项目选择逻辑](../../backend/app/modules/ai/service.py)
5. **沿用已有密钥不回显的行为。** 编辑界面显示“密钥已保存”，替换和删除作为明确操作；探测由服务端读取已保存密钥。这样可以解决当前每次获取模型都要重新输入密钥的不便。[本项目设置逻辑](../../backend/app/modules/ai/service.py)、[个人设置界面](../../frontend/src/views/AISettingsView.vue)
6. **监控以 Token 和调用状态为中心。** 使用统一时间范围、接入和模型筛选，再展示模型分布、Token 趋势和用户趋势。已有资料能支持这些日常管理需求；复杂计费、交易、多租户和路由策略需要另外的实际需求依据。[Sub2API 管理大屏源码](https://github.com/Wei-Shaw/sub2api/blob/530c5e3a4f9c73ca2b0881191d0ef8e0d82c5484/frontend/src/views/admin/DashboardView.vue)

据此可将管理入口组织为“监控概览、API 接入、模型目录、默认模型”。这四个入口对应查看使用情况、配置连接、选择可用模型和决定实际调用目标四个不同动作。

## Sub2API 大屏的可核对依据

确认研究对象为原始仓库 [Wei-Shaw/sub2api](https://github.com/Wei-Shaw/sub2api)，本次源码引用固定到提交 `530c5e3a4f9c73ca2b0881191d0ef8e0d82c5484`。

| 区域 | 源码中的行为 | 适合本项目的解释 |
| --- | --- | --- |
| 模型分布 | 环图旁显示模型、请求数和 Token 表格；分布可按 Token 统计 | 环图标题明确“Token 占比”；表格保留请求数和 Token，省去金额 |
| Token 趋势 | Input、Output、Cache Creation、Cache Read 四条 Token 曲线；Cache Hit Rate 使用右侧百分比轴 | Input 明确标成“普通输入”，缓存读写独立列出；鼠标提示解释总输入 |
| 用户趋势 | 独立的用户时间趋势，支持 Token 维度 | 合成示例使用“教师 A”“教师 B”；人数多时筛选或显示前几名及其他 |

依据：[模型分布组件](https://github.com/Wei-Shaw/sub2api/blob/530c5e3a4f9c73ca2b0881191d0ef8e0d82c5484/frontend/src/components/charts/ModelDistributionChart.vue)、[Token 趋势组件](https://github.com/Wei-Shaw/sub2api/blob/530c5e3a4f9c73ca2b0881191d0ef8e0d82c5484/frontend/src/components/charts/TokenUsageTrend.vue)、[管理大屏](https://github.com/Wei-Shaw/sub2api/blob/530c5e3a4f9c73ca2b0881191d0ef8e0d82c5484/frontend/src/views/admin/DashboardView.vue)。这里只引用界面组织和统计逻辑，不引入该项目的订阅中转及金额业务。

## 跨供应商 Token 口径

下表中的“总输入”包括普通输入、缓存读取和缓存创建。“普通输入”是未落入缓存读写分类的输入。保留原始供应商 usage 和协议类型，才能重新核对统计结果。

| 协议 | 总输入 | 缓存读取 | 缓存创建 | 普通输入 |
| --- | --- | --- | --- | --- |
| OpenAI Responses | `usage.input_tokens` | `input_tokens_details.cached_tokens` | 当前接口的 `input_tokens_details.cache_write_tokens` | 总输入减去缓存读取和缓存创建 |
| OpenAI Chat Completions | `usage.prompt_tokens` | `prompt_tokens_details.cached_tokens` | 当前接口的 `prompt_tokens_details.cache_write_tokens` | 总输入减去缓存读取和缓存创建 |
| Anthropic Messages | `input_tokens + cache_read_input_tokens + cache_creation_input_tokens` | `cache_read_input_tokens` | `cache_creation_input_tokens` | `input_tokens` |

OpenAI 的缓存读写已经包含在总输入中，再加一次会重复统计；当前官方接口已经存在缓存创建字段，不能笼统认为 OpenAI 都不提供。不同模型、旧接口及兼容供应商的实际返回可能不同，缺失值需要保留。Anthropic 的 `input_tokens` 单独表示普通输入，必须加上两类缓存才能得到总输入。[OpenAI 缓存说明与计算示例](https://developers.openai.com/api/docs/guides/prompt-caching)、[OpenAI Chat Completions usage](https://developers.openai.com/api/reference/resources/chat/subresources/completions/streaming-events)、[Anthropic 缓存统计说明](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)

统计判断：

- **总 Token = 总输入 + 总输出。** 缓存读取和创建属于输入分项；推理 Token 属于输出分项。分项与总量不能再次相加。[OpenAI Token 说明](https://help.openai.com/en/articles/4936856-understanding-and-counting-tokens)
- **缓存命中率 = 缓存读取 Token 之和 / 同一批记录的总输入 Token 之和。** 这是按 Token 加权的读取占比，不能平均每个请求的百分比。缓存创建不是命中。Sub2API 的相应公式为 `read / (ordinaryInput + creation + read)`；跨供应商时先按上表统一。[Sub2API 趋势计算](https://github.com/Wei-Shaw/sub2api/blob/530c5e3a4f9c73ca2b0881191d0ef8e0d82c5484/frontend/src/components/charts/TokenUsageTrend.vue)
- **未知不能当作零。** 未返回 usage、流式请求中断、供应商未提供缓存细分分别显示“未知”“部分统计”“未提供”。已有总输入和缓存读取时，缺缓存创建不妨碍计算读取占比，但无法可靠拆出普通输入。分母为零时命中率显示“—”；数据齐全且读取为零才显示 `0%`。这属于统计解释要求。
- **流式 usage 不能逐事件相加。** OpenAI 流式调用可能缺少最终 usage 块；Anthropic `message_delta` 的 usage 是累计值。应保留最终累计值和完整性状态，避免重复计数或把中断请求记成零消耗。[OpenAI 流式 usage](https://developers.openai.com/api/reference/resources/chat/subresources/completions/streaming-events)、[Anthropic 流式说明](https://platform.claude.com/docs/en/build-with-claude/streaming)
- **部分统计需要覆盖率。** 汇总同时显示“已取得完整 usage 的调用数 / 总调用数”；缓存命中率只计算读取量和总输入都已知的同一批记录，并标明覆盖范围。缺测时间段留空，确认无调用的时间段才显示零。这里的覆盖率是数据完整程度，不表示模型成功率。

合成示例：教师 A 的 OpenAI 请求返回总输入 1,000、缓存读取 600、缓存创建 200、输出 100；教师 B 的 Anthropic 请求返回普通输入 200、缓存读取 600、缓存创建 200、输出 100。两者均应显示普通输入 200、总输入 1,000、总 Token 1,100、缓存命中率 60%。如果创建字段缺失，仍可显示已知的总输入和读取占比，但普通输入与缓存创建不能填零。

监控原型的核心统计口径可以限制在：上游模型调用次数、成功率、总 Token、缓存读取占比及平均响应耗时；模型表和用户趋势沿用同一筛选范围。一次代理任务可能产生多次模型调用，因此“调用次数”不能直接标成“对话次数”。探测请求单独标记，默认不混入教学使用趋势。全部数值为原型合成示例时，需要在页面明确写明“演示数据”。这些属于依据接口结构作出的产品判断，当前仓库没有对应采集能力。
