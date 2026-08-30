# web_client

Mobile-first SPA: вход, контакты, комната 2×2, WebRTC, PCM на ASR, живые субтитры (шаг 3.4).
Открывается с signaling: `http://127.0.0.1:8000/`. ASR: порт 8001 (URL из `GET /v1/client-config`). Нужен fan-out: ASR `SIGNALING_INTERNAL_URL` → `subtitle.update` в комнату (плюс локальные `asr.partial`/`asr.final`).

Демо (пароль `family`): `you`, `mama`, `sister`.

Проверка: две вкладки, звонок; при работающем ASR под сеткой появляется лента субтитров (partial курсивом, final обычным, цветной бейдж говорящего). Если ASR не запущен, звонок жив. HTTPS нужен для камеры на телефоне (фаза 5).
