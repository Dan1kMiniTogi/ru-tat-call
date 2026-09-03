"""Same-origin ASR proxy and public WS URL behind a TLS tunnel (step 5.2)."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

from fastapi.testclient import TestClient
from ru_tat_call_shared.config import Settings
from websockets.asyncio.server import serve

from signaling_server.app import create_app
from signaling_server.public_urls import asr_upstream_url


def _settings(tmp_path: Path, **kwargs) -> Settings:
    return Settings(_env_file=None, sqlite_path=tmp_path / "tun.db", **kwargs)


def test_client_config_same_origin_asr_path(tmp_path: Path) -> None:
    """GET /v1/client-config points at /v1/asr-stream on this host, not :8001."""
    with TestClient(create_app(_settings(tmp_path))) as client:
        url = client.get("/v1/client-config").json()["asr_ws_url"]
        assert url.endswith("/v1/asr-stream")
        assert ":8001" not in url
        assert url.startswith("ws://")


def test_client_config_uses_forwarded_https(tmp_path: Path) -> None:
    """cloudflared / ngrok: X-Forwarded-Proto https → wss on the public host."""
    with TestClient(create_app(_settings(tmp_path))) as client:
        url = client.get(
            "/v1/client-config",
            headers={
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "demo.trycloudflare.com",
            },
        ).json()["asr_ws_url"]
        assert url == "wss://demo.trycloudflare.com/v1/asr-stream"


def test_client_config_override(tmp_path: Path) -> None:
    """ASR_PUBLIC_WS_URL wins when ASR is on a second tunnel."""
    settings = _settings(tmp_path, asr_public_ws_url="wss://asr.example/v1/stream")
    with TestClient(create_app(settings)) as client:
        url = client.get("/v1/client-config").json()["asr_ws_url"]
        assert url == "wss://asr.example/v1/stream"


def test_asr_upstream_appends_query() -> None:
    """Proxy forwards the browser token query to local ASR."""
    settings = Settings(_env_file=None, asr_port=8001)
    assert asr_upstream_url(settings, "token=abc") == (
        "ws://127.0.0.1:8001/v1/stream?token=abc"
    )


def test_asr_proxy_echoes(tmp_path: Path) -> None:
    """Browser WS on /v1/asr-stream is bridged to the upstream ASR socket."""
    ready = threading.Event()
    port_box: dict[str, int] = {}
    stop = threading.Event()

    def runner() -> None:
        async def echo(ws) -> None:
            async for msg in ws:
                await ws.send(msg)

        async def main() -> None:
            async with serve(echo, "127.0.0.1", 0) as server:
                port_box["port"] = server.sockets[0].getsockname()[1]
                ready.set()
                while not stop.is_set():
                    await asyncio.sleep(0.05)

        asyncio.run(main())

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    assert ready.wait(timeout=5)
    upstream = f"ws://127.0.0.1:{port_box['port']}"
    settings = _settings(tmp_path, asr_upstream_ws_url=upstream)
    with TestClient(create_app(settings)) as client:
        with client.websocket_connect("/v1/asr-stream?token=t") as ws:
            ws.send_text("ping")
            assert ws.receive_text() == "ping"
    stop.set()
