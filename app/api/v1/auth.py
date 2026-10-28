from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.api.deps import AppSettings, CurrentUser, DbSession, get_login_limiter
from app.core.errors import TooManyRequests
from app.core.rate_limit import SlidingWindowLimiter
from app.core.security import create_access_token
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserOut
from app.schemas.common import problem_responses
from app.services import auth as auth_service

router = APIRouter(tags=["auth"])


@router.post(
    "/auth/register",
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация",
    responses=problem_responses(409, 422),
)
def register(body: RegisterRequest, db: DbSession) -> UserOut:
    user = auth_service.register(db, body.email, body.password)
    return UserOut.model_validate(user)


@router.post(
    "/auth/login",
    summary="Вход: выдаёт JWT access-токен",
    responses=problem_responses(401, 422, 429),
)
def login(
    body: LoginRequest,
    request: Request,
    db: DbSession,
    settings: AppSettings,
    limiter: Annotated[SlidingWindowLimiter, Depends(get_login_limiter)],
) -> TokenResponse:
    client_ip = request.client.host if request.client else "unknown"
    retry_after = limiter.hit(f"{client_ip}:{body.email}")
    if retry_after is not None:
        raise TooManyRequests(
            f"Повторите попытку через {retry_after} с",
            headers={"Retry-After": str(retry_after)},
        )
    user = auth_service.authenticate(db, body.email, body.password)
    token, expires_in = create_access_token(user.id, settings)
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.get("/users/me", summary="Текущий пользователь", responses=problem_responses(401))
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.delete(
    "/users/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить аккаунт со всеми игроками и целями",
    responses=problem_responses(401),
)
def delete_me(user: CurrentUser, db: DbSession) -> Response:
    auth_service.delete_account(db, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
