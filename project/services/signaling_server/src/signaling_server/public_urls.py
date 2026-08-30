"""Build browser-facing WebSocket URLs behind a TLS terminator (step 5.2)."""

from __future__ import annotations

from fastapi import Request
from ru_tat_call_shared.config import Settings


def public_asr_ws_url(settings: Settings, request: Request) -> str:
    """ASR WebSocket URL for the SPA.

    Prefers `asr_public_ws_url` (second public tunnel). Otherwise same host as
    the page, path `/v1/asr-stream`, with `wss` when the request is HTTPS
    (including `X-Forwarded-Proto` from cloudflared / ngrok).

    Args:
        settings: Process settings.
        request: Incoming HTTP request (`GET /v1/client-config`).

    Returns:
        Absolute `ws://` or `wss://` URL.

    Example:
        public_asr_ws_url(settings, request)
        # "wss://abc.trycloudflare.com/v1/asr-stream"
    """
    override = (settings.asr_public_ws_url or "").strip()
    if override:
        return override.rstrip("/")
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "http")
    proto = proto.split(",")[0].strip().lower()
    scheme = "wss" if proto == "https" else "ws"
    host = (
        request.headers.get("x-forwarded-host")
        or request.headers.get("host")
        or request.url.hostname
        or "127.0.0.1"
    )
    host = host.split(",")[0].strip()
    return f"{scheme}://{host}/v1/asr-stream"


def asr_upstream_url(settings: Settings, query_string: str) -> str:
    """Local ASR WebSocket URL the proxy connects to.

    Args:
        settings: Process settings (`asr_upstream_ws_url` or `asr_port`).
        query_string: Raw query from the browser (`token=...`), no leading `?`.

    Returns:
        `ws://127.0.0.1:{port}/v1/stream?...`

    Example:
        asr_upstream_url(settings, "token=abc")
    """
    base = (settings.asr_upstream_ws_url or "").strip().rstrip("/")
    if not base:
        base = f"ws://127.0.0.1:{settings.asr_port}/v1/stream"
    if query_string:
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}{query_string}"
    return base
