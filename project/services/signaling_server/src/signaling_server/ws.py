"""WebSocket signaling endpoint: `/ws/signaling?token=ACCESS_TOKEN`."""

import time

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from ru_tat_call_shared.contracts.common import ErrorCode, ErrorPayload
from ru_tat_call_shared.contracts.signaling import SignalingErrorEvent

from signaling_server.rooms import dump_message

ws_router = APIRouter()


@ws_router.websocket("/ws/signaling")
async def signaling_socket(websocket: WebSocket, token: str = Query(...)) -> None:
    """Authenticate via query token, then run the room-event loop.

    Args:
        websocket: Client socket.
        token: Access token from POST /v1/auth/login.
    """
    await websocket.accept()
    db = websocket.app.state.db
    user_id = db.user_id_for_token(token)
    if user_id is None:
        err = SignalingErrorEvent(
            type="error",
            request_id="auth",
            timestamp=int(time.time()),
            payload=ErrorPayload(
                code=ErrorCode.INVALID_TOKEN,
                message="Access token is invalid or expired",
            ),
        )
        await websocket.send_json(dump_message(err))
        await websocket.close()
        return
    rooms = websocket.app.state.rooms
    await rooms.connect(user_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            if not isinstance(data, dict):
                continue
            await rooms.handle(user_id, data)
    except WebSocketDisconnect:
        await rooms.disconnect(user_id, websocket)
    except Exception:
        await rooms.disconnect(user_id, websocket)
        raise
