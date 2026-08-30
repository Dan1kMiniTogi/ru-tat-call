# web_client

Mobile-first SPA: вход, контакты, комната 2×2, WebRTC, PCM на ASR, живые субтитры (фаза 3).
Открывается с signaling: `http://127.0.0.1:8000/`. ASR: тот же origin, `GET /v1/client-config` → `/v1/asr-stream` (прокси на порт 8001). Fan-out: `SIGNALING_INTERNAL_URL` → `subtitle.update` в комнату.

При обрыве signaling/ASR сокета клиент переподключается с backoff (до 15 с) и делает ICE restart; PCM и WebRTC peers не сбрасываются. Hangup (`Сброс`) — намеренное завершение.

Демо (пароль `family`): `you`, `mama`, `sister`.

Автотест двух «вкладок»: `uv run pytest tests/test_e2e_call_subtitles.py`.

В браузере (по желанию): оба сервера или `docker compose -f infra/docker-compose.yml up --build` → две вкладки, разные логины → звонок. Если ASR не запущен, звонок жив. Камера на телефоне: HTTPS через `./infra/tunnel.sh` (см. `project/infra/README.md`).
