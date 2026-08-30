# signaling_server

Signaling HTTP API (FastAPI + SQLite). WebSocket комнат — шаги 1.2–1.3.

```bash
cd project
cp -n .env.example .env
uv sync --all-packages --group dev
uv run uvicorn signaling_server.app:app --host 0.0.0.0 --port 8000
```

Демо: логин `you` / `mama` / `sister`, пароль `family`. Docs: http://127.0.0.1:8000/docs
