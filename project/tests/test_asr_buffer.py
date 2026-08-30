"""ASR PCM buffer unit tests (step 2.1)."""

import base64

import pytest
from ru_tat_call_shared.contracts.asr import AsrAudioPayload, AsrStartPayload

from asr_server.buffer import AudioFormatError, StreamSession


def _pcm_payload(raw: bytes, *, sample_rate: int = 16000) -> AsrAudioPayload:
    return AsrAudioPayload(
        chunk_id="c1",
        timestamp=1,
        sample_rate=sample_rate,
        channels=1,
        encoding="pcm_s16le",
        audio_base64=base64.b64encode(raw).decode("ascii"),
    )


def test_append_and_stop() -> None:
    session = StreamSession("asr_1", "u_you")
    session.start(AsrStartPayload(room_id="room_1"))
    raw = b"\x00\x00\x01\x00"
    n = session.append_audio(_pcm_payload(raw))
    assert n == 4
    assert bytes(session.pcm) == raw
    assert session.stop() == 4
    assert session.pcm == b""
    assert session.started is False


def test_rejects_wrong_rate() -> None:
    session = StreamSession("asr_1", "u_you")
    session.start(AsrStartPayload(room_id="room_1"))
    with pytest.raises(AudioFormatError, match="sample_rate"):
        session.append_audio(_pcm_payload(b"\x00\x00", sample_rate=8000))


def test_audio_before_start() -> None:
    session = StreamSession("asr_1", "u_you")
    with pytest.raises(AudioFormatError, match="asr.start"):
        session.append_audio(_pcm_payload(b"\x00\x00"))
