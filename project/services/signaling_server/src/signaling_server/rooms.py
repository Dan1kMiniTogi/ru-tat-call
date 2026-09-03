"""In-memory call rooms and WebSocket fan-out (no media)."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

from fastapi import WebSocket
from pydantic import ValidationError
from ru_tat_call_shared.contracts.common import ErrorCode, ErrorPayload
from ru_tat_call_shared.contracts.signaling import (
    CallAcceptEvent,
    CallInviteEvent,
    CallRejectEvent,
    ParticipantJoinedEvent,
    ParticipantLeftEvent,
    ParticipantPayload,
    RoomCreateEvent,
    RoomCreatedEvent,
    RoomCreatedPayload,
    SignalingErrorEvent,
    WebrtcAnswerEvent,
    WebrtcIceEvent,
    WebrtcOfferEvent,
    parse_signaling_message,
)
from ru_tat_call_shared.contracts.subtitles import SubtitleUpdateEvent

from signaling_server.security import new_token


def _now() -> int:
    return int(time.time())


def dump_message(model) -> dict:
    """Serialize a signaling event to a JSON-ready dict (ICE uses sdpMid aliases)."""
    return model.model_dump(mode="json", by_alias=True)


@dataclass
class Room:
    """One call room.

    Attributes:
        room_id: Public id.
        owner_id: Who created the room.
        allowed: Users who may join (owner + invited).
        members: Users who accepted / are in the call.
    """

    room_id: str
    owner_id: str
    allowed: set[str] = field(default_factory=set)
    members: set[str] = field(default_factory=set)


class RoomManager:
    """Track sockets and rooms. One WebSocket per user for MVP.

    Args:
        max_participants: Product cap (default 4).
        disconnect_grace_s: Wait before `participant.left` so a WS reconnect
            can keep the same room membership (step 5.1).

    Example:
        manager = RoomManager(max_participants=4, disconnect_grace_s=3.0)
        await manager.connect("u_you", websocket)
    """

    def __init__(self, max_participants: int = 4, disconnect_grace_s: float = 3.0) -> None:
        self.max_participants = max_participants
        self.disconnect_grace_s = max(0.0, float(disconnect_grace_s))
        self._sockets: dict[str, WebSocket] = {}
        self._rooms: dict[str, Room] = {}
        self._user_room: dict[str, str] = {}
        self._leave_after: dict[str, asyncio.Task] = {}

    def _cancel_leave(self, user_id: str) -> None:
        task = self._leave_after.pop(user_id, None)
        if task is not None:
            task.cancel()

    def cancel_pending_leaves(self) -> None:
        """Cancel delayed leave tasks (app shutdown / tests)."""
        for user_id in list(self._leave_after):
            self._cancel_leave(user_id)

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        """Register a live signaling socket. Cancels a pending leave (reconnect)."""
        self._cancel_leave(user_id)
        previous = self._sockets.get(user_id)
        self._sockets[user_id] = websocket
        if previous is not None and previous is not websocket:
            try:
                await previous.close()
            except Exception:
                pass

    async def disconnect(self, user_id: str, websocket: Optional[WebSocket] = None) -> None:
        """Drop this socket. Leave the room only after `disconnect_grace_s`.

        A newer socket for the same user is ignored (stale close after reconnect).
        """
        current = self._sockets.get(user_id)
        if websocket is not None and current is not websocket:
            return
        self._sockets.pop(user_id, None)
        if user_id not in self._user_room:
            return
        if self.disconnect_grace_s <= 0:
            await self._leave_room(user_id, self._user_room[user_id])
            return
        self._cancel_leave(user_id)
        self._leave_after[user_id] = asyncio.create_task(self._grace_leave(user_id))

    async def _grace_leave(self, user_id: str) -> None:
        """Leave the room if the user did not reconnect in time."""
        try:
            await asyncio.sleep(self.disconnect_grace_s)
        except asyncio.CancelledError:
            return
        self._leave_after.pop(user_id, None)
        if user_id in self._sockets:
            return
        room_id = self._user_room.get(user_id)
        if room_id:
            await self._leave_room(user_id, room_id)

    def is_online(self, user_id: str) -> bool:
        """Whether the user has an open signaling socket."""
        return user_id in self._sockets

    async def send(self, user_id: str, payload: dict) -> bool:
        """Send JSON to one user. Returns False if offline."""
        socket = self._sockets.get(user_id)
        if socket is None:
            return False
        try:
            await socket.send_json(payload)
            return True
        except Exception:
            return False

    async def send_error(
        self,
        user_id: str,
        request_id: str,
        code: ErrorCode,
        message: str,
    ) -> None:
        """Send a signaling `error` event."""
        event = SignalingErrorEvent(
            type="error",
            request_id=request_id or "unknown",
            timestamp=_now(),
            payload=ErrorPayload(code=code, message=message),
        )
        await self.send(user_id, dump_message(event))

    async def handle(self, user_id: str, raw: dict) -> None:
        """Dispatch a client signaling message.

        Args:
            user_id: Authenticated sender.
            raw: JSON object from the socket.
        """
        request_id = str(raw.get("request_id") or "unknown")
        try:
            msg = parse_signaling_message(raw)
        except ValidationError:
            await self.send_error(
                user_id, request_id, ErrorCode.INTERNAL_ERROR, "Invalid signaling message"
            )
            return
        if isinstance(msg, RoomCreateEvent):
            await self._on_room_create(user_id, msg)
        elif isinstance(msg, CallInviteEvent):
            await self._on_invite(user_id, msg)
        elif isinstance(msg, CallAcceptEvent):
            await self._on_accept(user_id, msg)
        elif isinstance(msg, CallRejectEvent):
            await self._on_reject(user_id, msg)
        elif isinstance(msg, (WebrtcOfferEvent, WebrtcAnswerEvent, WebrtcIceEvent)):
            await self._on_webrtc(user_id, msg)
        else:
            await self.send_error(
                user_id,
                msg.request_id,
                ErrorCode.INTERNAL_ERROR,
                "Unsupported signaling event",
            )

    async def _on_room_create(self, user_id: str, msg: RoomCreateEvent) -> None:
        ids = set(msg.payload.participant_ids) | {user_id}
        if len(ids) > self.max_participants:
            await self.send_error(
                user_id, msg.request_id, ErrorCode.ROOM_FULL, "Room supports at most 4 participants"
            )
            return
        room_id = f"room_{new_token()[:16]}"
        room = Room(room_id=room_id, owner_id=user_id, allowed=ids, members={user_id})
        self._rooms[room_id] = room
        self._user_room[user_id] = room_id
        created = RoomCreatedEvent(
            type="room.created",
            request_id=msg.request_id,
            timestamp=_now(),
            payload=RoomCreatedPayload(room_id=room_id, status="created"),
        )
        await self.send(user_id, dump_message(created))

    async def _on_invite(self, user_id: str, msg: CallInviteEvent) -> None:
        room = self._rooms.get(msg.payload.room_id)
        if room is None:
            await self.send_error(
                user_id, msg.request_id, ErrorCode.ROOM_NOT_FOUND, "Room not found"
            )
            return
        if user_id not in room.members:
            await self.send_error(
                user_id, msg.request_id, ErrorCode.UNAUTHORIZED, "Not in this room"
            )
            return
        target = msg.payload.target_user_id
        if target not in room.allowed:
            if len(room.allowed) >= self.max_participants:
                await self.send_error(
                    user_id, msg.request_id, ErrorCode.ROOM_FULL, "Room is full"
                )
                return
            room.allowed.add(target)
        if not self.is_online(target):
            await self.send_error(
                user_id, msg.request_id, ErrorCode.USER_OFFLINE, "Callee is offline"
            )
            return
        invite = CallInviteEvent(
            type="call.invite",
            request_id=msg.request_id,
            timestamp=_now(),
            payload=msg.payload,
        )
        await self.send(target, dump_message(invite))

    async def _on_accept(self, user_id: str, msg: CallAcceptEvent) -> None:
        room = self._rooms.get(msg.payload.room_id)
        if room is None:
            await self.send_error(
                user_id, msg.request_id, ErrorCode.ROOM_NOT_FOUND, "Room not found"
            )
            return
        if user_id not in room.allowed:
            await self.send_error(
                user_id, msg.request_id, ErrorCode.UNAUTHORIZED, "Not invited to this room"
            )
            return
        if len(room.members) >= self.max_participants and user_id not in room.members:
            await self.send_error(
                user_id, msg.request_id, ErrorCode.ROOM_FULL, "Room is full"
            )
            return
        already = user_id in room.members
        room.members.add(user_id)
        self._user_room[user_id] = room.room_id
        if already:
            return
        joined = ParticipantJoinedEvent(
            type="participant.joined",
            request_id=msg.request_id,
            timestamp=_now(),
            payload=ParticipantPayload(room_id=room.room_id, user_id=user_id),
        )
        accept = CallAcceptEvent(
            type="call.accept",
            request_id=msg.request_id,
            timestamp=_now(),
            payload=msg.payload,
        )
        blob_joined = dump_message(joined)
        blob_accept = dump_message(accept)
        for member in room.members:
            if member == user_id:
                continue
            await self.send(member, blob_accept)
            await self.send(member, blob_joined)

    async def _on_reject(self, user_id: str, msg: CallRejectEvent) -> None:
        room = self._rooms.get(msg.payload.room_id)
        if room is None:
            await self.send_error(
                user_id, msg.request_id, ErrorCode.ROOM_NOT_FOUND, "Room not found"
            )
            return
        room.allowed.discard(user_id)
        reject = CallRejectEvent(
            type="call.reject",
            request_id=msg.request_id,
            timestamp=_now(),
            payload=msg.payload,
        )
        blob = dump_message(reject)
        for member in set(room.members) | {room.owner_id}:
            if member != user_id:
                await self.send(member, blob)

    async def _on_webrtc(
        self,
        user_id: str,
        msg: WebrtcOfferEvent | WebrtcAnswerEvent | WebrtcIceEvent,
    ) -> None:
        """Forward SDP/ICE to the peer if both are members of the room."""
        room = self._rooms.get(msg.payload.room_id)
        if room is None:
            await self.send_error(
                user_id, msg.request_id, ErrorCode.ROOM_NOT_FOUND, "Room not found"
            )
            return
        if user_id not in room.members:
            await self.send_error(
                user_id, msg.request_id, ErrorCode.UNAUTHORIZED, "Not in this room"
            )
            return
        if msg.payload.from_user_id != user_id:
            await self.send_error(
                user_id, msg.request_id, ErrorCode.UNAUTHORIZED, "from_user_id must match sender"
            )
            return
        target = msg.payload.to_user_id
        if target not in room.members:
            await self.send_error(
                user_id, msg.request_id, ErrorCode.UNAUTHORIZED, "Peer is not in this room"
            )
            return
        if not self.is_online(target):
            return
        await self.send(target, dump_message(msg))

    async def broadcast_subtitle(self, event: SubtitleUpdateEvent) -> int:
        """Send `subtitle.update` to every member of the room.

        Args:
            event: Validated subtitle event (room_id + payload).

        Returns:
            Number of sockets the JSON was written to. 0 if the room is unknown
            or empty (ASR must still keep streaming).

        Example:
            n = await manager.broadcast_subtitle(event)
        """
        room = self._rooms.get(event.room_id)
        if room is None:
            return 0
        blob = event.model_dump(mode="json")
        delivered = 0
        for member in list(room.members):
            if await self.send(member, blob):
                delivered += 1
        return delivered

    async def _leave_room(self, user_id: str, room_id: str) -> None:
        if user_id in self._sockets:
            return
        room = self._rooms.get(room_id)
        self._user_room.pop(user_id, None)
        if room is None:
            return
        room.members.discard(user_id)
        left = ParticipantLeftEvent(
            type="participant.left",
            request_id="sys",
            timestamp=_now(),
            payload=ParticipantPayload(room_id=room_id, user_id=user_id),
        )
        blob = dump_message(left)
        for member in list(room.members):
            await self.send(member, blob)
        if not room.members:
            self._rooms.pop(room_id, None)
