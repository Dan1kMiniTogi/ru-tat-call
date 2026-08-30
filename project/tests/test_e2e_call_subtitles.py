"""Step 3.5: two signaling clients in a room see mock ASR subtitles via HTTP fan-out."""

from __future__ import annotations

import base64
from pathlib import Path

from fastapi.testclient import TestClient
from ru_tat_call_shared.config import Settings
from ru_tat_call_shared.contracts.subtitles import SubtitleUpdateEvent

from asr_server.app import create_app as create_asr_app
from asr_server.mock_engine import MOCK_PHRASES, TICK_BYTES
from signaling_server.app import create_app as create_signaling_app


class SignalingHttpFanout:
    """POST `/v1/internal/subtitles` on a live signaling TestClient.

    Same path as production `HttpSubtitlePublisher`, without opening a TCP port.

    Args:
        client: Signaling TestClient (WebSockets already connected).
        secret: `SECRET_KEY` / `X-Internal-Token`.

    Example:
        pub = SignalingHttpFanout(sig, "test-secret")
        create_asr_app(settings, publisher=pub)
    """

    def __init__(self, client: TestClient, secret: str) -> None:
        self._client = client
        self._secret = secret

    async def publish(self, event: SubtitleUpdateEvent) -> None:
        resp = self._client.post(
            "/v1/internal/subtitles",
            json=event.model_dump(mode="json"),
            headers={"X-Internal-Token": self._secret},
        )
        if resp.status_code != 200:
            raise AssertionError(f"fan-out HTTP {resp.status_code}: {resp.text}")

    async def aclose(self) -> None:
        return None


def _pcm_b64(n: int) -> str:
    return base64.b64encode(b"\x00" * n).decode("ascii")


def _login(client: TestClient, identifier: str) -> str:
    return client.post(
        "/v1/auth/login", json={"identifier": identifier, "password": "family"}
    ).json()["access_token"]


def _recv_type(ws, expected: str, limit: int = 16) -> dict:
    """Skip unrelated WS frames until `expected` type arrives.

    Args:
        ws: Starlette TestClient websocket.
        expected: `type` field to wait for.
        limit: Max frames to read.

    Returns:
        The matching JSON object.

    Example:
        ev = _recv_type(ws_mama, "subtitle.update")
    """
    for _ in range(limit):
        msg = ws.receive_json()
        if msg.get("type") == expected:
            return msg
    raise AssertionError(f"did not receive {expected}")


def test_two_clients_receive_mock_subtitles(tmp_path: Path) -> None:
    """you invites mama; mock PCM yields partial then final on both signaling sockets."""
    secret = "e2e-secret-key!!"
    settings = Settings(
        _env_file=None,
        sqlite_path=tmp_path / "e2e.db",
        secret_key=secret,
        signaling_internal_url="",
        asr_vad="off",
        asr_engine="mock",
    )
    with TestClient(create_signaling_app(settings)) as sig:
        token_you = _login(sig, "you")
        token_mama = _login(sig, "mama")
        publisher = SignalingHttpFanout(sig, secret)
        with TestClient(create_asr_app(settings, publisher=publisher)) as asr:
            with (
                sig.websocket_connect(f"/ws/signaling?token={token_you}") as ws_you,
                sig.websocket_connect(f"/ws/signaling?token={token_mama}") as ws_mama,
            ):
                ws_you.send_json(
                    {
                        "type": "room.create",
                        "request_id": "c1",
                        "timestamp": 1,
                        "payload": {"participant_ids": ["u_you", "u_mama"]},
                    }
                )
                room_id = ws_you.receive_json()["payload"]["room_id"]
                ws_you.send_json(
                    {
                        "type": "call.invite",
                        "request_id": "i1",
                        "timestamp": 2,
                        "payload": {"room_id": room_id, "target_user_id": "u_mama"},
                    }
                )
                assert ws_mama.receive_json()["type"] == "call.invite"
                ws_mama.send_json(
                    {
                        "type": "call.accept",
                        "request_id": "a1",
                        "timestamp": 3,
                        "payload": {"room_id": room_id},
                    }
                )
                assert {ws_you.receive_json()["type"] for _ in range(2)} == {
                    "call.accept",
                    "participant.joined",
                }

                with asr.websocket_connect(f"/v1/stream?token={token_you}") as ws_asr:
                    ws_asr.send_json(
                        {
                            "type": "asr.start",
                            "session_id": "asr_e2e",
                            "payload": {
                                "room_id": room_id,
                                "language_mode": "auto",
                                "return_partial": True,
                                "return_final": True,
                            },
                        }
                    )
                    started = ws_asr.receive_json()
                    assert started["payload"]["model_name"] == "mock"

                    asr_kinds: list[str] = []
                    for i in range(3):
                        ws_asr.send_json(
                            {
                                "type": "asr.audio",
                                "session_id": "asr_e2e",
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
                        buffered = ws_asr.receive_json()
                        assert buffered["payload"]["message"] == "chunk_buffered"
                        asr_kinds.append(ws_asr.receive_json()["type"])

                    assert asr_kinds[0] == "asr.partial"
                    assert asr_kinds[1] == "asr.partial"
                    assert asr_kinds[2] == "asr.final"

                    you_subs = [_recv_type(ws_you, "subtitle.update") for _ in range(3)]
                    mama_subs = [_recv_type(ws_mama, "subtitle.update") for _ in range(3)]
                    assert [e["payload"]["status"] for e in you_subs] == [
                        "partial",
                        "partial",
                        "final",
                    ]
                    assert [e["payload"]["text"] for e in you_subs] == [
                        e["payload"]["text"] for e in mama_subs
                    ]
                    assert you_subs[0]["payload"]["text"] == MOCK_PHRASES[0][0]
                    assert you_subs[-1]["payload"]["text"] == "".join(MOCK_PHRASES[0])
                    assert you_subs[-1]["payload"]["speaker_id"] == "u_you"
                    assert you_subs[-1]["payload"]["speaker_name"] == "Ты"
                    assert mama_subs[-1]["payload"]["status"] == "final"
                    assert mama_subs[-1]["room_id"] == room_id
