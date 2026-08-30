"""GPU ASR worker for Google Colab / Kaggle (step 4.1).

Contract used by `RemoteColabASREngine` (step 4.2):

    POST /v1/transcribe
    {"audio_base64": "...", "sample_rate": 16000, "encoding": "pcm_s16le"}
    → {"text": "...", "language": "tt"|"ru"|"mixed"|"unknown", "is_final": true}

Default checkpoints (from context/asr.md, not a quality benchmark):
    wav2vec2: anton-l/wav2vec2-large-xlsr-53-tatar
    whisper:  openai/whisper-small

`--backend dummy` skips HuggingFace (pytest / smoke without GPU).

Example:
    python worker.py --backend dummy --port 8090
    curl -s http://127.0.0.1:8090/health
"""

from __future__ import annotations

import argparse
import base64
import os
from dataclasses import dataclass
from typing import Literal, Optional, Protocol

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

Language = Literal["ru", "tt", "mixed", "unknown"]

TT_LETTERS = frozenset("әөүҗңһӘӨҮҖҢҺ")
CYRILLIC = frozenset("абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ") | TT_LETTERS

DEFAULT_WAV2VEC2 = "anton-l/wav2vec2-large-xlsr-53-tatar"
DEFAULT_WHISPER = "openai/whisper-small"


class TranscribeRequest(BaseModel):
    """JSON body for POST /v1/transcribe.

    Args:
        audio_base64: Mono PCM (usually 16 kHz s16le) as base64.
        sample_rate: Native rate of the buffer (worker may resample).
        encoding: Only `pcm_s16le` in MVP.
    """

    audio_base64: str
    sample_rate: int = 16000
    encoding: Literal["pcm_s16le"] = "pcm_s16le"


class TranscribeResponse(BaseModel):
    """JSON body returned to the laptop ASR process."""

    text: str
    language: Language
    is_final: bool = True


@dataclass(frozen=True)
class TranscribeResult:
    """Internal recognizer output (same fields as the HTTP response)."""

    text: str
    language: Language
    is_final: bool = True


class SpeechRecognizer(Protocol):
    """One-shot PCM → text. Implementations must not raise on empty audio."""

    name: str

    def transcribe(self, pcm: bytes, sample_rate: int) -> TranscribeResult:
        """Decode 16-bit little-endian mono PCM.

        Args:
            pcm: Raw s16le bytes.
            sample_rate: Sample rate of `pcm`.

        Returns:
            Text plus a coarse language label.
        """


def guess_language(text: str) -> Language:
    """Coarse RU/TT/mixed tag (no LID model).

    Tatar-specific letters (ә ө ү җ ң һ) → `tt`, unless Latin letters are also
    present (`mixed`). Other Cyrillic without those letters → `ru`.

    Args:
        text: Recognizer transcript.

    Returns:
        One of ru, tt, mixed, unknown.

    Example:
        guess_language("Әни килде") == "tt"
        guess_language("Привет") == "ru"
        guess_language("Әни, today") == "mixed"
    """
    if not text or not text.strip():
        return "unknown"
    has_tt = any(ch in TT_LETTERS for ch in text)
    has_cyr = any(ch in CYRILLIC for ch in text)
    has_lat = any(("a" <= ch <= "z") or ("A" <= ch <= "Z") for ch in text)
    if has_tt and has_lat:
        return "mixed"
    if has_cyr and has_lat:
        return "mixed"
    if has_tt:
        return "tt"
    if has_cyr:
        return "ru"
    return "unknown"


def decode_pcm_s16le(audio_base64: str) -> bytes:
    """Decode base64 to even-length s16le bytes.

    Args:
        audio_base64: Base64 payload from the client.

    Returns:
        Raw PCM bytes.

    Raises:
        ValueError: Invalid base64 or odd length.
    """
    try:
        raw = base64.b64decode(audio_base64, validate=False)
    except Exception as exc:
        raise ValueError("audio_base64 is not valid base64") from exc
    if len(raw) % 2 != 0:
        raise ValueError("pcm_s16le length must be even")
    return raw


class DummyRecognizer:
    """Deterministic backend for tests and Colab smoke without downloading weights."""

    name = "dummy"

    def transcribe(self, pcm: bytes, sample_rate: int) -> TranscribeResult:
        _ = sample_rate
        if not pcm:
            return TranscribeResult(text="", language="unknown", is_final=True)
        text = "Әни, сегодня я дома."
        return TranscribeResult(text=text, language=guess_language(text), is_final=True)


