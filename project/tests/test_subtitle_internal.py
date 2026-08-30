"""Internal subtitle fan-out into a live signaling room (step 2.2)."""

from pathlib import Path

from fastapi.testclient import TestClient
from ru_tat_call_shared.config import Settings

from signaling_server.app import create_app


def _client(tmp_path: Path) -> TestClient:
    settings = Settings(_env_file=None, sqlite_path=tmp_path / "sub.db", secret_key="test-secret-key!!")
    return TestClient(create_app(settings))


def test_internal_subtitle_reaches_room_member(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        you = client.post(
            "/v1/auth/login", json={"identifier": "you", "password": "family"}
        ).json()["access_token"]
        with client.websocket_connect(f"/ws/signaling?token={you}") as ws:
            ws.send_json(
                {
                    "type": "room.create",
                    "request_id": "r1",
                    "timestamp": 1,
                    "payload": {"participant_ids": ["u_you"]},
                }
            )
            room_id = ws.receive_json()["payload"]["room_id"]
            body = {
                "type": "subtitle.update",
                "room_id": room_id,
                "payload": {
                    "subtitle_id": "sub_101",
                    "speaker_id": "u_you",
                    "speaker_name": "Ты",
                    "text": "Әни, сегодня я дома.",
                    "status": "final",
                    "language": "mixed",
                },
            }
            resp = client.post(
                "/v1/internal/subtitles",
                json=body,
                headers={"X-Internal-Token": "test-secret-key!!"},
            )
            assert resp.status_code == 200
            assert resp.json() == {"ok": True, "delivered": 1}
            event = ws.receive_json()
            assert event["type"] == "subtitle.update"
            assert event["payload"]["text"] == "Әни, сегодня я дома."
            assert event["payload"]["status"] == "final"


def test_internal_subtitle_rejects_bad_token(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        resp = client.post(
            "/v1/internal/subtitles",
            json={
                "type": "subtitle.update",
                "room_id": "room_missing",
                "payload": {
                    "subtitle_id": "sub_1",
                    "speaker_id": "u_you",
                    "speaker_name": "Ты",
                    "text": "x",
                    "status": "partial",
                    "language": "mixed",
                },
            },
            headers={"X-Internal-Token": "wrong"},
        )
        assert resp.status_code == 401


def test_internal_subtitle_unknown_room(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        resp = client.post(
            "/v1/internal/subtitles",
            json={
                "type": "subtitle.update",
                "room_id": "room_missing",
                "payload": {
                    "subtitle_id": "sub_1",
                    "speaker_id": "u_you",
                    "speaker_name": "Ты",
                    "text": "x",
                    "status": "partial",
                    "language": "mixed",
                },
            },
            headers={"X-Internal-Token": "test-secret-key!!"},
        )
        assert resp.status_code == 200
        assert resp.json()["delivered"] == 0
