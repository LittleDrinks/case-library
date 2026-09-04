# MEMORY

## Agent 派发（herdr / oh-my-herdr）

- worker 一律用 **glm-5.3**（pi profile，contest-qwen provider；即用户说的 glm5.3flash）；kimi 可作第二 worker，启动模式是 **--auto**（不是 --yolo）。codex/gpt-5.6-sol 仅咨询用，其端点（150.158.82.70:8080 /responses）不稳，502 时勿重试会话，直接换 kimi 审核。
- agent 只开独立 tab（`herdr tab create --label <name> --no-focus`），不用侧边栏 split pane。
- 监控：`herdr agent get/read/prompt --wait`；收口：worker 只推自己分支不开 PR 不合 main，parent 负 PR/合并/issue 留痕（round、commit、review 决定、耗时）。

## 并行批次约束（Alpha 收尾）

冲突面串行：CI 线 #58→#60（都碰 workflows/Dockerfile）；AI 模块 #14→#22；工作台前端 #16→#37→#48→#49。跨线可并行。Wave 划分见 GitHub Milestone「Alpha 0.1」16 个 open issue 与各 issue 依赖节。
