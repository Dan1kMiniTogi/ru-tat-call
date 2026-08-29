# Архитектура

## Почему своё приложение

ОС телефона почти не даёт стабильно перехватывать аудио чужого звонка и рисовать оверлей субтитров поверх WhatsApp/Telegram. Поэтому продукт **сам** владеет звонком: UI, медиа, субтитры.

## Компоненты

| Компонент | Делает | Не делает |
| --- | --- | --- |
| **Flutter-клиент** | Логин, контакты, UI звонка (до 4 плиток), субтитры, разрешения, форвард аудио в ASR | ASR, анализ модели |
| **Signaling** | Presence, invite/accept/reject, SDP, ICE, комнаты | Медиа, распознавание |
| **Media (WebRTC)** | Низколатентные A/V. Для малых групп — P2P; SFU/инфра — позже, если понадобится | Текст субтитров |
| **ASR server** | Чанки аудио → partial/final текст (+ timestamps, language, speaker_id если есть) | UI, аккаунты, управление звонком |
| **User directory** | Identity, контакты, membership группы, метаданные комнаты, опционально настройки транскриптов | Соцсеть |

Ключ: **клиент не привязан к модели и к конкретной машине.** ASR API стабильный; железо можно менять.

## Потоки

Медиа и субтитры **разведены**:

```
Клиенты ── WebRTC media ── друг другу
   │
   └── signaling (WebSocket)
   └── ASR stream (WebSocket в MVP; gRPC позже если нужно)
           → partial/final → subtitle.update → UI
```

Атрибуция говорящего в MVP: **по источнику аудиопотока**, не acoustic diarization.

Язык: одна multilingual-модель предпочтительнее двух моделей + LID. Клиент не хардкодит язык. Режимы API: `auto` / `mixed` / `ru` / `tt`.

## Стек (baseline MVP)

- Клиент: **Flutter** + native plugins только там, где нужны WebRTC/аудио.
- Signaling: лёгкий backend, **WebSocket**; REST — auth и метаданные.
- ASR: streaming, local, **model-agnostic HTTP/WS API**.
- Деплой: **Docker** (signaling и ASR раздельно), опционально reverse proxy + TLS.

Конкретный язык backend в Notion не зафиксирован — выбрать при этапе 1.

## Слои клиента

Presentation (login, contacts, call, subtitle overlay, settings) → state (session, call, participants, subtitles, connection) → communication (signaling, WebRTC wrapper, ASR consumer) → domain models → infrastructure (REST, WS, permissions, logging).

Экраны MVP: вход, контакты, исходящий/входящий звонок, активный звонок, настройки, ошибка/reconnect. Во время звонка на первом плане только видео и субтитры.

Состояния звонка: `idle`, `incoming_call`, `outgoing_call`, `connecting`, `connected`, `reconnecting`, `asr_disconnected`, `ended`, `error`.

Состояния субтитров: empty, receiving partial, received final, delayed, interrupted, unavailable — **отдельно** от состояния звонка.

## Репозиторий (целевая структура)

```
project-root/
  apps/mobile_client/
  services/signaling_server/
  services/asr_server/
  services/user_directory/
  shared/contracts/
  shared/models/
  infra/docker/
  infra/nginx/
  infra/scripts/
  context/          # этот рабочий контекст (не путать с исходными Notion-черновиками)
```

Сейчас в репо только заготовка имени проекта и эта папка `context/`. Код ещё не начат.

## Производительность и деградация

Субтитры не должны заметно портить звонок. При нехватке ресурсов режется ASR, не медиа. Reconnect signaling/ASR с экспоненциальной паузой; при потере ASR UI звонка остаётся.

## Расширения без переписывания клиента

Новые языки и модели, хранение транскриптов, перевод, поиск по истории, персонализация голоса, cloud-деплой, админка. Не тащить это в MVP.
