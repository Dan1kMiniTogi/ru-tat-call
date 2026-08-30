"""Tests that examples from context/contracts.md parse as Pydantic models."""

from ru_tat_call_shared.contracts import (
    ContactsListResponse,
    ErrorCode,
    LanguageMode,
    LoginRequest,
    LoginResponse,
    SpeechLanguage,
    SubtitleStatus,
    SubtitleUpdateEvent,
    TranscriptionSettings,
    UserProfile,
    parse_asr_message,
    parse_signaling_message,
)
from ru_tat_call_shared.contracts.asr import AsrPartialEvent
from ru_tat_call_shared.contracts.signaling import RoomCreateEvent, WebrtcIceEvent


def test_login_roundtrip() -> None:
    """Login request/response JSON from the spec validates."""
    req = LoginRequest.model_validate(
        {"identifier": "user@example.com", "password": "secret"}
    )
    assert req.identifier == "user@example.com"
    resp = LoginResponse.model_validate(
        {
            "user_id": "u_123",
            "access_token": "eyJ...",
            "refresh_token": "eyJ...",
            "expires_in": 3600,
        }
    )
    assert resp.user_id == "u_123"


def test_profile_contacts_settings() -> None:
    """REST user, contacts and transcription settings parse."""
    me = UserProfile.model_validate(
        {"user_id": "u_123", "display_name": "Amina", "avatar_url": None}
    )
    assert me.avatar_url is None
    contacts = ContactsListResponse.model_validate(
        {
            "items": [
                {"user_id": "u_201", "display_name": "Mama", "status": "offline"},
            ]
        }
    )
    assert contacts.items[0].status == "offline"
    settings = TranscriptionSettings.model_validate(
        {"enabled": True, "store_transcripts": False, "show_speaker_labels": True}
    )
    assert settings.enabled is True


def test_signaling_room_create_and_ice() -> None:
    """Signaling discriminator maps type to the right model, including ICE aliases."""
    created = parse_signaling_message(
        {
            "type": "room.create",
            "request_id": "req_001",
            "timestamp": 1710000000,
            "payload": {"participant_ids": ["u_123", "u_201"]},
        }
    )
    assert isinstance(created, RoomCreateEvent)
    ice = parse_signaling_message(
        {
            "type": "webrtc.ice",
            "request_id": "req_007",
            "timestamp": 1710000000,
            "payload": {
                "room_id": "room_555",
                "from_user_id": "u_123",
                "to_user_id": "u_201",
                "candidate": {
                    "candidate": "candidate:...",
                    "sdpMid": "0",
                    "sdpMLineIndex": 0,
                },
            },
        }
    )
    assert isinstance(ice, WebrtcIceEvent)
    assert ice.payload.candidate.sdp_mid == "0"
    err = parse_signaling_message(
        {
            "type": "error",
            "request_id": "req_010",
            "timestamp": 1710000000,
            "payload": {
                "code": "INVALID_TOKEN",
                "message": "Access token is invalid or expired",
            },
        }
    )
    assert err.payload.code == ErrorCode.INVALID_TOKEN


def test_asr_start_audio_partial() -> None:
    """ASR start, audio chunk and partial transcript from the spec parse."""
    start = parse_asr_message(
        {
            "type": "asr.start",
            "session_id": "asr_100",
            "payload": {
                "room_id": "room_555",
                "language_mode": "auto",
                "return_partial": True,
                "return_final": True,
                "speaker_labels": True,
            },
        }
    )
    assert start.payload.language_mode == LanguageMode.AUTO
    audio = parse_asr_message(
        {
            "type": "asr.audio",
            "session_id": "asr_100",
            "payload": {
                "chunk_id": "chunk_001",
                "timestamp": 1710000001,
                "sample_rate": 16000,
                "channels": 1,
                "encoding": "pcm_s16le",
                "audio_base64": "UklGR...",
            },
        }
    )
    assert audio.payload.encoding == "pcm_s16le"
    partial = parse_asr_message(
        {
            "type": "asr.partial",
            "session_id": "asr_100",
            "payload": {
                "subtitle_id": "sub_101",
                "speaker_id": "u_123",
                "speaker_name": "Ты",
                "text": "Әни, сегодня...",
                "language": "mixed",
                "confidence": 0.81,
                "start_time_ms": 1020,
                "end_time_ms": 1840,
            },
        }
    )
    assert isinstance(partial, AsrPartialEvent)
    assert partial.payload.language == SpeechLanguage.MIXED


def test_subtitle_update() -> None:
    """subtitle.update event used by the call UI."""
    event = SubtitleUpdateEvent.model_validate(
        {
            "type": "subtitle.update",
            "room_id": "room_555",
            "payload": {
                "subtitle_id": "sub_101",
                "speaker_id": "u_123",
                "speaker_name": "Ты",
                "text": "Бүген соңрак кайтам.",
                "status": "final",
                "language": "mixed",
                "confidence": 0.91,
                "start_time_ms": 1020,
                "end_time_ms": 2900,
            },
        }
    )
    assert event.payload.status == SubtitleStatus.FINAL
