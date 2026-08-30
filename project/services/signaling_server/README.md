# signaling_server

Signaling HTTP API (FastAPI + SQLite). WebSocket комнат — шаги 1.2–1.3.

```bash
cd project
cp -n .env.example .env
uv sync --all-packages --group dev
uv run uvicorn signaling_server.app:app --host 0.0.0.0 --port 8000
```

WebSocket: `ws://127.0.0.1:8000/ws/signaling?token=ACCESS_TOKEN`  
UI: `http://127.0.0.1:8000/` (шаг 3.1).
Публичный HTTPS (телефон): `project/infra/README.md` — ASR через `/v1/asr-stream` на том же origin.
События: `room.create`, `call.invite`, `call.accept`, `call.reject`, `webrtc.offer` / `answer` / `ice`.
Обрыв WS: участник остаётся в комнате `SIGNALING_DISCONNECT_GRACE_S` секунд (по умолчанию 3), чтобы клиент успел переподключиться.
