"""WebSocket signaling events (no media)."""

from typing import Annotated, Literal, Optional, Union

from pydantic import ConfigDict, Field, TypeAdapter

from ru_tat_call_shared.contracts.common import ApiModel, ErrorPayload


class IceCandidate(ApiModel):
    """RTCIceCandidateInit fields used in webrtc.ice."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    candidate: str
    sdp_mid: Optional[str] = Field(default=None, alias="sdpMid")
    sdp_m_line_index: Optional[int] = Field(default=None, alias="sdpMLineIndex")


class RoomCreatePayload(ApiModel):
    """room.create payload."""

    participant_ids: list[str]


class RoomCreatedPayload(ApiModel):
    """room.created payload."""

    room_id: str
    status: str


class CallInvitePayload(ApiModel):
    """call.invite payload."""

    room_id: str
    target_user_id: str


class CallAcceptPayload(ApiModel):
    """call.accept payload."""

    room_id: str


class CallRejectPayload(ApiModel):
    """call.reject payload."""

    room_id: str
    reason: str


class WebrtcOfferPayload(ApiModel):
    """webrtc.offer payload."""

    room_id: str
    from_user_id: str
    to_user_id: str
    sdp: str


class WebrtcAnswerPayload(ApiModel):
    """webrtc.answer payload."""

    room_id: str
    from_user_id: str
    to_user_id: str
    sdp: str


class WebrtcIcePayload(ApiModel):
    """webrtc.ice payload."""

    room_id: str
    from_user_id: str
    to_user_id: str
    candidate: IceCandidate


class ParticipantPayload(ApiModel):
    """participant.joined / participant.left payload."""

    room_id: str
    user_id: str


class _SignalingEnvelope(ApiModel):
    """Common signaling envelope fields."""

    request_id: str
    timestamp: int


class RoomCreateEvent(_SignalingEnvelope):
    type: Literal["room.create"]
    payload: RoomCreatePayload


class RoomCreatedEvent(_SignalingEnvelope):
    type: Literal["room.created"]
    payload: RoomCreatedPayload


class CallInviteEvent(_SignalingEnvelope):
    type: Literal["call.invite"]
    payload: CallInvitePayload


class CallAcceptEvent(_SignalingEnvelope):
    type: Literal["call.accept"]
    payload: CallAcceptPayload


class CallRejectEvent(_SignalingEnvelope):
    type: Literal["call.reject"]
    payload: CallRejectPayload


class WebrtcOfferEvent(_SignalingEnvelope):
    type: Literal["webrtc.offer"]
    payload: WebrtcOfferPayload


class WebrtcAnswerEvent(_SignalingEnvelope):
    type: Literal["webrtc.answer"]
    payload: WebrtcAnswerPayload


class WebrtcIceEvent(_SignalingEnvelope):
    type: Literal["webrtc.ice"]
    payload: WebrtcIcePayload


class ParticipantJoinedEvent(_SignalingEnvelope):
    type: Literal["participant.joined"]
    payload: ParticipantPayload


class ParticipantLeftEvent(_SignalingEnvelope):
    type: Literal["participant.left"]
    payload: ParticipantPayload


class SignalingErrorEvent(_SignalingEnvelope):
    type: Literal["error"]
    payload: ErrorPayload


SignalingMessage = Annotated[
    Union[
        RoomCreateEvent,
        RoomCreatedEvent,
        CallInviteEvent,
        CallAcceptEvent,
        CallRejectEvent,
        WebrtcOfferEvent,
        WebrtcAnswerEvent,
        WebrtcIceEvent,
        ParticipantJoinedEvent,
        ParticipantLeftEvent,
        SignalingErrorEvent,
    ],
    Field(discriminator="type"),
]

_signaling_adapter: TypeAdapter[SignalingMessage] = TypeAdapter(SignalingMessage)


def parse_signaling_message(data: dict) -> SignalingMessage:
    """Parse a signaling WebSocket JSON object.

    Args:
        data: Dict with type, request_id, timestamp, payload.

    Returns:
        Discriminated signaling event.

    Example:
        parse_signaling_message({
            "type": "room.create",
            "request_id": "req_001",
            "timestamp": 1710000000,
            "payload": {"participant_ids": ["u_123"]},
        })
    """
    return _signaling_adapter.validate_python(data)
