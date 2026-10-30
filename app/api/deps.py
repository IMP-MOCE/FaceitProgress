from typing import Annotated

from fastapi import Depends, Path, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.clients.faceit import FaceitClient
from app.core.config import Settings, get_settings
from app.core.errors import NotFound, Unauthorized
from app.core.rate_limit import SlidingWindowLimiter
from app.core.security import TokenClaims, decode_token_claims
from app.db.session import get_db
from app.models import Player, User
from app.repositories import players, tokens, users

_bearer = HTTPBearer(auto_error=False, description="JWT из POST /api/v1/auth/login")
_WWW_AUTH = {"WWW-Authenticate": "Bearer"}

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def get_token_claims(
    settings: AppSettings,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> TokenClaims:
    if credentials is None:
        raise Unauthorized(headers=_WWW_AUTH)
    claims = decode_token_claims(credentials.credentials, settings)
    if claims is None:
        raise Unauthorized("Токен недействителен или истёк", headers=_WWW_AUTH)
    return claims


TokenClaimsDep = Annotated[TokenClaims, Depends(get_token_claims)]


def get_current_user(db: DbSession, claims: TokenClaimsDep) -> User:
    # Токен после выхода из аккаунта отклоняется, даже если срок ещё не истёк
    if tokens.is_revoked(db, claims.jti):
        raise Unauthorized("Сессия завершена, войдите снова", headers=_WWW_AUTH)
    user = users.get(db, claims.user_id)
    # Удалённый или заблокированный пользователь не проходит даже с действующим токеном.
    if user is None or not user.is_active:
        raise Unauthorized("Пользователь не найден или заблокирован", headers=_WWW_AUTH)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_owned_player(
    db: DbSession, user: CurrentUser, player_id: Annotated[int, Path(gt=0)]
) -> Player:
    player = players.get_owned(db, user.id, player_id)
    if player is None:
        raise NotFound("Игрок не найден")
    return player


OwnedPlayer = Annotated[Player, Depends(get_owned_player)]


def get_faceit_client(request: Request) -> FaceitClient:
    client: FaceitClient = request.app.state.faceit_client
    return client


Faceit = Annotated[FaceitClient, Depends(get_faceit_client)]


def get_login_limiter(request: Request) -> SlidingWindowLimiter:
    limiter: SlidingWindowLimiter = request.app.state.login_limiter
    return limiter
