# ru-tat-call

Self-hosted семейные видеозвонки с live-субтитрами для смешанной русско-татарской речи.

- Контекст и план для агента: [`context/`](context/README.md), [`context/roadmap.md`](context/roadmap.md)
- Код: [`project/`](project/README.md)

## Структура репозитория

| Путь | Назначение |
| --- | --- |
| `context/` | ТЗ, архитектура, roadmap |
| `project/` | Вся реализация (uv workspace) |
| `.cursor/rules/` | Правила для агента |

Внутри `project/`: `shared/`, `services/`, `web_client/`, `apps/`, `infra/`, `tests/`.

## Разработка

Нужны Python 3.10+ и [uv](https://docs.astral.sh/uv/).

```bash
git clone git@github.com:Dan1kMiniTogi/ru-tat-call.git
cd ru-tat-call
git checkout develop
cd project
uv sync --all-packages --group dev
cp .env.example .env
uv run uvicorn signaling_server.app:app --host 0.0.0.0 --port 8000
```

Ветка `develop` — повседневная работа. `main` — только стабильный MVP.
