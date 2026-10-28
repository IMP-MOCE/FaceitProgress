# FACEIT Progress API

Backend сервиса аналитики игроков FACEIT в CS2: учебный командный проект, ПР2.
Пользователь отслеживает FACEIT-профили, видит обзор последних матчей с прозрачными формулами
и ставит цель, прогресс по которой сервис честно сравнивает с исходной выборкой.

**Стек:** Python 3.13 · FastAPI · PostgreSQL 16 · SQLAlchemy 2 · Alembic · Pydantic 2 ·
JWT (PyJWT, HS256) · Argon2id · pytest · ruff · mypy · GitHub Actions · Docker

## Быстрый старт

```bash
cp .env.example .env
```

```bash
docker compose up --build -d
```

- API: http://localhost:8000/api/v1/health
- Swagger UI: http://localhost:8000/docs

Без `FACEIT_API_KEY` сервис работает на встроенных демо-профилях: `demo_player`, `patchy_player`,
`newbie_player`, `no_cs2_player`. Ник `source_down` имитирует недоступность FACEIT.

Подробно о запуске, переменных окружения и production — в [docs/deploy.md](docs/deploy.md).

## Что реализовано

| Ресурс | Операции | Требования ПР1 |
|---|---|---|
| Аутентификация | регистрация, вход (JWT), профиль, удаление аккаунта | — |
| Игроки | CRUD + синхронизация с FACEIT | S01, S03 |
| Матчи | история с фильтрами по карте и периоду, пагинация | S03, S04 |
| Статистика | обзор 20 матчей: доля побед, K/D, размер выборки, покрытие истории | S02, S06 |
| Цели | CRUD, одна активная, неизменяемый снимок 20 матчей, проверка прогресса | S11, S12 |

## Документация (состав отчёта)

| Документ | Содержание |
|---|---|
| [docs/api.md](docs/api.md) + [docs/openapi.json](docs/openapi.json) | Спецификация API: ресурсы, коды ответов, формат ошибок |
| [docs/database.md](docs/database.md) | ER-диаграмма, ограничения целостности, индексы |
| [docs/architecture.md](docs/architecture.md) | Схема слоёв, путь запроса, решения, изменения относительно ПР1 |
| [docs/security.md](docs/security.md) | Меры по OWASP Top 10 и тесты, которые их проверяют |
| [docs/testing.md](docs/testing.md) | Уровни тестов, протокол прогона, метрики, конвейер CI |
| [docs/deploy.md](docs/deploy.md) | Инструкция по развёртыванию |
| [docs/demo.md](docs/demo.md) | Демо-сценарий защиты |

## Разработка

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
pre-commit install
```

| Команда | Что делает |
|---|---|
| `docker compose up -d db` | PostgreSQL для разработки и тестов |
| `alembic upgrade head` | Применить миграции |
| `uvicorn app.main:app --reload` | Запуск API |
| `pytest --cov=app` | Тесты с покрытием |
| `ruff check . && ruff format --check . && mypy` | Линтеры и проверка типов, как в CI |
| `python scripts/export_openapi.py` | Обновить `docs/openapi.json` после изменения API |

## Структура

```
app/
  api/v1/        роутеры: auth, players, goals, health
  api/deps.py    JWT → пользователь, проверка владельца
  core/          настройки, безопасность, ошибки, rate limit
  services/      бизнес-логика и формулы (metrics.py)
  repositories/  запросы к БД
  models/        таблицы SQLAlchemy
  schemas/       контракт запросов и ответов
  clients/       FACEIT Data API и демо-данные
alembic/         миграции
tests/           unit, api, contract
docs/            документы для отчёта
.github/         CI: линтеры → тесты → образ
```

## Ограничения

- Сравнение 20/20 матчей и правила рекомендаций A01–A03 (S07–S10) запланированы в R2 по ПР1.
- Названия полей FACEIT Data API нужно сверить с реальными ответами после получения ключа:
  разбор сделан терпимым к отсутствующим полям.
- Остальные ограничения перечислены в [docs/security.md](docs/security.md#известные-ограничения).
