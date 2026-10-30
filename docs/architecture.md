# Архитектура FACEIT Progress

## Слои

```mermaid
flowchart TB
    subgraph ui["Веб-интерфейс - frontend/ (ES-модули, без сборки)"]
        views["views<br/>auth · players · player · goals · account"]
        uikit["ui.js · dom.js · format.js<br/>состояния: загрузка, ошибка, пусто"]
        apijs["api.js<br/>JWT, problem+json → ApiError,<br/>тайм-аут 30 с"]
    end
    client["Swagger UI / curl"]

    subgraph api["API - app/api"]
        routers["Роутеры v1<br/>auth · players · goals · health"]
        deps["Зависимости<br/>JWT → текущий пользователь<br/>проверка владельца"]
    end

    subgraph core["Ядро - app/core"]
        security["security<br/>Argon2id, JWT HS256"]
        errors["errors<br/>problem+json (RFC 9457)"]
        limiter["rate_limit<br/>попытки входа"]
        config["config<br/>переменные окружения"]
    end

    subgraph services["Сервисы - app/services"]
        auth_s["auth"]
        players_s["players<br/>поиск, синхронизация,<br/>покрытие истории"]
        stats_s["stats<br/>обзор 20 матчей"]
        analytics_s["analytics<br/>сравнение, карты, сводка"]
        rules_s["rules<br/>A01–A03, группы 20/20"]
        goals_s["goals<br/>снимки, прогресс"]
        metrics_s["metrics<br/>формулы ПР1"]
    end

    subgraph repos["Репозитории - app/repositories"]
        repo["users · players · matches · goals · tokens<br/>SQLAlchemy 2, фильтр по владельцу"]
    end

    subgraph clients["Внешние источники - app/clients"]
        faceit["HttpFaceitClient<br/>FACEIT Data API v4"]
        fixtures["FixtureFaceitClient<br/>демо-данные"]
    end

    db[("PostgreSQL 16<br/>миграции Alembic")]
    faceit_api(["open.faceit.com"])

    views --> uikit
    views --> apijs
    apijs -->|"fetch /api/v1, Bearer JWT"| routers
    client -->|"HTTPS, Bearer JWT"| routers
    routers --> deps
    deps --> security
    routers --> services
    stats_s --> metrics_s
    goals_s --> metrics_s
    analytics_s --> rules_s
    rules_s --> metrics_s
    services --> repos
    players_s --> clients
    repos --> db
    faceit --> faceit_api
```

Каждый слой обращается только к слою ниже. Роутеры не работают с БД напрямую:
они проверяют входные данные (Pydantic), вызывают сервис и преобразуют результат в схему ответа.
Интерфейс ничего не считает сам: все показатели, пороги и тексты выводов приходят из API,
поэтому обзор, сравнение и цель используют одни и те же формулы (NFR08).

| Слой | Каталог | Ответственность |
|---|---|---|
| Интерфейс | `frontend/` | Экраны, маршрутизация по hash, состояния загрузки/ошибки/пусто, адаптив 360–1440 px |
| API | `app/api` | Маршруты, коды ответов, валидация параметров, аутентификация, проверка владельца |
| Схемы | `app/schemas` | Контракт запросов и ответов; из них FastAPI строит OpenAPI |
| Сервисы | `app/services` | Бизнес-правила: формулы, пороги, правила A01–A03, снимки целей, покрытие истории. `rules.py` не зависит от БД и тестируется отдельно |
| Репозитории | `app/repositories` | Запросы к БД; фильтр `user_id` стоит в каждом запросе к пользовательским данным |
| Модели | `app/models` | Таблицы SQLAlchemy и ограничения целостности |
| Клиенты | `app/clients` | Доступ к FACEIT; без ключа API - детерминированные демо-данные |
| Ядро | `app/core` | Настройки, безопасность, формат ошибок |

## Путь запроса: постановка цели

```mermaid
sequenceDiagram
    participant C as Клиент
    participant R as goals router
    participant D as deps
    participant S as goals service
    participant M as metrics
    participant DB as PostgreSQL

    C->>R: POST /api/v1/goals (Bearer JWT)
    R->>D: get_current_user
    D->>D: проверка подписи, exp, alg=HS256
    D->>DB: пользователь существует и активен?
    R->>DB: игрок принадлежит пользователю?
    alt чужой или несуществующий игрок
        R-->>C: 404 problem+json
    end
    R->>S: create(metric, map, action)
    S->>DB: есть активная цель?
    alt есть, replace_active=false
        S-->>C: 409 + active_goal_id
    end
    S->>DB: 20 последних матчей в контексте
    S->>M: проверка полноты, расчёт числителя и знаменателя
    alt меньше 20 или нет данных метрики
        S-->>C: 422 insufficient-data
    end
    S->>DB: цель + снимок 20 матчей (одна транзакция)
    R-->>C: 201 Created, Location
```