class HuggingFaceRecognizer:
    """Wav2Vec2 CTC or Whisper via transformers (GPU on Colab).

    Args:
        backend: `wav2vec2` or `whisper`.
        model_id: HuggingFace hub id.
        device: `cuda` or `cpu`.

    Example:
        HuggingFaceRecognizer("wav2vec2", DEFAULT_WAV2VEC2, "cuda")
    """

    def __init__(self, backend: str, model_id: str, device: str) -> None:
        self.backend = backend
        self.model_id = model_id
        self.device = device
        self.name = f"{backend}:{model_id}"
        self._pipe = None

    def _load(self):
        if self._pipe is not None:
            return self._pipe
        import numpy as np
        import torch
        from transformers import pipeline

        device = 0 if self.device == "cuda" and torch.cuda.is_available() else -1
        task = "automatic-speech-recognition"
        kwargs: dict = {"model": self.model_id, "device": device}
        if self.backend == "whisper":
            kwargs["chunk_length_s"] = 30
        self._np = np
        self._pipe = pipeline(task, **kwargs)
        return self._pipe

    def transcribe(self, pcm: bytes, sample_rate: int) -> TranscribeResult:
        if not pcm:
            return TranscribeResult(text="", language="unknown", is_final=True)
        try:
            pipe = self._load()
            np = self._np
            audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
            out = pipe({"array": audio, "sampling_rate": int(sample_rate)})
            text = (out.get("text") or "").strip() if isinstance(out, dict) else str(out).strip()
            return TranscribeResult(text=text, language=guess_language(text), is_final=True)
        except Exception:
            return TranscribeResult(text="", language="unknown", is_final=True)


def build_recognizer(backend: str, model_id: Optional[str], device: str) -> SpeechRecognizer:
    """Factory for dummy / wav2vec2 / whisper.

    Args:
        backend: dummy | wav2vec2 | whisper.
        model_id: Hub id; defaults per backend.
        device: cuda | cpu.

    Returns:
        Ready recognizer (HF weights load on first transcribe).
    """
    kind = backend.strip().lower()
    if kind == "dummy":
        return DummyRecognizer()
    if kind == "wav2vec2":
        return HuggingFaceRecognizer("wav2vec2", model_id or DEFAULT_WAV2VEC2, device)
    if kind == "whisper":
        return HuggingFaceRecognizer("whisper", model_id or DEFAULT_WHISPER, device)
    raise ValueError(f"unknown backend {backend!r}")


def create_app(
    recognizer: SpeechRecognizer,
    worker_token: str = "",
) -> FastAPI:
    """Build the Colab worker FastAPI app.

    Args:
        recognizer: Dummy or HuggingFace backend.
        worker_token: If non-empty, require header `X-Worker-Token`.

    Returns:
        FastAPI application.

    Example:
        app = create_app(DummyRecognizer())
    """
    app = FastAPI(title="ru-tat-call colab asr", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.recognizer = recognizer
    app.state.worker_token = worker_token

    @app.get("/health")
    def health() -> dict:
        """Liveness plus which backend is loaded."""
        rec: SpeechRecognizer = app.state.recognizer
        return {"ok": True, "role": "colab-asr", "backend": rec.name}

    @app.post("/v1/transcribe", response_model=TranscribeResponse)
    def transcribe(
        body: TranscribeRequest,
        x_worker_token: Optional[str] = Header(default=None),
    ) -> TranscribeResponse:
        """Transcribe one PCM chunk. Failures return empty text (call stays up)."""
        expected = app.state.worker_token
        if expected and x_worker_token != expected:
            raise HTTPException(status_code=401, detail="Invalid worker token")
        if body.sample_rate < 8000 or body.sample_rate > 48000:
            raise HTTPException(status_code=400, detail="Unsupported sample_rate")
        try:
            pcm = decode_pcm_s16le(body.audio_base64)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        rec: SpeechRecognizer = app.state.recognizer
        result = rec.transcribe(pcm, body.sample_rate)
        return TranscribeResponse(
            text=result.text,
            language=result.language,
            is_final=result.is_final,
        )

    return app


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """CLI for uvicorn on Colab.

    Args:
        argv: Optional argument list (tests).

    Returns:
        Parsed namespace.
    """
    parser = argparse.ArgumentParser(description="Colab ASR HTTP worker")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument(
        "--backend",
        default=os.environ.get("ASR_WORKER_BACKEND", "wav2vec2"),
        choices=("dummy", "wav2vec2", "whisper"),
    )
    parser.add_argument("--model", default=os.environ.get("ASR_WORKER_MODEL", ""))
    parser.add_argument(
        "--device",
        default=os.environ.get("ASR_WORKER_DEVICE", "cuda"),
        choices=("cuda", "cpu"),
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("ASR_WORKER_TOKEN", ""),
        help="Optional X-Worker-Token (laptop can send the same value later)",
    )
    return parser.parse_args(argv)


def main() -> None:
    """Load recognizer and serve FastAPI.

    Example:
        python worker.py --backend dummy --port 8090
    """
    import uvicorn

    args = parse_args()
    model_id = args.model.strip() or None
    rec = build_recognizer(args.backend, model_id, args.device)
    app = create_app(rec, worker_token=args.token.strip())
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
