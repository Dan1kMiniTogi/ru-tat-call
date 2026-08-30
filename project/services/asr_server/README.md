# asr_server

Потоковый ASR. Шаг 2.2: mock-движок (смешанные RU/TT фразы по объёму PCM) → `asr.partial` / `asr.final` и fan-out `subtitle.update` в signaling.

```bash
cd project
uv run uvicorn signaling_server.app:app --host 0.0.0.0 --port 8000
uv run uvicorn asr_server.app:app --host 0.0.0.0 --port 8001
```

Токен тот же, что после `POST /v1/auth/login`. Fan-out: `SIGNALING_INTERNAL_URL` + общий `SECRET_KEY`.
