"""ASR engine protocol: mock now, Colab/ONNX later without changing the WS loop.

The WebSocket handler only calls `feed` / `flush`. Swap engines via `ASR_ENGINE`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Protocol

from ru_tat_call_shared.config import Settings
from ru_tat_call_shared.contracts.asr import (
    AsrFinalEvent,
    AsrPartialEvent,
    AsrStartPayload,
    AsrTranscriptPayload,
)
from ru_tat_call_shared.contracts.common import SpeechLanguage, SubtitleStatus
from ru_tat_call_shared.contracts.subtitles import SubtitleUpdateEvent, SubtitleUpdatePayload


@dataclass(frozen=True)
class TranscriptUtterance:
    """One partial or final transcript step from any ASREngine.

    Attributes:
        subtitle_id: Stable id until the phrase is finalized.
        text: Growing (partial) or complete (final) string.
        status: partial or final.
        language: Label for the UI badge.
        confidence: Optional model score.
        start_time_ms: Segment start.
        end_time_ms: Segment end.
    """

    subtitle_id: str
    text: str
    status: Literal["partial", "final"]
    language: SpeechLanguage = SpeechLanguage.MIXED
    confidence: Optional[float] = None
    start_time_ms: Optional[int] = None
    end_time_ms: Optional[int] = None


class ASREngine(Protocol):
    """Streaming recognizer: speech PCM in, transcript steps out.

    Implementations must not raise into the audio loop; return [] on failure
    so the WebRTC call stays up (product rule: ASR ≠ call).

    Attributes:
        name: `mock`, `remote`, or `local` (shown on asr.info).

    Example:
        engine = build_asr_engine(settings, start.payload)
        for utt in engine.feed(speech_pcm):
            ...
        engine.flush()
    """

    name: str

    def feed(self, pcm: bytes) -> list[TranscriptUtterance]:
        """Consume 16 kHz mono s16le speech (already VAD-gated).

        Args:
            pcm: Speech bytes; empty means silence / nothing to score.

        Returns:
            Zero or more partial/final steps in order.
        """

    def flush(self) -> list[TranscriptUtterance]:
        """Finalize an open partial on asr.stop.

        Returns:
            Zero or one final utterance.
        """


def build_asr_engine(settings: Settings, start: AsrStartPayload) -> ASREngine:
    """Pick an engine from `ASR_ENGINE`. Missing remote URL / ONNX path → mock.

    Args:
        settings: Process settings (`asr_engine`, `asr_remote_url`, `asr_onnx_path`).
        start: asr.start payload (partial/final flags, language_mode).

    Returns:
        Ready-to-feed engine for one WebSocket session.

    Example:
        engine = build_asr_engine(settings, msg.payload)
    """
    kind = (settings.asr_engine or "mock").strip().lower()
    if kind == "remote" and (settings.asr_remote_url or "").strip():
        return RemoteColabASREngine(
            base_url=settings.asr_remote_url.strip(),
            return_partial=start.return_partial,
            return_final=start.return_final,
        )
    if kind == "local" and (settings.asr_onnx_path or "").strip():
        return LocalOnnxASREngine(
            model_path=settings.asr_onnx_path.strip(),
            return_partial=start.return_partial,
            return_final=start.return_final,
        )
    from asr_server.mock_engine import MockEngine

    return MockEngine(
        return_partial=start.return_partial,
        return_final=start.return_final,
    )


class RemoteColabASREngine:
    """Placeholder for step 4.2: HTTP worker behind ngrok/cloudflared.

    Planned worker contract (not called until 4.2 fills `feed`):
    `POST {base_url}/v1/transcribe` JSON `{audio_base64, sample_rate, encoding}`
    → `{text, language, is_final}`. Failures must return [] (call stays up).

    Args:
        base_url: Tunnel origin, e.g. https://xxxx.ngrok.io.
        return_partial: Honor asr.start.return_partial.
        return_final: Honor asr.start.return_final.

    Example:
        RemoteColabASREngine("https://xxxx.ngrok.io")
    """

    name = "remote"

    def __init__(
        self,
        base_url: str,
        *,
        return_partial: bool = True,
        return_final: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.return_partial = return_partial
        self.return_final = return_final

    def feed(self, pcm: bytes) -> list[TranscriptUtterance]:
        """No-op until the Colab connector lands (step 4.2)."""
        _ = pcm
        return []

    def flush(self) -> list[TranscriptUtterance]:
        """No-op until the Colab connector lands (step 4.2)."""
        return []


class LocalOnnxASREngine:
    """Placeholder for a local ONNX streaming model (step 4).

    Args:
        model_path: Filesystem path to an ONNX checkpoint.
        return_partial: Honor asr.start.return_partial.
        return_final: Honor asr.start.return_final.

    Example:
        LocalOnnxASREngine("/models/xlsr-tatar.onnx")
    """

    name = "local"

    def __init__(
        self,
        model_path: str,
        *,
        return_partial: bool = True,
        return_final: bool = True,
    ) -> None:
        self.model_path = model_path
        self.return_partial = return_partial
        self.return_final = return_final

    def feed(self, pcm: bytes) -> list[TranscriptUtterance]:
        """No-op until a local ONNX runtime is wired (step 4)."""
        _ = pcm
        return []

    def flush(self) -> list[TranscriptUtterance]:
        """No-op until a local ONNX runtime is wired (step 4)."""
        return []


def to_asr_event(session_id: str, speaker_id: str, speaker_name: str, utt: TranscriptUtterance):
    """Build asr.partial or asr.final from a transcript step.

    Args:
        session_id: ASR WebSocket session id.
        speaker_id: Authenticated user id.
        speaker_name: Display name (or empty if speaker_labels is off).
        utt: Engine output.

    Returns:
        AsrPartialEvent or AsrFinalEvent.

    Example:
        to_asr_event("asr_1", "u_you", "Ты", utt)
    """
    payload = AsrTranscriptPayload(
        subtitle_id=utt.subtitle_id,
        speaker_id=speaker_id,
        speaker_name=speaker_name,
        text=utt.text,
        language=utt.language,
        confidence=utt.confidence,
        start_time_ms=utt.start_time_ms,
        end_time_ms=utt.end_time_ms,
        segment_id=utt.subtitle_id if utt.status == "final" else None,
    )
    if utt.status == "final":
        return AsrFinalEvent(type="asr.final", session_id=session_id, payload=payload)
    return AsrPartialEvent(type="asr.partial", session_id=session_id, payload=payload)


def to_subtitle_event(
    room_id: str, speaker_id: str, speaker_name: str, utt: TranscriptUtterance
) -> SubtitleUpdateEvent:
    """Build subtitle.update for signaling fan-out.

    Args:
        room_id: Call room from asr.start.
        speaker_id: Authenticated user id.
        speaker_name: Display name.
        utt: Engine output.

    Returns:
        SubtitleUpdateEvent for all room members.

    Example:
        to_subtitle_event("room_1", "u_you", "Ты", utt)
    """
    status = SubtitleStatus.FINAL if utt.status == "final" else SubtitleStatus.PARTIAL
    return SubtitleUpdateEvent(
        type="subtitle.update",
        room_id=room_id,
        payload=SubtitleUpdatePayload(
            subtitle_id=utt.subtitle_id,
            speaker_id=speaker_id,
            speaker_name=speaker_name,
            text=utt.text,
            status=status,
            language=utt.language,
            confidence=utt.confidence,
            start_time_ms=utt.start_time_ms,
            end_time_ms=utt.end_time_ms,
        ),
    )
