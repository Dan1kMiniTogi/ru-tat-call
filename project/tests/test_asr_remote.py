"""RemoteColabASREngine POSTs PCM to the Colab worker (step 4.2)."""

import base64
import json
import sys

import httpx
from ru_tat_call_shared.config import PROJECT_ROOT
from ru_tat_call_shared.contracts.common import SpeechLanguage

from asr_server.engine import RemoteColabASREngine
from asr_server.mock_engine import TICK_BYTES

sys.path.insert(0, str(PROJECT_ROOT / "apps" / "colab_asr"))
from worker import DummyRecognizer, create_app  # noqa: E402


def _engine_from_handler(handler, **kwargs) -> RemoteColabASREngine:
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="http://worker.test")
    return RemoteColabASREngine("http://worker.test", http_client=client, **kwargs)


def test_feed_partial_then_final() -> None:
    """Worker is_final=false then true maps to partial/final with a stable id until final."""
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content.decode("utf-8")))
        n = len(calls)
        if n == 1:
            return httpx.Response(
                200, json={"text": "Әни,", "language": "tt", "is_final": False}
            )
        return httpx.Response(
            200, json={"text": "Әни, сегодня", "language": "mixed", "is_final": True}
        )

    engine = _engine_from_handler(handler)
    pcm = b"\x00" * TICK_BYTES
    first = engine.feed(pcm)
    assert len(first) == 1
    assert first[0].status == "partial"
    assert first[0].text == "Әни,"
    assert first[0].language == SpeechLanguage.TT
    second = engine.feed(pcm)
    assert second[0].status == "final"
    assert second[0].text == "Әни, сегодня"
    assert second[0].language == SpeechLanguage.MIXED
    assert first[0].subtitle_id == second[0].subtitle_id
    body = calls[0]
    assert body["encoding"] == "pcm_s16le"
    assert body["sample_rate"] == 16000
    assert base64.b64decode(body["audio_base64"]) == pcm
    assert engine.flush() == []


def test_http_error_and_empty_pcm_return_empty() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json={"detail": "down"})

    engine = _engine_from_handler(handler)
    assert engine.feed(b"") == []
    assert engine.feed(b"\x00\x00") == []


def test_flush_finalizes_open_partial() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"text": "Кичә", "language": "tt", "is_final": False}
        )

    engine = _engine_from_handler(handler)
    engine.feed(b"\x00\x00")
    flushed = engine.flush()
    assert flushed[0].status == "final"
    assert flushed[0].text == "Кичә"
    assert flushed[0].language == SpeechLanguage.TT


def test_worker_token_header() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("x-worker-token", ""))
        return httpx.Response(
            200, json={"text": "ok", "language": "ru", "is_final": True}
        )

    engine = _engine_from_handler(handler, worker_token="secret")
    engine.feed(b"\x00\x00")
    assert seen == ["secret"]


def test_against_dummy_colab_app() -> None:
    """Same JSON contract as the Colab dummy backend, via Starlette TestClient."""
    from fastapi.testclient import TestClient

    app = create_app(DummyRecognizer())

    class _Shim:
        def post(self, url: str, json=None, headers=None):
            path = url.split("://", 1)[-1]
            path = "/" + path.split("/", 1)[-1] if "/" in path else path
            if not path.startswith("/"):
                path = "/v1/transcribe"
            with TestClient(app) as client:
                return client.post(path, json=json, headers=headers)

    engine = RemoteColabASREngine("http://colab", http_client=_Shim())
    utt = engine.feed(b"\x00" * 320)
    assert utt[0].text.startswith("Әни")
    assert utt[0].status == "final"
    assert utt[0].language == SpeechLanguage.TT
