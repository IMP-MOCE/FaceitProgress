"""Единый формат ошибок API - application/problem+json (RFC 9457)"""

import logging
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.errors")

PROBLEM_JSON = "application/problem+json"


class AppError(Exception):
    """Ожидаемая ошибка предметной области с HTTP-статусом и машинным кодом"""

    status: int = 400
    code: str = "bad-request"
    title: str = "Некорректный запрос"

    def __init__(
        self,
        detail: str | None = None,
        *,
        extra: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail or self.title)
        self.detail = detail or self.title
        self.extra = extra or {}
        self.headers = headers


class Unauthorized(AppError):
    status = 401
    code = "unauthorized"
    title = "Требуется аутентификация"


class InvalidCredentials(AppError):
    status = 401
    code = "invalid-credentials"
    title = "Неверный email или пароль"


class NotFound(AppError):
    status = 404
    code = "not-found"
    title = "Ресурс не найден"


class PlayerNotFoundInSource(AppError):
    status = 404
    code = "faceit-player-not-found"
    title = "Игрок не найден"


class Conflict(AppError):
    status = 409
    code = "conflict"
    title = "Конфликт с текущим состоянием"


class InvalidInput(AppError):
    status = 422
    code = "invalid-input"
    title = "Некорректные данные"


class InsufficientData(AppError):
    status = 422
    code = "insufficient-data"
    title = "Недостаточно данных"


class TooManyRequests(AppError):
    status = 429
    code = "too-many-requests"
    title = "Слишком много попыток"


class SourceUnavailable(AppError):
    status = 503
    code = "source-unavailable"
    title = "Источник данных FACEIT временно недоступен"


def problem(
    status: int,
    code: str,
    title: str,
    detail: str,
    instance: str,
    extra: dict[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"/problems/{code}",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": instance,
    }
    if extra:
        body.update(extra)
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON, headers=headers)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return problem(
            exc.status,
            exc.code,
            exc.title,
            exc.detail,
            request.url.path,
            exc.extra,
            exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Введённые значения не возвращаем: в них может оказаться пароль
        errors = [
            {"loc": list(err["loc"]), "msg": err["msg"], "type": err["type"]}
            for err in exc.errors()
        ]
        return problem(
            422,
            "validation-error",
            "Ошибка валидации",
            "Запрос не прошёл проверку полей",
            request.url.path,
            {"errors": errors},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return problem(
            exc.status_code,
            "http-error",
            str(exc.detail),
            str(exc.detail),
            request.url.path,
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Стек пишем в лог, клиенту - только общий текст без деталей реализации
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return problem(
            500,
            "internal-error",
            "Внутренняя ошибка сервера",
            "Попробуйте повторить запрос позже",
            request.url.path,
        )
