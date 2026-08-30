# GitHub Issues
工作项使用 GitHub Issues，通过 `gh` 创建、读取、评论、标记和关闭。PR 不作为分诊入口。
## Wayfinding operations
地图与决策票分别使用 `wayfinder:map` 和 `wayfinder:research|prototype|grilling|task` 标签。决策票通过 GraphQL `addSubIssue` 挂到地图，通过 `addBlockedBy` 建立原生阻塞关系。frontier 是地图的 open、无 assignee、`blockedBy` 全部 closed 的子 Issue。认领先添加当前执行者为 assignee；解决时先评论答案，再关闭决策票，并在地图 `Decisions so far` 追加链接与一句结论。
