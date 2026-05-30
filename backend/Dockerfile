# syntax=docker/dockerfile:1
FROM python:3.12-slim

# uv из официального образа astral (как в исходном репозитории)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Системное: драйверы Postgres + pg_isready для ожидания БД
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Сначала манифесты — слой с зависимостями кэшируется.
# uv.lock необязателен: если его нет, uv создаст его при сборке (нужна сеть).
# Для воспроизводимости закоммитьте lock: `cd backend && uv lock`.
COPY pyproject.toml README.md uv.lock* ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --no-install-project

# Затем код
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev

# venv в PATH -> entrypoint вызывает uvicorn напрямую
ENV PATH="/app/.venv/bin:$PATH"

RUN chmod +x entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["bash", "entrypoint.sh"]
