"""Mock transcripts on `/v1/stream` and captured subtitle.update (step 2.2)."""

import base64
from pathlib import Path

from fastapi.testclient import TestClient
from ru_tat_call_shared.config import Settings

from asr_server.app import create_app as create_asr_app
from asr_server.mock_engine import MOCK_PHRASES, TICK_BYTES
from asr_server.publish import RecordingSubtitlePublisher
from signaling_server.app import create_app as create_signaling_app


def _pcm_b64(n: int) -> str:
    return base64.b64encode(b"\x00" * n).decode("ascii")


def _login(tmp_path: Path) -> tuple[Settings, str]:
    settings = Settings(
        _env_file=None,
        sqlite_path=tmp_path / "mock.db",
        signaling_internal_url="",
    )
    with TestClient(create_signaling_app(settings)) as client:
        token = client.post(
            "/v1/auth/login", json={"identifier": "you", "password": "family"}
        ).json()["access_token"]
    return settings, token


def test_mock_partial_and_publisher(tmp_path: Path) -> None:
    settings, token = _login(tmp_path)
    rec = RecordingSubtitlePublisher()
    with TestClient(create_asr_app(settings, publisher=rec)) as client:
        with client.websocket_connect(f"/v1/stream?token={token}") as ws:
            ws.send_json(
                {
                    "type": "asr.start",
                    "session_id": "asr_100",
                    "payload": {"room_id": "room_555", "language_mode": "auto"},
                }
            )
            assert ws.receive_json()["payload"]["model_name"] == "mock"
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
                        "audio_base64": _pcm_b64(TICK_BYTES),
                    },
                }
            )
            buffered = ws.receive_json()
            assert buffered["payload"]["message"] == "chunk_buffered"
            partial = ws.receive_json()
            assert partial["type"] == "asr.partial"
            assert partial["payload"]["text"] == MOCK_PHRASES[0][0]
            assert partial["payload"]["speaker_id"] == "u_you"
            assert partial["payload"]["speaker_name"] == "Ты"
            assert partial["payload"]["language"] == "mixed"
    assert len(rec.events) == 1
    assert rec.events[0].type == "subtitle.update"
    assert rec.events[0].room_id == "room_555"
    assert rec.events[0].payload.status.value == "partial"
    assert rec.events[0].payload.text == MOCK_PHRASES[0][0]


def test_mock_final_after_full_phrase(tmp_path: Path) -> None:
    settings, token = _login(tmp_path)
    rec = RecordingSubtitlePublisher()
    with TestClient(create_asr_app(settings, publisher=rec)) as client:
        with client.websocket_connect(f"/v1/stream?token={token}") as ws:
            ws.send_json(
                {
                    "type": "asr.start",
                    "session_id": "asr_100",
                    "payload": {"room_id": "room_555"},
                }
            )
            ws.receive_json()
            for i in range(3):
                ws.send_json(
                    {
                        "type": "asr.audio",
                        "session_id": "asr_100",
                        "payload": {
                            "chunk_id": f"c{i}",
                            "timestamp": i,
                            "sample_rate": 16000,
                            "channels": 1,
                            "encoding": "pcm_s16le",
                            "audio_base64": _pcm_b64(TICK_BYTES),
                        },
                    }
                )
                ws.receive_json()
                kind = ws.receive_json()["type"]
                if i < 2:
                    assert kind == "asr.partial"
                else:
                    assert kind == "asr.final"
    assert rec.events[-1].payload.status.value == "final"
    assert rec.events[-1].payload.text == "".join(MOCK_PHRASES[0])
