# asr_server

Потоковый ASR. Шаг 2.1: WebSocket `/v1/stream?token=…` — `asr.start`, `asr.audio` (PCM 16 kHz s16le), буфер, `asr.stop`. Partial/final — шаг 2.2.

```bash
cd project
uv run uvicorn asr_server.app:app --host 0.0.0.0 --port 8001
```

Токен тот же, что после `POST /v1/auth/login` на signaling (общий SQLite).
