#!/usr/bin/env bash
set -e
echo "==> Ожидание PostgreSQL (${POSTGRES_HOST:-db})..."
until pg_isready -h "${POSTGRES_HOST:-db}" -p "${POSTGRES_PORT:-5432}" >/dev/null 2>&1; do
  sleep 1
done
echo "==> PostgreSQL готов. Запуск API."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
