# ru-tat-call

Self-hosted семейные видеозвонки с live-субтитрами для смешанной русско-татарской речи.

Рабочий контекст: [`context/`](context/README.md). План шагов: [`context/roadmap.md`](context/roadmap.md).

## Структура

| Путь | Назначение |
| --- | --- |
| `shared/` | Общие контракты (`ru-tat-call-shared`) |
| `services/signaling_server/` | Signaling / REST / комнаты |
| `services/asr_server/` | Потоковый ASR |
| `web_client/` | HTML-стенд для отладки WebRTC |
| `apps/` | Flutter-клиент (позже) |
| `infra/` | Docker и скрипты |
| `tests/` | Интеграционные тесты |

## Разработка

Нужны Python 3.10+ и [uv](https://docs.astral.sh/uv/).

```bash
git clone git@github.com:Dan1kMiniTogi/ru-tat-call.git
cd ru-tat-call
git checkout develop
uv sync --all-packages --group dev
```

Ветка `develop` — повседневная работа. `main` — только стабильный MVP.
