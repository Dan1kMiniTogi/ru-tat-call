# Runtime image for signaling + ASR (same uv workspace).
# Build context: `project/`  (docker compose -f infra/docker-compose.yml)
#
# Example:
#     docker compose -f infra/docker-compose.yml up --build
FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
COPY shared ./shared
COPY services ./services
COPY web_client ./web_client

RUN uv sync --frozen --no-dev --all-packages \
    && mkdir -p /data

EXPOSE 8000

CMD ["uvicorn", "signaling_server.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
