"""Colab ASR worker HTTP contract (step 4.1) — no GPU, dummy backend."""

import base64
import sys

from fastapi.testclient import TestClient
from ru_tat_call_shared.config import PROJECT_ROOT

sys.path.insert(0, str(PROJECT_ROOT / "apps" / "colab_asr"))

from worker import (  # noqa: E402
    DummyRecognizer,
    build_recognizer,
    create_app,
    decode_pcm_s16le,
    guess_language,
    parse_args,
)


def _pcm_b64(n: int = 320) -> str:
    return base64.b64encode(b"\x00" * n).decode("ascii")


def test_guess_language_tt_ru_mixed() -> None:
    assert guess_language("Әни килде") == "tt"
    assert guess_language("Привет мама") == "ru"
    assert guess_language("Әни, today") == "mixed"
    assert guess_language("Привет hello") == "mixed"
    assert guess_language("") == "unknown"
    assert guess_language("hello") == "unknown"


def test_decode_pcm_rejects_odd_length() -> None:
    odd = base64.b64encode(b"\x00").decode("ascii")
    try:
        decode_pcm_s16le(odd)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_health_and_transcribe_dummy() -> None:
    app = create_app(DummyRecognizer())
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["role"] == "colab-asr"
        assert health.json()["backend"] == "dummy"
        res = client.post(
            "/v1/transcribe",
            json={
                "audio_base64": _pcm_b64(),
                "sample_rate": 16000,
                "encoding": "pcm_s16le",
            },
        )
        assert res.status_code == 200
        body = res.json()
        assert "Әни" in body["text"]
        assert body["language"] == "tt"
        assert body["is_final"] is True


def test_transcribe_empty_pcm() -> None:
    app = create_app(DummyRecognizer())
    with TestClient(app) as client:
        res = client.post(
            "/v1/transcribe",
            json={"audio_base64": "", "sample_rate": 16000, "encoding": "pcm_s16le"},
        )
        assert res.json()["text"] == ""
        assert res.json()["language"] == "unknown"


def test_worker_token_required() -> None:
    app = create_app(DummyRecognizer(), worker_token="secret")
    with TestClient(app) as client:
        denied = client.post(
            "/v1/transcribe",
            json={"audio_base64": _pcm_b64(), "sample_rate": 16000, "encoding": "pcm_s16le"},
        )
        assert denied.status_code == 401
        ok = client.post(
            "/v1/transcribe",
            json={"audio_base64": _pcm_b64(), "sample_rate": 16000, "encoding": "pcm_s16le"},
            headers={"X-Worker-Token": "secret"},
        )
        assert ok.status_code == 200


def test_bad_sample_rate() -> None:
    app = create_app(DummyRecognizer())
    with TestClient(app) as client:
        res = client.post(
            "/v1/transcribe",
            json={"audio_base64": _pcm_b64(), "sample_rate": 100, "encoding": "pcm_s16le"},
        )
        assert res.status_code == 400


def test_build_dummy_and_parse_args() -> None:
    rec = build_recognizer("dummy", None, "cpu")
    assert rec.name == "dummy"
    args = parse_args(["--backend", "dummy", "--port", "8091"])
    assert args.backend == "dummy"
    assert args.port == 8091


def test_notebook_and_worker_files_exist() -> None:
    root = PROJECT_ROOT / "apps" / "colab_asr"
    assert (root / "worker.py").is_file()
    nb = root / "colab_asr_worker.ipynb"
    assert nb.is_file()
    text = nb.read_text(encoding="utf-8")
    assert "v1/transcribe" in text
    assert "ngrok" in text.lower() or "cloudflared" in text
    assert "anton-l/wav2vec2-large-xlsr-53-tatar" in text
    assert "openai/whisper-small" in text
