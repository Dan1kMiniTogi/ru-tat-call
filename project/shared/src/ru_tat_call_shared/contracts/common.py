"""Enums and base model shared by all API contracts."""

from enum import Enum

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    """Base JSON model: unknown fields are ignored for forward compatibility.

    Example:
        class Item(ApiModel):
            id: str
    """

    model_config = ConfigDict(extra="ignore")


class ErrorCode(str, Enum):
    """Stable error codes from the API spec."""

    INVALID_TOKEN = "INVALID_TOKEN"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    UNAUTHORIZED = "UNAUTHORIZED"
    ROOM_NOT_FOUND = "ROOM_NOT_FOUND"
    ROOM_FULL = "ROOM_FULL"
    USER_OFFLINE = "USER_OFFLINE"
    ASR_UNAVAILABLE = "ASR_UNAVAILABLE"
    MODEL_BUSY = "MODEL_BUSY"
    INVALID_AUDIO_FORMAT = "INVALID_AUDIO_FORMAT"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class LanguageMode(str, Enum):
    """ASR session language_mode on asr.start."""

    AUTO = "auto"
    MIXED = "mixed"
    RU = "ru"
    TT = "tt"


class SpeechLanguage(str, Enum):
    """Language label on transcript and subtitle events."""

    AUTO = "auto"
    MIXED = "mixed"
    RU = "ru"
    TT = "tt"
    UNKNOWN = "unknown"


class SubtitleStatus(str, Enum):
    """partial is updated in place; final is frozen in call history."""

    PARTIAL = "partial"
    FINAL = "final"


class ErrorPayload(ApiModel):
    """Error body used on WebSocket `error` events.

    Args:
        code: Machine-readable ErrorCode.
        message: Human-readable explanation (not shown as-is to end users).
    """

    code: ErrorCode
    message: str
