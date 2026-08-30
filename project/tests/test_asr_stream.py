"""ASR WebSocket `/v1/stream` tests (step 2.1)."""

import base64
from pathlib import Path

from fastapi.testclient import TestClient
from ru_tat_call_shared.config import Settings
from ru_tat_call_shared.contracts.common import ErrorCode

from asr_server.app import create_app as create_asr_app
from signaling_server.app import create_app as create_signaling_app


def _settings(tmp_path: Path, name: str = "asr.db") -> Settings:
    """Shared sqlite + no HTTP fan-out (tests inject a publisher when needed)."""
    return Settings(
        _env_file=None,
        sqlite_path=tmp_path / name,
        signaling_internal_url="",
        asr_vad="off",
    )


def _login_token(tmp_path: Path) -> tuple[Settings, str]:
    """Create the shared SQLite DB via signaling login and return (settings, token)."""
    settings = _settings(tmp_path)
    with TestClient(create_signaling_app(settings)) as client:
        token = client.post(
            "/v1/auth/login", json={"identifier": "you", "password": "family"}
        ).json()["access_token"]
    return settings, token


def test_health(tmp_path: Path) -> None:
    settings = _settings(tmp_path, "empty.db")
    with TestClient(create_asr_app(settings)) as client:
        assert client.get("/health").json() == {"ok": True, "role": "asr", "engine": "mock"}


def test_invalid_token(tmp_path: Path) -> None:
    settings = _settings(tmp_path, "none.db")
    with TestClient(create_asr_app(settings)) as client:
        with client.websocket_connect("/v1/stream?token=not-a-session") as ws:
            err = ws.receive_json()
            assert err["type"] == "asr.error"
            assert err["payload"]["code"] == ErrorCode.INVALID_TOKEN.value


def test_start_audio_stop(tmp_path: Path) -> None:
    settings, token = _login_token(tmp_path)
    pcm = b"\x00\x00\x00\x00"
    with TestClient(create_asr_app(settings)) as client:
        with client.websocket_connect(f"/v1/stream?token={token}") as ws:
            ws.send_json(
                {
                    "type": "asr.start",
                    "session_id": "asr_100",
                    "payload": {"room_id": "room_555", "language_mode": "auto"},
                }
            )
            started = ws.receive_json()
            assert started["type"] == "asr.info"
            assert started["payload"]["message"] == "session_started"
            ws.send_json(
                {
                    "type": "asr.audio",
                    "session_id": "asr_100",
                    "payload": {
                        "chunk_id": "chunk_001",
                        "timestamp": 1,
                        "sample_rate": 16000,
                        "channels": 1,
                        "encoding": "pcm_s16le",
                        "audio_base64": base64.b64encode(pcm).decode("ascii"),
                    },
                }
            )
            buffered = ws.receive_json()
            assert buffered["payload"]["message"] == "chunk_buffered"
            assert buffered["payload"]["chunk_bytes"] == 4
            assert buffered["payload"]["buffered_bytes"] == 4
            ws.send_json(
                {
                    "type": "asr.stop",
                    "session_id": "asr_100",
                    "payload": {"room_id": "room_555"},
                }
            )
            stopped = ws.receive_json()
            assert stopped["payload"]["message"] == "session_stopped"
            assert stopped["payload"]["buffered_bytes"] == 4


def test_invalid_sample_rate(tmp_path: Path) -> None:
    settings, token = _login_token(tmp_path)
    with TestClient(create_asr_app(settings)) as client:
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
                        "sample_rate": 8000,
                        "channels": 1,
                        "encoding": "pcm_s16le",
                        "audio_base64": base64.b64encode(b"\x00\x00").decode("ascii"),
                    },
                }
            )
            err = ws.receive_json()
            assert err["type"] == "asr.error"
            assert err["payload"]["code"] == ErrorCode.INVALID_AUDIO_FORMAT.value


def test_audio_before_start(tmp_path: Path) -> None:
    settings, token = _login_token(tmp_path)
    with TestClient(create_asr_app(settings)) as client:
        with client.websocket_connect(f"/v1/stream?token={token}") as ws:
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
                        "audio_base64": base64.b64encode(b"\x00\x00").decode("ascii"),
                    },
                }
            )
            err = ws.receive_json()
            assert err["type"] == "asr.error"
            assert err["payload"]["code"] == ErrorCode.INTERNAL_ERROR.value
