"""Mock ASR engine unit tests (step 2.2)."""

from asr_server.mock_engine import MOCK_PHRASES, TICK_BYTES, MockEngine


def test_partial_then_final_first_phrase() -> None:
    engine = MockEngine()
    first = engine.feed(TICK_BYTES)
    assert len(first) == 1
    assert first[0].status == "partial"
    assert first[0].text == MOCK_PHRASES[0][0]
    sub_id = first[0].subtitle_id
    second = engine.feed(TICK_BYTES)
    assert second[0].status == "partial"
    assert second[0].subtitle_id == sub_id
    assert second[0].text == MOCK_PHRASES[0][0] + MOCK_PHRASES[0][1]
    third = engine.feed(TICK_BYTES)
    assert third[0].status == "final"
    assert third[0].subtitle_id == sub_id
    assert third[0].text == "".join(MOCK_PHRASES[0])


def test_small_chunk_emits_nothing() -> None:
    engine = MockEngine()
    assert engine.feed(4) == []


def test_flush_open_partial() -> None:
    engine = MockEngine()
    engine.feed(TICK_BYTES)
    flushed = engine.flush()
    assert len(flushed) == 1
    assert flushed[0].status == "final"
    assert flushed[0].text == MOCK_PHRASES[0][0]


def test_return_partial_false() -> None:
    engine = MockEngine(return_partial=False, return_final=True)
    assert engine.feed(TICK_BYTES) == []
    assert engine.feed(TICK_BYTES) == []
    finals = engine.feed(TICK_BYTES)
    assert len(finals) == 1
    assert finals[0].status == "final"
