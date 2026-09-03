"""Proxy `/v1/asr-stream` to the local ASR process (one public HTTPS origin)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from signaling_server.public_urls import asr_upstream_url

asr_proxy_router = APIRouter()


async def _bridge(client: WebSocket, upstream) -> None:
    """Copy frames both ways until either socket closes.

    Args:
        client: Browser WebSocket (already accepted).
        upstream: `websockets` connection to local ASR.

    Example:
        async with connect(url) as up:
            await _bridge(websocket, up)
    """

    async def to_up() -> None:
        try:
            while True:
                message = await client.receive()
                typ = message["type"]
                if typ == "websocket.disconnect":
                    return
                if typ != "websocket.receive":
                    continue
                text = message.get("text")
                if text is not None:
                    await upstream.send(text)
                else:
                    await upstream.send(message["bytes"])
        except (WebSocketDisconnect, ConnectionClosed):
            return

    async def to_client() -> None:
        try:
            async for frame in upstream:
                if isinstance(frame, bytes):
                    await client.send_bytes(frame)
                else:
                    await client.send_text(frame)
        except (WebSocketDisconnect, ConnectionClosed, Exception):
            return

    tasks = {asyncio.create_task(to_up()), asyncio.create_task(to_client())}
    _done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    for task in pending:
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


@asr_proxy_router.websocket("/v1/asr-stream")
async def asr_stream_proxy(websocket: WebSocket) -> None:
    """Accept a browser ASR socket and bridge it to `asr_upstream_ws_url`.

    Query string (`token=...`) is forwarded. If ASR is down the socket closes;
    the call itself is unaffected (client already treats ASR as optional).
    """
    await websocket.accept()
    settings = websocket.app.state.settings
    qs = websocket.scope.get("query_string", b"")
    if isinstance(qs, bytes):
        qs = qs.decode()
    url = asr_upstream_url(settings, qs)
    try:
        async with connect(url, open_timeout=5) as upstream:
            await _bridge(websocket, upstream)
    except Exception:
        pass
    try:
        await websocket.close()
    except Exception:
        pass
