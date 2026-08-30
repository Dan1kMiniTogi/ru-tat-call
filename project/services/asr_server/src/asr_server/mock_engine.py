"""Deterministic mock ASR: mixed RU/TT phrases from PCM byte count (no model)."""

from __future__ import annotations

from typing import Literal, Optional, Union

from ru_tat_call_shared.contracts.common import SpeechLanguage

from asr_server.engine import TranscriptUtterance, to_asr_event, to_subtitle_event

# 500 ms of mono 16 kHz s16le.
TICK_BYTES = 16_000
BYTES_PER_MS = 32

MOCK_PHRASES: tuple[tuple[str, ...], ...] = (
    ("Әни,", " сегодня", " я дома."),
    ("Кичә", " килдем."),
)

MockUtterance = TranscriptUtterance


class MockEngine:
    """Advance canned mixed phrases every `tick_bytes` of PCM.

    Does not inspect samples. Used locally so CPU stays idle until a real engine.
    Implements ASREngine (`name`, `feed`, `flush`).

    Args:
        return_partial: Emit asr.partial / subtitle status partial.
        return_final: Emit asr.final / subtitle status final.
        tick_bytes: PCM bytes per mock step (default 500 ms).

    Example:
        engine = MockEngine()
        events = engine.feed(b"\\x00" * TICK_BYTES)
        assert events[0].text == "Әни,"
    """

    name = "mock"

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

    def feed(self, pcm: Union[bytes, int]) -> list[TranscriptUtterance]:
        """Consume speech PCM (or a byte count) and emit zero or more utterances.

        Args:
            pcm: s16le bytes from the VAD gate, or an int length (unit tests).

        Returns:
            Partial/final steps in order.
        """
        pcm_bytes = pcm if isinstance(pcm, int) else len(pcm)
        if pcm_bytes <= 0:
            return []
        self._pending += pcm_bytes
        out: list[TranscriptUtterance] = []
        while self._pending >= self.tick_bytes:
            self._pending -= self.tick_bytes
            self._elapsed_ms += max(1, self.tick_bytes // BYTES_PER_MS)
            step = self._advance()
            if step is not None:
                out.append(step)
        return out

    def flush(self) -> list[TranscriptUtterance]:
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

    def _advance(self) -> Optional[TranscriptUtterance]:
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

    def _utterance(self, status: Literal["partial", "final"]) -> TranscriptUtterance:
        return TranscriptUtterance(
            subtitle_id=self._subtitle_id,
            text=self._text,
            status=status,
            language=SpeechLanguage.MIXED,
            confidence=0.9,
            start_time_ms=self._start_ms,
            end_time_ms=self._elapsed_ms,
        )


__all__ = [
    "BYTES_PER_MS",
    "MOCK_PHRASES",
    "MockEngine",
    "MockUtterance",
    "TICK_BYTES",
    "to_asr_event",
    "to_subtitle_event",
]
