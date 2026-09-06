---
sources:
  zotero_tags: https://www.zotero.org/support/collections_and_tags#the_tag_selector
  algolia_refinement_list: https://www.algolia.com/doc/api-reference/widgets/refinement-list/js
  algolia_hierarchy: https://www.algolia.com/doc/api-reference/widgets/hierarchical-menu/js
  meilisearch_facets: https://www.meilisearch.com/docs/capabilities/filtering_sorting_faceting/how_to/filter_with_facets
  meilisearch_facet_search: https://www.meilisearch.com/docs/reference/api/facet-search/search-for-facet-values
---
# 标签筛选与分面检索
## 成熟产品事实
| 来源 | 已核实行为 | 适用边界 |
| --- | --- | --- |
| Zotero `zotero_tags` | 同时选择多个标签要求全部具备，即 AND；标签选择器支持搜索标签名，随当前结果更新候选标签；显示全库标签时，无当前结果的标签置灰 | 证明逐步缩小文献结果是一种成熟交互，不代表所有产品都默认 AND |
| Algolia `algolia_refinement_list` | `refinementList` 可设 AND 或 OR，组件默认 OR；支持标签值搜索、限量显示、展开更多及计数 | 证明两种逻辑都常用；组件配置能力不等于产品已经提供用户切换控件 |
| Algolia `algolia_hierarchy` | `hierarchicalMenu` 使用分层路径属性；一条记录可以具有多条路径；`refine` 设置层级筛选路径 | 层级导航组件带有路径筛选语义，不能直接等同于仅用于组织任意多选标签的目录 |
| Meilisearch `meilisearch_facets` | 搜索响应的 `facetDistribution` 返回结果中各属性值的文档数量，支持按数量排序 | 计数依赖请求的查询和过滤条件，不是无条件全库数量，也不天然等于加入标签后的总数 |
| Meilisearch `meilisearch_facet_search` | 独立搜索标签值，`q` 和 `filter` 限制参与计算的文档，`facetQuery` 匹配标签值；属性需列入 `filterableAttributes` | 当前文档说明仅使用 `facetQuery` 第一词匹配；未传此参数时最多返回 100 个值，不能把返回列表当完整分类目录 |
Meilisearch 当前文档中，facet-search 计数默认估算，`exhaustiveFacetCount: true` 请求精确计数且更慢。部署版本是否具备该参数、中文标签和别名如何匹配，需对实际版本核验。来源：`meilisearch_facets`、`meilisearch_facet_search`。
## 本项目规则
标签目录负责组织和找词，查询条件负责布尔关系。管理员新建的组与标签直接进入案例属性和搜索选项，不因所属组而改变匹配规则。
普通页面默认“全部符合”（AND），可切换“任一符合”（OR）。后端支持 `(毛概 OR 马原) AND 创新` 等混合条件，供 Agent 使用；当前不要求前端高级条件编辑器，目录层级不参与推导查询关系。
Agent 可以自主换词、翻页和补充检索；放宽条件得到的资源标记为替代候选，说明未满足的原始要求，不视为严格匹配。
## 标签与计数
万级案例的界面重点是“搜索正文 + 搜索标签名 + 按目录浏览 + 已选标签可移除”，避免一次铺开全部标签。已选标签始终保留在条件区，不因当前候选列表截断或变成零结果而消失。管理员目录包含尚未用于任何案例的标签，不能完全由搜索分面反推目录。
标签旁数字定义为“当前结果中带该标签的案例数”。AND 模式下，未选标签的这个数字等于再加入该条件后剩余的数量；OR 模式下不是加入后的总数，不能相加，因为案例可能同时具有多个标签。OR 模式不能隐藏或禁用仅因当前结果中未出现而计数为零的标签，它们仍可能扩展结果。
管理看板按案例去重统计。默认采用当前发布版本；全部案例范围内，有工作稿取最新工作内容，否则取发布内容。一个案例可计入多个标签，案例总数只计算一次，零案例分类仍显示。
若展示“加入后共多少条”，必须按对应布尔表达式求去重后的结果数；不能把排除自身标签过滤的分面计数直接当作预测。列表、标签计数和标签名检索均应使用同一可见范围，搜索计数也不能代替管理看板的全库统计。
## 性能与验收
一万条案例本身不足以证明检索延迟；正文长度、标签种类、每案标签数、分布偏斜、权限过滤、并发和精确计数共同影响成本。现有搜索引擎已有分面和过滤能力，不应仅凭数量更换引擎。
使用接近真实正文和标签分布的万级数据，测量正文搜索、AND/OR 组合、标签名搜索及计数的端到端 p50/p95；包括热门标签、罕见标签、零结果、标签重叠及并发。另核验管理员新增标签后出现、改名后案例关联不丢、筛选与计数权限一致。性能目标尚未决定；未执行压测。
