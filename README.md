# Dara Qyzmet — цифровая приёмка накладных (MVP по ТЗ)

SaaS-бэкенд на **FastAPI + PostgreSQL** с распознаванием накладных через **VLM Qwen2.5-VL (vLLM)**.
Реализует ТЗ: заявки и их статусы, загрузку/распознавание накладной, редактирование до подтверждения,
расхождения (недостача/излишек/пересорт/брак) с **автопересчётом суммы**, акт расхождений,
роль поставщика, агента поддержки и распознавание товара по штрихкоду/фото.

## Запуск

Нужен **NVIDIA GPU + nvidia-container-toolkit**: распознавание накладных и агент работают
через реальную модель Qwen2.5-VL (vLLM). Сначала поднимите vLLM, затем приложение:

```bash
bash run_vllm.sh                 # отдельный терминал; ждём загрузки весов (долго при первом старте)
docker compose up --build        # db + qdrant + api + web
```

- **Фронтенд (React):**  http://localhost:3000
- API/Swagger:  http://localhost:8080/docs
- Демо-логины: `store@dara.kz` (магазин) и `dist@dara.kz` (поставщик), пароль `demo12345`.

При старте БД создаётся автоматически и наполняется демо-данными (магазин «Береке»,
поставщик «Молпром», каталог, одна заявка в статусе «отгружен» — готова к приёмке).
Параметры подключения к vLLM — в `.env` (см. `.env.example`); по умолчанию api ходит к
`host.docker.internal:8000/v1`, куда `run_vllm.sh` поднимает модель.

## Демо-сценарий
1. Войдите как магазин → «Заявки» → у заявки «Отгружен» нажмите **Принять**.
2. Загрузите фото/PDF накладной и нажмите **Распознать** (Qwen2.5-VL извлечёт позиции).
3. Проверьте/поправьте позиции — проверка подсветит подозрительные строки, суммы пересчитываются.
4. Добавьте расхождение (недостача/пересорт), измените факт → **К оплате** пересчитывается вживую.
5. **Сформировать акт** или **Подтвердить приёмку** (товары уйдут в сток).
6. Войдите как поставщик → «Акты расхождений» → **Скорректировать счёт**.
7. Кнопка 🤖 справа внизу — агент: «сколько молока на складе?», «какие расхождения?».

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
