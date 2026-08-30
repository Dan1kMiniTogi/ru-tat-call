"""Live subtitle events delivered to the client UI."""

from typing import Literal, Optional

from ru_tat_call_shared.contracts.common import ApiModel, SpeechLanguage, SubtitleStatus


class SubtitleUpdatePayload(ApiModel):
    """Body of subtitle.update."""

    subtitle_id: str
    speaker_id: str
    speaker_name: str
    text: str
    status: SubtitleStatus
    language: SpeechLanguage
    confidence: Optional[float] = None
    start_time_ms: Optional[int] = None
    end_time_ms: Optional[int] = None


class SubtitleUpdateEvent(ApiModel):
    """Client-facing subtitle stream event (not REST).

    Args:
        type: Always `subtitle.update`.
        room_id: Call room.
        payload: Segment to render (partial in-place, final frozen).

    Example:
        SubtitleUpdateEvent.model_validate({
            "type": "subtitle.update",
            "room_id": "room_555",
            "payload": {
                "subtitle_id": "sub_101",
                "speaker_id": "u_123",
                "speaker_name": "Ты",
                "text": "Бүген соңрак кайтам.",
                "status": "final",
                "language": "mixed",
            },
        })
    """

    type: Literal["subtitle.update"] = "subtitle.update"
    room_id: str
    payload: SubtitleUpdatePayload
