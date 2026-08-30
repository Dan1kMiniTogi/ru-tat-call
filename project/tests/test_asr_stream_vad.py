"""Energy VAD on the ASR WebSocket: silence does not advance mock (step 2.3)."""

import base64
import math
import struct
from pathlib import Path

from fastapi.testclient import TestClient
from ru_tat_call_shared.config import Settings

from asr_server.app import create_app as create_asr_app
from asr_server.mock_engine import TICK_BYTES
from asr_server.publish import RecordingSubtitlePublisher
from asr_server.vad import WINDOW_BYTES
from signaling_server.app import create_app as create_signaling_app


def _pcm_b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _sine(n_bytes: int) -> bytes:
    n = n_bytes // 2
    samples = [int(0.4 * 32767 * math.sin(2 * math.pi * 440 * i / 16000)) for i in range(n)]
    return struct.pack("<" + "h" * n, *samples)


def _login(tmp_path: Path) -> tuple[Settings, str]:
    settings = Settings(
        _env_file=None,
        sqlite_path=tmp_path / "vad.db",
        signaling_internal_url="",
        asr_vad="energy",
    )
    with TestClient(create_signaling_app(settings)) as client:
        token = client.post(
            "/v1/auth/login", json={"identifier": "you", "password": "family"}
        ).json()["access_token"]
    return settings, token


def test_silence_does_not_emit_partial(tmp_path: Path) -> None:
    settings, token = _login(tmp_path)
    rec = RecordingSubtitlePublisher()
    with TestClient(create_asr_app(settings, publisher=rec)) as client:
        with client.websocket_connect(f"/v1/stream?token={token}") as ws:
            ws.send_json(
                {
                    "type": "asr.start",
                    "session_id": "asr_100",
                    "payload": {"room_id": "room_1"},
                }
            )
            started = ws.receive_json()
            assert started["payload"]["version"] == "energy"
            ws.send_json(
                {
                    "type": "asr.audio",
                    "session_id": "asr_100",
                    "payload": {
                        "chunk_id": "c1",
                        "timestamp": 1,
                        "sample_rate": 16000,
                        "channels": 1,
                        "encoding": "pcm_s16le",
                        "audio_base64": _pcm_b64(b"\x00" * TICK_BYTES),
                    },
                }
            )
            info = ws.receive_json()
            assert info["payload"]["message"] == "chunk_buffered"
            assert info["payload"]["speech_bytes"] == 0
    assert rec.events == []


def test_sine_emits_partial(tmp_path: Path) -> None:
    settings, token = _login(tmp_path)
    rec = RecordingSubtitlePublisher()
    speech = _sine(WINDOW_BYTES * 16)
    with TestClient(create_asr_app(settings, publisher=rec)) as client:
        with client.websocket_connect(f"/v1/stream?token={token}") as ws:
            ws.send_json(
                {
                    "type": "asr.start",
                    "session_id": "asr_100",
                    "payload": {"room_id": "room_1"},
                }
            )
            ws.receive_json()
            ws.send_json(
                {
                    "type": "asr.audio",
                    "session_id": "asr_100",
                    "payload": {
                        "chunk_id": "c1",
                        "timestamp": 1,
                        "sample_rate": 16000,
                        "channels": 1,
                        "encoding": "pcm_s16le",
                        "audio_base64": _pcm_b64(speech),
                    },
                }
            )
            info = ws.receive_json()
            assert info["payload"]["speech_bytes"] == WINDOW_BYTES * 16
            partial = ws.receive_json()
            assert partial["type"] == "asr.partial"
    assert rec.events[0].payload.status.value == "partial"
