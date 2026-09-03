"""进程内活动 Run 注册表：同 worker 即时取消，跨 worker 由 DB 标记加心跳观察。"""

from __future__ import annotations

import asyncio

from app.modules.agent.service import RunContext, execute_run


class RunSupervisor:
    def __init__(self) -> None:
        self._contexts: dict[str, RunContext] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    def start(self, context: RunContext) -> None:
        self._contexts[context.run.id] = context
        self._tasks[context.run.id] = asyncio.create_task(
            execute_run(context, self), name=f"agent-run-{context.run.id}"
        )

    def unregister(self, run_id: str) -> None:
        self._contexts.pop(run_id, None)
        self._tasks.pop(run_id, None)

    def cancel_local(self, run_id: str) -> bool:
        """同一进程内直接触发 Pydantic AI cancellation token。"""
        context = self._contexts.get(run_id)
        if context is None or context.token is None:
            return False
        context.token.cancel()
        return True

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.get_loop().call_soon_threadsafe(task.cancel)
        own = [task for task in tasks if task.get_loop() is asyncio.get_running_loop()]
        if own:
            await asyncio.gather(*own, return_exceptions=True)
        self._contexts.clear()
        self._tasks.clear()
