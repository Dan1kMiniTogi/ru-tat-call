# web_client

Mobile-first SPA: вход, контакты, комната 2×2, WebRTC, PCM на ASR, живые субтитры (фаза 3).
Открывается с signaling: `http://127.0.0.1:8000/`. ASR: порт 8001 (URL из `GET /v1/client-config`). Fan-out: `SIGNALING_INTERNAL_URL` → `subtitle.update` в комнату.

Демо (пароль `family`): `you`, `mama`, `sister`.

Автотест двух «вкладок»: `uv run pytest tests/test_e2e_call_subtitles.py`.

В браузере (по желанию): оба сервера → две вкладки, разные логины → звонок → лента mock-субтитров. Если ASR не запущен, звонок жив. HTTPS нужен для камеры на телефоне (фаза 5).
