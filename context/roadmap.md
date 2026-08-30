# Детальный итеративный план разработки (Granular Roadmap)

Проект: **ru-tat-call** (Self-Hosted Multilingual Family Video Calls with Real-Time Subtitles)

## Утвержденный технический стек и решения:
- **Архитектура клиента**: Mobile-First Web Application (PWA / HTML5 / WebRTC JS) — zero-install для семьи по прямой ссылке на iPhone (Safari), Android (Chrome) и ПК.
- **Бэкенд**: Python 3.10+ (FastAPI, WebSockets, Pydantic v2, `uv` менеджер пакетов).
- **Хранилище**: SQLite + In-memory (быстрый старт).
- **ML / ASR стратегия**:
  - Локально на ноутбуке: Mock ASR / VAD (Silero) для отладки без нагрузки на CPU.
  - Тестирование реальных моделей: Бесплатный Google Colab / Kaggle с GPU (T4) + туннель (ngrok / cloudflared).
- **Сетевой доступ / HTTPS**: Cloudflare Tunnel / ngrok для защищенного доступа мобильных браузеров к камере и микрофону.

---

## Фаза 0: Окружение, архитектурный каркас и контракты
> **Цель**: Создать скелет монорепозитория, настроить `uv`, зафиксировать Pydantic-контракты (REST, Signaling WS, ASR WS).

- [x] **Шаг 0.1**: Инициализация структуры монорепозитория в `project/` (`services/`, `shared/`, `web_client/`, `infra/`, `tests/`) и настройка `uv` окружения (`project/pyproject.toml`).
- [x] **Шаг 0.2**: Определение общих Pydantic контрактов в `project/shared/` (модели Auth, Signaling Events, WebRTC SDP/ICE, ASR Stream Frames, Subtitle Updates).
- [x] **Шаг 0.3**: Конфигурация запуска (`config.py`, `.env.example`, CORS, порты, пути статики).

---

## Фаза 1: Signaling Server и управление комнатами (FastAPI)
> **Цель**: Работающий сервер сигнализации с поддержкой комнат, авторизации и маршрутизации WebRTC сигналов.

- [x] **Шаг 1.1**: Базовый HTTP API (авторизация по токену/сессии, контакты, настройки) на FastAPI + SQLite.
- [ ] **Шаг 1.2**: WebSocket менеджер комнат (`RoomManager`): подключение, отключение, `room.create`, `call.invite`, `call.accept`, `call.reject`.
- [ ] **Шаг 1.3**: Маршрутизация WebRTC-сигналов (`webrtc.offer`, `webrtc.answer`, `webrtc.ice`) между участниками комнаты (до 4 человек).
- [ ] **Шаг 1.4**: Автоматические pytest тесты сигналинга с эмуляцией нескольких клиентов.

---

## Фаза 2: ASR Streaming Server (Скелет и Mock движок)
> **Цель**: Потоковый ASR-сервер, принимающий PCM аудиочанками и отдающий partial/final субтитры.

- [ ] **Шаг 2.1**: WebSocket endpoint `/v1/stream` для ASR: прием `asr.start`, `asr.audio` (PCM 16kHz s16le), буферизация.
- [ ] **Шаг 2.2**: Mock-движок распознавания (генерация тестовых partial/final субтитров) и рассылка `subtitle.update`.
- [ ] **Шаг 2.3**: Интеграция VAD (Voice Activity Detection через Silero VAD на CPU) для фильтрации тишины.
- [ ] **Шаг 2.4**: Абстрактный интерфейс `ASREngine` (готовый к подключению Colab GPU туннеля или локального ONNX).

---

## Фаза 3: Mobile-First Web-клиент (WebRTC + Live Subtitles)
> **Цель**: Готовый браузерный интерфейс для звонков на мобильных устройствах и ПК с оверлеем субтитров.

- [ ] **Шаг 3.1**: Адаптивный UI: экран входа/выбора имени, комната звонка, сетка видео (2x2 до 4 окон), кнопки микрофона/камеры.
- [ ] **Шаг 3.2**: WebRTC медиа-пайплайн: захват камеры/микрофона, установка P2P Mesh соединений через signaling WebSocket.
- [ ] **Шаг 3.3**: Аудио-пайплайн в браузере: Web Audio API (AudioWorklet/ScriptProcessor) даунсемплинг в 16 kHz PCM и отправка на ASR WebSocket.
- [ ] **Шаг 3.4**: Виджет живых субтитров (in-place обновление partial, фиксация final, цветные бейджи участников, плавная автопрокрутка).
- [ ] **Шаг 3.5**: Сквозное тестирование звонка между двумя вкладками/устройствами с генерацией mock-субтитров.

---

## Фаза 4: Подключение реального ASR (Татарский + Русский + Mixed)
> **Цель**: Распознавание реальной речи через Colab GPU туннель или локальный легковесный инференс.

- [ ] **Шаг 4.1**: Готовый Jupyter/Colab ноутбук для поднятия ASR-воркера с GPU (HuggingFace чекпоинты `wav2vec2-xlsr-tatar` / `whisper`) и туннелем ngrok/cloudflared.
- [ ] **Шаг 4.2**: Коннектор `RemoteColabASREngine` в бэкенде к туннелю Colab.
- [ ] **Шаг 4.3**: Тестирование и бенчмарк задержки на реальных смешанных фразах (RU / TT / code-switching).
- [ ] **Шаг 4.4**: Постобработка текста (склейка сегментов, пунктуация, подавление дубликатов).

---

## Фаза 5: Стабилизация, HTTPS туннель и Docker-деплой
> **Цель**: Устойчивость к обрывам сети, запуск в мобильных браузерах по HTTPS и контейнеризация.

- [ ] **Шаг 5.1**: Логика реконнекта (WebSocket backoff, WebRTC ICE restart, ASR fallback без обрыва звонка).
- [ ] **Шаг 5.2**: Настройка Cloudflare Tunnel / ngrok для публичного HTTPS доступа с iPhone Safari и Android Chrome.
- [ ] **Шаг 5.3**: Dockerfile и `docker-compose.yml` для единого запуска бэкенда.
- [ ] **Шаг 5.4**: Финальное нагрузочное тестирование и чеклист готовности MVP.
