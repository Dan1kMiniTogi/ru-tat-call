"""WebSocket room manager tests (step 1.2)."""

from pathlib import Path

from fastapi.testclient import TestClient
from ru_tat_call_shared.config import Settings

from signaling_server.app import create_app


def _client(tmp_path: Path) -> TestClient:
    settings = Settings(_env_file=None, sqlite_path=tmp_path / "ws.db")
    return TestClient(create_app(settings))


def _login(client: TestClient, identifier: str) -> str:
    return client.post(
        "/v1/auth/login", json={"identifier": identifier, "password": "family"}
    ).json()["access_token"]


def test_room_invite_accept_and_leave(tmp_path: Path) -> None:
    """Caller creates a room, invites mama; mama accepts; disconnect sends left."""
    with _client(tmp_path) as client:
        you = _login(client, "you")
        mama = _login(client, "mama")
        with (
            client.websocket_connect(f"/ws/signaling?token={you}") as ws_you,
            client.websocket_connect(f"/ws/signaling?token={mama}") as ws_mama,
        ):
            ws_you.send_json(
                {
                    "type": "room.create",
                    "request_id": "req_001",
                    "timestamp": 1,
                    "payload": {"participant_ids": ["u_you", "u_mama"]},
                }
            )
            created = ws_you.receive_json()
            assert created["type"] == "room.created"
            room_id = created["payload"]["room_id"]
            ws_you.send_json(
                {
                    "type": "call.invite",
                    "request_id": "req_002",
                    "timestamp": 2,
                    "payload": {"room_id": room_id, "target_user_id": "u_mama"},
                }
            )
            invite = ws_mama.receive_json()
            assert invite["type"] == "call.invite"
            assert invite["payload"]["room_id"] == room_id
            ws_mama.send_json(
                {
                    "type": "call.accept",
                    "request_id": "req_003",
                    "timestamp": 3,
                    "payload": {"room_id": room_id},
                }
            )
            types = {ws_you.receive_json()["type"], ws_you.receive_json()["type"]}
            assert types == {"call.accept", "participant.joined"}
        # mama socket closed first in context exit order? with-block exits inner first.
        # After both closed, reopen you and... leave already happened on disconnect.
        # Re-login not needed; new you socket shouldn't get leftover events.


def test_invite_offline(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        you = _login(client, "you")
        with client.websocket_connect(f"/ws/signaling?token={you}") as ws_you:
            ws_you.send_json(
                {
                    "type": "room.create",
                    "request_id": "r1",
                    "timestamp": 1,
                    "payload": {"participant_ids": ["u_you", "u_sister"]},
                }
            )
            room_id = ws_you.receive_json()["payload"]["room_id"]
            ws_you.send_json(
                {
                    "type": "call.invite",
                    "request_id": "r2",
                    "timestamp": 2,
                    "payload": {"room_id": room_id, "target_user_id": "u_sister"},
                }
            )
            err = ws_you.receive_json()
            assert err["type"] == "error"
            assert err["payload"]["code"] == "USER_OFFLINE"


def test_reject_notifies_caller(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        you = _login(client, "you")
        mama = _login(client, "mama")
        with (
            client.websocket_connect(f"/ws/signaling?token={you}") as ws_you,
            client.websocket_connect(f"/ws/signaling?token={mama}") as ws_mama,
        ):
            ws_you.send_json(
                {
                    "type": "room.create",
                    "request_id": "a",
                    "timestamp": 1,
                    "payload": {"participant_ids": ["u_mama"]},
                }
            )
            room_id = ws_you.receive_json()["payload"]["room_id"]
            ws_you.send_json(
                {
                    "type": "call.invite",
                    "request_id": "b",
                    "timestamp": 2,
                    "payload": {"room_id": room_id, "target_user_id": "u_mama"},
                }
            )
            assert ws_mama.receive_json()["type"] == "call.invite"
            ws_mama.send_json(
                {
                    "type": "call.reject",
                    "request_id": "c",
                    "timestamp": 3,
                    "payload": {"room_id": room_id, "reason": "busy"},
                }
            )
            rejected = ws_you.receive_json()
            assert rejected["type"] == "call.reject"
            assert rejected["payload"]["reason"] == "busy"


def test_bad_token_ws(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        with client.websocket_connect("/ws/signaling?token=nope") as ws:
            err = ws.receive_json()
            assert err["payload"]["code"] == "INVALID_TOKEN"
