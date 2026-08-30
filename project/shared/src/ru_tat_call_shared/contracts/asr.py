"""Streaming ASR WebSocket messages (PCM chunks in, transcript events out)."""

from typing import Annotated, Literal, Optional, Union

from pydantic import Field, TypeAdapter

from ru_tat_call_shared.contracts.common import (
    ApiModel,
    ErrorCode,
    LanguageMode,
    SpeechLanguage,
)


class AsrStartPayload(ApiModel):
    """asr.start payload."""

    room_id: str
    language_mode: LanguageMode = LanguageMode.AUTO
    return_partial: bool = True
    return_final: bool = True
    speaker_labels: bool = True


class AsrAudioPayload(ApiModel):
    """asr.audio payload: mono 16 kHz PCM s16le as base64 for MVP."""

    chunk_id: str
    timestamp: int
    sample_rate: int = 16000
    channels: int = 1
    encoding: Literal["pcm_s16le"] = "pcm_s16le"
    audio_base64: str


class AsrTranscriptPayload(ApiModel):
    """Shared body for asr.partial and asr.final."""

    subtitle_id: str
    speaker_id: str
    speaker_name: str
    text: str
    language: SpeechLanguage
    confidence: Optional[float] = None
    start_time_ms: Optional[int] = None
    end_time_ms: Optional[int] = None
    segment_id: Optional[str] = None


class AsrInfoPayload(ApiModel):
    """asr.info payload (model_loaded, session_started, chunk_buffered, …)."""

    message: str
    model_name: Optional[str] = None
    version: Optional[str] = None
    chunk_bytes: Optional[int] = None
    buffered_bytes: Optional[int] = None


class AsrErrorPayload(ApiModel):
    """asr.error payload."""

    code: ErrorCode
    message: str


class AsrStopPayload(ApiModel):
    """asr.stop payload."""

    room_id: str


class _AsrEnvelope(ApiModel):
    session_id: str


class AsrStartEvent(_AsrEnvelope):
    type: Literal["asr.start"]
    payload: AsrStartPayload


class AsrAudioEvent(_AsrEnvelope):
    type: Literal["asr.audio"]
    payload: AsrAudioPayload


class AsrPartialEvent(_AsrEnvelope):
    type: Literal["asr.partial"]
    payload: AsrTranscriptPayload


class AsrFinalEvent(_AsrEnvelope):
    type: Literal["asr.final"]
    payload: AsrTranscriptPayload


class AsrInfoEvent(_AsrEnvelope):
    type: Literal["asr.info"]
    payload: AsrInfoPayload


class AsrErrorEvent(_AsrEnvelope):
    type: Literal["asr.error"]
    payload: AsrErrorPayload


class AsrStopEvent(_AsrEnvelope):
    type: Literal["asr.stop"]
    payload: AsrStopPayload


AsrMessage = Annotated[
    Union[
        AsrStartEvent,
        AsrAudioEvent,
        AsrPartialEvent,
        AsrFinalEvent,
        AsrInfoEvent,
        AsrErrorEvent,
        AsrStopEvent,
    ],
    Field(discriminator="type"),
]

_asr_adapter: TypeAdapter[AsrMessage] = TypeAdapter(AsrMessage)


def parse_asr_message(data: dict) -> AsrMessage:
    """Parse an ASR WebSocket JSON object.

    Args:
        data: Dict with type, session_id, payload.

    Returns:
        Discriminated ASR event.

    Example:
        parse_asr_message({
            "type": "asr.start",
            "session_id": "asr_100",
            "payload": {"room_id": "room_555", "language_mode": "auto"},
        })
    """
    return _asr_adapter.validate_python(data)
