import logging
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1 import router as v1_router
from app.clients.faceit import FaceitClient, HttpFaceitClient
from app.clients.fixtures import FixtureFaceitClient
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.rate_limit import SlidingWindowLimiter

logger = logging.getLogger("app")

DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")
API_PREFIX = "/api/"
# Интерфейс загружает только собственные скрипты и стили, без inline-кода и сторонних CDN
UI_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; "
    "form-action 'self'; frame-ancestors 'none'"
)


def build_faceit_client(settings: Settings) -> FaceitClient:
    if settings.faceit_api_key and settings.faceit_api_key.get_secret_value():
        return HttpFaceitClient(
            settings.faceit_api_key.get_secret_value(),
            settings.faceit_base_url,
            settings.faceit_timeout_seconds,
        )
    logger.warning("FACEIT_API_KEY не задан - используются демонстрационные данные")
    return FixtureFaceitClient()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="FACEIT Progress API",
        version="0.2.0",
        description=(
            "Backend сервиса аналитики игроков FACEIT в CS2 "
            "Аутентификация - JWT Bearer; ошибки - application/problem+json (RFC 9457)"
        ),
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.state.faceit_client = build_faceit_client(settings)
    app.state.login_limiter = SlidingWindowLimiter(
        settings.login_rate_limit, settings.login_rate_window_seconds
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        path = request.url.path
        if path.startswith(API_PREFIX):
            response.headers["Content-Security-Policy"] = "default-src 'none'"
            response.headers["Cache-Control"] = "no-store"
        elif not path.startswith(DOCS_PATHS):
            # Swagger UI грузит скрипты с CDN, поэтому для него CSP не задаётся
            response.headers["Content-Security-Policy"] = UI_CSP
            # Файлы интерфейса кэшируются, но проверяются при каждом открытии
            response.headers["Cache-Control"] = "no-cache"
        return response

    register_error_handlers(app)
    app.include_router(v1_router)
    if settings.ui_enabled and settings.frontend_dir.is_dir():
        # Монтируется последним: маршруты API имеют приоритет
        app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="ui")
    elif settings.ui_enabled:
        logger.warning("Каталог интерфейса %s не найден - UI отключён", settings.frontend_dir)
    return app


app = create_app()
