"""Stream VAD: drop silence before the mock (and later real) ASR engine.

Silero runs on CPU via `silero-vad-lite` (bundled ONNX, no PyTorch). If the
package cannot load, the gate falls back to RMS energy so the call still works.
"""

from __future__ import annotations

import array
import math
import struct
from typing import Protocol

WINDOW_SAMPLES = 512
"""Silero VAD frame at 16 kHz (32 ms)."""

WINDOW_BYTES = WINDOW_SAMPLES * 2
"""s16le bytes in one Silero frame."""

ENERGY_RMS_THRESHOLD = 0.02


class SpeechGate(Protocol):
    """Per-session VAD: consume PCM, return speech bytes for the recognizer."""

    def feed(self, pcm: bytes) -> bytes:
        """Score complete 32 ms frames and return concatenated speech PCM.

        Args:
            pcm: New 16 kHz mono s16le bytes.

        Returns:
            Speech frames only (length is a multiple of WINDOW_BYTES, or the
            raw chunk for `off`).
        """

    def reset(self) -> None:
        """Clear leftover samples (call on asr.start)."""


class PassthroughGate:
    """`asr_vad=off`: every byte is treated as speech."""

    def feed(self, pcm: bytes) -> bytes:
        return pcm

    def reset(self) -> None:
        return None


class FrameGate:
    """Buffer 32 ms frames and score each with a probability function.

    Args:
        score: Maps one s16le frame to a speech probability in [0, 1].
        threshold: Accept the frame if score >= threshold.
        name: Backend label for logs / asr.info.

    Example:
        gate = FrameGate(energy_speech_prob, threshold=ENERGY_RMS_THRESHOLD)
        speech = gate.feed(pcm)
    """

    def __init__(self, score, threshold: float, name: str) -> None:
        self._score = score
        self.threshold = threshold
        self.name = name
        self._buf = bytearray()

    def feed(self, pcm: bytes) -> bytes:
        self._buf.extend(pcm)
        speech = bytearray()
        while len(self._buf) >= WINDOW_BYTES:
            frame = bytes(self._buf[:WINDOW_BYTES])
            del self._buf[:WINDOW_BYTES]
            if self._score(frame) >= self.threshold:
                speech.extend(frame)
        return bytes(speech)

    def reset(self) -> None:
        self._buf.clear()


def energy_speech_prob(frame: bytes) -> float:
    """RMS of s16le samples, normalized to ~[0, 1].

    Args:
        frame: One VAD window (or any even-length PCM).

    Returns:
        1.0 if RMS >= ENERGY_RMS_THRESHOLD, else 0.0.
    """
    n = len(frame) // 2
    if n == 0:
        return 0.0
    samples = struct.unpack("<" + "h" * n, frame[: n * 2])
    acc = 0.0
    for s in samples:
        acc += s * s
    rms = math.sqrt(acc / n) / 32768.0
    return 1.0 if rms >= ENERGY_RMS_THRESHOLD else 0.0


def s16le_to_f32_array(frame: bytes):
    """Convert a s16le frame to a writable float32 array in [-1, 1].

    silero-vad-lite requires writable buffers (not plain `bytes`).

    Args:
        frame: PCM s16le, length multiple of 2.

    Returns:
        array.array('f') with one sample per input sample.

    Example:
        s16le_to_f32_array(b"\x00\x00" * 512)
    """
    n = len(frame) // 2
    samples = struct.unpack("<" + "h" * n, frame[: n * 2])
    return array.array("f", [s / 32768.0 for s in samples])


def _silero_score_factory():
    """Return a stateful scorer using silero-vad-lite, or raise ImportError."""
    from silero_vad_lite import SileroVAD

    vad = SileroVAD(16000)

    def score(frame: bytes) -> float:
        return float(vad.process(s16le_to_f32_array(frame)))

    return score


def build_speech_gate(backend: str, silero_threshold: float) -> tuple[SpeechGate, str]:
    """Build a gate for one ASR session.

    Args:
        backend: `silero`, `energy`, or `off`.
        silero_threshold: Probability cutoff for Silero.

    Returns:
        (gate, resolved_backend) — resolved is `energy` if Silero failed to load.

    Example:
        gate, name = build_speech_gate("silero", 0.5)
    """
    kind = (backend or "silero").strip().lower()
    if kind == "off":
        return PassthroughGate(), "off"
    if kind == "energy":
        return FrameGate(energy_speech_prob, ENERGY_RMS_THRESHOLD, "energy"), "energy"
    if kind != "silero":
        return FrameGate(energy_speech_prob, ENERGY_RMS_THRESHOLD, "energy"), "energy"
    try:
        score = _silero_score_factory()
        return FrameGate(score, silero_threshold, "silero"), "silero"
    except Exception:
        return FrameGate(energy_speech_prob, ENERGY_RMS_THRESHOLD, "energy"), "energy"
