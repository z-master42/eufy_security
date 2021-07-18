import logging

import asyncio
import aiohttp
import traceback
from typing import Any, Coroutine, Text
from typing import Callable  # noqa pylint: disable=unused-import

from .const import DOMAIN

_LOGGER: logging.Logger = logging.getLogger(__package__)


class EufySecurityWebSocket:
    def __init__(
        self,
        host: str,
        port: int,
        session: aiohttp.ClientSession,
        open_callback: Callable[[], Coroutine[Any, Any, None]],
        message_callback: Callable[[], Coroutine[Any, Any, None]],
        close_callback: Callable[[], Coroutine[Any, Any, None]],
        error_callback: Callable[[Text], Coroutine[Any, Any, None]],
    ):
        self.host = host
        self.port = port
        self.session = session
        self.open_callback = open_callback
        self.message_callback = message_callback
        self.close_callback = close_callback
        self.error_callback = error_callback

        self.base = f"ws://{self.host}:{self.port}"
        self.ws: aiohttp.ClientWebSocketResponse = None
        self.loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()

    async def set_ws(self):
        self.ws: aiohttp.ClientWebSocketResponse = await self.session.ws_connect(
            self.base, autoclose=False, autoping=True, heartbeat=60
        )
        task = self.loop.create_task(self.process_messages())
        task.add_done_callback(self.on_close)
        await self.async_on_open()

    async def async_on_open(self) -> None:
        if not self.ws.closed:
            if self.open_callback is not None:
                await self.open_callback()

    async def process_messages(self):
        counter = 1
        async for msg in self.ws:
            try:
                await self.on_message(msg)
            except Exception as ex:  # pylint: disable=broad-except
                _LOGGER.error(
                    f"{DOMAIN} - Exception - process_messages : %s - traceback: %s",
                    ex,
                    traceback.format_exc(),
                )
            if counter % 100 == 0:
                counter = 1
                await asyncio.sleep(1)
            else:
                counter = counter + 1

    async def on_message(self, message):
        # _LOGGER.debug(f"{DOMAIN} - WebSocket message received {message[0:150]}")
        if self.message_callback is not None:
            await self.message_callback(message)

    def on_error(self, error: Text = "Unspecified") -> None:
        _LOGGER.debug(f"{DOMAIN} - WebSocket Error: %s", error)
        if self.error_callback is not None:
            asyncio.run_coroutine_threadsafe(
                self.error_callback(error), self.loop
            ).result()

    def on_close(self, future="") -> None:
        _LOGGER.debug(f"{DOMAIN} - WebSocket Connection Closed. %s", future)
        self.ws = None
        if self.close_callback is not None:
            asyncio.run_coroutine_threadsafe(self.close_callback(), self.loop).result()

    async def send_message(self, message):
        if self.ws is None or self.ws.closed == True:
            await self.set_ws()
        _LOGGER.debug(f"{DOMAIN} - WebSocket message sent. %s", message)
        await self.ws.send_str(message)
