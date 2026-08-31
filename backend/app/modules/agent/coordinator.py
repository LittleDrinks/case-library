from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable


_END = object()


class RunChannel:
    def __init__(self, adapter) -> None:
        self.adapter = adapter
        self._items: list[object] = []
        self._subscribers: set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()
        self._done = False

    async def publish(self, item: object) -> None:
        async with self._lock:
            self._items.append(item)
            for subscriber in tuple(self._subscribers):
                subscriber.put_nowait(item)

    async def close(self) -> None:
        async with self._lock:
            self._done = True
            for subscriber in tuple(self._subscribers):
                subscriber.put_nowait(_END)

    async def stream(self) -> AsyncIterator[object]:
        queue: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            replay = tuple(self._items)
            done = self._done
            if not done:
                self._subscribers.add(queue)
        for item in replay:
            yield item
        if done:
            return
        try:
            while True:
                item = await queue.get()
                if item is _END:
                    return
                yield item
        finally:
            self._subscribers.discard(queue)


class RunCoordinator:
    def __init__(self) -> None:
        self._channels: dict[str, RunChannel] = {}
        self._tasks: set[asyncio.Task] = set()

    def start(self, run_id: str, adapter, factory: Callable[[], AsyncIterator]) -> RunChannel:
        channel = RunChannel(adapter)
        self._channels[run_id] = channel
        task = asyncio.create_task(self._consume(run_id, channel, factory))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return channel

    async def _consume(self, run_id: str, channel: RunChannel, factory) -> None:
        try:
            async for item in factory():
                await channel.publish(item)
        finally:
            await channel.close()
            self._channels.pop(run_id, None)

    async def shutdown(self) -> None:
        for task in tuple(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
