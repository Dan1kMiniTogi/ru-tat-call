# project

Корень реализации. Workspace `uv` живёт здесь; из корня репозитория запускать `uv sync` не нужно.

```bash
cd project
uv sync --all-packages --group dev
cp .env.example .env   # при необходимости поправь порты и CORS
uv run uvicorn signaling_server.app:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'
uv run uvicorn asr_server.app:app --host 0.0.0.0 --port 8001
# UI: http://127.0.0.1:8000/  (ASR: same origin /v1/asr-stream)
# Phone HTTPS: ./infra/tunnel.sh   →  https://….trycloudflare.com
```
