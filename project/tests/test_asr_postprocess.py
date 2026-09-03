"""Transcript postprocess: glue, de-stutter, light punct; never rewrite mixed Tatar."""

from ru_tat_call_shared.contracts.common import SpeechLanguage

from asr_server.engine import TranscriptUtterance
from asr_server.postprocess import (
    TranscriptSmoother,
    collapse_repeated_words,
    collapse_ws,
    ensure_final_punct,
    polish,
    stitch,
)


def _utt(text: str, *, status: str = "partial", sid: str = "sub_1") -> TranscriptUtterance:
    return TranscriptUtterance(
        subtitle_id=sid,
        text=text,
        status=status,  # type: ignore[arg-type]
        language=SpeechLanguage.MIXED,
    )


def test_collapse_ws_keeps_tatar_letters() -> None:
    assert collapse_ws("  Әни,   сегодня  ") == "Әни, сегодня"


def test_stitch_grows_and_overlaps() -> None:
    assert stitch("Әни,", "Әни, сегодня") == "Әни, сегодня"
    assert stitch("сегодня я", "я дома") == "сегодня я дома"
    assert stitch("Әни, сегодня я дома.", "Әни") == "Әни, сегодня я дома."


def test_no_latinize_mixed() -> None:
    mixed = "Әни, сегодня я дома."
    assert polish(mixed, is_final=True) == mixed


def test_repeated_words() -> None:
    assert collapse_repeated_words("килдем килдем мама") == "килдем мама"


def test_final_punct_skips_existing() -> None:
    assert ensure_final_punct("Кичә килдем") == "Кичә килдем."
    assert ensure_final_punct("Әни,") == "Әни,"


def test_smoother_drops_duplicate_and_glues() -> None:
    s = TranscriptSmoother()
    a = s.apply(_utt("Әни,"))
    assert a is not None and a.text == "Әни,"
    b = s.apply(_utt("Әни, сегодня"))
    assert b is not None and b.text == "Әни, сегодня"
    c = s.apply(_utt("Әни, сегодня"))
    assert c is None
    d = s.apply(_utt("Әни, сегодня я дома.", status="final"))
    assert d is not None and d.text == "Әни, сегодня я дома."
    e = s.apply(_utt("Әни, сегодня я дома.", status="final"))
    assert e is None
