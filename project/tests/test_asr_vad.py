"""VAD gates silence before the mock engine (step 2.3)."""

import math
import struct

from asr_server.vad import (
    ENERGY_RMS_THRESHOLD,
    WINDOW_BYTES,
    build_speech_gate,
    energy_speech_prob,
)


def sine_pcm(n_bytes: int, freq: float = 440.0, amp: float = 0.4) -> bytes:
    """Generate 16 kHz mono s16le sine. n_bytes must be even."""
    n = n_bytes // 2
    samples = [
        int(amp * 32767 * math.sin(2 * math.pi * freq * i / 16000)) for i in range(n)
    ]
    return struct.pack("<" + "h" * n, *samples)


def test_energy_silence_is_zero() -> None:
    assert energy_speech_prob(b"\x00" * WINDOW_BYTES) == 0.0


def test_energy_sine_is_speech() -> None:
    assert energy_speech_prob(sine_pcm(WINDOW_BYTES)) == 1.0
    assert ENERGY_RMS_THRESHOLD < 1.0


def test_energy_gate_drops_silence() -> None:
    gate, name = build_speech_gate("energy", 0.5)
    assert name == "energy"
    assert gate.feed(b"\x00" * WINDOW_BYTES * 20) == b""


def test_energy_gate_passes_sine() -> None:
    gate, _ = build_speech_gate("energy", 0.5)
    frames = 16
    n = gate.feed(sine_pcm(WINDOW_BYTES * frames))
    assert len(n) == WINDOW_BYTES * frames


def test_off_passthrough() -> None:
    gate, name = build_speech_gate("off", 0.5)
    assert name == "off"
    assert gate.feed(b"\x00\x00") == b"\x00\x00"


def test_silero_backend_loads_or_falls_back() -> None:
    """Silero should load with silero-vad-lite; energy is the documented fallback."""
    gate, name = build_speech_gate("silero", 0.5)
    assert name in {"silero", "energy"}
    assert gate.feed(b"\x00" * WINDOW_BYTES * 8) == b""
    if name == "silero":
        n = gate.feed(harmonic_pcm(WINDOW_BYTES * 8))
        assert len(n) == WINDOW_BYTES * 8
    else:
        assert len(gate.feed(sine_pcm(WINDOW_BYTES))) == WINDOW_BYTES


def harmonic_pcm(n_bytes: int) -> bytes:
    """s16le mix that Silero typically scores as speech (not a pure tone)."""
    n = n_bytes // 2
    samples = []
    for i in range(n):
        t = i / 16000
        v = (
            0.3 * math.sin(2 * math.pi * 140 * t)
            + 0.2 * math.sin(2 * math.pi * 280 * t)
            + 0.15 * math.sin(2 * math.pi * 420 * t)
        )
        samples.append(int(v * 32000))
    return struct.pack("<" + "h" * n, *samples)
