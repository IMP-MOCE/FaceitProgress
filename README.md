# FACEIT Progress

Сервис аналитики игроков FACEIT в CS2: учебный командный проект, ПР2.
Пользователь отслеживает FACEIT-профили, видит обзор последних матчей с прозрачными формулами,
сравнивает выборки, получает объяснимые рекомендации и ставит цель, прогресс по которой сервис
честно сравнивает с исходной выборкой.

**Стек:** Python 3.13 · FastAPI · PostgreSQL 16 · SQLAlchemy 2 · Alembic · Pydantic 2 ·
JWT (PyJWT, HS256) · Argon2id · веб-интерфейс на ES-модулях без сборки · pytest · Playwright ·
ruff · mypy · ESLint · Prettier · GitHub Actions · Docker

## Быстрый старт

```bash
cp .env.example .env
```

```bash
docker compose up --build -d
```

- Веб-интерфейс: http://localhost:8000/
- API: http://localhost:8000/api/v1/health
- Swagger UI: http://localhost:8000/docs

Без `FACEIT_API_KEY` сервис работает на встроенных демо-профилях: `demo_player`, `patchy_player`,
`newbie_player`, `no_cs2_player`. Ник `source_down` имитирует недоступность FACEIT.

Демо-аккаунт с готовым примером прогресса цели: `docker compose exec api python -m app.seed_demo`.
Подробно о запуске, переменных окружения и production - в [docs/deploy.md](docs/deploy.md).

## Что реализовано

| Ресурс | Операции | Требования ПР1 |
|---|---|---|
| Аутентификация | регистрация, вход (JWT), выход с отзывом токена, профиль, удаление аккаунта | - |
| Игроки | CRUD + синхронизация с FACEIT | S01, S03 |
| Матчи | история с фильтрами по карте и периоду, пагинация | S03, S04 |
| Статистика | обзор 20 матчей: доля побед, K/D, размер выборки, покрытие истории | S02, S06 |
| Сравнение | последние 20 матчей против предыдущих 20, без пересечения | S07 |
| Карты | результаты по картам с порогом 10 матчей | S08 |
| Сводка | правила A01–A03: наблюдение, ограничение, действие, исходные матчи | S09, S10 |
| Цели | CRUD, одна активная, неизменяемый снимок 20 матчей, проверка прогресса | S11, S12 |
| Интерфейс | все сценарии выше на телефоне, планшете и компьютере; загрузка, ошибки, пустые данные | S05, NFR01, NFR03, NFR06 |

## Документация (состав отчёта)

| Документ | Содержание |
|---|---|
| [docs/api.md](docs/api.md) + [docs/openapi.json](docs/openapi.json) | Спецификация API: ресурсы, коды ответов, формат ошибок, правила A01–A03 |
| [docs/database.md](docs/database.md) | ER-диаграмма, ограничения целостности, индексы |
| [docs/architecture.md](docs/architecture.md) | Схема слоёв (интерфейс → API → сервисы → БД), путь запроса, решения |
| [docs/security.md](docs/security.md) | Меры по OWASP Top 10 и тесты, которые их проверяют |
| [docs/testing.md](docs/testing.md) | Уровни тестов, протокол прогона, метрики, конвейер CI |
| [docs/deploy.md](docs/deploy.md) | Инструкция по развёртыванию |
| [docs/demo.md](docs/demo.md) | Демо-сценарий защиты |

## Разработка

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev,e2e]"
python -m playwright install chromium
pre-commit install
npm install
```

| Команда | Что делает |
|---|---|
| `docker compose up -d db` | PostgreSQL для разработки и тестов |
| `alembic upgrade head` | Применить миграции |
| `uvicorn app.main:app --reload` | Запуск API и интерфейса на http://localhost:8000 |
| `pytest --cov=app` | Unit, API и контрактные тесты с покрытием |
| `pytest -m e2e tests/e2e` | Сквозные тесты интерфейса в Chromium |
| `ruff check . && ruff format --check . && mypy` | Линтеры и проверка типов backend, как в CI |
| `npm run lint` | ESLint и Prettier для интерфейса |
| `python scripts/export_openapi.py` | Обновить `docs/openapi.json` после изменения API |
| `python scripts/collect_reports.py` | Все проверки разом → `reports/summary.md`, скриншоты |
| `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` | То же на Windows с нуля: БД, venv, зависимости, Chromium, проверки |
| `python scripts/load_test.py` | Нагрузочная проверка NFR02 на запущенном сервисе |

## Структура

```
app/
  api/v1/        роутеры: auth, players, goals, health
  api/deps.py    JWT → пользователь, отзыв токена, проверка владельца
  core/          настройки, безопасность, ошибки, rate limit
  services/      бизнес-логика: формулы (metrics), правила A01–A03 (rules), аналитика
  repositories/  запросы к БД
  models/        таблицы SQLAlchemy
  schemas/       контракт запросов и ответов
  clients/       FACEIT Data API и демо-данные
frontend/        веб-интерфейс: index.html, css/, js/ (views, api, ui)
alembic/         миграции
tests/           unit, api, contract, e2e
scripts/         выгрузка OpenAPI, нагрузочный тест, сбор отчёта
docs/            документы для отчёта
.github/         CI: линтеры → тесты и e2e → образ
```

## Ограничения

- Названия полей FACEIT Data API нужно сверить с реальными ответами после получения ключа:
  разбор сделан терпимым к отсутствующим полям.
- Анализ демо (R4) по плану ПР1 не входит в семестровую версию.
- Остальные ограничения перечислены в [docs/security.md](docs/security.md#известные-ограничения).
