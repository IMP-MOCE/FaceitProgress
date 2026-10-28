import logging
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as v1_router
from app.clients.faceit import FaceitClient, HttpFaceitClient
from app.clients.fixtures import FixtureFaceitClient
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.rate_limit import SlidingWindowLimiter

logger = logging.getLogger("app")

DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


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
        version="0.1.0",
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
        if not request.url.path.startswith(DOCS_PATHS):
            # Swagger UI грузит скрипты с CDN, поэтому строгий CSP - только для API
            response.headers["Content-Security-Policy"] = "default-src 'none'"
            response.headers["Cache-Control"] = "no-store"
        return response

    register_error_handlers(app)
    app.include_router(v1_router)
    return app


app = create_app()
