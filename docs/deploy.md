# Инструкция по развёртыванию

## Требования

- Docker Desktop 4.x (или Docker Engine + Compose v2)
- Для разработки без контейнера API: Python 3.12+ и запущенный PostgreSQL 16

## Вариант 1. Всё в Docker (демонстрация, защита)

```bash
cp .env.example .env
```

В `.env` задайте `JWT_SECRET`, например сгенерированный командой:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Запуск:

```bash
docker compose up --build -d
```

Контейнер `api` при старте применяет миграции (`alembic upgrade head`) и запускает uvicorn на порту 8000.

Проверка:

```bash
curl http://localhost:8000/api/v1/health
```

Ответ: `{"status":"ok"}`. Swagger UI: http://localhost:8000/docs

Демонстрационный аккаунт с готовым примером прогресса цели:

```bash
docker compose exec api python -m app.seed_demo
```

Остановка (данные БД сохраняются в томе `pgdata`):

```bash
docker compose down
```

Полный сброс вместе с данными:

```bash
docker compose down -v
```

## Вариант 2. Локальная разработка

```bash
docker compose up -d db
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

На Linux/macOS venv активируется командой `source .venv/bin/activate`.

## Переменные окружения

| Переменная | Обязательна | По умолчанию | Назначение |
|---|---|---|---|
| `JWT_SECRET` | да | - | Секрет подписи JWT, не короче 32 символов |
| `DATABASE_URL` | нет | `postgresql+psycopg://faceit:faceit@localhost:15432/faceit` | Подключение к PostgreSQL |
| `JWT_TTL_MINUTES` | нет | 30 | Срок жизни токена |
| `CORS_ORIGINS` | нет | `["http://localhost:5173"]` | Разрешённые origin frontend (JSON-список) |
| `FACEIT_API_KEY` | нет | пусто | Ключ FACEIT Data API; без него работают демо-данные |
| `LOGIN_RATE_LIMIT` | нет | 5 | Попыток входа в минуту на IP + email |
| `DOCS_ENABLED` | нет | true | Swagger UI и `/openapi.json` |
| `APP_ENV` | нет | development | `development` / `test` / `production` |

## Образ из CI

После слияния в `main` workflow публикует образ в GitHub Container Registry:

```
ghcr.io/<владелец>/<репозиторий>:latest
ghcr.io/<владелец>/<репозиторий>:sha-<коммит>
```

Запуск на сервере с внешней БД:

```bash
docker run -d -p 8000:8000 -e JWT_SECRET=... -e DATABASE_URL=postgresql+psycopg://user:pass@host:5432/db -e DOCS_ENABLED=false ghcr.io/<владелец>/<репозиторий>:latest
```

## Рекомендации для production

- Отдельный длинный `JWT_SECRET`, хранящийся в секретах окружения, а не в файле.
- `DOCS_ENABLED=false`, `APP_ENV=production`.
- TLS на обратном прокси (nginx, Caddy) перед сервисом.
- Свой пароль БД вместо `faceit/faceit` из docker-compose.
- Откат: запустить образ предыдущего тега `sha-…`. Если откатывается схема - `alembic downgrade -1`.
