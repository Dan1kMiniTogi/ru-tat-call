# signaling_server

Signaling HTTP API (FastAPI + SQLite). WebSocket комнат — шаги 1.2–1.3.

```bash
cd project
cp -n .env.example .env
uv sync --all-packages --group dev
uv run uvicorn signaling_server.app:app --host 0.0.0.0 --port 8000
```

WebSocket: `ws://127.0.0.1:8000/ws/signaling?token=ACCESS_TOKEN`  
События: `room.create`, `call.invite`, `call.accept`, `call.reject`, `webrtc.offer` / `answer` / `ice`.
