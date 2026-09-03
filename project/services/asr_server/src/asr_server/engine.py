"""ASR engine protocol: mock, Colab remote, or local ONNX stub.

The WebSocket handler only calls `feed` / `flush`. Swap engines via `ASR_ENGINE`.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Literal, Optional, Protocol

import httpx
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
            worker_token=(settings.asr_remote_token or "").strip(),
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
    """POST PCM to the Colab worker (`project/apps/colab_asr/worker.py`).

    `POST {base_url}/v1/transcribe` JSON `{audio_base64, sample_rate, encoding}`
    → `{text, language, is_final}`. Network/HTTP failures return [] so the call stays up.

    Args:
        base_url: Tunnel origin, e.g. https://xxxx.ngrok-free.app.
        worker_token: Optional `X-Worker-Token` (same as worker `--token`).
        return_partial: Honor asr.start.return_partial.
        return_final: Honor asr.start.return_final.
        http_client: Injected `httpx.Client` (tests). Owned client is created otherwise.
        timeout_s: HTTP timeout in seconds (Colab cold start can be slow).

    Example:
        RemoteColabASREngine("https://xxxx.ngrok-free.app")
    """

    name = "remote"

    def __init__(
        self,
        base_url: str,
        *,
        worker_token: str = "",
        return_partial: bool = True,
        return_final: bool = True,
        http_client: Optional[httpx.Client] = None,
        timeout_s: float = 20.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.worker_token = worker_token
        self.return_partial = return_partial
        self.return_final = return_final
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(timeout=timeout_s)
        self._sub_n = 0
        self._subtitle_id = self._alloc_id()
        self._open_text = ""
        self._open_language = SpeechLanguage.UNKNOWN

    def _alloc_id(self) -> str:
        self._sub_n += 1
        return f"sub_remote_{self._sub_n}"

    def _parse_language(self, raw: object) -> SpeechLanguage:
        try:
            return SpeechLanguage(str(raw or "unknown"))
        except ValueError:
            return SpeechLanguage.UNKNOWN

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "ngrok-skip-browser-warning": "1",
        }
        if self.worker_token:
            headers["X-Worker-Token"] = self.worker_token
        return headers

    def _post(self, pcm: bytes) -> Optional[dict]:
        try:
            resp = self._client.post(
                f"{self.base_url}/v1/transcribe",
                json={
                    "audio_base64": base64.b64encode(pcm).decode("ascii"),
                    "sample_rate": 16000,
                    "encoding": "pcm_s16le",
                },
                headers=self._headers(),
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _utterance(self, text: str, language: SpeechLanguage, status: Literal["partial", "final"]) -> TranscriptUtterance:
        return TranscriptUtterance(
            subtitle_id=self._subtitle_id,
            text=text,
            status=status,
            language=language,
        )

    def feed(self, pcm: bytes) -> list[TranscriptUtterance]:
        """Send VAD-gated speech to the worker. Returns [] on empty PCM or errors.

        Args:
            pcm: 16 kHz mono s16le speech bytes.

        Returns:
            Zero or one partial/final step.
        """
        if not pcm:
            return []
        body = self._post(pcm)
        if not body:
            return []
        text = str(body.get("text") or "").strip()
        if not text:
            return []
        language = self._parse_language(body.get("language"))
        is_final = bool(body.get("is_final"))
        if is_final:
            if not self.return_final:
                self._open_text = ""
                self._subtitle_id = self._alloc_id()
                return []
            utt = self._utterance(text, language, "final")
            self._open_text = ""
            self._subtitle_id = self._alloc_id()
            return [utt]
        self._open_text = text
        self._open_language = language
        if not self.return_partial:
            return []
        return [self._utterance(text, language, "partial")]

    def flush(self) -> list[TranscriptUtterance]:
        """Turn a leftover partial into a final on asr.stop.

        Returns:
            Zero or one final utterance.
        """
        if not self._open_text or not self.return_final:
            self._open_text = ""
            return []
        utt = self._utterance(self._open_text, self._open_language, "final")
        self._open_text = ""
        self._subtitle_id = self._alloc_id()
        return [utt]


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
