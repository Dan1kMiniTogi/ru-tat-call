"""PCM stream session: start, append 16 kHz s16le chunks, stop."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field

from ru_tat_call_shared.contracts.asr import AsrAudioPayload, AsrStartPayload

EXPECTED_RATE = 16000
EXPECTED_CHANNELS = 1
EXPECTED_ENCODING = "pcm_s16le"
# ~30 s of mono 16-bit 16 kHz; later steps can flush to the engine sooner.
MAX_BUFFER_BYTES = 16_000 * 2 * 30


class AudioFormatError(ValueError):
    """Chunk is not 16 kHz mono PCM s16le or is not valid base64/PCM."""


@dataclass
class StreamSession:
    """One ASR WebSocket session and its PCM buffer.

    Args:
        session_id: Client-provided session id.
        user_id: Authenticated speaker (stream attribution).
        room_id: Call room from asr.start.
        language_mode: Requested language mode.

    Example:
        session = StreamSession("asr_1", "u_you")
        session.start(AsrStartPayload(room_id="room_1"))
        n = session.append_audio(payload)
    """

    session_id: str
    user_id: str
    room_id: str = ""
    language_mode: str = "auto"
    started: bool = False
    pcm: bytearray = field(default_factory=bytearray)

    def start(self, payload: AsrStartPayload) -> None:
        """Mark the session started and reset the PCM buffer."""
        self.room_id = payload.room_id
        self.language_mode = payload.language_mode.value
        self.started = True
        self.pcm.clear()

    def append_audio(self, payload: AsrAudioPayload) -> int:
        """Decode and append one audio chunk.

        Args:
            payload: asr.audio payload.

        Returns:
            Number of PCM bytes appended.

        Raises:
            AudioFormatError: Wrong format, bad base64, odd length, or overflow.
        """
        if not self.started:
            raise AudioFormatError("asr.start is required before asr.audio")
        if payload.sample_rate != EXPECTED_RATE:
            raise AudioFormatError("sample_rate must be 16000")
        if payload.channels != EXPECTED_CHANNELS:
            raise AudioFormatError("channels must be 1")
        if payload.encoding != EXPECTED_ENCODING:
            raise AudioFormatError("encoding must be pcm_s16le")
        try:
            try:
                raw = base64.b64decode(payload.audio_base64, validate=True)
            except TypeError:
                raw = base64.b64decode(payload.audio_base64)
        except Exception as exc:
            raise AudioFormatError("audio_base64 is invalid") from exc
        if len(raw) % 2 != 0:
            raise AudioFormatError("PCM s16le length must be even")
        if len(self.pcm) + len(raw) > MAX_BUFFER_BYTES:
            raise AudioFormatError("PCM buffer overflow")
        self.pcm.extend(raw)
        return len(raw)

    def stop(self) -> int:
        """Clear the buffer. Returns bytes that were buffered."""
        n = len(self.pcm)
        self.pcm.clear()
        self.started = False
        return n
