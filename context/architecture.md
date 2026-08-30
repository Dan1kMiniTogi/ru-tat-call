# Архитектура

## Почему Mobile-First Web-приложение (PWA)

Для семейного использования критичен нулевой порог входа:
- На iOS (iPhone) установка сторонних приложений без App Store ограничена сертификатом на 7 дней либо платным аккаунтом Apple Developer ($99/год) + TestFlight.
- В современных мобильных браузерах (Safari iOS 14.3+, Chrome Android) есть полноценный **WebRTC** (`RTCPeerConnection`, `getUserMedia`) и **Web Audio API** (захват 16 kHz PCM для ASR).
- Ссылка на комнату кидается в семейный чат Telegram/WhatsApp, пользователь открывает ссылку и сразу попадает в защищенный звонок с живыми субтитрами.
- При желании веб-клиент сохраняется на главный экран смартфона как PWA (без адресной строки).

## Компоненты системы

| Компонент | Делает | Не делает |
| --- | --- | --- |
| **Mobile-First Web Client** | UI звонка (сетка до 4 видео), захват камеры/микрофона, даунсемплинг в 16kHz PCM, оверлей субтитров | ASR инференс |
| **Signaling Server (FastAPI)** | Аутентификация, список контактов, комнаты звонков, обмен SDP offer/answer и ICE | Передача тяжелого видео |
| **WebRTC Media Layer** | Прямой P2P обмен аудио/видео между браузерами с минимальной задержкой | Распознавание речи |
| **ASR Server (FastAPI / WS)** | Прием PCM чанков по WebSocket, VAD, инференс (Mock / Colab GPU / ONNX), выдача partial/final субтитров | Управление звонком |

## Потоки данных

```
Браузер A (iPhone Safari) ─────── WebRTC P2P Media (A/V) ─────── Браузер B (Android Chrome)
       │                                                                 │
       ├─── WebSocket Signaling (SDP, ICE, Room State) ──────────────────┤
       │                                                                 │
       └─── WebSocket ASR Stream (16kHz PCM chunks) ─────────────────────┤
                     ↓                                                   ↓
                ASR Server (VAD + Model Inference)
                     ↓
             subtitle.update → signaling POST /v1/internal/subtitles → комнаты
```

## Стек технологий

- **Фронтенд**: HTML5, Modern Vanilla JS / Web Components, WebRTC API, Web Audio API, CSS Flex/Grid (Touch-optimized для мобильных).
- **Бэкенд**: Python 3.10+ (FastAPI, WebSockets, Pydantic v2, `uv` менеджер пакетов).
- **Хранилище**: SQLite + In-memory.
- **ASR инференс**:
  - Локально при разработке: Mock ASR + Silero VAD (нагрузка на CPU < 2%).
  - Реальные модели: Бесплатный Google Colab / Kaggle (GPU T4) + туннель (`ngrok` / `cloudflared`) к бэкенду.
- **Сетевой доступ и HTTPS**: Cloudflare Tunnel / ngrok (дает валидный HTTPS сертификат, необходимый для доступа мобильных браузеров к камере и микрофону).

## Структура репозитория

```
repo-root/
  context/                 # ТЗ, архитектура и roadmap для агента
  project/                 # вся реализация (uv workspace)
    services/
      signaling_server/    # FastAPI + WebSockets + Web static
      asr_server/          # Streaming ASR + VAD + Model Connectors
    shared/                # Общие Pydantic v2 контракты (ru-tat-call-shared)
    web_client/            # Mobile-first Web UI (HTML5, JS, CSS, PWA)
    infra/                 # Docker, nginx, скрипты туннелей
    tests/                 # Интеграционные тесты
```

## Отказоустойчивость

Субтитры работают изолированно от медиапотока звонка. При сбое или перегрузке ASR-сервера WebRTC-видеосвязь между участниками **не прерывается**, а на экране появляется мягкий индикатор временной недоступности распознавания.
