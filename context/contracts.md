# Контракты API (v1)

Принципы: явные версии (`/v1/`), стабильные контракты, мелкие сообщения на стримах, TLS, разделение signaling / media / ASR. MVP: JSON. Аудио ASR позже можно увести в бинарный фрейм без Base64.

Auth: `Authorization: Bearer <access_token>`. Токены не логировать.

## REST

**POST `/v1/auth/login`**

```json
{ "identifier": "user@example.com", "password": "secret" }
```

```json
{
  "user_id": "u_123",
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "expires_in": 3600
}
```

**GET `/v1/users/me`** → `user_id`, `display_name`, `avatar_url`.

**GET `/v1/contacts`** → `items[]` с `user_id`, `display_name`, `status`.

**POST `/v1/contacts`** → `{ "target_user_id": "u_201" }`.

**GET/POST `/v1/groups`**, **POST `/v1/groups/{group_id}/members`**.

**GET/PATCH `/v1/transcription/settings`**

```json
{ "enabled": true, "store_transcripts": false, "show_speaker_labels": true }
```

**GET `/v1/calls/{call_id}/transcript`** — только если сохранение включено.

## Signaling WebSocket

`wss://…/ws/signaling?token=ACCESS_TOKEN`

Каркас:

```json
{
  "type": "event_name",
  "request_id": "req_123",
  "timestamp": 1710000000,
  "payload": {}
}
```

События MVP:

| type | Направление | payload (суть) |
| --- | --- | --- |
| `room.create` | C→S | `participant_ids[]` |
| `room.created` | S→C | `room_id`, `status` |
| `call.invite` | | `room_id`, `target_user_id` |
| `call.accept` | | `room_id` |
| `call.reject` | | `room_id`, `reason` |
| `webrtc.offer` / `webrtc.answer` | | `room_id`, `from_user_id`, `to_user_id`, `sdp` |
| `webrtc.ice` | | + `candidate` (`candidate`, `sdpMid`, `sdpMLineIndex`) |
| `participant.joined` / `participant.left` | S→C | `room_id`, `user_id` |

Сигнализация **не** носит аудио.

## ASR WebSocket

`wss://…/v1/stream?token=ACCESS_TOKEN`

Аудио: mono, 16 kHz, PCM s16le, короткие чанки. JSON+base64 — ок для MVP.

**`asr.start`**

```json
{
  "type": "asr.start",
  "session_id": "asr_100",
  "payload": {
    "room_id": "room_555",
    "language_mode": "auto",
    "return_partial": true,
    "return_final": true,
    "speaker_labels": true
  }
}
```

**`asr.audio`**

```json
{
  "type": "asr.audio",
  "session_id": "asr_100",
  "payload": {
    "chunk_id": "chunk_001",
    "timestamp": 1710000001,
    "sample_rate": 16000,
    "channels": 1,
    "encoding": "pcm_s16le",
    "audio_base64": "..."
  }
}
```

**`asr.partial` / `asr.final`**

```json
{
  "type": "asr.partial",
  "session_id": "asr_100",
  "payload": {
    "subtitle_id": "sub_101",
    "speaker_id": "u_123",
    "speaker_name": "Ты",
    "text": "Әни, сегодня...",
    "language": "mixed",
    "confidence": 0.81,
    "start_time_ms": 1020,
    "end_time_ms": 1840
  }
}
```

У final те же поля; текст стабилизирован, есть `segment_id` в черновике — клиенту достаточно стабильного `subtitle_id`.

Также: `asr.info` (например `session_started`, `chunk_buffered` с опциональными `chunk_bytes` / `buffered_bytes`, позже `model_loaded`), `asr.error`, `asr.stop`.

Клиент: **один** partial обновляется in-place; final фиксируется в истории текущего звонка.

## Субтитры в клиент

Может приходить как ASR-событие или как `subtitle.update` в комнату:

```json
{
  "type": "subtitle.update",
  "room_id": "room_555",
  "payload": {
    "subtitle_id": "sub_101",
    "speaker_id": "u_123",
    "speaker_name": "Ты",
    "text": "Бүген соңрак кайтам.",
    "status": "partial",
    "language": "mixed",
    "confidence": 0.83,
    "start_time_ms": 1020,
    "end_time_ms": 1840
  }
}
```

`language`: `auto` | `mixed` | `ru` | `tt` | `unknown`. Confidence в UI MVP не обязателен.

## Ошибки

```json
{
  "type": "error",
  "request_id": "req_010",
  "payload": { "code": "INVALID_TOKEN", "message": "..." }
}
```

Коды: `INVALID_TOKEN`, `TOKEN_EXPIRED`, `UNAUTHORIZED`, `ROOM_NOT_FOUND`, `ROOM_FULL`, `USER_OFFLINE`, `ASR_UNAVAILABLE`, `MODEL_BUSY`, `INVALID_AUDIO_FORMAT`, `RATE_LIMITED`, `INTERNAL_ERROR`.

Ошибка субтитров ≠ ошибка звонка. Идемпотентность критичных команд через `request_id` / ids комнаты.

## Правила

1. Клиент не знает структуру модели.
2. ASR не управляет звонком.
3. REST не для live-субтитров.
4. Трассировка: `request_id`, `session_id`, `room_id`, `call_id`.
