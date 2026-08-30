"""ASREngine factory and stubs (step 2.4)."""

from ru_tat_call_shared.config import Settings
from ru_tat_call_shared.contracts.asr import AsrStartPayload

from asr_server.engine import LocalOnnxASREngine, RemoteColabASREngine, build_asr_engine
from asr_server.mock_engine import MOCK_PHRASES, TICK_BYTES, MockEngine


def _start() -> AsrStartPayload:
    return AsrStartPayload(room_id="room_1")


def test_default_is_mock() -> None:
    engine = build_asr_engine(Settings(_env_file=None), _start())
    assert isinstance(engine, MockEngine)
    assert engine.name == "mock"
    utt = engine.feed(b"\x00" * TICK_BYTES)
    assert utt[0].text == MOCK_PHRASES[0][0]


def test_remote_without_url_falls_back_to_mock() -> None:
    settings = Settings(_env_file=None, asr_engine="remote", asr_remote_url="")
    engine = build_asr_engine(settings, _start())
    assert isinstance(engine, MockEngine)


def test_remote_with_url_is_stub() -> None:
    settings = Settings(
        _env_file=None,
        asr_engine="remote",
        asr_remote_url="https://example.ngrok.io",
    )
    engine = build_asr_engine(settings, _start())
    assert isinstance(engine, RemoteColabASREngine)
    assert engine.name == "remote"
    assert engine.feed(b"\x00" * TICK_BYTES) == []
    assert engine.flush() == []


def test_local_without_path_falls_back_to_mock() -> None:
    settings = Settings(_env_file=None, asr_engine="local", asr_onnx_path="")
    engine = build_asr_engine(settings, _start())
    assert isinstance(engine, MockEngine)


def test_local_with_path_is_stub() -> None:
    settings = Settings(_env_file=None, asr_engine="local", asr_onnx_path="/tmp/model.onnx")
    engine = build_asr_engine(settings, _start())
    assert isinstance(engine, LocalOnnxASREngine)
    assert engine.name == "local"
    assert engine.feed(b"\x00" * 16) == []
