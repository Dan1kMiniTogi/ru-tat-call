"""Push subtitle.update into the signaling process (HTTP), or no-op."""

from __future__ import annotations

from typing import Optional, Protocol

import httpx
from ru_tat_call_shared.config import Settings
from ru_tat_call_shared.contracts.subtitles import SubtitleUpdateEvent


class SubtitlePublisher(Protocol):
    """Fan-out hook used by the ASR WebSocket handler."""

    async def publish(self, event: SubtitleUpdateEvent) -> None:
        """Send one subtitle event. Must not raise into the audio loop."""

    async def aclose(self) -> None:
        """Release HTTP clients."""


class NullSubtitlePublisher:
    """Drop events when SIGNALING_INTERNAL_URL is empty (tests / ASR-only)."""

    async def publish(self, event: SubtitleUpdateEvent) -> None:
        _ = event

    async def aclose(self) -> None:
        return None


class HttpSubtitlePublisher:
    """POST `/v1/internal/subtitles` on the signaling server.

    Args:
        base_url: Signaling origin, e.g. http://127.0.0.1:8000.
        secret: Same `SECRET_KEY` as signaling (`X-Internal-Token`).

    Example:
        pub = HttpSubtitlePublisher("http://127.0.0.1:8000", "dev-only-change-me")
        await pub.publish(event)
    """

    def __init__(self, base_url: str, secret: str) -> None:
        self._url = f"{base_url.rstrip('/')}/v1/internal/subtitles"
        self._secret = secret
        self._client = httpx.AsyncClient(timeout=1.0)

    async def publish(self, event: SubtitleUpdateEvent) -> None:
        try:
            await self._client.post(
                self._url,
                json=event.model_dump(mode="json"),
                headers={"X-Internal-Token": self._secret},
            )
        except Exception:
            return

    async def aclose(self) -> None:
        await self._client.aclose()


class RecordingSubtitlePublisher:
    """In-memory publisher for tests.

    Example:
        rec = RecordingSubtitlePublisher()
        create_app(settings, publisher=rec)
    """

    def __init__(self) -> None:
        self.events: list[SubtitleUpdateEvent] = []

    async def publish(self, event: SubtitleUpdateEvent) -> None:
        self.events.append(event)

    async def aclose(self) -> None:
        return None


def make_publisher(settings: Settings, override: Optional[SubtitlePublisher] = None) -> SubtitlePublisher:
    """Build the process publisher from settings unless a test override is given.

    Args:
        settings: App settings.
        override: Injected publisher (tests).

    Returns:
        Null, HTTP, or override publisher.
    """
    if override is not None:
        return override
    url = (settings.signaling_internal_url or "").strip()
    if not url:
        return NullSubtitlePublisher()
    return HttpSubtitlePublisher(url, settings.secret_key)
