# Безопасность: меры по OWASP Top 10 (2021)

| Риск OWASP | Мера в проекте | Где в коде | Чем проверено |
|---|---|---|---|
| **A01 Broken Access Control** | Каждый запрос к пользовательским данным фильтруется по `user_id`. Чужой ресурс возвращает 404, как несуществующий (защита от IDOR и перебора id). Цель нельзя создать на чужого игрока | `app/repositories/*.get_owned`, `app/api/deps.py::get_owned_player` | `test_other_users_player_is_invisible`, `test_other_users_goal_is_invisible`, `test_list_only_own_players` |
| **A02 Cryptographic Failures** | Пароли хешируются Argon2id с солью. JWT подписывается секретом из окружения: без секрета длиной от 32 символов приложение не стартует. Секреты не хранятся в репозитории (`.env` в `.gitignore`) | `app/core/security.py`, `app/core/config.py` | `test_password_hash_is_argon2_and_verifies` |
| **A03 Injection** (в т.ч. XSS) | Только ORM-запросы с параметрами, без сборки SQL из строк. Входные данные проверяет Pydantic: ник по белому списку символов, карта по шаблону `^[a-z0-9_]{2,32}$`, ссылка только на `faceit.com`. Интерфейс выводит данные только через `textContent` (функция `h()`), ESLint запрещает `innerHTML`, `insertAdjacentHTML`, `eval`. CSP интерфейса запрещает inline-скрипты и сторонние источники | `app/schemas`, `app/services/players.py::parse_query`, `frontend/js/dom.js`, `eslint.config.js`, `app/main.py::UI_CSP` | `test_bad_filters`, `test_rejects_foreign_links_and_bad_nicknames`, `test_index_is_served_with_strict_csp`, `test_index_has_no_inline_code`, e2e: нарушения CSP приводят к падению теста |
| **A04 Insecure Design** | Одна активная цель обеспечивается уникальным индексом в БД, а не только проверкой в коде (гонка запросов). Снимки целей неизменяемы. Удаление аккаунта каскадно удаляет данные | `app/models/goal.py`, миграция `0001` | `test_only_one_active_goal`, `test_progress_ready_and_frozen` |
| **A05 Security Misconfiguration** | CORS - только перечисленные origin; интерфейс на том же origin, что и API. Заголовки `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`; CSP `default-src 'none'` и `Cache-Control: no-store` для API, отдельная CSP `default-src 'self'; frame-ancestors 'none'` для интерфейса. Swagger отключается через `DOCS_ENABLED=false`. Ошибки 500 без стека. Контейнер работает не от root | `app/main.py`, `app/core/errors.py`, `Dockerfile` | `test_security_headers`, `test_cors_allows_only_configured_origin`, `test_api_keeps_its_own_policy` |
| **A06 Vulnerable Components** | `pip-audit` и `npm audit` в CI проверяют зависимости по базе уязвимостей. Версии ограничены диапазонами в `pyproject.toml`. Интерфейс не использует сторонних библиотек в браузере | `.github/workflows/ci.yml` | Шаги CI «pip-audit», «npm audit» |
| **A07 Identification and Authentication Failures** | Ограничение 5 попыток входа в минуту на IP + email (429, `Retry-After`). Одинаковый ответ и одинаковое время проверки для неизвестного email и неверного пароля. Короткий срок жизни токена (30 мин). Принимается только HS256, `alg=none` и чужие алгоритмы отклоняются; обязательны `exp`, `iat`, `sub`, `jti`. Выход отзывает токен на сервере (`revoked_tokens`). Токен удалённого пользователя не работает. Интерфейс при 401 очищает сессию; адрес возврата после входа - только внутренний (нет открытого редиректа) | `app/api/v1/auth.py`, `app/core/rate_limit.py`, `app/core/security.py`, `app/api/deps.py`, `frontend/js/views/auth.js` | `test_login_rate_limit`, `test_wrong_password_and_unknown_email_look_the_same`, `test_invalid_tokens_are_rejected`, `test_deleted_user_token_stops_working`, `test_logout_revokes_only_current_token`, e2e `test_expired_session_returns_to_login` |
| **A08 Software and Data Integrity Failures** | Сборка и публикация образа идут только из CI после успешных линтеров и тестов. Миграции версионируются в git | `.github/workflows/ci.yml`, `alembic/` | `test_migrations_match_models` |
| **A09 Logging and Monitoring Failures** | Непредвиденные ошибки логируются со стеком на сервере. Пароли и токены в логи и ответы не попадают | `app/core/errors.py` | `test_validation_error_does_not_echo_password` |
| **A10 SSRF** | Запросы уходят только на фиксированный `FACEIT_BASE_URL`. Ник из пользовательского ввода проходит белый список и не может изменить хост | `app/clients/faceit.py`, `parse_query` | `test_rejects_foreign_links_and_bad_nicknames` |

## Ключ FACEIT (NFR04 из ПР1)

Ключ хранится только в переменной окружения `FACEIT_API_KEY` на сервере. Браузер его не получает:
все обращения к FACEIT идут через backend. При сетевой ошибке в текст исключения попадает только
тип ошибки, без заголовков запроса (`test_network_error_does_not_leak_api_key`).

## Хранение токена в браузере

Токен хранится в `sessionStorage`: он живёт до закрытия вкладки и не отправляется автоматически
с запросами, поэтому CSRF к API невозможен. Риск такого хранения - кража токена при XSS. Он
снижен тремя мерами: строгая CSP без inline-скриптов и сторонних источников, вывод данных только
через `textContent` (правило ESLint) и короткий срок жизни токена с возможностью отзыва.

## Известные ограничения

- Счётчик попыток входа хранится в памяти процесса. При нескольких экземплярах сервиса его нужно
  вынести в Redis.
- Refresh-токенов нет: после истечения 30 минут нужно войти заново. Отзыв токена при выходе есть.
- Регистрация с занятым email отвечает 409, поэтому по ней можно узнать, зарегистрирован ли адрес.
  Для учебного проекта это принятый компромисс. Полная защита требует подтверждения email по письму.
