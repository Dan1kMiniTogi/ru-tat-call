# infra

Туннель HTTPS (шаг 5.2) и позже Docker (шаг 5.3).

Мобильные браузеры отдают камеру и микрофон только на **HTTPS** (исключение — `localhost`). Один туннель на порт **8000** достаточно: UI, signaling WS и ASR WS идут с того же origin (`/v1/asr-stream` проксируется на ASR `:8001`).

## Cloudflare quick tunnel (без аккаунта)

В трёх терминалах из `project/`:

```bash
uv run uvicorn signaling_server.app:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'
uv run uvicorn asr_server.app:app --host 0.0.0.0 --port 8001
./infra/tunnel.sh
```

В логе cloudflared появится `https://….trycloudflare.com`. Эту ссылку открывают на iPhone Safari / Android Chrome. CORS менять не нужно (тот же origin).

`cloudflared`: [установка](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/).

Именной туннель со своим доменом: `cloudflared.yml.example`.

## ngrok (нужен аккаунт)

```bash
ngrok http 8000
```

Токен клади в локальный конфиг ngrok, не в git и не в чат. Постоянный URL: замените origin в семейном чате, когда ngrok его сменит (бесплатный план).
