from __future__ import annotations

from functools import partial

import anyio
from starlette._utils import create_collapsing_task_group
from starlette.requests import ClientDisconnect
from starlette.responses import StreamingResponse


async def _close_iterator(iterator) -> None:
    close = getattr(iterator, "aclose", None)
    if close:
        await close()


class ClosableStreamingResponse(StreamingResponse):
    def __init__(self, response, source) -> None:
        super().__init__(
            response.body_iterator, response.status_code, dict(response.headers),
            response.media_type, response.background,
        )
        self._source = source

    async def stream_response(self, send) -> None:
        try:
            await super().stream_response(send)
        finally:
            with anyio.CancelScope(shield=True):
                await _close_iterator(self._source)
                await _close_iterator(self.body_iterator)

    async def _serve_with_disconnect(self, receive, send) -> None:
        async with create_collapsing_task_group() as task_group:

            async def run_and_cancel(func) -> None:
                await func()
                task_group.cancel_scope.cancel()

            task_group.start_soon(run_and_cancel, partial(self.stream_response, send))
            await run_and_cancel(partial(self.listen_for_disconnect, receive))

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "websocket":
            await super().__call__(scope, receive, send)
            return
        try:
            await self._serve_with_disconnect(receive, send)
        except OSError as error:
            raise ClientDisconnect() from error
        if self.background is not None:
            await self.background()
