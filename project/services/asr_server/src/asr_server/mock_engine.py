"""Deterministic mock ASR: mixed RU/TT phrases from PCM byte count (no model)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from ru_tat_call_shared.contracts.asr import (
    AsrFinalEvent,
    AsrPartialEvent,
    AsrTranscriptPayload,
)
from ru_tat_call_shared.contracts.common import SpeechLanguage, SubtitleStatus
from ru_tat_call_shared.contracts.subtitles import SubtitleUpdateEvent, SubtitleUpdatePayload

# 500 ms of mono 16 kHz s16le.
TICK_BYTES = 16_000
BYTES_PER_MS = 32

MOCK_PHRASES: tuple[tuple[str, ...], ...] = (
    ("Әни,", " сегодня", " я дома."),
    ("Кичә", " килдем."),
)


@dataclass(frozen=True)
class MockUtterance:
    """One mock transcript step.

    Attributes:
        subtitle_id: Stable id until the phrase is finalized.
        text: Growing (partial) or complete (final) string.
        status: partial or final.
        start_time_ms: Phrase start on the mock timeline.
        end_time_ms: Current mock time.
    """

    subtitle_id: str
    text: str
    status: Literal["partial", "final"]
    start_time_ms: int
    end_time_ms: int


class MockEngine:
    """Advance canned mixed phrases every `tick_bytes` of PCM.

    Does not inspect samples. Used locally so CPU stays idle until a real engine.

    Args:
        return_partial: Emit asr.partial / subtitle status partial.
        return_final: Emit asr.final / subtitle status final.
        tick_bytes: PCM bytes per mock step (default 500 ms).

    Example:
        engine = MockEngine()
        events = engine.feed(TICK_BYTES)
        assert events[0].text == "Әни,"
    """

    def __init__(
        self,
        *,
        return_partial: bool = True,
        return_final: bool = True,
        tick_bytes: int = TICK_BYTES,
    ) -> None:
        self.return_partial = return_partial
        self.return_final = return_final
        self.tick_bytes = tick_bytes
        self._pending = 0
        self._elapsed_ms = 0
        self._phrase_i = 0
        self._part_i = 0
        self._sub_n = 0
        self._subtitle_id = self._alloc_id()
        self._start_ms = 0
        self._text = ""

    def feed(self, pcm_bytes: int) -> list[MockUtterance]:
        """Consume PCM length and emit zero or more utterances.

        Args:
            pcm_bytes: Number of s16le bytes just appended.

        Returns:
            Partial/final steps in order.
        """
        if pcm_bytes <= 0:
            return []
        self._pending += pcm_bytes
        out: list[MockUtterance] = []
        while self._pending >= self.tick_bytes:
            self._pending -= self.tick_bytes
            self._elapsed_ms += max(1, self.tick_bytes // BYTES_PER_MS)
            step = self._advance()
            if step is not None:
                out.append(step)
        return out

    def flush(self) -> list[MockUtterance]:
        """Finalize the open partial (if any) on asr.stop.

        Returns:
            Zero or one final utterance.
        """
        if not self._text or not self.return_final:
            self._reset_phrase()
            return []
        event = self._utterance("final")
        self._reset_phrase()
        self._phrase_i += 1
        return [event]

    def _advance(self) -> Optional[MockUtterance]:
        phrase = MOCK_PHRASES[self._phrase_i % len(MOCK_PHRASES)]
        piece = phrase[self._part_i]
        if self._part_i == 0:
            self._text = piece
            self._start_ms = self._elapsed_ms - max(1, self.tick_bytes // BYTES_PER_MS)
        else:
            self._text += piece
        last = self._part_i >= len(phrase) - 1
        if last:
            event = self._utterance("final") if self.return_final else None
            self._reset_phrase()
            self._phrase_i += 1
            return event
        self._part_i += 1
        if self.return_partial:
            return self._utterance("partial")
        return None

    def _reset_phrase(self) -> None:
        self._part_i = 0
        self._text = ""
        self._subtitle_id = self._alloc_id()

    def _alloc_id(self) -> str:
        self._sub_n += 1
        return f"sub_mock_{self._sub_n}"

    def _utterance(self, status: Literal["partial", "final"]) -> MockUtterance:
        return MockUtterance(
            subtitle_id=self._subtitle_id,
            text=self._text,
            status=status,
            start_time_ms=self._start_ms,
            end_time_ms=self._elapsed_ms,
        )


def to_asr_event(session_id: str, speaker_id: str, speaker_name: str, utt: MockUtterance):
    """Build asr.partial or asr.final from a mock step.

    Args:
        session_id: ASR WebSocket session id.
        speaker_id: Authenticated user id.
        speaker_name: Display name (or empty if speaker_labels is off).
        utt: Mock step.

    Returns:
        AsrPartialEvent or AsrFinalEvent.

    Example:
        to_asr_event("asr_1", "u_you", "Ты", utt)
    """
    """Build asr.partial or asr.final from a mock step.

    Args:
        session_id: ASR WebSocket session id.
        speaker_id: Authenticated user id.
        speaker_name: Display name (or empty if speaker_labels is off).
        utt: Mock step.

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
        language=SpeechLanguage.MIXED,
        confidence=0.9,
        start_time_ms=utt.start_time_ms,
        end_time_ms=utt.end_time_ms,
        segment_id=utt.subtitle_id if utt.status == "final" else None,
    )
    if utt.status == "final":
        return AsrFinalEvent(type="asr.final", session_id=session_id, payload=payload)
    return AsrPartialEvent(type="asr.partial", session_id=session_id, payload=payload)


def to_subtitle_event(
    room_id: str, speaker_id: str, speaker_name: str, utt: MockUtterance
) -> SubtitleUpdateEvent:
    """Build subtitle.update for signaling fan-out.

    Args:
        room_id: Call room from asr.start.
        speaker_id: Authenticated user id.
        speaker_name: Display name.
        utt: Mock step.

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
            language=SpeechLanguage.MIXED,
            confidence=0.9,
            start_time_ms=utt.start_time_ms,
            end_time_ms=utt.end_time_ms,
        ),
    )
