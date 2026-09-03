"""Household mixed RU/TT phrases for latency / smoke checks (step 4.3).

These are reference *texts* for code-switch coverage. CI uses synthetic PCM
(silence/sine of 500–1000 ms). Real WER needs spoken recordings + a live GPU
worker — the CLI prints hypothesis vs reference and does not invent scores.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Lang = Literal["ru", "tt", "mixed"]


@dataclass(frozen=True)
class BenchPhrase:
    """One evaluation utterance.

    Args:
        phrase_id: Stable id for logs.
        language: Expected UI language badge.
        text: Reference transcript (human).
    """

    phrase_id: str
    language: Lang
    text: str


# Everyday call-style lines (not a published corpus). Mixed items code-switch.
PHRASES: tuple[BenchPhrase, ...] = (
    BenchPhrase("ru_home", "ru", "Мама, я сегодня дома."),
    BenchPhrase("tt_came", "tt", "Әни, кичә килдем."),
    BenchPhrase("mixed_home", "mixed", "Әни, сегодня я дома."),
    BenchPhrase("mixed_came", "mixed", "Кичә килдем, мама."),
)

# DummyRecognizer always returns this string (worker.py).
DUMMY_TEXT = "Әни, сегодня я дома."
