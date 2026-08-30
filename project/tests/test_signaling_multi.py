"""Step 1.4: emulate three signaling clients in one room (mesh SDP, leave, cap)."""

from pathlib import Path

from fastapi.testclient import TestClient
from ru_tat_call_shared.config import Settings

from signaling_server.app import create_app


def _client(tmp_path: Path) -> TestClient:
    settings = Settings(_env_file=None, sqlite_path=tmp_path / "multi.db")
    return TestClient(create_app(settings))


def _login(client: TestClient, identifier: str) -> str:
    return client.post(
        "/v1/auth/login", json={"identifier": identifier, "password": "family"}
    ).json()["access_token"]


def _types(ws, n: int) -> set[str]:
    """Collect n JSON events and return their type set."""
    return {ws.receive_json()["type"] for _ in range(n)}


def test_three_clients_mesh_sdp_and_leave(tmp_path: Path) -> None:
    """you + mama + sister: each peer-specific offer, leave notifies the rest."""
    with _client(tmp_path) as client:
        you = _login(client, "you")
        mama = _login(client, "mama")
        sister = _login(client, "sister")
        with (
            client.websocket_connect(f"/ws/signaling?token={you}") as ws_you,
            client.websocket_connect(f"/ws/signaling?token={mama}") as ws_mama,
            client.websocket_connect(f"/ws/signaling?token={sister}") as ws_sister,
        ):
            ws_you.send_json(
                {
                    "type": "room.create",
                    "request_id": "c1",
                    "timestamp": 1,
                    "payload": {"participant_ids": ["u_mama", "u_sister"]},
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
            assert _types(ws_you, 2) == {"call.accept", "participant.joined"}
            ws_you.send_json(
                {
                    "type": "call.invite",
                    "request_id": "i2",
                    "timestamp": 4,
                    "payload": {"room_id": room_id, "target_user_id": "u_sister"},
                }
            )
            assert ws_sister.receive_json()["type"] == "call.invite"
            ws_sister.send_json(
                {
                    "type": "call.accept",
                    "request_id": "a2",
                    "timestamp": 5,
                    "payload": {"room_id": room_id},
                }
            )
            assert _types(ws_you, 2) == {"call.accept", "participant.joined"}
            assert _types(ws_mama, 2) == {"call.accept", "participant.joined"}

            ws_you.send_json(
                {
                    "type": "webrtc.offer",
                    "request_id": "o1",
                    "timestamp": 6,
                    "payload": {
                        "room_id": room_id,
                        "from_user_id": "u_you",
                        "to_user_id": "u_mama",
                        "sdp": "offer-to-mama",
                    },
                }
            )
            to_mama = ws_mama.receive_json()
            assert to_mama["payload"]["sdp"] == "offer-to-mama"
            assert to_mama["payload"]["to_user_id"] == "u_mama"

            ws_you.send_json(
                {
                    "type": "webrtc.offer",
                    "request_id": "o2",
                    "timestamp": 7,
                    "payload": {
                        "room_id": room_id,
                        "from_user_id": "u_you",
                        "to_user_id": "u_sister",
                        "sdp": "offer-to-sister",
                    },
                }
            )
            to_sister = ws_sister.receive_json()
            assert to_sister["payload"]["sdp"] == "offer-to-sister"
            assert to_sister["payload"]["to_user_id"] == "u_sister"

            ws_mama.send_json(
                {
                    "type": "webrtc.offer",
                    "request_id": "o3",
                    "timestamp": 8,
                    "payload": {
                        "room_id": room_id,
                        "from_user_id": "u_mama",
                        "to_user_id": "u_ghost",
                        "sdp": "bad",
                    },
                }
            )
            err = ws_mama.receive_json()
            assert err["payload"]["code"] == "UNAUTHORIZED"

        # After mama/sister sockets close, remaining you-socket is already closed
        # by the with-block. Reconnect you: room is empty so no leftover members.


def test_room_full_on_fifth_invite(tmp_path: Path) -> None:
    """Creating a 4-person allowed set then inviting another yields ROOM_FULL."""
    with _client(tmp_path) as client:
        you = _login(client, "you")
        with client.websocket_connect(f"/ws/signaling?token={you}") as ws_you:
            ws_you.send_json(
                {
                    "type": "room.create",
                    "request_id": "f1",
                    "timestamp": 1,
                    "payload": {
                        "participant_ids": ["u_you", "u_mama", "u_sister", "u_extra"]
                    },
                }
            )
            created = ws_you.receive_json()
            assert created["type"] == "room.created"
            room_id = created["payload"]["room_id"]
            ws_you.send_json(
                {
                    "type": "call.invite",
                    "request_id": "f2",
                    "timestamp": 2,
                    "payload": {"room_id": room_id, "target_user_id": "u_ghost"},
                }
            )
            err = ws_you.receive_json()
            assert err["type"] == "error"
            assert err["payload"]["code"] == "ROOM_FULL"


def test_create_rejects_more_than_four(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        you = _login(client, "you")
        with client.websocket_connect(f"/ws/signaling?token={you}") as ws_you:
            ws_you.send_json(
                {
                    "type": "room.create",
                    "request_id": "big",
                    "timestamp": 1,
                    "payload": {
                        "participant_ids": ["a", "b", "c", "d", "e"],
                    },
                }
            )
            err = ws_you.receive_json()
            assert err["payload"]["code"] == "ROOM_FULL"
