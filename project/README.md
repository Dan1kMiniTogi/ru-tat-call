# project

Корень реализации. Workspace `uv` живёт здесь; из корня репозитория запускать `uv sync` не нужно.

```bash
cd project
uv sync --all-packages --group dev
cp .env.example .env   # при необходимости поправь порты и CORS
```