## Путь пользователя в интерфейсе

```mermaid
sequenceDiagram
    participant U as Игрок
    participant F as Интерфейс (браузер)
    participant A as API
    participant DB as PostgreSQL

    U->>F: ник или ссылка FACEIT
    F->>A: POST /players
    A-->>F: 201 игрок (или 404 / 503 - разные сообщения)
    F->>A: GET /stats, /matches (одни и те же фильтры)
    A->>DB: последние 20 матчей
    A-->>F: значения + числитель, знаменатель, выборка
    U->>F: вкладка «Сводка и рекомендации»
    F->>A: GET /insights
    A-->>F: A01–A03 с основанием и действием
    U->>F: «Сделать целью»
    F->>A: POST /goals (409 → явная замена)
    A->>DB: цель + снимок 20 матчей
    F->>A: GET /goals/{id}/progress
    A-->>F: collecting / ready / incomplete_data / unrecoverable
```

Переход между страницами отменяет незавершённые запросы прошлой страницы (`AbortController`),
поэтому при быстром поиске двух игроков на экране не остаются показатели предыдущего (S01, крит. 6).
Ответ 401 очищает сессию и возвращает на вход с сохранением адреса.

## Решения и их причины

**Игроки принадлежат пользователю.** Таблица `players` содержит `user_id`. Это упрощает
проверку доступа: чужой игрок не находится тем же запросом, что и несуществующий, и API
отвечает одинаковым 404. Дублирование матчей у разных пользователей для учебного объёма некритично.

**Снимки целей хранятся копией.** `goal_snapshot_matches` не ссылается на `matches`.
Обновление или удаление истории не меняет исходную выборку и готовое сравнение (ПР1, раздел 2.2).

**Итог метрики без округления.** В цели хранятся числитель и знаменатель
(`baseline_numerator/denominator`), значение вычисляется при выдаче. Округление влияет
только на отображение.

**Покрытие истории.** FACEIT отдаёт не больше 100 последних матчей. При каждой синхронизации
сервис проверяет, пересекается ли новая порция с сохранённой. Если не пересекается,
`coverage_from` сдвигается и цель, начатая раньше, получает статус `unrecoverable`.
Последние матчи не подставляются вместо пропущенных первых.

**Интерфейс без сборки.** Статические ES-модули раздаются тем же процессом FastAPI. Нет шага
сборки, Node.js нужен только для линтера в CI, а API и интерфейс находятся на одном origin -
не нужны CORS и хранение токена в cookie. DOM строится функцией `h()` только через `textContent`;
ESLint запрещает `innerHTML` и `eval`.

**Отзыв токенов.** JWT остаётся без состояния, но при выходе его `jti` записывается в
`revoked_tokens` до момента `exp`. Проверка - один запрос по первичному ключу; истёкшие записи
удаляются при следующем выходе.

**Демо-данные вместо FACEIT.** Пока ключ FACEIT не получен, `FixtureFaceitClient` выдаёт
вымышленные детерминированные профили. Они нужны для тестов, локальной разработки и защиты.
С ключом в `.env` тот же код работает с настоящим API.

## Изменения относительно ПР1

| ПР1 | Сейчас | Причина |
|---|---|---|
| Без аккаунтов; цель и снимки хранятся в браузере (NFR07) | Регистрация, JWT, цели и снимки в PostgreSQL | Задание ПР2 требует CRUD с аутентификацией. Заодно снято ограничение «только в том же браузере» |
| Одна активная цель на браузер | Одна активная цель на пользователя (частичный уникальный индекс) | Следствие перехода на аккаунты |
| Проверка динамики - R3 | Реализована на сервере: `GET /goals/{id}/progress` | Цели - основная сущность CRUD; правила сохранения выборок нужны уже при создании цели |
| Сравнение 20 / 20, карты и правила A01–A03 - R2 | Реализованы: `/compare`, `/maps`, `/insights` | Нужны для полного пользовательского сценария «обзор → вывод → действие → цель» |
| Веб-интерфейс на телефоне и компьютере (S05) | Адаптивный интерфейс в `frontend/`, проверен e2e-тестами на 360, 768 и 1440 px | Критерий «Интеграция и UI» |
| - | Выход из аккаунта с отзывом токена | Снято ограничение «нет отзыва токена» |
