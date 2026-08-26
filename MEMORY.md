# MEMORY

## Codex 任务派发（herdr）

每 task 独立 git worktree：`git worktree add -b issue/<NN>-<slug> ../cla-wt/<NN>-<slug> origin/main`；任务书写入 worktree 的 `TASK.md`（目标、实现顺序、范围文件、纪律、完成标记 `TASK_DONE_<NN>`），启动脚本为 worktree 内 `run.sh`：

```sh
#!/bin/sh
cd "<worktree 绝对路径>"
exec codex --model gpt-5.6-luna -c model_reasoning_effort="max" "Read TASK.md in this directory and execute it fully."
```

每个 task 开一个独立 herdr tab，不用 split：`herdr tab create --workspace <ws> --label "issue-<NN>-<slug>"`，从响应 `result.root_pane.pane_id` 取根窗格 id，再 `herdr pane run <pane_id> "sh <worktree>/run.sh"`。workspace id 以 `herdr workspace list` 实时为准，不持久。
模型名必须用全称 `gpt-5.6-luna`（`~/.codex/config.toml` 默认即它：max reasoning、danger-full-access、approval never）；传短名如 `luna` 会 404。
启动方式用 codex TUI，不用 `codex exec` 非交互式——人可随时进 tab 观察、esc 打断、直接补话。
监控：`herdr pane list` 看 `agent_status`；等待 `herdr wait agent-status <pane> --status idle --timeout …`；读屏 `herdr pane read <pane> --source recent --lines N`。
收口：agent 完成后人工检查 worktree diff，确认后建 PR；agent 自身只 push 自己分支，不 merge main、不开 PR。

## 并行批次约束（Alpha 收尾）

冲突面串行：CI 线 #58→#60（都碰 workflows/Dockerfile）；AI 模块 #14→#22；工作台前端 #16→#37→#48→#49。跨线可并行。Wave 划分见 GitHub Milestone「Alpha 0.1」16 个 open issue 与各 issue 依赖节。
