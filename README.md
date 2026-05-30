# Dara Kyzmet — цифровая приёмка накладных (MVP по ТЗ)

SaaS-бэкенд на **FastAPI + PostgreSQL** с распознаванием накладных через **VLM Qwen2.5-VL (vLLM)**.
Реализует ТЗ: заявки и их статусы, загрузку/распознавание накладной, редактирование до подтверждения,
расхождения (недостача/излишек/пересорт/брак) с **автопересчётом суммы**, акт расхождений,
роль поставщика, агента поддержки и распознавание товара по штрихкоду/фото.

## Запуск одной командой (без GPU, mock-режим VLM)

```bash
docker compose up --build
```

- **Фронтенд (React):**  http://localhost:3000
- API/Swagger:  http://localhost:8080/docs
- Демо-логины: `store@dara.kz` (магазин) и `dist@dara.kz` (поставщик), пароль `demo12345`.

При старте БД создаётся автоматически и наполняется демо-данными (магазин «Береке»,
поставщик «Молпром», каталог, одна заявка в статусе «отгружен» — готова к приёмке).

## Демо-сценарий
1. Войдите как магазин → «Заявки» → у заявки «Отгружен» нажмите **Принять**.
2. **Распознать** (в mock-режиме файл не важен — вернётся типовая накладная).
3. Проверьте/поправьте позиции (поля низкой уверенности подсвечены) — суммы пересчитываются.
4. Добавьте расхождение (недостача/пересорт), измените факт → **К оплате** пересчитывается вживую.
5. **Сформировать акт** или **Подтвердить приёмку** (товары уйдут в сток).
6. Войдите как поставщик → «Акты расхождений» → **Скорректировать счёт**.
7. Кнопка 🤖 справа внизу — агент: «сколько молока на складе?», «какие расхождения?».

## Реальный инференс Qwen2.5-VL (нужен NVIDIA GPU + nvidia-container-toolkit)

```bash
MOCK_VLM=false docker compose --profile gpu up --build
```

Поднимется сервис `vllm` (скачает веса Qwen2.5-VL при первом старте — долго),
приложение направит распознавание на него (OpenAI-совместимый `/v1/chat/completions`,
guided JSON). Параметры — в `.env` (см. `.env.example`).

## Структура
```
backend/                 FastAPI + PostgreSQL + VLM
  app/
    main.py              точка входа (create_all + seed + роутеры)
    config.py db.py      конфиг и подключение к Postgres
    models.py            модель данных (ТЗ 5)
    schemas.py           Pydantic-схемы
    security.py deps.py  JWT, хеширование, RBAC + изоляция тенантов
    services/recalc.py   автопересчёт сумм при расхождениях (ТЗ 5.3)
    vlm/                 распознавание: pdf, клиент vLLM, валидация (БИН, сходимость)
    routers/             auth, orders, invoices, acceptance, supplier, products, agent
  Dockerfile entrypoint.sh pyproject.toml (uv)
frontend/                React (Vite) — фронтенд в стиле Halyk
  src/
    App.jsx              роутинг по роли
    Login.jsx Orders.jsx Acceptance.jsx Supplier.jsx AgentWidget.jsx
    api.js styles.css
  Dockerfile nginx.conf  (сборка React -> nginx, проксирование /api на бэкенд)
docker-compose.yml  .env.example
```

## Локальная разработка фронта (без Docker)
```bash
cd frontend && npm install && npm run dev   # http://localhost:5173, /api проксируется на :8080
```

## Стек
FastAPI · SQLAlchemy 2 · PostgreSQL 16 · PyMuPDF/Pillow · httpx · vLLM (Qwen2.5-VL) · JWT.
Распознавание и нормализация PDF переиспользуют паттерны исходного репозитория Dara-Vision.
