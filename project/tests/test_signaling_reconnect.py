"""Signaling reconnect: grace period keeps room membership (step 5.1)."""

from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient
from ru_tat_call_shared.config import Settings

from signaling_server.app import create_app


def _client(tmp_path: Path, grace_s: float) -> TestClient:
    settings = Settings(
        _env_file=None,
        sqlite_path=tmp_path / "re.db",
        signaling_disconnect_grace_s=grace_s,
    )
    return TestClient(create_app(settings))


def _login(client: TestClient, identifier: str) -> str:
    return client.post(
        "/v1/auth/login", json={"identifier": identifier, "password": "family"}
    ).json()["access_token"]


def _join_you_mama(ws_you, ws_mama) -> str:
    """Create a room, invite mama, accept.

    Args:
        ws_you: Signaling WS for `u_you`.
        ws_mama: Signaling WS for `u_mama`.

    Returns:
        `room_id` from `room.created`.

    Example:
        room_id = _join_you_mama(ws_you, ws_mama)
    """
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
            "type": "call.accept",
            "request_id": "c",
            "timestamp": 3,
            "payload": {"room_id": room_id},
        }
    )
    {ws_you.receive_json()["type"], ws_you.receive_json()["type"]}
    return room_id


def _offer(ws, request_id: str, room_id: str) -> None:
    """Send a webrtc.offer from you to mama.

    Args:
        ws: Sender signaling socket (`u_you`).
        request_id: Correlation id.
        room_id: Live room.

    Example:
        _offer(ws_you, "d", room_id)
    """
    ws.send_json(
        {
            "type": "webrtc.offer",
            "request_id": request_id,
            "timestamp": 4,
            "payload": {
                "room_id": room_id,
                "from_user_id": "u_you",
                "to_user_id": "u_mama",
                "sdp": "v=0-reconnect",
            },
        }
    )


def test_fast_reconnect_stays_in_room(tmp_path: Path) -> None:
    """Drop and reopen you WS before grace: membership and SDP routing remain."""
    with _client(tmp_path, grace_s=0.5) as client:
        you = _login(client, "you")
        mama = _login(client, "mama")
        with client.websocket_connect(f"/ws/signaling?token={mama}") as ws_mama:
            room_id = ""
            with client.websocket_connect(f"/ws/signaling?token={you}") as ws_you:
                room_id = _join_you_mama(ws_you, ws_mama)
            with client.websocket_connect(f"/ws/signaling?token={you}") as ws_you2:
                _offer(ws_you2, "d", room_id)
                offer = ws_mama.receive_json()
                assert offer["type"] == "webrtc.offer"
                assert offer["payload"]["sdp"] == "v=0-reconnect"


def test_leave_after_grace(tmp_path: Path) -> None:
    """After grace without reconnect, mama sees participant.left; you cannot offer."""
    with _client(tmp_path, grace_s=0.12) as client:
        you = _login(client, "you")
        mama = _login(client, "mama")
        with client.websocket_connect(f"/ws/signaling?token={mama}") as ws_mama:
            room_id = ""
            with client.websocket_connect(f"/ws/signaling?token={you}") as ws_you:
                room_id = _join_you_mama(ws_you, ws_mama)
            time.sleep(0.35)
            left = ws_mama.receive_json()
            assert left["type"] == "participant.left"
            assert left["payload"]["user_id"] == "u_you"
            with client.websocket_connect(f"/ws/signaling?token={you}") as ws_you2:
                _offer(ws_you2, "d", room_id)
                err = ws_you2.receive_json()
                assert err["type"] == "error"
                assert err["payload"]["code"] == "UNAUTHORIZED"
