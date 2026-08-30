# asr_server

Потоковый ASR. Mock + VAD (Silero ONNX на CPU): тишина не генерирует субтитры.

```bash
cd project
uv run uvicorn signaling_server.app:app --host 0.0.0.0 --port 8000
uv run uvicorn asr_server.app:app --host 0.0.0.0 --port 8001
```

Токен — после `POST /v1/auth/login`. Fan-out: `SIGNALING_INTERNAL_URL` + `SECRET_KEY`. VAD: `ASR_VAD=silero` (по умолчанию).
