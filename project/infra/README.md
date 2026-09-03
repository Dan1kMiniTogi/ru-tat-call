# infra

Docker (шаг 5.3) и HTTPS-туннель (шаг 5.2).

## Docker — один запуск бэкенда

Нужен Docker Compose v2. Из `project/`:

```bash
docker compose -f infra/docker-compose.yml up --build
```

UI: `http://127.0.0.1:8000/` (демо `you` / `mama` / `sister`, пароль `family`).

Два контейнера из одного образа: **signaling** (порт 8000, статика + прокси ASR) и **asr** (только внутренняя сеть). SQLite — том `sqlite-data`. В compose уже стоят `ASR_UPSTREAM_WS_URL=ws://asr:8001/v1/stream` и `SIGNALING_INTERNAL_URL=http://signaling:8000` — не копируй `127.0.0.1` из локального `.env` в эти два ключа.

Свой `SECRET_KEY`:

```bash
docker compose --env-file .env -f infra/docker-compose.yml up --build
```

Остановка: `docker compose -f infra/docker-compose.yml down`. Том с БД: `down -v`.

## Cloudflare quick tunnel (без аккаунта)

Сначала подними backend (Docker или uvicorn). Туннель смотрит на **8000**:

```bash
./infra/tunnel.sh
```

Либо без Docker, три терминала:

```bash
uv run uvicorn signaling_server.app:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'
uv run uvicorn asr_server.app:app --host 0.0.0.0 --port 8001
./infra/tunnel.sh
```

В логе cloudflared: `https://….trycloudflare.com` — эту ссылку открывают на iPhone Safari / Android Chrome. CORS менять не нужно.

`cloudflared`: [установка](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/). Именной туннель: `cloudflared.yml.example`.

## ngrok (нужен аккаунт)

```bash
ngrok http 8000
```

Токен — в локальный конфиг ngrok, не в git и не в чат.
